"""
Quản lý ứng dụng desktop và điều khiển cửa sổ Hyprland (chuẩn Hyprland v0.56.2).
"""

import os
import re
import glob
import json
import shlex
import signal
import difflib
import subprocess
import time
import unicodedata
from ai_assistant.config import APP_ALIASES, PROTECTED_CLASSES

def build_app_index() -> dict:
    """Quét các file .desktop để tạo danh sách ứng dụng đã cài đặt."""
    apps = {}
    search_dirs = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/local/share/applications",
        "/usr/share/applications"
    ]
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for f in glob.glob(os.path.join(d, "*.desktop")):
            fname = os.path.basename(f)
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                    lines = fp.readlines()
                name = ""
                exec_cmd = ""
                nodisplay = False
                for line in lines:
                    line = line.strip()
                    if line.startswith("Name=") and not name:
                        name = line.split("=", 1)[1].strip()
                    elif line.startswith("Exec=") and not exec_cmd:
                        exec_cmd = line.split("=", 1)[1].strip()
                    elif line.lower() == "nodisplay=true":
                        nodisplay = True
                if name and exec_cmd and not nodisplay:
                    apps[name.lower()] = {
                        "name": name,
                        "desktop_id": fname,
                        "exec": exec_cmd
                    }
            except Exception:
                pass
    return apps

def clean_target_query(q: str) -> str:
    """Chuẩn hóa và loại bỏ các từ phụ trợ, từ đệm ở đầu và cuối chuỗi tìm kiếm app."""
    s = q.lower().strip()
    s = re.sub(r"[,\.!?]", " ", s)
    s = re.sub(r"^(?:hãy|cho tôi|giúp tôi|hộ tôi|giùm tôi|làm ơn|vui lòng|bạn|thử)\s+", "", s).strip()
    s = re.sub(r"^(?:ứng dụng|phần mềm|app|trình duyệt)\s+", "", s).strip()
    s = re.sub(r"^(?:cho tôi|giúp tôi|hộ tôi|giùm tôi)\s+", "", s).strip()
    pattern = r"\s+(?:lên|đi|nào|với|cho tôi|giúp tôi|hộ tôi|giùm tôi|giùm|hộ|ngay|nhé|nha|nhá|được không|ạ|với ạ|nào bạn|xem nào|nghe nhạc)$"
    while True:
        prev = s
        s = re.sub(pattern, "", s).strip()
        if s == prev:
            break
    return s.strip()

def match_app(query: str, app_index: dict):
    """Tìm ứng dụng phù hợp nhất dựa trên từ khóa người dùng, alias hoặc so khớp mờ."""
    clean = clean_target_query(query)
    if not clean or app_index is None:
        return None

    # 1. Tra cứu trực tiếp từ bảng alias
    target = APP_ALIASES.get(clean, clean)
    if target in app_index:
        return app_index[target]

    # Tra cứu alias không dấu (nếu người dùng gõ không dấu, vd: "trinh duyet" -> "trình duyệt" -> "firefox")
    def _strip(s: str) -> str:
        s = s.replace("đ", "d").replace("Đ", "D")
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()

    clean_unacc = _strip(clean)
    for alias, mapped in APP_ALIASES.items():
        if _strip(alias) == clean_unacc:
            target = mapped
            if target in app_index:
                return app_index[target]
            break

    # Dự phòng thông minh cho trình duyệt: Nếu alias chỉ định trình duyệt chưa cài (vd: brave/chrome),
    # tự động trỏ về trình duyệt có sẵn trên hệ thống (Firefox).
    if target in ["firefox", "brave", "chrome", "google-chrome", "chromium", "trình duyệt", "browser", "web"]:
        for b in ["firefox", "google-chrome", "brave", "chromium"]:
            if b in app_index:
                return app_index[b]

    # 2. Khớp chuỗi con và kiểm tra ranh giới từ
    for k, v in app_index.items():
        if target == k or target in k or k in target:
            return v

    # 3. Kiểm tra tên file desktop_id
    for k, v in app_index.items():
        if target in v["desktop_id"].lower():
            return v

    # 4. So khớp mờ (Fuzzy matching)
    matches = difflib.get_close_matches(target, list(app_index.keys()), n=1, cutoff=0.7)
    if matches:
        return app_index[matches[0]]

    return None

def find_app_in_text(text: str, app_index: dict):
    """Tìm kiếm trực tiếp bất kỳ ứng dụng nào được đề cập trong toàn bộ câu nói."""
    t = text.lower()
    sorted_aliases = sorted(APP_ALIASES.keys(), key=lambda x: len(x), reverse=True)
    for alias in sorted_aliases:
        if alias in ["web", "file", "nhạc", "cốt", "code"] and len(alias) <= 4:
            pattern = r"(?:\b(?:mở|bật|chạy|khởi động)\s+)(?:ứng dụng\s+|phần mềm\s+|app\s+)?" + re.escape(alias) + r"\b"
            if not re.search(pattern, t):
                continue
        pattern = r"(?:\b|(?<=^))" + re.escape(alias) + r"(?:\b|(?=$))"
        if re.search(pattern, t):
            mapped = APP_ALIASES[alias]
            if mapped in app_index:
                return app_index[mapped]

    for k, v in app_index.items():
        if len(k) >= 4:
            pattern = r"(?:\b|(?<=^))" + re.escape(k) + r"(?:\b|(?=$))"
            if re.search(pattern, t):
                return v

    return None

def launch_desktop_app(app_info: dict) -> bool:
    """Khởi chạy ứng dụng an toàn mà không chặn tiến trình chính."""
    desktop_id = app_info.get("desktop_id")
    if desktop_id:
        try:
            subprocess.Popen(
                ["gtk-launch", desktop_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return True
        except Exception:
            pass

    exec_cmd = app_info.get("exec", "")
    if exec_cmd:
        try:
            clean_cmd = re.sub(r'%[a-zA-Z]', '', exec_cmd).strip()
            args = shlex.split(clean_cmd)
            subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return True
        except Exception:
            pass
    return False

def get_hyprland_clients() -> list[dict]:
    """Lấy danh sách các cửa sổ GUI đang mở trên Hyprland."""
    try:
        res = subprocess.run(["hyprctl", "clients", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return []

def get_hyprland_active_window() -> dict:
    """Lấy thông tin cửa sổ đang active trên Hyprland."""
    try:
        res = subprocess.run(["hyprctl", "activewindow", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return {}

def close_hyprland_window_by_address(address: str) -> bool:
    """Đóng cửa sổ cụ thể theo địa chỉ hex thông qua Lua Dispatcher của Hyprland 0.56.2 có fallback tiêu chuẩn."""
    if not address:
        return False
    # Hyprland 0.56.2 Lua Dispatcher: tìm window và đóng bằng hl.dsp.window.close({ window = w })
    lua = f"""
    local target_addr = "{address.lower()}"
    local windows = hl.get_windows()
    for _, w in ipairs(windows) do
        if string.lower(w.address) == target_addr then
            hl.dispatch(hl.dsp.window.close({{ window = w }}))
            return "CLOSED"
        end
    end
    return "NOT_FOUND"
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True
    except Exception:
        pass
    try:
        res = subprocess.run(["hyprctl", "dispatch", "closewindow", f"address:{address}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False

def focus_window_by_class(cls_name: str) -> bool:
    """Đưa cửa sổ ứng dụng lên tiêu điểm và chuyển workspace tới ứng dụng nếu đang ở workspace khác."""
    if not cls_name:
        return False
    lua = f"""
    local clients = hl.get_windows()
    for _, c in ipairs(clients) do
        if string.find(string.lower(c.class), "{cls_name.lower()}") then
            if c.workspace then
                local ws = hl.get_workspace(c.workspace.id)
                if ws then
                    hl.dispatch(hl.dsp.focus({{ workspace = ws }}))
                end
            end
            hl.dispatch(hl.dsp.focus({{ window = c }}))
            return true
        end
    end
    return false
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        return res.returncode == 0 and res.stdout.strip() == "ok"
    except Exception:
        return False

def close_active_window(dry_run: bool = False) -> tuple[bool, str]:
    """Đóng cửa sổ hiện tại (bảo vệ tuyệt đối terminal chạy trợ lý)."""
    if dry_run:
        return True, "Đã đóng cửa sổ hiện tại cho bạn rồi nhé."

    active = get_hyprland_active_window()
    if not active or not active.get("address"):
        return True, "Không tìm thấy cửa sổ nào đang hoạt động."

    title = active.get("title", "").lower()
    cls = active.get("class", "").lower()
    if any(k in title for k in ["agy", "antigravity", "assistant", "terminal", "voice-ai", "chats", "tmux"]) or cls in PROTECTED_CLASSES:
        return True, "Cửa sổ này là môi trường làm việc đang được bảo vệ, tôi không đóng nhé."

    addr = active.get("address")
    close_hyprland_window_by_address(addr)
    app_name = active.get("initialTitle") or active.get("title") or active.get("class") or "cửa sổ hiện tại"
    return True, f"Đã đóng {app_name} cho bạn rồi nhé."

def close_active_tab(dry_run: bool = False) -> tuple[bool, str]:
    """Đóng tab hiện tại trong trình duyệt hoặc trình soạn thảo (bằng phím tắt Ctrl+W qua ydotool)."""
    if dry_run:
        return True, "Đã đóng tab hiện tại cho bạn rồi nhé."
    try:
        res = subprocess.run(["ydotool", "key", "29:1", "17:1", "17:0", "29:0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        if res.returncode == 0:
            return True, "Đã đóng tab hiện tại cho bạn rồi nhé."
    except Exception:
        pass
    return close_active_window(dry_run=dry_run)

def close_all_open_apps(dry_run: bool = False) -> tuple[bool, str]:
    """Đóng tất cả các ứng dụng người dùng đang mở trên màn hình."""
    if dry_run:
        return True, "Đã đóng tất cả ứng dụng đang mở cho bạn rồi nhé."

    clients = get_hyprland_clients()
    closed_count = 0
    closed_names = []

    for c in clients:
        cls = c.get("class", "").lower()
        title = c.get("title", "").lower()
        addr = c.get("address", "")
        pid = c.get("pid", 0)

        if cls in PROTECTED_CLASSES or "agy" in title or "antigravity" in title:
            continue

        if addr:
            close_hyprland_window_by_address(addr)
            closed_count += 1
            name = c.get("initialTitle") or c.get("class") or "ứng dụng"
            if name not in closed_names:
                closed_names.append(name)

        if pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

    if closed_count > 0:
        return True, f"Đã đóng {closed_count} ứng dụng đang mở cho bạn rồi nhé."
    else:
        return True, "Hiện không có ứng dụng nào đang mở cần đóng."

def _close_single_app(target: str, app_index: dict = None, dry_run: bool = False) -> tuple[bool, str]:
    """Đóng một ứng dụng hoặc dịch vụ cụ thể theo tên."""
    target = target.strip().lower()
    target = re.sub(r"^(?:ứng dụng|phần mềm|app|cửa sổ|trang web|trang|web)\s+", "", target).strip()
    if not target or target in ["hẹn giờ", "báo thức", "nhạc", "wifi", "bluetooth"]:
        return False, ""

    display_name = target.capitalize()

    search_keys = [target]
    if target in ["zalo", "da lô", "za lô"]:
        search_keys.extend(["zalo"])
        display_name = "Zalo"
    elif target in ["code", "vs code", "vscode", "visual studio code"]:
        search_keys.extend(["code", "vscode", "visual-studio-code"])
        display_name = "VS Code"
    elif target in ["chrome", "trình duyệt", "trình diệt", "trình diệt web", "trình duyệt web", "trình zuyệt", "google chrome", "web", "internet", "browser", "brave"]:
        search_keys.extend(["brave", "chrome", "google-chrome", "firefox", "edge", "chromium"])
        display_name = "Trình duyệt"
    elif target in ["facebook", "phây búc", "phây buk", "phe búc", "phây", "fb", "phây-búc"]:
        search_keys.extend(["facebook"])
        display_name = "Facebook"
    elif target in ["github", "gít húp", "gít háp", "git hup", "git hub", "gít-húp", "gh"]:
        search_keys.extend(["github"])
        display_name = "GitHub"
    elif target in [
        "gmail", "gờ meo", "gở meo", "gơ meo", "gờ mail", "gở mail", "gừa mêu", "gửa mêu",
        "gờ mêu", "gơ mêu", "gừ mail", "g mail", "gờ-meo", "gờ-mail", "gơ-meo", "g-meo",
        "g-mail", "gmeo", "gờ neo", "gờ-neo", "gờ leo", "gờ-leo", "g neo", "g leo",
        "di meo", "zi meo", "hòm thư", "hộp thư"
    ]:
        search_keys.extend(["gmail", "mail.google.com"])
        display_name = "Gmail"
    elif target in ["youtube", "du túp", "dút túp", "diu túp"]:
        search_keys.extend(["youtube"])
        display_name = "YouTube"
    elif target in ["spotify"]:
        search_keys.extend(["spotify"])
        display_name = "Spotify"
    elif target in ["terminal", "dòng lệnh"]:
        search_keys.extend(["kitty", "alacritty", "foot"])
        display_name = "Terminal"
    elif target in ["telegram"]:
        search_keys.extend(["telegram", "telegramdesktop"])
        display_name = "Telegram"

    matched_app = None
    if app_index:
        matched_app = match_app(target, app_index)
        if matched_app:
            display_name = matched_app.get("name", display_name)

    if dry_run:
        return True, f"Đã đóng ứng dụng {display_name} cho bạn rồi nhé."

    clients = get_hyprland_clients()
    matched_addrs = []
    matched_pids = set()

    for c in clients:
        cls = c.get("class", "").lower()
        title = c.get("title", "").lower()
        init_cls = c.get("initialClass", "").lower()
        init_title = c.get("initialTitle", "").lower()
        addr = c.get("address", "")
        pid = c.get("pid", 0)

        if cls in PROTECTED_CLASSES or "agy" in title or "antigravity" in title:
            continue

        if any(k in cls or k in title or k in init_cls or k in init_title for k in search_keys):
            if addr:
                matched_addrs.append(addr)
            if pid > 0:
                matched_pids.add(pid)
            display_name = c.get("initialTitle") or c.get("class") or display_name

    proc_keywords = list(search_keys)
    if matched_app:
        exec_raw = matched_app.get("exec", "").strip()
        exec_parts = exec_raw.split()
        exec_bin = exec_parts[0] if exec_parts else ""
        if exec_bin:
            proc_keywords.append(os.path.basename(exec_bin).lower())
        d_id = matched_app.get("desktop_id", "").lower()
        proc_keywords.append(d_id.replace(".desktop", ""))

    # 1. Gửi D-Bus Quit trực tiếp cho trình phát nhạc (Spotify MPRIS)
    if any(k in ["spotify", "spotfy", "ncspot"] for k in search_keys):
        try:
            subprocess.run(["dbus-send", "--type=method_call", "--dest=org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Quit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass

    # 2. Đóng cửa sổ Hyprland theo địa chỉ hex
    for addr in matched_addrs:
        close_hyprland_window_by_address(addr)

    # 3. Gửi SIGTERM tới các PID cửa sổ đã tìm thấy
    for pid in matched_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

    # 4. Quét và dừng tiến trình nền theo từ khóa ứng dụng (bảo vệ tuyệt đối môi trường shell & hệ thống)
    safe_blocklist = [
        "python", "bash", "kitty", "alacritty", "foot", "wezterm", "sh", "zsh",
        "systemd", "root", "agy", "antigravity", "hyprland", "waybar", "quickshell",
        "qs", "dunst", "swaync", "pipewire", "wireplumber"
    ]
    for kw in set(proc_keywords):
        if len(kw) >= 3 and kw not in safe_blocklist:
            try:
                subprocess.run(["pkill", "-15", "-f", kw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if kw in ["spotify", "discord", "telegram"]:
                    time.sleep(0.08)
                    subprocess.run(["pkill", "-9", "-f", kw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    if matched_addrs or matched_pids or matched_app:
        return True, f"Đã đóng ứng dụng {display_name} cho bạn rồi nhé."
    elif target in ["gmail", "facebook", "github", "youtube"]:
        active = get_hyprland_active_window()
        active_cls = active.get("class", "").lower()
        if any(b in active_cls for b in ["brave", "chrome", "firefox", "edge"]):
            try:
                subprocess.run(["ydotool", "key", "29:1", "17:1", "17:0", "29:0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                return True, f"Đã đóng tab {display_name} trên trình duyệt cho bạn rồi nhé."
            except Exception:
                pass
        return True, f"Hiện không tìm thấy cửa sổ {display_name} nào đang mở."
    else:
        return True, f"Đã đóng ứng dụng {display_name} cho bạn rồi nhé."

def close_specific_app(target: str, app_index: dict = None, dry_run: bool = False) -> tuple[bool, str]:
    """Đóng ứng dụng hoặc trang web cụ thể theo tên (hỗ trợ đóng một hoặc nhiều app/web cùng lúc)."""
    target = target.strip().lower()
    target = re.sub(r"^(?:ứng dụng|phần mềm|app|cửa sổ|trang web|trang|web)\s+", "", target).strip()
    if not target or target in ["hẹn giờ", "báo thức", "nhạc", "wifi", "bluetooth", "lại", "đi", "này", "nào", "hộ", "giúp", "giùm", "nhé", "nha"]:
        return False, ""

    # Hỗ trợ đóng nhiều mục tiêu: "đóng youtube và facebook", "tắt zalo, vs code và spotify"
    s = re.sub(r"\b(?:và|với|với\s+cả|cùng\s+với|cùng|đồng\s+thời|rồi|lẫn)\s+(?:đóng|tắt|thoát|kill)\b", " và ", target)
    s = re.sub(r"\b(?:rồi\s+)?(?:đóng|tắt|thoát|kill)\b", " và ", s)
    if re.search(r"\s*(?:,|\bvà\b|\bvới\b|\bvới\s+cả\b|\bcùng\s+với\b|\bcùng\b|\blẫn\b|\bđồng\s+thời\b|\brồi\b)\s*", s):
        parts = re.split(r"\s*(?:,|\bvà\b|\bvới\b|\bvới\s+cả\b|\bcùng\s+với\b|\bcùng\b|\blẫn\b|\bđồng\s+thời\b|\brồi\b)\s*", s)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            closed_names = []
            for p in parts:
                ok, rep = _close_single_app(p, app_index, dry_run=dry_run)
                if ok:
                    m = re.search(r"Đã đóng (?:ứng dụng |tab )?(.+?) (?:cho bạn|trên trình)", rep)
                    name = m.group(1).strip() if m else p.capitalize()
                    if name not in closed_names:
                        closed_names.append(name)
            if closed_names:
                if len(closed_names) == 1:
                    return True, f"Đã đóng {closed_names[0]} cho bạn rồi nhé."
                elif len(closed_names) == 2:
                    return True, f"Đã đóng {closed_names[0]} và {closed_names[1]} cho bạn rồi nhé."
                else:
                    return True, f"Đã đóng {', '.join(closed_names[:-1])} và {closed_names[-1]} cho bạn rồi nhé."
            return True, "Đã thực hiện đóng các ứng dụng theo yêu cầu của bạn."

    return _close_single_app(target, app_index, dry_run=dry_run)

def launch_multiple_targets(text: str, app_index: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    Khởi chạy đồng thời nhiều ứng dụng desktop hoặc trang web trong cùng một câu lệnh.
    Ví dụ: 'Mở Youtube và Facebook', 'Mở Zalo và VS Code', 'Bật Spotify, Kitty và Brave'.
    """
    from ai_assistant.config import URL_SHORTCUTS, URL_DISPLAY_NAMES
    from ai_assistant.tools.web import open_url

    t = text.lower().strip()
    # Loại bỏ tiền tố động từ ở đầu câu
    s = re.sub(r"^(?:hãy\s+|cho tôi\s+|giúp tôi\s+|hộ tôi\s+|làm ơn\s+)?(?:mở|bật|chạy|khởi động|vào|truy cập)\s+", "", t).strip()
    # Chuẩn hóa các liên từ kèm lặp động từ: "và mở", "với mở", "cùng với mở", "rồi mở", v.v. -> " và "
    s = re.sub(r"\b(?:và|với|với\s+cả|cùng\s+với|cùng|đồng\s+thời|rồi|lẫn)\s+(?:mở|bật|chạy|khởi động|vào|truy cập)\b", " và ", s)
    # Chuẩn hóa động từ thứ hai xuất hiện ở giữa câu (vd: "gmail vào facebook", "gmail rồi vào facebook", "gmail mở facebook") -> " và "
    s = re.sub(r"\b(?:rồi\s+)?(?:mở|bật|chạy|khởi động|vào|truy cập)\b", " và ", s)
    # Tự động chèn liên từ 'và' nếu hai ứng dụng/web được đọc liền kề nhau mà không có từ nối (vd: "youtube gmail")
    known_targets = r"(?:youtube|facebook|gmail|github|zalo|vs\s*code|vscode|spotify|firefox|chrome|kitty|terminal|trình\s*duyệt)"
    s = re.sub(rf"(\b{known_targets}\b)\s+(\b{known_targets}\b)", r"\1 và \2", s, flags=re.IGNORECASE)

    # Tách các mục tiêu
    parts = re.split(r"\s*(?:,|\bvà\b|\bvới\b|\bvới\s+cả\b|\bcùng\s+với\b|\bcùng\b|\blẫn\b|\bđồng\s+thời\b|\brồi\b)\s*", s)
    cleaned_parts = [p.strip() for p in parts if p.strip()]

    if len(cleaned_parts) < 2:
        return False, ""

    opened_names = []
    unrecognized = []

    for item in cleaned_parts:
        clean_item = re.sub(r"^(?:ứng dụng|phần mềm|app|trang web|trang|web)\s+", "", item).strip()
        clean_item = re.sub(r"\s+(?:trên web|ở trên web|trang web|ứng dụng web|trên browser|trên trình duyệt|trên firefox|bằng firefox|ở firefox|trên chrome|bằng chrome|web)$", "", clean_item).strip()
        if clean_item in [
            "mail", "e-mail", "email", "gmaill", "gmailll", "gourmiel", "gour miel", "gourmeo", "gourmail",
            "gồm yêu", "gôm yêu", "gờ yêu", "cơm meo", "cơm mail", "con meo", "com meo", "ca meo",
            "gồm meo", "gôm meo", "gờ miêu", "miêu", "hòm thư", "hộp thư", "thư điện tử", "ca mèo",
            "gần miêu", "gồm nhau", "gôm nhau", "gờ nhau", "gờ meo", "gở meo", "gơ meo", "gờ mail",
            "gở mail", "gơ mail", "g mail", "gờ-meo", "gờ-mail", "gơ-meo", "g-meo", "g-mail", "gmeo",
            "gờ neo", "gờ-neo", "gờ leo", "gờ-leo", "g neo", "g leo", "di meo", "zi meo"
        ]:
            clean_item = "gmail"
        if clean_item in ["vô tấp", "vô túp", "dô túp", "dô tấp", "zu túp", "du tốc", "dưu tốc", "diu tốc"]:
            clean_item = "youtube"
        if not clean_item:
            continue

        # 1. Kiểm tra Web shortcut (YouTube, Facebook, GitHub, Gmail...)
        if clean_item in URL_SHORTCUTS:
            link = URL_SHORTCUTS[clean_item]
            name = URL_DISPLAY_NAMES.get(clean_item, clean_item.capitalize())
            if not dry_run:
                if opened_names:
                    import time
                    time.sleep(0.3)
                open_url(link)
            if name not in opened_names:
                opened_names.append(name)
            continue

        # 2. Kiểm tra Desktop App trong app_index
        matched = match_app(clean_item, app_index)
        if not matched:
            matched = find_app_in_text(clean_item, app_index)

        if matched:
            name = matched.get("name", clean_item.capitalize())
            if not dry_run:
                if opened_names:
                    import time
                    time.sleep(0.3)
                launch_desktop_app(matched)
            if name not in opened_names:
                opened_names.append(name)
            continue

        unrecognized.append(clean_item)

    if opened_names:
        if len(opened_names) == 1:
            msg = f"Đã mở {opened_names[0]} cho bạn rồi nhé."
        elif len(opened_names) == 2:
            msg = f"Đã mở {opened_names[0]} và {opened_names[1]} cho bạn rồi nhé."
        else:
            msg = f"Đã mở {', '.join(opened_names[:-1])} và {opened_names[-1]} cho bạn rồi nhé."

        if unrecognized:
            msg += f" (Không tìm thấy: {', '.join(unrecognized)})."
        return True, msg

    return False, ""

def set_window_fullscreen(maximize: bool = True):
    """Phóng to tối đa hoặc thu nhỏ cửa sổ tiêu chuẩn trong không gian làm việc."""
    active = get_hyprland_active_window()
    is_fs = (active.get("fullscreen", 0) > 0) if active else False
    if maximize:
        if not is_fs:
            subprocess.run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.fullscreen({ mode = 'maximized' }))"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        if is_fs:
            subprocess.run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.fullscreen())"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def switch_hyprland_workspace(workspace_id: int) -> tuple[bool, str]:
    """Chuyển không gian làm việc (workspace) trên Hyprland v0.56.2."""
    if workspace_id < 1 or workspace_id > 10:
        return False, "Không gian làm việc không hợp lệ."
    lua = f"""
    local ws = hl.get_workspace({workspace_id})
    if ws then
        hl.dispatch(hl.dsp.focus({{ workspace = ws }}))
        return true
    end
    return false
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True, f"Đã chuyển sang không gian làm việc số {workspace_id} cho bạn."
    except Exception:
        pass
    return False, f"Không thể chuyển sang không gian làm việc {workspace_id}."

def move_active_window_to_workspace(workspace_id: int) -> tuple[bool, str]:
    """Di chuyển cửa sổ đang hoạt động sang workspace khác trên Hyprland v0.56.2."""
    if workspace_id < 1 or workspace_id > 10:
        return False, "Không gian làm việc không hợp lệ."
    lua = f"""
    local w = hl.get_active_window()
    local ws = hl.get_workspace({workspace_id})
    if w and ws then
        hl.dispatch(hl.dsp.window.move({{ window = w, workspace = ws }}))
        return true
    end
    return false
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True, f"Đã chuyển cửa sổ hiện tại sang không gian làm việc số {workspace_id}."
    except Exception:
        pass
    return False, f"Không thể chuyển cửa sổ sang không gian làm việc {workspace_id}."

def toggle_window_floating() -> tuple[bool, str]:
    """Chuyển đổi trạng thái cửa sổ nổi (floating) hoặc cố định (tiling)."""
    lua = """
    local w = hl.get_active_window()
    if w then
        hl.dispatch(hl.dsp.window.float({ window = w }))
        return true
    end
    return false
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True, "Đã chuyển đổi trạng thái cửa sổ nổi cho bạn."
    except Exception:
        pass
    return False, "Không thể chuyển đổi trạng thái cửa sổ nổi."

def toggle_window_pin() -> tuple[bool, str]:
    """Ghim hoặc bỏ ghim cửa sổ hiện tại nổi trên tất cả các workspace."""
    lua = """
    local w = hl.get_active_window()
    if w then
        hl.dispatch(hl.dsp.window.pin({ window = w }))
        return true
    end
    return false
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True, "Đã ghim cửa sổ này hiển thị trên mọi không gian làm việc."
    except Exception:
        pass
    return False, "Không thể ghim cửa sổ này."

def toggle_hyprland_split() -> tuple[bool, str]:
    """Đổi hướng chia màn hình (ngang/dọc) trong Hyprland v0.56.2 qua Lua layout dispatcher."""
    lua = """
    local ws = hl.get_active_workspace()
    local wins = hl.get_workspace_windows(ws)
    for _, win in ipairs(wins) do
        if win.floating then
            hl.dispatch(hl.dsp.window.float({ window = win }))
        end
    end
    return hl.dispatch(hl.dsp.layout('togglesplit'))
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True, "Đã đổi hướng chia màn hình cho bạn rồi nhé."
    except Exception:
        pass
    return False, "Không thể đổi hướng chia màn hình."

def set_hyprland_split_ratio(ratio_cmd: str) -> tuple[bool, str]:
    """
    Điều chỉnh tỷ lệ chia màn hình trên Hyprland (ví dụ: '1.0' cho 50/50, '1.4' cho 70/30, '+0.15', '-0.15').
    Tự động chuyển các cửa sổ đang mở trôi (floating) về lưới (tiling) để chia đều màn hình.
    """
    lua = f"""
    local ws = hl.get_active_workspace()
    local wins = hl.get_workspace_windows(ws)
    for _, win in ipairs(wins) do
        if win.floating then
            hl.dispatch(hl.dsp.window.float({{ window = win }}))
        end
    end

    local w = hl.get_active_window()
    local m = hl.get_active_monitor()
    if w and m then
        local target_x = nil
        if "{ratio_cmd}" == "1.0" then
            target_x = math.floor(m.width * 0.5)
        elseif "{ratio_cmd}" == "1.4" then
            target_x = math.floor(m.width * 0.7)
        elseif "{ratio_cmd}" == "0.7" then
            target_x = math.floor(m.width * 0.3)
        end

        if target_x then
            hl.dispatch(hl.dsp.window.resize({{ x = target_x, y = w.size.y, relative = false, window = w }}))
        elseif string.sub("{ratio_cmd}", 1, 1) == "+" then
            hl.dispatch(hl.dsp.window.resize({{ x = 150, y = 0, relative = true, window = w }}))
        elseif string.sub("{ratio_cmd}", 1, 1) == "-" then
            hl.dispatch(hl.dsp.window.resize({{ x = -150, y = 0, relative = true, window = w }}))
        end
        return true
    end
    return false
    """
    try:
        res = subprocess.run(["hyprctl", "eval", lua], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            if ratio_cmd == "1.0":
                return True, "Đã đưa cửa sổ vào lưới và chia đều màn hình tỷ lệ 50 50 cho bạn rồi nhé."
            elif ratio_cmd == "1.4":
                return True, "Đã điều chỉnh cửa sổ chiếm 70% màn hình cho bạn rồi nhé."
            elif ratio_cmd == "0.7":
                return True, "Đã điều chỉnh cửa sổ chiếm 30% màn hình cho bạn rồi nhé."
            elif ratio_cmd.startswith("+"):
                return True, "Đã mở rộng kích thước cửa sổ cho bạn."
            elif ratio_cmd.startswith("-"):
                return True, "Đã thu hẹp kích thước cửa sổ cho bạn."
            return True, "Đã điều chỉnh tỷ lệ chia màn hình."
    except Exception:
        pass
    return False, "Không thể điều chỉnh tỷ lệ màn hình."

def apply_workspace_preset(preset_type: str, app_index: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    Kích hoạt kịch bản không gian làm việc (Workspace Preset) thông minh.
    - 'coding': Chuyển sang Workspace 2, mở VS Code + Kitty Terminal.
    - 'entertainment': Chuyển sang Workspace 3, mở Spotify + YouTube.
    """
    import time
    from ai_assistant.config import URL_SHORTCUTS
    from ai_assistant.tools.web import open_url

    if preset_type == "coding":
        ws_id = 2
        msg = "Đã kích hoạt chế độ lập trình trên workspace 2: mở VS Code và Terminal."
        if dry_run:
            return True, msg

        # 1. Chuyển sang Workspace 2
        switch_hyprland_workspace(ws_id)
        time.sleep(0.3)

        # 2. Khởi chạy VS Code (nếu chưa có trong index thì gọi lệnh binary 'code')
        code_app = match_app("code", app_index) or match_app("vs code", app_index)
        if code_app:
            launch_desktop_app(code_app)
        else:
            subprocess.Popen(["code"])
        time.sleep(0.5)

        # 3. Khởi chạy Kitty Terminal
        kitty_app = match_app("kitty", app_index) or match_app("terminal", app_index)
        if kitty_app:
            launch_desktop_app(kitty_app)
        else:
            subprocess.Popen(["kitty"])

        return True, msg

    elif preset_type == "entertainment":
        ws_id = 3
        msg = "Đã kích hoạt chế độ giải trí trên workspace 3: mở Spotify và YouTube."
        if dry_run:
            return True, msg

        # 1. Chuyển sang Workspace 3
        switch_hyprland_workspace(ws_id)
        time.sleep(0.3)

        # 2. Khởi chạy Spotify
        spot_app = match_app("spotify", app_index)
        if spot_app:
            launch_desktop_app(spot_app)
        else:
            subprocess.Popen(["spotify"])
        time.sleep(0.5)

        # 3. Mở YouTube trên Browser
        open_url(URL_SHORTCUTS.get("youtube", "https://youtube.com"))

        return True, msg

    return False, ""

