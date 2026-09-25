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
    if not clean:
        return None

    # 1. Tra cứu trực tiếp từ bảng alias
    target = APP_ALIASES.get(clean, clean)
    if target in app_index:
        return app_index[target]

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
    try:
        cmd = f"hl.dispatch(hl.dsp.window.close('address:{address}'))"
        res = subprocess.run(["hyprctl", "eval", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True
    except Exception:
        pass
    try:
        res = subprocess.run(["hyprctl", "dispatch", "closewindow", f"address:{address}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False

def close_active_window() -> tuple[bool, str]:
    """Đóng cửa sổ hiện tại (bảo vệ tuyệt đối terminal chạy trợ lý)."""
    active = get_hyprland_active_window()
    if not active or not active.get("address"):
        return True, "Không tìm thấy cửa sổ nào đang hoạt động."

    title = active.get("title", "").lower()
    cls = active.get("class", "").lower()
    if "agy" in title or "antigravity" in title or cls in PROTECTED_CLASSES:
        return True, "Cửa sổ này đang làm việc và được bảo vệ, tôi không đóng nhé."

    addr = active.get("address")
    close_hyprland_window_by_address(addr)
    app_name = active.get("initialTitle") or active.get("title") or active.get("class") or "cửa sổ hiện tại"
    return True, f"Đã đóng {app_name} cho bạn rồi nhé."

def close_all_open_apps() -> tuple[bool, str]:
    """Đóng tất cả các ứng dụng người dùng đang mở trên màn hình."""
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

def close_specific_app(target: str, app_index: dict = None) -> tuple[bool, str]:
    """Đóng ứng dụng cụ thể theo tên (Zalo, Chrome, VS Code, Spotify, v.v.)."""
    target = target.strip().lower()
    target = re.sub(r"^(?:ứng dụng|phần mềm|app|cửa sổ|trình duyệt)\s+", "", target).strip()
    if not target or target in ["hẹn giờ", "báo thức", "nhạc", "wifi", "bluetooth"]:
        return False, ""

    clients = get_hyprland_clients()
    matched_addrs = []
    matched_pids = set()
    display_name = target

    search_keys = [target]
    if target in ["zalo", "da lô", "za lô"]:
        search_keys.extend(["zalo"])
    elif target in ["code", "vs code", "vscode", "visual studio code"]:
        search_keys.extend(["code", "vscode", "visual-studio-code"])
    elif target in ["chrome", "trình duyệt", "google chrome", "web", "internet"]:
        search_keys.extend(["chrome", "google-chrome", "firefox", "brave", "edge"])
    elif target in ["spotify"]:
        search_keys.extend(["spotify"])
    elif target in ["terminal", "dòng lệnh"]:
        search_keys.extend(["kitty", "alacritty", "foot"])
    elif target in ["telegram"]:
        search_keys.extend(["telegram", "telegramdesktop"])

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
            display_name = c.get("initialTitle") or c.get("class") or target

    proc_keywords = list(search_keys)
    if app_index:
        matched_app = match_app(target, app_index)
        if matched_app:
            display_name = matched_app.get("name", display_name)
            exec_raw = matched_app.get("exec", "").strip()
            exec_parts = exec_raw.split()
            exec_bin = exec_parts[0] if exec_parts else ""
            if exec_bin:
                proc_keywords.append(os.path.basename(exec_bin).lower())
            d_id = matched_app.get("desktop_id", "").lower()
            proc_keywords.append(d_id.replace(".desktop", ""))

    for addr in matched_addrs:
        close_hyprland_window_by_address(addr)

    for pid in matched_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

    for kw in set(proc_keywords):
        if len(kw) >= 3 and kw not in ["python", "bash", "kitty", "sh", "systemd", "root"]:
            try:
                subprocess.run(["pkill", "-15", "-f", kw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    return True, f"Đã đóng ứng dụng {display_name} cho bạn rồi nhé."

def set_window_fullscreen(maximize: bool = True):
    """Phóng to tối đa hoặc thu nhỏ cửa sổ tiêu chuẩn."""
    mode = "maximized" if maximize else "none"
    subprocess.run(["hyprctl", "eval", f"hl.dispatch(hl.dsp.window.fullscreen({{ mode = '{mode}' }}))"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
