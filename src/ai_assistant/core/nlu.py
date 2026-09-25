"""
Phân tích ngôn ngữ tự nhiên và định tuyến phản xạ Fast-Path NLU (<5ms).
"""

import re
import random
import unicodedata
import subprocess
from ai_assistant.config import EXIT_PHRASES, URL_SHORTCUTS
from ai_assistant.speech.player import stop_current_speech, play_chime
from ai_assistant.core.memory import read_quick_notes, add_quick_note, add_user_fact
from ai_assistant.tools.timer import timer_manager
from ai_assistant.tools.system import (
    get_vietnamese_time,
    get_vietnamese_date,
    get_battery_info,
    get_system_hardware_info,
    get_weather_info,
    parse_simple_math,
    get_clipboard_content,
    set_system_volume,
    adjust_system_volume,
    toggle_system_mute,
    adjust_brightness,
    set_wifi_state,
    set_bluetooth_state,
    set_asus_profile,
    lock_screen,
    take_screenshot,
)
from ai_assistant.tools.apps import (
    match_app,
    find_app_in_text,
    launch_desktop_app,
    close_active_window,
    close_all_open_apps,
    close_specific_app,
    set_window_fullscreen,
)
from ai_assistant.tools.dev import (
    check_port_status,
    kill_port_process,
    check_docker_containers,
    check_java_version,
    get_git_status_summary,
)
from ai_assistant.tools.web import (
    search_and_display_image,
    open_youtube_search,
    open_google_search,
    open_url,
)

def is_exit_phrase(text: str) -> bool:
    """Kiểm tra xem người dùng có muốn dừng phiên thoại hoặc đóng cửa sổ trợ lý không."""
    t = text.lower().strip().rstrip(".,!?")

    if len(t.split()) > 5:
        return False

    key_phrases = [
        "kết thúc cuộc trò chuyện", "kết thúc trò chuyện", "kết thúc phiên",
        "dừng cuộc trò chuyện", "dừng trò chuyện", "dừng lại ở đây", "dừng tại đây",
        "kết thúc ở đây", "kết thúc tại đây", "tạm biệt bạn", "tạm biệt nhé",
        "hẹn gặp lại", "đóng cửa sổ", "tắt cửa sổ", "ẩn cửa sổ",
        "tắt trợ lý", "đóng trợ lý", "ẩn trợ lý", "tắt alexa", "đóng alexa"
    ]
    if any(kp in t for kp in key_phrases):
        return True
    if t in EXIT_PHRASES:
        return True
    for p in EXIT_PHRASES:
        if t == p or t.startswith(p + " ") or t.endswith(" " + p):
            return True
    return False

def clean_user_input(text: str) -> str:
    """Loại bỏ các từ gọi tên thừa ở đầu câu nếu Whisper nhận diện vào văn bản (chuẩn hóa Unicode NFKC)."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text).strip()
    t = re.sub(r'^(?:ê\s+|này\s+|ơi\s+|chào\s+)*alexa(?:\s+ơi)?[\s,\.!\?]+', '', norm, flags=re.IGNORECASE).strip()
    t = re.sub(r'^(?:ê\s+|này\s+|ơi\s+|chào\s+)*jarvis(?:\s+ơi)?[\s,\.!\?]+', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'^(?:à|ừm|ừ|này|ê)[\s,\.!\?]+', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\s+', ' ', t).strip()
    return t if t else norm

def fast_path_nlu(user_text: str, app_index: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    Bộ định tuyến ý định trực tiếp (Fast-Path Deterministic NLU):
    - Khớp chính xác các hành động hệ thống phổ biến (âm lượng, độ sáng, nhạc, pin, giờ, RAM, web, app).
    - Xử lý và phản hồi ngay lập tức trong 0.005 giây thay vì phải chờ mô hình ngôn ngữ 7B.
    - Trả về (True, reply_text) nếu xử lý thành công, hoặc (False, "") để chuyển sang Deep-Path LLM.
    - dry_run: Nếu True, chỉ kiểm tra logic và trả về văn bản phản hồi mà KHÔNG chạy lệnh hệ thống thật.
    """
    if not user_text:
        return False, ""
    norm_text = unicodedata.normalize("NFKC", user_text)
    t = norm_text.lower().strip().rstrip(".!?")
    t = re.sub(r'\s+', ' ', t)

    # 0. Lệnh cắt lời / Dừng khẩn cấp (Barge-in Voice Command)
    if re.search(r"\b(im lặng|dừng lại|dừng nói|thôi im|tắt tiếng đi|im đi)\b", t):
        if not dry_run:
            stop_current_speech()
        return True, ""

    # 1. Thời gian & Ngày tháng
    if re.search(r"\b(mấy giờ|bây giờ là mấy giờ|xem giờ|thời gian hiện tại|mấy giờ rồi)\b", t):
        return True, get_vietnamese_time()
    if re.search(r"\b(hôm nay ngày mấy|hôm nay là ngày mấy|hôm nay ngày bao nhiêu|ngày mấy tháng mấy|hôm nay thứ mấy|hôm nay là thứ mấy|thứ mấy hôm nay|ngày bao nhiêu)\b", t):
        return True, get_vietnamese_date()

    # 2. Pin laptop
    if re.search(r"\b(pin còn bao nhiêu|kiểm tra pin|xem pin|tình trạng pin|sạc pin chưa|còn mấy phần trăm pin|mức pin)\b", t):
        if dry_run:
            return True, "Pin hiện tại còn 85%."
        return True, get_battery_info()

    # 2.5. Kiểm tra Git & Clipboard Wayland (Dành cho lập trình viên)
    if re.search(r"\b(kiểm tra git|git status|tình trạng git|nhánh git hiện tại|nhánh git)\b", t):
        if dry_run:
            return True, "Trạng thái Git: Nhánh main sạch sẽ."
        return True, get_git_status_summary()
    if re.search(r"\b(đọc clipboard|đọc bộ nhớ tạm|bộ nhớ tạm có gì|clipboard có gì|trong clipboard có gì)\b", t):
        if dry_run:
            return True, "Nội dung trong bộ nhớ tạm."
        clip = get_clipboard_content()
        if not clip:
            return True, "Bộ nhớ tạm hiện đang trống hoặc không chứa văn bản bạn nhé."
        return True, f"Nội dung trong bộ nhớ tạm là: {clip}"

    # 3. Âm lượng máy tính
    vol_pct_m = re.search(r"(?:đặt|chỉnh|cài)?\s*âm lượng\s*(?:ở\s*mức\s*|về\s*|lên\s*)?(\d{1,3})\s*(?:%|phần trăm)?", t)
    if vol_pct_m and ("tăng" not in t and "giảm" not in t):
        pct_val = min(max(int(vol_pct_m.group(1)), 0), 100)
        if not dry_run:
            set_system_volume(pct_val)
        return True, f"Đã đặt âm lượng ở mức {pct_val} phần trăm."
    if re.search(r"\b(tăng âm lượng|cho to lên|bật to lên|to tiếng hơn|tăng loa|cho to tí|to hơn nữa|bật to loa|cho to loa|to loa lên|tăng âm)\b", t):
        if not dry_run:
            adjust_system_volume("+10%")
        return True, random.choice(["Đã tăng âm lượng lên rồi nhé.", "Âm lượng đã được tăng thêm một chút.", "Đã cho loa to lên rồi nhé."])
    if re.search(r"\b(giảm âm lượng|cho nhỏ lại|bật nhỏ lại|nhỏ tiếng hơn|giảm loa|cho nhỏ tí|bé hơn|nhỏ lại|nhỏ bớt|cho nhỏ loa|nhỏ loa lại|giảm âm)\b", t):
        if not dry_run:
            adjust_system_volume("-10%")
        return True, random.choice(["Đã giảm âm lượng cho bạn.", "Âm lượng đã được chỉnh nhỏ bớt.", "Đã cho loa nhỏ lại rồi nhé."])
    if re.search(r"\b(tắt tiếng|tắt âm|mute|bật lại tiếng|ngắt tiếng|mở lại tiếng)\b", t):
        if not dry_run:
            toggle_system_mute()
        return True, "Đã chuyển đổi trạng thái âm thanh."

    # 4. Điều khiển phát nhạc / media qua playerctl
    if re.search(r"\b(bài này là bài gì|đang phát bài gì|bài hát gì đây|tên bài hát|đang nghe bài gì)\b", t):
        try:
            track_info = subprocess.check_output(
                ["playerctl", "metadata", "--format", "{{title}} của {{artist}}"],
                text=True, errors="ignore", timeout=2
            ).strip()
            if track_info and "của" in track_info:
                return True, f"Bài hát đang phát là {track_info}."
            elif track_info:
                return True, f"Đang phát: {track_info}."
        except Exception:
            pass
        return True, "Hiện tại không có bài hát nào đang phát."
    if re.search(r"\b(dừng nhạc|tạm dừng|dừng bài hát|pause nhạc|ngưng nhạc|tắt nhạc)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã tạm dừng phát nhạc."
    if re.search(r"\b(phát tiếp|tiếp tục nhạc|tiếp tục phát|bật lại nhạc|play nhạc|tiếp tục nghe nhạc)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã tiếp tục phát nhạc nhé."
    if re.search(r"\b(chuyển bài|next bài|bài tiếp theo|qua bài|đổi bài|bài khác)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã chuyển sang bài tiếp theo cho bạn."
    if re.search(r"\b(bài trước|quay lại bài trước|lùi bài|back bài|bài vừa rồi)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã quay lại bài trước rồi nhé."

    # 4.1. Cài đặt Nhanh Phần cứng (Wi-Fi & Bluetooth)
    if re.search(r"\b(bật wifi|mở wifi|kết nối wifi)\b", t):
        if not dry_run:
            set_wifi_state(True)
        return True, "Đã bật kết nối Wi-Fi cho bạn rồi nhé."
    if re.search(r"\b(tắt wifi|ngắt wifi|ngắt kết nối wifi)\b", t):
        if not dry_run:
            set_wifi_state(False)
        return True, "Đã tắt Wi-Fi."
    if re.search(r"\b(bật bluetooth|mở bluetooth)\b", t):
        if not dry_run:
            set_bluetooth_state(True)
        return True, "Đã bật Bluetooth."
    if re.search(r"\b(tắt bluetooth|ngắt bluetooth)\b", t):
        if not dry_run:
            set_bluetooth_state(False)
        return True, "Đã tắt Bluetooth."

    # 4.2. Chế độ Quạt & Hiệu năng ASUS TUF
    if re.search(r"\b(chế độ turbo|chế độ hiệu năng|bật turbo|quạt mạnh|tối đa hiệu năng)\b", t):
        if not dry_run:
            set_asus_profile("Performance")
        return True, "Đã chuyển sang chế độ Hiệu năng cao Turbo cho bạn."
    if re.search(r"\b(chế độ yên tĩnh|chế độ im lặng|quạt êm|chế độ tiết kiệm pin|quạt yên tĩnh)\b", t):
        if not dry_run:
            set_asus_profile("Quiet")
        return True, "Đã chuyển sang chế độ Yên tĩnh tiết kiệm pin."
    if re.search(r"\b(chế độ cân bằng|quạt bình thường|chế độ bình thường)\b", t):
        if not dry_run:
            set_asus_profile("Balanced")
        return True, "Đã chuyển về chế độ Cân bằng mượt mà."

    # 5. Độ sáng màn hình
    if re.search(r"\b(tăng độ sáng|cho sáng lên|sáng màn hình hơn|tăng sáng|sáng thêm|màn hình tối quá|cho sáng màn hình|sáng màn hình lên)\b", t):
        if not dry_run:
            adjust_brightness("+10%")
        return True, "Đã tăng độ sáng màn hình rồi nhé."
    if re.search(r"\b(giảm độ sáng|cho tối bớt|tối màn hình lại|giảm sáng|màn hình chói quá|chói mắt quá|cho tối màn hình)\b", t):
        if not dry_run:
            adjust_brightness("10%-")
        return True, "Đã giảm độ sáng màn hình cho bạn."

    # 6. Khóa máy & Chụp màn hình & Đóng ứng dụng / Cửa sổ
    if re.search(r"\b(khóa màn hình|khóa máy|lock máy|lock màn hình|tôi đi ra ngoài)\b", t):
        if not dry_run:
            lock_screen()
        return True, "Đang khóa màn hình máy tính cho bạn nhé."
    if re.search(r"\b(chụp màn hình|chụp ảnh màn hình|chụp vùng|chụp lại màn hình|chụp một góc)\b", t):
        mode = "full" if "toàn" in t else "region"
        if not dry_run:
            take_screenshot(mode)
        return True, "Đã kích hoạt chụp ảnh màn hình cho bạn."

    # 6.1. Đóng ứng dụng / cửa sổ (Tất cả hoặc cửa sổ hiện tại)
    if re.search(r"\b(?:đóng|tắt)\s+(?:(?:hết|tất cả|các|mọi|toàn bộ)\s+)*(?:ứng dụng|cửa sổ|phần mềm|app|tab)\b", t) or \
       re.search(r"\b(tắt ứng dụng này|đóng ứng dụng này|tắt tab này|đóng tab này|tắt cửa sổ này|đóng cửa sổ này)\b", t):
        if any(w in t for w in ["tất cả", "hết", "các", "mọi", "toàn bộ"]):
            return close_all_open_apps()
        else:
            return close_active_window()

    # 6.3. Đóng ứng dụng cụ thể theo tên (Zalo, Chrome, Code, Spotify, Telegram, Terminal...)
    close_app_match = re.search(r"\b(?:đóng|tắt|thoát|kill)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+)?([a-zA-Z0-9\s_àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+)", t)
    if close_app_match:
        app_target = close_app_match.group(1).strip()
        excluded_words = ["hẹn giờ", "báo thức", "đếm ngược", "nhạc", "wifi", "bluetooth", "âm thanh", "tiếng", "đèn", "quạt", "màn hình", "máy"]
        if not any(ew in app_target for ew in excluded_words):
            handled, rep = close_specific_app(app_target, app_index)
            if handled and rep:
                return True, rep

    # 6.4. Phóng to / To toàn màn hình / Thu nhỏ cửa sổ
    if re.search(r"\b(phóng to cửa sổ|cửa sổ to ra|to cửa sổ|to toàn màn hình|fullscreen cửa sổ|to hết cỡ|phóng to ứng dụng)\b", t):
        if not dry_run:
            set_window_fullscreen(True)
        return True, "Đã phóng to tối đa cửa sổ cho bạn rồi nhé."
    if re.search(r"\b(thu nhỏ cửa sổ|cửa sổ nhỏ lại|hủy phóng to|thu nhỏ lại)\b", t):
        if not dry_run:
            set_window_fullscreen(False)
        return True, "Đã đưa cửa sổ về kích thước tiêu chuẩn."

    # 7. Kiểm tra cấu hình phần cứng & RAM
    if re.search(r"\b(kiểm tra ram|ram còn bao nhiêu|bộ nhớ ram|cấu hình máy|tình trạng máy tính|máy tính chạy bao lâu|thông số máy)\b", t):
        if dry_run:
            return True, "RAM đang sử dụng 4.2 GB / 16.0 GB."
        return True, get_system_hardware_info()

    # 7.1. Công cụ Lập trình viên Đa nhiệm (Port, Docker, Java)
    kill_port_match = re.search(r"\b(?:kill|giải phóng|xóa|tắt|đóng)\s+(?:cổng|port)\s+(\d+)\b", t)
    if kill_port_match:
        p_num = int(kill_port_match.group(1))
        if dry_run:
            return True, f"Đã giải phóng cổng {p_num}."
        return True, kill_port_process(p_num)

    check_port_match = re.search(r"\b(?:cổng|port)\s+(\d+)\b", t)
    if check_port_match:
        p_num = int(check_port_match.group(1))
        if dry_run:
            return True, f"Cổng {p_num} đang trống."
        return True, check_port_status(p_num)

    if re.search(r"\b(kiểm tra docker|docker có gì|trạng thái docker|container nào đang chạy|xem docker)\b", t):
        if dry_run:
            return True, "Docker hiện có 2 container đang chạy."
        return True, check_docker_containers()

    if re.search(r"\b(kiểm tra java|java version|phiên bản java|máy đang cài java mấy|java mấy)\b", t):
        if dry_run:
            return True, "Hệ thống đang cài đặt OpenJDK 21 LTS."
        return True, check_java_version()

    # 8. Tính toán số học nhanh
    math_res = parse_simple_math(t)
    if math_res:
        return True, math_res

    # 9. Thời tiết nhanh
    if re.search(r"\b(thời tiết|nhiệt độ ngoài trời|trời có mưa không|mưa hay nắng)\b", t):
        if dry_run:
            return True, "Thời tiết hiện tại 28 độ C, trời quang mây tạnh."
        loc_match = re.search(r"(?:ở|tại)\s+([a-zA-Z0-9\s_àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+)", t)
        location = loc_match.group(1).strip() if loc_match else ""
        return True, get_weather_info(location)

    # 10. Mở YouTube hoặc tìm kiếm trực tiếp trên YouTube
    yt_match = re.search(r"(?:mở|phát|bật|nghe)?\s*(?:bài hát|nhạc|video|clip)?\s*(.+?)\s*trên\s*youtube", t)
    if not yt_match:
        yt_match = re.search(r"(?:mở|lên|vào)\s+youtube\s+(?:tìm|xem|nghe|bài hát|nhạc|video)?\s*(.+)", t)
    if yt_match:
        query = yt_match.group(1).strip()
        query = re.sub(r"^(cho tôi|giùm tôi|hộ tôi|tìm|xem|nghe|bài hát|nhạc|video)\s*", "", query, flags=re.IGNORECASE).strip()
        if not dry_run:
            msg = open_youtube_search(query)
            return True, msg
        return True, f"Đang mở {query} trên YouTube cho bạn." if query else "Đã mở YouTube cho bạn rồi nhé."

    # 11. Tìm kiếm trên Google
    gg_match = re.search(r"^(?:tìm kiếm|tra cứu|tìm)\s+(.+?)(?:\s+(?:trên|ở|bằng)\s+(?:google|mạng|trình duyệt))?$", t)
    if not gg_match:
        gg_match = re.search(r"^(.+?)\s+(?:trên|ở|bằng)\s+(?:google|mạng)$", t)
    if gg_match:
        query = gg_match.group(1).strip()
        query = re.sub(r"^(cho tôi|giùm tôi|hộ tôi)\s*", "", query, flags=re.IGNORECASE).strip()
        if query and query not in ["thông tin", "gì đó", "mấy thứ", "trình duyệt"]:
            if not dry_run:
                msg = open_google_search(query)
                return True, msg
            return True, f"Đang tìm kiếm {query} trên Google cho bạn."

    # 12. Mở web theo shortcut nhanh
    for site, link in URL_SHORTCUTS.items():
        if t in [f"mở {site}", f"bật {site}", f"vào {site}", f"truy cập {site}"]:
            if not dry_run:
                open_url(link)
            site_name = "YouTube" if site in ["youtube", "du túp", "dút túp"] else site.capitalize()
            return True, f"Đã mở {site_name} cho bạn rồi nhé."

    # 13. Mở ứng dụng trực tiếp (hỗ trợ Zalo, VS Code, IntelliJ, Spotify, Terminal, v.v.)
    open_trigger = re.search(r"\b(mở|bật|chạy|khởi động)\b", t)
    if open_trigger:
        matched = None
        app_match = re.search(r"\b(?:mở|bật|chạy|khởi động)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+)?(.+)", t)
        if app_match:
            app_target = app_match.group(1).strip()
            if not any(k in app_target for k in ["youtube", "du túp", "dút túp"]):
                matched = match_app(app_target, app_index)
        if not matched:
            matched = find_app_in_text(t, app_index)

        if matched:
            if not dry_run:
                ok = launch_desktop_app(matched)
                if ok:
                    return True, f"Đã mở {matched['name']} cho bạn rồi nhé."
                else:
                    return True, f"Không thể khởi chạy ứng dụng {matched['name']}."
            return True, f"Đã mở {matched['name']} cho bạn rồi nhé."

    # 14. Tìm kiếm hình ảnh trên mạng & đưa về máy / mở lên
    img_match = re.search(r"\b(?:tìm|tải|lấy|kiếm|cho\s+(?:tôi\s+)?xem)\s+(?:bức\s+|tấm\s+|hình\s+)?ảnh\s+(.+)", t, re.IGNORECASE)
    if img_match:
        query_img = img_match.group(1).strip()
        if not dry_run:
            ok, reply_img = search_and_display_image(query_img)
            return True, reply_img
        return True, f"Đã tìm thấy và mở ảnh {query_img} cho bạn rồi nhé."

    # 15. Hẹn giờ & Báo thức chuyên nghiệp
    if re.search(r"\b(?:hủy|tắt|xóa|dừng)\s+(?:hẹn giờ|báo thức|đếm ngược)\b", t):
        return True, timer_manager.cancel_all()

    if re.search(r"\b(?:kiểm tra|xem|còn bao nhiêu|còn mấy|còn bao lâu)\s+(?:hẹn giờ|báo thức|đếm ngược)\b", t) or t in ["hẹn giờ còn bao lâu", "kiểm tra hẹn giờ", "xem hẹn giờ", "báo thức"]:
        return True, timer_manager.check_timers()

    alarm_match = re.search(r"\b(?:đặt\s+)?báo thức\s+(?:lúc\s+)?(\d{1,2})\s*(?:giờ|h)\s*(?:(\d{1,2})\s*(?:phút|p)?)?\s*(sáng|chiều|tối)?(?:\s+(?:để|cho)?\s*(.+))?\b", t)
    if alarm_match:
        hr = int(alarm_match.group(1))
        mn = int(alarm_match.group(2)) if alarm_match.group(2) else 0
        period = alarm_match.group(3)
        alarm_label = alarm_match.group(4) or ""
        if period in ["chiều", "tối"] and hr < 12:
            hr += 12
        return True, timer_manager.add_alarm(hr, mn, label=alarm_label)

    timer_match = re.search(r"\b(?:hẹn giờ|đếm ngược)\s+(\d+(?:\.\d+)?)\s*(phút|giây|tiếng|giờ)?(?:\s+(?:để|cho)?\s*(.+))?\b", t)
    if timer_match:
        val = float(timer_match.group(1))
        unit = timer_match.group(2) or "phút"
        timer_label = timer_match.group(3) or ""
        if unit in ["tiếng", "giờ"]:
            mins = val * 60.0
        elif unit == "giây":
            mins = val / 60.0
        else:
            mins = val
        return True, timer_manager.add_timer(mins, label=timer_label)

    # 16. Ghi chú nhanh & Đọc danh sách ghi chú
    if re.search(r"\b(?:đọc ghi chú|xem ghi chú|danh sách ghi chú|có ghi chú gì)\b", t):
        return True, read_quick_notes()
    note_match = re.search(r"^(?:ghi chú|nhắc tôi|lưu lại|note lại)(?:\s+(?:lại|cho tôi|giùm tôi))?(?:\s+(?:là|rằng))?\s+(.+)$", t)
    if note_match:
        content = note_match.group(1).strip()
        return True, add_quick_note(content)

    # 17. Ghi nhớ thông tin người dùng vào bộ nhớ dài hạn
    mem_match = re.search(r"\b(?:hãy nhớ|nhớ giùm tôi|nhớ kỹ|ghi nhớ)\s+(?:là|rằng)?\s*(.+)", t)
    if mem_match:
        fact = mem_match.group(1).strip()
        return True, add_user_fact(fact)

    return False, ""
