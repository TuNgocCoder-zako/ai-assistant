"""
Phân tích ngôn ngữ tự nhiên và định tuyến phản xạ Fast-Path NLU (<5ms).
"""

import re
import random
import unicodedata
import subprocess
import difflib
from ai_assistant.config import EXIT_PHRASES, URL_SHORTCUTS, URL_DISPLAY_NAMES
from ai_assistant.speech.player import stop_current_speech
from ai_assistant.core.memory import read_quick_notes, add_quick_note, add_user_fact
from ai_assistant.tools.timer import timer_manager
from ai_assistant.tools.system import (
    get_vietnamese_time,
    get_vietnamese_date,
    get_battery_info,
    get_cpu_info,
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
    get_network_speed_info,
    get_current_media_track,
    media_pause,
    media_play,
    media_next,
    media_previous,
    is_media_playing,
)
from ai_assistant.tools.apps import (
    match_app,
    find_app_in_text,
    launch_desktop_app,
    launch_multiple_targets,
    close_active_window,
    close_active_tab,
    close_all_open_apps,
    close_specific_app,
    set_window_fullscreen,
    switch_hyprland_workspace,
    move_active_window_to_workspace,
    toggle_window_floating,
    toggle_window_pin,
    toggle_hyprland_split,
    set_hyprland_split_ratio,
    apply_workspace_preset,
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
        "hẹn gặp lại", "tắt trợ lý", "đóng trợ lý", "ẩn trợ lý", "tắt alexa", "đóng alexa"
    ]
    if any(kp in t for kp in key_phrases):
        return True
    if t in EXIT_PHRASES:
        return True
    for p in EXIT_PHRASES:
        if t == p or t.startswith(p + " ") or t.endswith(" " + p):
            return True
    return False

def strip_vietnamese_accents(text: str) -> str:
    """Loại bỏ toàn bộ dấu tiếng Việt (chuẩn hóa ký tự cơ bản, đ/Đ -> d/D)."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", text)
    res = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", res).strip()

# Bảng quy đổi tự động từ/cụm từ không dấu sang có dấu chuẩn cho các ý định điều khiển (Unaccented Intent Map)
UNACCENTED_INTENT_MAP = [
    # Cụm từ điều khiển Hyprland & màn hình
    (r"\bchia\s+doi\s+man\s+hinh\b", "chia đôi màn hình"),
    (r"\bchia\s+doi\b", "chia đôi"),
    (r"\bchia\s+ngang\b", "chia ngang"),
    (r"\bchia\s+doc\b", "chia dọc"),
    (r"\bphong\s+to\s+len\b", "phóng to lên"),
    (r"\bphong\s+to\s+cua\s+so\b", "phóng to cửa sổ"),
    (r"\bphong\s+to\s+ung\s+dung\b", "phóng to ứng dụng"),
    (r"\bphong\s+to\b", "phóng to"),
    (r"\bthu\s+nho\s+cua\s+so\b", "thu nhỏ cửa sổ"),
    (r"\bthu\s+nho\s+ung\s+dung\b", "thu nhỏ ứng dụng"),
    (r"\bthu\s+nho\b", "thu nhỏ"),
    (r"\bchuyen\s+workspace\b", "chuyển workspace"),
    (r"\bchuyen\s+khong\s+gian\s+lam\s+viec\b", "chuyển không gian làm việc"),
    (r"\bkhong\s+gian\s+lam\s+viec\b", "không gian làm việc"),
    (r"\bchup\s+man\s+hinh\b", "chụp màn hình"),
    (r"\btoan\s+man\s+hinh\b", "toàn màn hình"),
    # Cửa sổ & ứng dụng
    (r"\bdong\s+cua\s+so\b", "đóng cửa sổ"),
    (r"\btat\s+cua\s+so\b", "tắt cửa sổ"),
    (r"\btat\s+ung\s+dung\b", "tắt ứng dụng"),
    (r"\bdong\s+ung\s+dung\b", "đóng ứng dụng"),
    (r"\bthoat\s+ung\s+dung\b", "thoát ứng dụng"),
    (r"\btat\s+spotify\b", "tắt spotify"),
    (r"\bdong\s+spotify\b", "đóng spotify"),
    (r"\btat\s+spotfy\b", "tắt spotify"),
    (r"\bdong\s+spotfy\b", "đóng spotify"),
    (r"\bthoat\s+spotfy\b", "thoát spotify"),
    (r"\btat\s+no(?:\s+di)?\b", "tắt nó"),
    (r"\bdong\s+no(?:\s+lai)?\b", "đóng nó"),
    (r"\btat\s+cai\s+nay\b", "tắt cái này"),
    (r"\bdong\s+cai\s+nay\b", "đóng cái này"),
    (r"\bphong\s+to\s+no(?:\s+len)?\b", "phóng to nó lên"),
    (r"\bcho\s+no\s+to\s+len\b", "cho nó to lên"),
    (r"\bthu\s+nho\s+no(?:\s+lai)?\b", "thu nhỏ nó lại"),
    (r"\bchuyen\s+no\s+sang\b", "chuyển nó sang"),
    (r"\bthoat\b", "thoát"),
    (r"\btrinh\s+duyet\b", "trình duyệt"),
    # Thời gian & Ngày tháng & Thời tiết
    (r"\bmay\s+gio\s+roi\b", "mấy giờ rồi"),
    (r"\bmay\s+gio\b", "mấy giờ"),
    (r"\bbay\s+gio\s+la\s+may\s+gio\b", "bây giờ là mấy giờ"),
    (r"\bngay\s+may\b", "ngày mấy"),
    (r"\bhom\s+nay\b", "hôm nay"),
    (r"\bthoi\s+tiet\b", "thời tiết"),
    # Pin & Hệ thống & Mạng
    (r"\bkiem\s+tra\s+pin\b", "kiểm tra pin"),
    (r"\bpin\s+con\s+bao\s+nhieu\b", "pin còn bao nhiêu"),
    (r"\bkiem\s+tra\s+mang\b", "kiểm tra mạng"),
    (r"\btoc\s+do\s+mang\b", "tốc độ mạng"),
    (r"\bkiem\s+tra\s+toc\s+do\s+mang\b", "kiểm tra tốc độ mạng"),
    (r"\bdoc\s+clipboard\b", "đọc clipboard"),
    (r"\bbo\s+nho\s+tam\b", "bộ nhớ tạm"),
    (r"\bkiem\s+tra\s+git\b", "kiểm tra git"),
    # Âm lượng & Độ sáng
    (r"\btang\s+am\s+luong\b", "tăng âm lượng"),
    (r"\bgiam\s+am\s+luong\b", "giảm âm lượng"),
    (r"\bam\s+luong\b", "âm lượng"),
    (r"\btat\s+tieng\b", "tắt tiếng"),
    (r"\bbat\s+lai\s+tieng\b", "bật lại tiếng"),
    (r"\btang\s+do\s+sang\b", "tăng độ sáng"),
    (r"\bgiam\s+do\s+sang\b", "giảm độ sáng"),
    (r"\bdo\s+sang\b", "độ sáng"),
    # Điều khiển nhạc & Media
    (r"\bbat\s+nhac\b", "bật nhạc"),
    (r"\bphat\s+nhac\b", "phát nhạc"),
    (r"\btat\s+nhac\b", "tắt nhạc"),
    (r"\bdung\s+nhac\b", "dừng nhạc"),
    (r"\btam\s+dung\s+nhac\b", "tạm dừng nhạc"),
    (r"\btam\s+dung\b", "tạm dừng"),
    (r"\btiep\s+tuc\s+phat\s+nhac\b", "tiếp tục phát nhạc"),
    (r"\btiep\s+tuc\b", "tiếp tục"),
    (r"\bchuyen\s+bai\s+hat\b", "chuyển bài hát"),
    (r"\bchuyen\s+bai\b", "chuyển bài"),
    (r"\bdoi\s+bai\b", "đổi bài"),
    (r"\bbai\s+truoc\b", "bài trước"),
    (r"\bbai\s+tiep\s+theo\b", "bài tiếp theo"),
    # Hẹn giờ & Báo thức
    (r"\bhen\s+gio\b", "hẹn giờ"),
    (r"\bhuy\s+hen\s+gio\b", "hủy hẹn giờ"),
    (r"\bdat\s+bao\s+thuc\b", "đặt báo thức"),
    (r"\bbao\s+thuc\b", "báo thức"),
    # Tìm kiếm & tiện ích
    (r"\btim\s+kiem\b", "tìm kiếm"),
    # Từ đơn hành động cốt lõi
    (r"\bmo\b", "mở"),
    (r"\bbat\b", "bật"),
    (r"\btat\b", "tắt"),
    (r"\bdong\b", "đóng"),
    (r"\bchay\b", "chạy"),
    (r"\bchuyen\b", "chuyển"),
    (r"\bdoi\b", "đổi"),
    (r"\bchup\b", "chụp"),
    (r"\btang\b", "tăng"),
    (r"\bgiam\b", "giảm"),
    (r"\bnhac\b", "nhạc"),
    (r"\bcua\s+so\b", "cửa sổ"),
    (r"\bman\s+hinh\b", "màn hình"),
    (r"\bung\s+dung\b", "ứng dụng"),
    (r"\bphut\b", "phút"),
    (r"\bgiay\b", "giây"),
    (r"\bgio\b", "giờ"),
]

# Bảng mẫu hành động hệ thống chuẩn dùng cho so khớp mờ dị âm / đồng âm (Fuzzy Homophone Actions)
CANONICAL_ACTIONS = {
    "bat nhac": "bật nhạc",
    "phat nhac": "phát nhạc",
    "tat nhac": "tắt nhạc",
    "dung nhac": "dừng nhạc",
    "tam dung nhac": "tạm dừng nhạc",
    "tam dung": "tạm dừng",
    "tiep tuc": "tiếp tục",
    "tiep tuc phat nhac": "tiếp tục phát nhạc",
    "bai tiep theo": "bài tiếp theo",
    "chuyen bai": "chuyển bài",
    "chuyen bai hat": "chuyển bài hát",
    "doi bai": "đổi bài",
    "bai truoc": "bài trước",
    "tang am luong": "tăng âm lượng",
    "giam am luong": "giảm âm lượng",
    "tat am thanh": "tắt tiếng",
    "tat tieng": "tắt tiếng",
    "bat lai tieng": "bật lại tiếng",
    "bat lai am thanh": "bật lại tiếng",
    "tang do sang": "tăng độ sáng",
    "giam do sang": "giảm độ sáng",
    "may gio roi": "mấy giờ rồi",
    "hom nay ngay may": "hôm nay ngày mấy",
    "kiem tra pin": "kiểm tra pin",
    "pin con bao nhieu": "pin còn bao nhiêu",
    "kiem tra mang": "kiểm tra mạng",
    "toc do mang": "tốc độ mạng",
    "chup man hinh": "chụp màn hình",
    "dong cua so": "đóng cửa sổ",
    "tat ung dung": "tắt ứng dụng",
    "phong to": "phóng to",
    "thu nho": "thu nhỏ",
    "chia doi man hinh": "chia đôi màn hình",
    "chia doc": "chia dọc",
    "chia ngang": "chia ngang",
    "huy hen gio": "hủy hẹn giờ",
    "kiem tra hen gio": "kiểm tra hẹn giờ",
    "doc clipboard": "đọc clipboard",
}

def fuzzy_match_canonical_action(text: str, threshold: float = 0.82) -> tuple[str, float] | None:
    """
    So khớp mờ (Fuzzy matching Levenshtein/difflib) đối chiếu câu nói người dùng
    với danh sách các hành động hệ thống chuẩn dựa trên chuỗi không dấu.
    Cứu các câu lệnh bị Whisper nghe nhầm dấu thanh, phụ âm đầu hoặc âm cuối (bật nhạt -> bật nhạc, tăng âm nượng -> tăng âm lượng).
    """
    unacc = strip_vietnamese_accents(text).lower().strip()
    if not unacc or len(unacc) < 4:
        return None
    best_match = None
    best_ratio = 0.0
    for canon_unacc, canon_acc in CANONICAL_ACTIONS.items():
        ratio = difflib.SequenceMatcher(None, unacc, canon_unacc).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = canon_acc
    if best_ratio >= threshold:
        return best_match, best_ratio
    return None

def clean_user_input(text: str) -> str:
    """Loại bỏ các từ gọi tên thừa ở đầu câu nếu Whisper nhận diện vào văn bản (chuẩn hóa Unicode NFKC) và tự động khôi phục câu lệnh không dấu."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text).strip()
    t = re.sub(r'^(?:ê\s+|này\s+|ơi\s+|chào\s+)*alexa(?:\s+ơi)?[\s,\.!\?]+', '', norm, flags=re.IGNORECASE).strip()
    t = re.sub(r'^(?:ê\s+|này\s+|ơi\s+|chào\s+)*jarvis(?:\s+ơi)?[\s,\.!\?]+', '', t, flags=re.IGNORECASE).strip()

    # Tự động khôi phục dấu tiếng Việt cho các ý định điều khiển (Unaccented Intent Restoration)
    for pat, repl in UNACCENTED_INTENT_MAP:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)

    # Chuẩn hóa dị âm cửa sổ (của sổ -> cửa sổ)
    t = re.sub(r"\bc[ủũụùú]a\s+s[ổỗộồốo]\b", "cửa sổ", t, flags=re.IGNORECASE)

    # Tự động gộp "m ở", "em ở", "ê ở" và các biến thể bị Whisper tách rời từ:
    t = re.sub(r'\b(?:m\s+[ởờỡớơ]|em\s+[ởờỡớơ]|ê\s+[ởờỡớơ])\b', 'mở', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:à|ừm|ừ|này|ê)[\s,\.!\?]+', '', t, flags=re.IGNORECASE).strip()
    # Loại bỏ các ký tự CJK (chữ Hán/Nhật) do Whisper ảo giác sinh ra từ tiếng ồn nền (vd: 'Mở個 miêu')
    t = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff]', '', t)
    # Tự động chuẩn hóa động từ mở bị Whisper nghe nhầm dấu thanh hoặc âm đuôi (mỡ/mớ/mờ/mợ/mơ/mỗi/mởn/mỡn/mớn/mờn/mợn/mởng/mẫn/mởm -> mở)
    t = re.sub(r'\b(?:mỡ|mớ|mờ|mợ|mơ|mỗi|mởn|mỡn|mớn|mờn|mợn|mởng|mẫn|mởm)\b', 'mở', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(mở|bật|chạy)\s+(?:dùng|zùng)\b', r'\1 ứng dụng', t, flags=re.IGNORECASE)
    # Tự động khắc phục các lỗi nhận diện âm đồng / từ lóng công nghệ của Whisper
    t = re.sub(r'\b(?:mọi\s+người\s+(?:ở|mở))\s+mail\b', 'mở gmail', t, flags=re.IGNORECASE)
    t = re.sub(r'\bthông sót\b', 'thông số', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:kiêm|kim|kem)\s+tự\s+(?:thép|tháp|thắp|thác)\b', 'kim tự tháp', t, flags=re.IGNORECASE)
    t = re.sub(r'\bxây\s+(?:dòng|zòng|ròng|dồn|dần)\b', 'xây dựng', t, flags=re.IGNORECASE)
    t = re.sub(r'\bkhá\s+niệm\b', 'khái niệm', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:kiểm\s+tinh|kiểm\s+bin)\b', 'kiểm tra pin', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:báo|bán)\s+là\s+ai\b', 'bạn là ai', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:báo|bán)\s+tên\s+gì\b', 'bạn tên gì', t, flags=re.IGNORECASE)
    t = re.sub(r'\bcbo\b', 'cpu', t, flags=re.IGNORECASE)
    t = re.sub(r'\bgbo\b', 'gpu', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tạch|tắc|tắp)\s+(?:tân\s+duyệt|trân\s+duyệt|tân\s+diệt|trình\s+duyệt|duyệt|diệt)\b', 'tắt trình duyệt', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tạch|tắc|tắp)\b', 'tắt', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:trình\s+(?:diệt|zuyệt|ruyệt)|chình\s+(?:duyệt|diệt)|diệt\s+web)\b', 'trình duyệt', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:gour\s*miel|gourmiel|gour\s*meo|gour\s*mail)\b', 'gmail', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:cơm|com|con)[-\s]*(?:meo|mêu|miêu|mail|yêu)\b', 'gmail', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:g(?:ờ|ở|ơ|ừ|ừa|ửa|e|ê|ồm|ôm)?[-\s]*(?:meo|mêu|miêu|mail|nhau|yêu|neo|leo|meow)|g\s*mail+l*|di\s*(?:meo|mêu|mail)|zi\s*(?:meo|mêu|mail)|hòm\s+thư|hộp\s+thư|thư\s+điện\s+tử|ca\s*mèo|ca\s*meo|gần\s*miêu)\b', 'gmail', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:mở|vào|đọc|xem|check|kiểm\s+tra)\s+(?:gmail|mail|email|e-mail|miêu|meo|thư|hòm\s+thư|hộp\s+thư)\b', 'mở gmail', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:g[ií]t\s*(?:h[uú]p|h[aá]p|hub|hup|hap|h[uú]c|h[oó]p|h[oớ]p|h[aặ]p)|gít\s*húp|gh)\b', 'github', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:ph[âe]y\s*(?:b[uú][ckpt]|book|booc|bô|bô\s*k)?|phe\s*b[uú][ckpt]|fb|phai\s*bước)\b', 'facebook', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:du\s*túp|dút\s*túp|diu\s*túp|diu\s*tup|du\s*tup|dút\s*tup|iu\s*túp|iu\s*tup|du\s*tốc|dưu\s*tốc|diu\s*tốc|vô\s*tấp|vô\s*túp|dô\s*túp|dô\s*tấp|zu\s*túp)\b', 'youtube', t, flags=re.IGNORECASE)
    # Chuẩn hóa liên từ vào/về/với bị Whisper nghe nhầm từ và khi đứng giữa 2 ứng dụng / website
    known_targets = r"(?:youtube|facebook|gmail|github|zalo|vs\s*code|vscode|spotify|firefox|chrome|kitty|terminal|trình\s*duyệt)"
    t = re.sub(rf"(\b{known_targets}\b)\s+(?:vào|về|với|cùng)\s+(\b{known_targets}\b)", r"\1 và \2", t, flags=re.IGNORECASE)
    t = re.sub(rf"(\b{known_targets}\b)\s+(\b{known_targets}\b)", r"\1 và \2", t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:da\s*lô|za\s*lô|dép\s*lào)\b', 'zalo', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:spotfy|spoty|spotifi|supportify|xì\s*po\s*ti\s*phai|sì\s*po\s*ti\s*phai|xì\s*po\s*ti\s*phi|sì\s*po\s*ti\s*phi|bót\s*ti\s*phai|bóp\s*ti\s*phai|bốt\s*ti\s*phai|sờ\s*po\s*ti\s*phai|xờ\s*po\s*ti\s*phai|xì\s*po\s*ti|sì\s*po\s*ti|xì\s*pô\s*ti|sì\s*pô\s*ti|sờ\s*po\s*ti)\b', 'spotify', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:téc\s*mi\s*nan|tẹc\s*mi\s*nan|tẹt\s*mi\s*nan|téc\s*min\s*nồ)\b', 'terminal', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:gu\s*gồ|gúc\s*gồ|gô\s*gồ)\b', 'google', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:vai\s*phai|quai\s*phai|quy\s*phuy)\b', 'wifi', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:lu\s*tút|bu\s*tút|bờ\s*lu\s*tút)\b', 'bluetooth', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:đốc\s*cơ|đốc\s*kơ)\b', 'docker', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:vi\s*ét\s*cốt|vi\s*ét\s*code|vê\s*ét\s*cốt|vé\s*code|vét\s*cốt|phi\s*ét\s*cốt)\b', 'vs code', t, flags=re.IGNORECASE)
    # Chuẩn hóa dị âm tiếng Việt & từ mượn cho Firefox
    t = re.sub(r'\b(?:phai|fai|phay|fay|phi|pha|fire|file)[-\s]*(?:fox|fóc|phóc|phốc|phót|phó|phọt|phốt|phot|phoc|phóp|pho)\b', 'firefox', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:cáo\s*lửa|cáo\s*đỏ|hỏa\s*hồ)\b', 'firefox', t, flags=re.IGNORECASE)
    # Khắc phục triệt để lỗi Whisper nhận diện 'Mở phai phốc' / 'Mở Firefox' [faɪər fɒks] thành 'Mở 5 phút' / 'Mở 5p' / 'Mở năm phút'
    t = re.sub(r'\b(?:mở|bật|chạy|vào|khởi động)\s+(?:5\s*phút|năm\s*phút|một\s*5\s*phút|1\s*5\s*phút|5p|năm\s*p|5\s*phúc|năm\s*phúc)\b', 'mở firefox', t, flags=re.IGNORECASE)
    # Chuẩn hóa dị âm hẹn giờ / báo thức
    t = re.sub(r'\b(?:để|đặt|bật)\s+(?:có|báo)\s*thức\b', 'đặt báo thức', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:nằm|lằm|lăm)\s+(?:phúc|phút|p)\b', '5 phút', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:thời\s*tiếc)\b', 'thời tiết', t, flags=re.IGNORECASE)
    # Chuẩn hóa dị âm các câu lệnh âm lượng
    t = re.sub(r'\b(?:tính|tinh|thanh|tênh|tánh|thính|tăn|tắng|tằng|tây|tay)\s*(?:,\s*)?(?:âm|ấm|ngâm|ôm)\s*(?:nượng|nương|lương|lường|lưỡng|lượng|lửa|lồ|lộ|lỗ)\b', 'tăng âm lượng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tính|tinh|thanh|tênh|tánh|thính|tăn|tắng|tằng)\s*(?:,\s*)?(?:âm\s*nượng|âm\s*nương|âm\s*lương|âm\s*lường|âm\s*lưỡng|âm\s*lượng)\b', 'tăng âm lượng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:giảm|dảm|dàm)\s*(?:âm\s*nượng|âm\s*nương|âm\s*lương|âm\s*lường|âm\s*lưỡng)\b', 'giảm âm lượng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:âm\s*nượng|âm\s*nương)\b', 'âm lượng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:độ\s*xáng)\b', 'độ sáng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tắt\s+táp|đóng\s+táp|mở\s+táp)\b', lambda m: m.group(0).replace('táp', 'tab'), t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tua\s*bô|tua\s*bo)\b', 'turbo', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bát\s*tơ\s*ri|bét\s*tờ\s*ri)\b', 'pin', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tạm\s*dân\s*nhét)\b', 'tạm dừng nhé', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tám\s*rung\s*nhập|tạm\s*dân|tạm\s*dâng|tạm\s*dung|tạm\s*zừng|tạm\s*zung|tạm\s*dừn|tám\s*dừng)\b', 'tạm dừng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:dương\s*nhiệt|dừng\s*nhiệt|dừng\s*nhạt|dừng\s*nhẹt)\b', 'dừng nhạc', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chiếm\s*bay\s*hát|chiếm\s*bài\s*hát|chuyển\s*bay\s*hát|chuyển\s*bài\s*hắc|chiếm\s*bài)\b', 'chuyển bài hát', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bye|bai|bay)\s*,?\s*tiếp\s*theo\b', 'bài tiếp theo', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bài\s*tiếp\s*thep)\b', 'bài tiếp theo', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:nhạc\s*tên\s*dì|nhạc\s*tên\s*zì|bài\s*tên\s*dì|tên\s*bài\s*hát\s*là\s*dì|bài\s*này\s*là\s*bài\s*dì|đang\s*phát\s*bài\s*dì)\b', lambda m: m.group(0).replace('dì', 'gì').replace('zì', 'gì'), t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bài\s*nhẹt|bài\s*nhạt|bài\s*nhac)\b', 'bài nhạc', t, flags=re.IGNORECASE)
    # Multi-Pronunciation: Chuẩn hóa dị âm 3 miền & từ mượn công nghệ
    t = re.sub(r'\b(?:phát|các|thác)\s+(?:nghiệm|nhiệm|nghiệc|nghiệp|nhạc|nhạt|nhác|nhẹt)\b', 'phát nhạc', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bạch\s*nhạc|bịch\s*nhạc|bình\s*nhạc|bọc\s*nhạc|ngọt\s*nhạc|ngon\s*nhạc|bấm\s*nhạc|bằng\s*nhân)\b', 'bật nhạc', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:mở|bật)\s+nha$', 'bật nhạc', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tất\s*nhiệt|tắt\s*nhiệt|tắt\s*nhạt)\b', 'tắt nhạc', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tạm\s*dường|tạm\s*giường)\b', 'tạm dừng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:mẹ\s*tịt|nghe\s*tịt)\b', 'nghe tiếp', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chuyện\s*bay|chuyện\s*bài|chuyện\s*nhạc|chuyễn\s*nhạc)\b', 'chuyển bài', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:mùa|mua|mò)\s+(?=spotify|firefox|chrome|zalo|terminal|vs\s*code|youtube|nhạc|trình\s*duyệt|sở\s*bớt)', 'mở ', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:sở\s*bớt\s*đi\s*phai|xa\s*bờ\s*tùy\s*phai|bớt\s*đi\s*phai)\b', 'spotify', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bơi\s*bài|bơi\s*nhạc)\b', 'đổi bài', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bài\s*chức|bài\s*trức)\b', 'bài trước', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:lời\s*bay|lùi\s*bay)\b', 'lùi bài', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tạm\s*ôn\s*ngựa|giảm\s*bao\s*ngựa|giảm\s*ống\s*lượng|tạm\s*âm\s*lượng)\b', 'giảm âm lượng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tăng\s*ấm\s*được|tăng\s*ấm\s*lượt)\b', 'tăng âm lượng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:ngồi\s*lại)\b', 'nhỏ lại', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bằng\s*lạc\s*tính|bật\s*lạc\s*tiếng)\b', 'bật lại tiếng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tam\s*bộ\s*sáng|tam\s*độ\s*sáng|tăng\s*độ\s*xáng)\b', 'tăng độ sáng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:thảm\s*luyện)\b', 'sáng lên', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bởi\s*thấm\s*nát|bởi\s*thấm\s*lạc|mở\s*thấm\s*lăng)\b', 'mở terminal', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:mời\s*mất\s*nhu|mời\s*vô\s*viêu|bởi\s*vui\s*chúc)\b', 'mở youtube', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:một\s*dao|bộ\s*giáo)\b', 'mở zalo', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bởi\s*din\s*a)\b', 'mở gmail', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:một\s*phép)\b', 'mở facebook', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tất\s*tướng\s*sổ)\b', 'tắt ứng dụng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:kiểm\s*chạy\s*tìm|kiểm\s*tra\s*tinh|kiểm\s*tra\s*tiên)\b', 'kiểm tra pin', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tin\s*còn\s*bao\s*nhiêu)\b', 'pin còn bao nhiêu', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bây\s*giờ\s*rồi)\b', 'mấy giờ rồi', t, flags=re.IGNORECASE)
    t = re.sub(r'\bhôm\s+nay,?\s+ngày\s+mỹ\b', 'hôm nay ngày mấy', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bất\s*phá\s*y)\b', 'bật wifi', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bật\s*mơ\s*tô|bật\s*mở\s*tô)\b', 'bật bluetooth', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bắt\s*mô\s*bộ)\b', 'tắt bluetooth', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chúc\s*màn\s*hình)\b', 'chụp màn hình', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:phải\s*giờ)\s+(\d+)\s*(?:phút|p)\b', r'hẹn giờ \1 phút', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:quý\s*vị\s*hẹn\s*giờ)\b', 'hủy hẹn giờ', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:báo\s*thức\s+bài\s+giờ)\b', 'báo thức 7 giờ', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chuyển|đổi|mở|bật|tắt|dừng|tạm\s*dừng|phát|nghe)\s+(?:nhạt|nhác|nhẹt)\b', lambda m: re.sub(r'nh[ạáẹ][tc]', 'nhạc', m.group(0), flags=re.IGNORECASE), t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chuyến\s*đi|chuyến\s*nhạc|chuyến\s*bài|chiếm\s*nhạc|chiếm\s*bài|chuyển\s*nhạt|chuyển\s*nhác|đổi\s*nhạt|đổi\s*nhác)\b', 'chuyển bài hát', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:đóng|tắt|mở|chuyển)\s+(?:tháp|táp)\b', lambda m: re.sub(r'(?:tháp|táp)', 'tab', m.group(0), flags=re.IGNORECASE), t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bật|mở|tắt|tăng|giảm)\s+(?:noa|noan)\b', lambda m: re.sub(r'noan?', 'loa', m.group(0), flags=re.IGNORECASE), t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:uốc\s*(?:xây|bay|sờ\s*bây)|quốc\s*(?:xây|bay|sờ\s*bây))\b', 'workspace', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:híp\s*(?:len|lần|lan|lơn)|hai\s*pơ\s*(?:len|lan))\b', 'hyprland', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chia|chi)\s+(?:rọc|giọc)\b', 'chia dọc', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:lập\s*chình)\b', 'lập trình', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tốc\s*gồ\s*s[ií]t|tốc\s*gồ\s*s[iì]\s*pờ\s*l[ií]t)\b', 'toggle split', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chào\s*ta\s*lên)\b', 'cho to lên', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tập\s*tuyến)\b', 'tắt tiếng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bọc\s*lại\s*tiếng)\b', 'bật lại tiếng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tính\s*bởi\s*sáng|tân\s*bởi\s*sáng)\b', 'tăng độ sáng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bởi\s*viết\s*cấp|bỏ\s*vsc)\b', 'mở vs code', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bởi\s*terminal)\b', 'mở terminal', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bấm\s*youtube)\b', 'mở youtube', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bởi\s*giờ\s*luôn|mở\s*gia\s*lồ)\b', 'mở zalo', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:báo\s*bao\s*nhiêu|bởi\s*vua\s*nêu)\b', 'mở gmail', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bởi\s*kích\s*húp|mở\s*kit\s*hút)\b', 'mở github', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bởi\s*facebook)\b', 'mở facebook', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bấm\s*cửa\s*sổ)\b', 'đóng cửa sổ', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:tiếp\s*ứng\s*dụt|tắt\s*ứng\s*dụ)\b', 'tắt ứng dụng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bên\s*còn\s*bao\s*nhiêu)\b', 'pin còn bao nhiêu', t, flags=re.IGNORECASE)
    t = re.sub(r'\bhôm\s+nay\s+ngày\s+mai\b', 'hôm nay ngày mấy', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:bằng\s*wifi|bác\s*wi-fi)\b', 'bật wifi', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:phát\s*bài\s*bluetooth|bật\s*bật\s*lưu\s*túc)\b', 'bật bluetooth', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chế\s*độ\s*yên\s*tỉnh)\b', 'chế độ yên tĩnh', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:chế\s*độ\s*cộng\s*bằng|chế\s*độ\s*công\s*bàn)\b', 'chế độ cân bằng', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:khởi\s*nghiệm\s*rồi|hởi\s*nghiệm\s*rồi)\b', 'hủy hẹn giờ', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:một\s+5|1\s+5)\s+phút\b', '15 phút', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+', ' ', t).strip()
    return t if t else norm

def fast_path_nlu(user_text: str, app_index: dict, dry_run: bool = False, is_retry: bool = False) -> tuple[bool, str]:
    """
    Bộ định tuyến ý định trực tiếp (Fast-Path Deterministic NLU):
    - Khớp chính xác các hành động hệ thống phổ biến (âm lượng, độ sáng, nhạc, pin, giờ, RAM, web, app).
    - Xử lý và phản hồi ngay lập tức trong 0.005 giây thay vì phải chờ mô hình ngôn ngữ 7B.
    - Trả về (True, reply_text) nếu xử lý thành công, hoặc (False, "") để chuyển sang Deep-Path LLM.
    - dry_run: Nếu True, chỉ kiểm tra logic và trả về văn bản phản hồi mà KHÔNG chạy lệnh hệ thống thật.
    - is_retry: Cờ chống đệ quy lặp vô hạn khi thử lại bằng so khớp mờ (Fuzzy matching).
    """
    if not user_text:
        return False, ""
    cleaned = clean_user_input(user_text)
    norm_text = unicodedata.normalize("NFKC", cleaned)
    t = norm_text.lower().strip().rstrip(".!?")
    t = re.sub(r'\s+', ' ', t)

    # 0. Lệnh cắt lời / Dừng khẩn cấp (Barge-in Voice Command)
    if re.search(r"\b(im lặng|dừng lại|dừng nói|thôi im|tắt tiếng đi|im đi)\b", t):
        if not dry_run:
            stop_current_speech()
            media_pause()
        return True, ""

    # 0.5. Danh tính trợ lý & Chào hỏi cơ bản (<5ms Fast-Path NLU)
    if re.search(r"\b(?:bạn\s+là\s+ai|bạn\s+tên\s+(?:là\s+)?gì|mày\s+là\s+ai|ai\s+đấy|ai\s+đó|giới\s+thiệu\s+bản\s+thân|bạn\s+là\s+trợ\s+lý\s+gì|bạn\s+làm\s+được\s+gì|bạn\s+có\s+thể\s+làm\s+gì)\b", t):
        return True, "Tôi là Alexa, trợ lý ảo giọng nói tiếng Việt trên hệ điều hành Arch Linux. Tôi có thể giúp bạn mở ứng dụng, nghe nhạc, điều khiển máy tính, lập trình và giải đáp mọi thắc mắc."

    if re.search(r"^(?:chào\s+bạn|xin\s+chào|chào\s+alexa|hello|hi|hế\s+lô)(?:\s+(?:bạn|nhé|nha|ạ))?$", t):
        return True, "Chào bạn! Tôi có thể giúp gì cho bạn hôm nay?"

    if re.search(r"^(?:bạn\s+khỏe\s+không|dạo\s+này\s+thế\s+nào)(?:\s+(?:alexa|ạ|nhỉ|hả))?$", t):
        return True, "Tôi luôn khỏe và sẵn sàng hỗ trợ bạn bất cứ lúc nào!"

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

    # 2.6. Đo tốc độ mạng Internet (Ping & Download Mbps)
    if re.search(r"\b(kiểm tra tốc độ mạng|đo tốc độ mạng|tốc độ mạng|tốc độ internet|kiểm tra mạng|đo mạng|đo băng thông|ping mạng)\b", t):
        if dry_run:
            return True, "Tốc độ mạng hiện tại: Độ trễ ping 35 ms, tốc độ tải xuống khoảng 120 Mbps."
        return True, get_network_speed_info()

    # 3. Âm lượng máy tính
    vol_pct_m = re.search(r"(?:đặt|chỉnh|cài)?\s*âm lượng\s*(?:ở\s*mức\s*|về\s*|lên\s*)?(\d{1,3})\s*(?:%|phần trăm)?", t)
    if vol_pct_m and ("tăng" not in t and "giảm" not in t):
        pct_val = min(max(int(vol_pct_m.group(1)), 0), 100)
        if not dry_run:
            set_system_volume(pct_val)
        return True, f"Đã đặt âm lượng ở mức {pct_val} phần trăm."
    if ("cửa sổ" not in t and "màn hình" not in t) and re.search(r"\b(tăng âm lượng|cho to lên|bật to lên|to tiếng hơn|tăng loa|cho to tí|to hơn nữa|bật to loa|cho to loa|to loa lên|tăng âm)\b", t):
        if not dry_run:
            adjust_system_volume("+10%")
        return True, random.choice(["Đã tăng âm lượng lên rồi nhé.", "Âm lượng đã được tăng thêm một chút.", "Đã cho loa to lên rồi nhé."])
    if ("cửa sổ" not in t and "màn hình" not in t) and re.search(r"\b(giảm âm lượng|cho nhỏ lại|bật nhỏ lại|nhỏ tiếng hơn|giảm loa|cho nhỏ tí|bé hơn|nhỏ lại|nhỏ bớt|cho nhỏ loa|nhỏ loa lại|giảm âm)\b", t):
        if not dry_run:
            adjust_system_volume("-10%")
        return True, random.choice(["Đã giảm âm lượng cho bạn.", "Âm lượng đã được chỉnh nhỏ bớt.", "Đã cho loa nhỏ lại rồi nhé."])
    if re.search(r"\b(tắt tiếng|tắt âm|mute|bật lại tiếng|ngắt tiếng|mở lại tiếng)\b", t):
        if not dry_run:
            toggle_system_mute()
        return True, "Đã chuyển đổi trạng thái âm thanh."

    # 4. Điều khiển phát nhạc / media qua playerctl (Spotify, trình duyệt, MPRIS)
    if re.search(r"\b(bài\s*(?:hát|này)?\s*(?:tên\s*là\s*gì|tên\s*gì|là\s*bài\s*gì)|đang\s*(?:phát|nghe|bật|chạy)\s*(?:bài|nhạc|bài\s*hát|bài\s*nhạc)?(?:\s*gì)?|tên\s*(?:của\s*)?bài\s*hát|bài\s*hát\s*gì\s*(?:đây|đấy|thế)|bài\s*gì\s*(?:đang\s*phát|thế|đây)|ai\s*đang\s*hát|ca\s*sĩ\s*nào\s*hát|thông\s*tin\s*bài\s*hát|nhạc\s*tên\s*gì|bài\s*tên\s*gì)\b", t) or \
       (("bài hát" in t or "bài này" in t or "bài nhạc" in t or "nhạc" in t) and ("tên gì" in t or "tên là gì" in t or "bài gì" in t or "ai hát" in t or "ca sĩ nào" in t)):
        if dry_run:
            return True, "Bài hát đang phát là Shape of You của Ed Sheeran."
        return True, get_current_media_track()

    # State-Aware Dialogue: Kiểm tra trạng thái máy đang phát nhạc
    is_playing = False if dry_run else is_media_playing()

    # Tạm dừng / Dừng nhạc
    if ((re.search(r"\b(tạm\s*dừng(?:\s*(?:nhạc|bài\s*hát|phát|nha|nhé|lại|cho\s*tôi|hộ))?|dừng\s*(?:nhạc|bài\s*hát|phát|bài|lại|nghe\s*nhạc)?|ngừng\s*(?:nhạc|phát|bài\s*hát)?|tắt\s*(?:nhạc|bài\s*hát)|pause(?:\s*nhạc)?|nghỉ\s*nghe\s*nhạc)\b", t) or \
         t in ["dừng lại", "tạm dừng", "dừng phát", "tắt nhạc", "ngừng phát", "tạm dừng nha", "tạm dừng nhé", "dừng bài", "tắt bài", "dừng nhạc", "tạm dừng nhạc", "nghỉ tí", "nghỉ nghe"]) or \
        (is_playing and t in ["dừng", "dừng đi", "thôi", "pause", "nghỉ"])) and \
       not any(k in t for k in ["báo thức", "hẹn giờ", "cuộc trò chuyện", "trò chuyện"]):
        if not dry_run:
            media_pause()
        return True, "Đã tạm dừng phát nhạc."

    # Tiếp tục phát nhạc
    if re.search(r"\b(phát\s*tiếp(?:\s*(?:nhạc|bài\s*hát))?|tiếp\s*tục\s*(?:nhạc|phát|nghe\s*nhạc|bài\s*hát)|phát\s*(?:bài\s*)?nhạc\s*tiếp|phát\s*bài\s*tiếp|bật\s*(?:lại\s*)?nhạc(?:\s*tiếp)?|mở\s*(?:lại\s*)?nhạc(?:\s*tiếp)?|play\s*nhạc|phát\s*nhạc|bật\s*nhạc(?:\s*lên)?|nghe\s*tiếp|nghe\s*nhạc\s*tiếp|tiếp\s*tục\s*nghe)\b", t):
        if not dry_run:
            media_play()
        return True, "Đã tiếp tục phát nhạc nhé."

    # Chuyển bài / Next track (hỗ trợ cả lệnh cụt lủn khi đang nghe nhạc)
    if re.search(r"\b(chuyển\s*(?:bài(?:\s*hát)?|nhạc)|đổi\s*(?:bài(?:\s*hát)?|nhạc)|bài\s*tiếp\s*(?:theo|kế)?|qua\s*bài|next\s*bài|bài\s*khác|bỏ\s*qua\s*bài|chuyển\s*sang\s*bài\s*tiếp)\b", t) or \
       (is_playing and (re.search(r"\b(?:tiếp\s*đi|tiếp\s*nào|tiếp\s*nhé|chuyển\s*đi|đổi\s*đi|qua\s*đi|next|bài\s*khác\s*đi)\b", t) or t in ["tiếp", "next", "chuyển", "đổi", "bài khác", "qua"])):
        if not dry_run:
            media_next()
        return True, "Đã chuyển sang bài tiếp theo cho bạn."

    if re.search(r"\b(bài\s*trước|quay\s*lại\s*bài\s*trước|lùi\s*bài|back\s*bài|bài\s*vừa\s*rồi|nghe\s*lại\s*bài\s*trước|phát\s*lại\s*bài\s*trước|bài\s*lúc\s*nãy|bài\s*vừa\s*phát)\b", t):
        if not dry_run:
            media_previous()
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
    if re.search(r"\b(tăng độ sáng|cho sáng lên|sáng màn hình hơn|tăng sáng|sáng thêm|sáng lên|màn hình tối quá|cho sáng màn hình|sáng màn hình lên)\b", t):
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
        # Nếu có từ khóa phân tích, đọc chữ hoặc suy luận -> Chuyển giao cho Agent Core (Vision)
        if any(w in t for w in ["và", "xem", "đọc", "phân tích", "báo", "có gì", "lỗi", "giúp", "nhìn", "hiện"]):
            return False, ""
        mode = "full" if "toàn" in t else "region"
        if not dry_run:
            take_screenshot(mode)
        return True, "Đã kích hoạt chụp ảnh màn hình cho bạn."

    # 6.1. Đóng toàn bộ ứng dụng / cửa sổ
    if re.search(r"\b(?:đóng|tắt)\s+(?:hết|tất cả|các|mọi|toàn bộ)\s+(?:ứng dụng|cửa sổ|phần mềm|app|tab)\b", t):
        return close_all_open_apps(dry_run=dry_run)

    # 6.2. Đóng tab hiện tại (dùng Ctrl+W cho trình duyệt / editor)
    if re.search(r"\b(tắt tab này|đóng tab này|đóng tab hiện tại|tắt tab hiện tại|đóng tab|tắt tab)\b", t):
        return close_active_tab(dry_run=dry_run)

    # 6.2.1. Đóng cửa sổ / ứng dụng hiện tại (hỗ trợ đại từ thay thế "nó", "cái này")
    if re.search(r"^(?:đóng|tắt)\s+(?:cửa sổ|ứng dụng|phần mềm|app)(?:\s+(?:này|hiện tại))?$", t) or \
       re.search(r"\b(tắt ứng dụng này|đóng ứng dụng này|tắt cửa sổ này|đóng cửa sổ này|tắt nó đi|đóng nó lại|tắt nó|đóng nó|tắt cái này|đóng cái này)\b", t):
        return close_active_window(dry_run=dry_run)

    # 6.3. Điều khiển không gian làm việc (Workspace) trên Hyprland
    ws_switch_match = re.search(r"\b(?:chuyển|sang|vào|qua|tới)\s+(?:không gian làm việc|bàn làm việc|workspace|màn hình)\s+(?:số\s+)?(\d{1,2})\b", t)
    if ws_switch_match:
        ws_num = int(ws_switch_match.group(1))
        if dry_run:
            return True, f"Đã chuyển sang không gian làm việc số {ws_num} cho bạn."
        ok, msg = switch_hyprland_workspace(ws_num)
        return True, msg

    ws_move_match = re.search(r"\b(?:đưa|chuyển|ném|mang)\s+(?:cửa sổ này|cửa sổ hiện tại|cửa sổ|ứng dụng này|nó|cái này)\s+(?:sang|vào|qua|tới)\s+(?:không gian làm việc|bàn làm việc|workspace|màn hình)\s+(?:số\s+)?(\d{1,2})\b", t)
    if ws_move_match:
        ws_num = int(ws_move_match.group(1))
        if dry_run:
            return True, f"Đã chuyển cửa sổ hiện tại sang không gian làm việc số {ws_num}."
        ok, msg = move_active_window_to_workspace(ws_num)
        return True, msg

    # 6.4. Chuyển đổi cửa sổ nổi (Float) & Ghim cửa sổ (Pin)
    if re.search(r"\b(cửa sổ nổi|chuyển thành cửa sổ nổi|bật cửa sổ nổi|tắt cửa sổ nổi|cửa sổ trôi nổi|toggle float)\b", t):
        if dry_run:
            return True, "Đã chuyển đổi trạng thái cửa sổ nổi cho bạn."
        ok, msg = toggle_window_floating()
        return True, msg

    if re.search(r"\b(ghim cửa sổ này|ghim cửa sổ|bỏ ghim cửa sổ|ghim lên trên cùng|pin cửa sổ)\b", t):
        if dry_run:
            return True, "Đã ghim cửa sổ này hiển thị trên mọi không gian làm việc."
        ok, msg = toggle_window_pin()
        return True, msg

    # 6.5. Đóng ứng dụng cụ thể theo tên (Zalo, Chrome, Facebook, VS Code, Spotify, Telegram, Terminal...)
    close_app_match = re.search(r"\b(?:đóng|tắt|thoát|kill)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+|trang web\s+|trang\s+|web\s+)?([a-zA-Z0-9\s_àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+)", t)
    if close_app_match:
        app_target = close_app_match.group(1).strip()
        excluded_words = ["hẹn giờ", "báo thức", "đếm ngược", "nhạc", "wifi", "bluetooth", "âm thanh", "tiếng", "đèn", "quạt", "màn hình", "máy", "cửa sổ nổi", "bàn làm việc", "workspace", "lại", "đi", "này", "nào", "hộ", "giúp", "giùm", "nhé", "nha", "nó", "cái này"]
        if not any(ew in app_target for ew in excluded_words):
            handled, rep = close_specific_app(app_target, app_index, dry_run=dry_run)
            if handled and rep:
                return True, rep

    # 6.6. Phóng to / To toàn màn hình / Hủy toàn màn hình cửa sổ trong workspace
    if re.search(r"\b(phóng to cửa sổ|cửa sổ to ra|to cửa sổ|to toàn màn hình|fullscreen cửa sổ|to hết cỡ|phóng to ứng dụng|phóng to lên|cho ứng dụng to lên|cho nó to lên|phóng to nó lên|phóng to nó|phóng to trong workspace|phóng to trong khu làm việc|maximize cửa sổ|maximize ứng dụng)\b", t):
        if not dry_run:
            set_window_fullscreen(True)
        return True, "Đã phóng to tối đa cửa sổ cho bạn rồi nhé."
    if re.search(r"\b(thoát toàn màn hình|hủy toàn màn hình|hủy phóng to|bỏ phóng to|thu nhỏ toàn màn hình|thu nhỏ phóng to|hủy maximize|thu nhỏ nó|thu nhỏ nó lại)\b", t):
        if not dry_run:
            set_window_fullscreen(False)
        return True, "Đã đưa cửa sổ về kích thước tiêu chuẩn."

    # 6.7. Tinh chỉnh Layout màn hình Hyprland (Gói 1)
    # 6.7.1. Đổi hướng chia màn hình (ngang / dọc)
    if re.search(r"\b(đổi hướng chia màn hình|đổi hướng chia|chia ngang|chia dọc|đổi chiều chia|xoay hướng chia|toggle split)\b", t):
        if dry_run:
            return True, "Đã đổi hướng chia màn hình cho bạn rồi nhé."
        ok, msg = toggle_hyprland_split()
        return True, msg

    # 6.7.2. Tỷ lệ chia màn hình (50/50, 70/30, tăng/giảm kích thước)
    if re.search(r"\b(chia\s*(?:lại\s*)?(?:(?:cho\s*)?đều\s*(?:màn\s*hình|cửa\s*sổ)|màn\s*hình\s*(?:cho\s*)?đều|đôi(?:\s*50\s*50)?|50\s*50|đều)|cân\s*bằng\s*màn\s*hình)\b", t):
        if dry_run:
            return True, "Đã chia đều màn hình tỷ lệ 50 50 cho bạn rồi nhé."
        ok, msg = set_hyprland_split_ratio("1.0")
        return True, msg

    if re.search(r"\b(chia màn hình 70 30|chia 70 30|tỷ lệ 70 30|tỉ lệ 70 30|cửa sổ 70|70 phần trăm)\b", t):
        if dry_run:
            return True, "Đã điều chỉnh cửa sổ chiếm 70% màn hình cho bạn rồi nhé."
        ok, msg = set_hyprland_split_ratio("1.4")
        return True, msg

    if re.search(r"\b(chia màn hình 30 70|chia 30 70|tỷ lệ 30 70|tỉ lệ 30 70)\b", t):
        if dry_run:
            return True, "Đã điều chỉnh cửa sổ chiếm 30% màn hình cho bạn rồi nhé."
        ok, msg = set_hyprland_split_ratio("0.7")
        return True, msg

    if re.search(r"\b(mở rộng cửa sổ|cho cửa sổ to hơn|tăng kích thước cửa sổ)\b", t):
        if dry_run:
            return True, "Đã mở rộng kích thước cửa sổ cho bạn."
        ok, msg = set_hyprland_split_ratio("+0.15")
        return True, msg

    if re.search(r"\b(thu hẹp cửa sổ|cho cửa sổ nhỏ hơn|cho cửa sổ nhỏ lại|giảm kích thước cửa sổ)\b", t):
        if dry_run:
            return True, "Đã thu hẹp kích thước cửa sổ cho bạn."
        ok, msg = set_hyprland_split_ratio("-0.15")
        return True, msg

    # 6.8. Kịch bản Presets không gian làm việc (Gói 2)
    # 6.8.1. Chế độ lập trình (Workspace 2: VS Code + Terminal)
    if re.search(r"\b(?:chế độ|bật chế độ|vào chế độ|chuyển sang chế độ)\s+(?:lập trình|code|coding|dev|lập trình viên)\b", t) or \
       re.search(r"^(?:chế độ lập trình|chế độ code|bật chế độ code)$", t):
        return apply_workspace_preset("coding", app_index, dry_run=dry_run)

    # 6.8.2. Chế độ giải trí (Workspace 3: Spotify + YouTube)
    if re.search(r"\b(?:chế độ|bật chế độ|vào chế độ|chuyển sang chế độ)\s+(?:giải trí|thư giãn|chill)\b", t) or \
       re.search(r"^(?:chế độ giải trí|bật chế độ giải trí|chế độ thư giãn)$", t):
        return apply_workspace_preset("entertainment", app_index, dry_run=dry_run)

    # 7. Kiểm tra cấu hình phần cứng (CPU, RAM, Phần cứng)
    # 7.1. CPU & Vi xử lý (hỗ trợ "thông số cpu", "thông số của cpu", "cpu của máy", "tình trạng cpu", v.v.)
    if re.search(r"\b(?:kiểm tra|xem|cho xem|báo|thông báo)?\s*(?:thông số|tình trạng|mức tải|nhiệt độ|xung nhịp)?\s*(?:của\s+)?(?:cpu|vi xử lý|chip)\b", t) or \
       re.search(r"\b(?:cpu|vi xử lý)\s*(?:của\s+máy|thế nào|chạy thế nào|ra sao|đang thế nào)\b", t):
        if dry_run:
            return True, "CPU Intel Core i5 đang hoạt động ổn định."
        return True, get_cpu_info()

    # 7.2. Toàn bộ máy / RAM / Phần cứng (hỗ trợ "kiểm tra thông số của máy", "cấu hình của máy", "thông số máy tính", v.v.)
    if re.search(r"\b(?:kiểm tra|xem|cho xem|báo|thông báo)?\s*(?:thông số|tình trạng|cấu hình|thông tin)?\s*(?:của\s+)?(?:máy|máy tính|hệ thống|thiết bị|laptop|pc|phần cứng)\b", t) or \
       re.search(r"\b(?:kiểm tra|xem)?\s*(?:dung lượng|bộ nhớ)?\s*(?:ram)\b", t) or \
       re.search(r"\b(?:thông số|kiểm tra)\s+(?:cpu\s+(?:và|với)\s+ram|ram\s+(?:và|với)\s+cpu)\b", t) or \
       re.search(r"\b(máy tính chạy bao lâu|thời gian bật máy)\b", t):
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

    # 9.9. Mở nhiều ứng dụng hoặc trang web cùng lúc (Ví dụ: "Mở Youtube và Facebook", "Mở Zalo và VS Code")
    if (re.search(r"\b(?:mở|bật|chạy|khởi động|vào|truy cập)\b", t) and \
        re.search(r"(?:,|\bvà\b|\bvới\b|\bvới\s+cả\b|\bcùng\s+với\b|\bcùng\b|\blẫn\b|\brồi\b|\bđồng\s+thời\b|\bvào\b)", t)) or \
       re.search(r"\b(?:mở|bật|chạy|khởi động|vào|truy cập)\b.+\b(?:mở|bật|chạy|khởi động|vào|truy cập)\b", t):
        multi_handled, multi_reply = launch_multiple_targets(t, app_index, dry_run=dry_run)
        if multi_handled and multi_reply:
            return True, multi_reply

    # 10. Mở web theo shortcut nhanh (YouTube, Gmail, Facebook, Github...)
    # Chuẩn hóa loại bỏ các từ đệm, tiền tố yêu cầu và hậu tố đệm:
    clean_site_t = t.lower().strip()
    clean_site_t = re.sub(r"^(?:hãy|vui lòng|làm ơn|giúp tôi|cho tôi|hộ tôi|giùm tôi|bạn|thử)\s+", "", clean_site_t).strip()
    clean_site_t = re.sub(r"\b(?:trên web|ở trên web|trang web|ứng dụng web|trên browser|trên trình duyệt|trên firefox|bằng firefox|ở firefox|trên chrome|bằng chrome|trên brave)\b", "", clean_site_t)
    clean_site_t = re.sub(r"\b(?:ứng dụng|phần mềm|trang|web)\b", "", clean_site_t)
    clean_site_t = re.sub(r"\s+(?:cho tôi|giúp tôi|hộ tôi|giùm tôi|giùm|hộ|đi|lên|nào|với|nhé|nha|nhá|ạ|ngay|xem nào|được không|với ạ|nào bạn)$", "", clean_site_t).strip()
    clean_site_t = re.sub(r"\s+", " ", clean_site_t).strip()

    web_matched = None
    for site, link in URL_SHORTCUTS.items():
        patterns = [
            f"mở {site}", f"bật {site}", f"vào {site}", f"truy cập {site}",
            f"mở trang {site}", f"vào trang {site}", f"mở web {site}",
            f"check {site}", f"kiểm tra {site}", f"xem {site}", f"đọc {site}",
            site
        ]
        if clean_site_t in patterns or clean_site_t == site or t in patterns:
            web_matched = (site, link)
            break

    if web_matched:
        site, link = web_matched
        if not dry_run:
            open_url(link)
        site_name = URL_DISPLAY_NAMES.get(site, site.capitalize())
        return True, f"Đã mở {site_name} cho bạn rồi nhé."

    # 10.1. Mở trình duyệt web nói chung (vd: "mở các ứng dụng web trên firefox", "mở trình duyệt", "mở web", "mở browser", "mở firefox")
    if re.search(r"^(?:mở|bật|chạy|khởi động|vào)\s+(?:các\s+|những\s+)?(?:ứng\s*dụng\s*web|trang\s*web|trình\s*duyệt(?:\s*web)?|browser|web)(?:\s+(?:trên|ở|bằng)\s+firefox)?$", t):
        browser_app = match_app("firefox", app_index) or match_app("trình duyệt", app_index) or match_app("brave", app_index) or match_app("chrome", app_index)
        b_name = browser_app.get("name", "Firefox") if browser_app else "Firefox"
        if not dry_run:
            if browser_app:
                launch_desktop_app(browser_app)
            else:
                open_url("https://www.google.com")
        return True, f"Đã mở {b_name} cho bạn rồi nhé."

    # 11. Mở YouTube hoặc tìm kiếm trực tiếp trên YouTube
    yt_match = re.search(r"(?:mở|phát|bật|nghe)?\s*(?:bài hát|nhạc|video|clip)?\s*(.+?)\s*trên\s*youtube", t)
    if not yt_match:
        yt_match = re.search(r"(?:mở|lên|vào)\s+youtube\s+(?:tìm|xem|nghe|bài hát|nhạc|video)?\s*(.+)", t)
    if yt_match:
        query = yt_match.group(1).strip()
        query = re.sub(r"^(cho tôi|giùm tôi|hộ tôi|tìm|xem|nghe|bài hát|nhạc|video)\s*", "", query, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r"\b(trên web|trang web|ứng dụng web|ứng dụng|trên trình duyệt|web)\b", "", query).strip()
        if not clean_q:
            if not dry_run:
                open_url(URL_SHORTCUTS.get("youtube", "https://www.youtube.com"))
            return True, "Đã mở YouTube cho bạn rồi nhé."
        if not dry_run:
            msg = open_youtube_search(clean_q)
            return True, msg
        return True, f"Đang mở {clean_q} trên YouTube cho bạn." if clean_q else "Đã mở YouTube cho bạn rồi nhé."

    # 12. Tìm kiếm trên Google
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

    # 13. Mở ứng dụng trực tiếp (hỗ trợ Zalo, VS Code, IntelliJ, Spotify, Terminal, v.v.)
    # 13.1. Hỗ trợ gọi độc một tên ứng dụng (Ví dụ: "Spotify", "Zalo", "Terminal", "VS Code")
    from ai_assistant.config import APP_ALIASES
    clean_solo = t.strip().lower()
    if clean_solo in app_index or clean_solo in APP_ALIASES:
        app_target_name = APP_ALIASES.get(clean_solo, clean_solo)
        matched_app = match_app(app_target_name, app_index)
        if matched_app:
            if not dry_run:
                launch_desktop_app(matched_app)
            return True, f"Đã mở {matched_app['name']} cho bạn rồi nhé."

    # 13.2. Mở ứng dụng có kèm động từ (thêm "vào", "nghe", "lên", "truy cập")
    open_trigger = re.search(r"\b(mở|bật|chạy|khởi động|vào|nghe|lên|truy cập)\b", t)
    if open_trigger:
        matched = None
        app_match = re.search(r"\b(?:mở|bật|chạy|khởi động|vào|nghe|lên|truy cập)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+)?(.+)", t)
        if app_match:
            app_target = app_match.group(1).strip()
            clean_app = re.sub(r"\b(trên web|trang web|ứng dụng web|trình duyệt|trên firefox|bằng firefox|ở firefox|trên chrome|bằng chrome|trên brave|web)\b", "", app_target).strip()
            clean_app = re.sub(r"\s+(?:cho tôi|giúp tôi|hộ tôi|giùm tôi|giùm|hộ|đi|lên|nào|với|nhé|nha|nhá|ạ|ngay|xem nào|được không|với ạ|nào bạn)$", "", clean_app).strip()
            for site, link in URL_SHORTCUTS.items():
                if clean_app == site or app_target == site:
                    if not dry_run:
                        open_url(link)
                    site_name = URL_DISPLAY_NAMES.get(site, site.capitalize())
                    return True, f"Đã mở {site_name} cho bạn rồi nhé."
            if not any(k in app_target for k in ["youtube", "du túp", "dút túp"]):
                matched = match_app(clean_app, app_index) or match_app(app_target, app_index)
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

    timer_match = re.search(r"\b(?:hẹn giờ|đếm ngược|hẹn|báo thức)\s+(\d+(?:\.\d+)?)\s*(phút|giây|tiếng|giờ|p)(?:\s+(?:để|cho)?\s*(.+))?\b", t)
    if not timer_match and not any(t.startswith(act) for act in ["mở", "bật", "chạy", "vào", "nghe", "xem"]):
        timer_match = re.search(r"^(?:đặt\s+)?(\d+(?:\.\d+)?)\s*(phút|giây|tiếng|giờ|p)$", t)
    if timer_match:
        val = float(timer_match.group(1))
        unit = timer_match.group(2) or "phút"
        timer_label = timer_match.group(3) if timer_match.lastindex and timer_match.lastindex >= 3 else ""
        if unit in ["tiếng", "giờ"]:
            mins = val * 60.0
        elif unit == "giây":
            mins = val / 60.0
        else:
            mins = val
        if dry_run:
            return True, f"Đã đặt hẹn giờ {int(val) if val.is_integer() else val} {unit}."
        return True, timer_manager.add_timer(mins, label=timer_label or "")

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

    # 17.5. Dự phòng khớp mờ hành động chuẩn (Fuzzy Homophone & Phonetic Recovery Fallback)
    if not is_retry:
        fuzzy_act = fuzzy_match_canonical_action(t, threshold=0.82)
        if fuzzy_act:
            canon_cmd, _ = fuzzy_act
            ok_f, res_f = fast_path_nlu(canon_cmd, app_index, dry_run=dry_run, is_retry=True)
            if ok_f:
                return True, res_f

    # 18. Smart Anti-Leak Guard (Chốt chặn thông minh ngăn rò rỉ câu lệnh hỏng xuống LLM)
    # Tín hiệu câu hỏi kiến thức / đàm thoại thực sự (để cho phép lọt xuống LLM)
    question_signals = [
        "là gì", "tại sao", "như thế nào", "sao lại", "thế nào", "bao nhiêu", "ở đâu", "khi nào",
        "mấy", "giải thích", "hướng dẫn", "phân tích", "so sánh", "nghĩa là", "có phải", "viết",
        "tạo", "làm sao", "code", "thuật toán", "lập trình", "ai là", "thế nào là", "kể chuyện", "hát"
    ]
    is_knowledge_query = any(qs in t for qs in question_signals) or any(t.endswith(end) for end in [" không", " hả", " nhỉ", " chứ", " thế", " vậy"])

    if not is_knowledge_query:
        words = t.split()
        # Nếu câu bắt đầu bằng động từ hành động điều khiển (dù dài 2 hay 6 từ)
        action_verbs = ["mở", "bật", "chạy", "vào", "nghe", "tắt", "đóng", "thoát", "kill", "chuyển", "ném", "đưa", "phóng to", "thu nhỏ", "ghim"]
        first_word = words[0] if words else ""
        has_action_start = first_word in action_verbs or (len(words) >= 2 and f"{words[0]} {words[1]}" in ["m ở", "em ở", "tạm dừng", "tiếp tục", "phóng to", "thu nhỏ"])

        # Nếu câu có dáng dấp của câu lệnh (Action Command) mà Fast-Path chạy từ trên xuống dưới không xử lý được
        # (nghĩa là tên app/web/workspace bị nghe nhầm thành từ vô nghĩa)
        if has_action_start and len(words) <= 7:
            if first_word in ["mở", "bật", "chạy", "vào", "nghe"] or "m ở" in t:
                return True, "Dạ, tôi chưa nghe rõ tên ứng dụng hoặc trang web bạn muốn mở. Bạn nói lại giúp tôi nhé?"
            elif first_word in ["tắt", "đóng", "thoát", "kill"]:
                return True, "Dạ, tôi chưa nghe rõ bạn muốn đóng ứng dụng hay cửa sổ nào vậy ạ?"
            elif first_word in ["chuyển", "ném", "đưa"]:
                return True, "Dạ, tôi chưa nghe rõ bạn muốn chuyển bài hát hay chuyển không gian làm việc số mấy ạ?"
            else:
                return True, "Dạ, tôi chưa nghe rõ câu lệnh điều khiển của bạn. Bạn nói lại giúp tôi nhé?"

        # Bổ sung chặn các danh từ điều khiển bị cụt hoặc ảo giác âm thanh
        if t in [
            "cửa sổ", "ứng dụng", "phần mềm", "máy tính", "bàn làm việc", "không gian làm việc",
            "chuyến đi", "chuyến bài", "tiếp theo", "vào trong", "ra ngoài"
        ]:
            return True, "Dạ, tôi chưa nghe rõ câu lệnh điều khiển của bạn. Bạn nói lại giúp tôi nhé?"

    return False, ""
