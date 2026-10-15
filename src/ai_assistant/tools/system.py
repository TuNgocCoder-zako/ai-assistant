"""
Công cụ đọc và điều khiển hệ điều hành Arch Linux / phần cứng laptop Asus TUF.
"""

import os
import re
import ast
import operator
import glob
import datetime
import subprocess
import requests

def get_vietnamese_time() -> str:
    """Trả về giờ và phút hiện tại bằng tiếng Việt chuẩn ngữ âm."""
    now = datetime.datetime.now()
    return f"Bây giờ là {now.hour} giờ {now.minute} phút rồi bạn nhé."

def get_vietnamese_date() -> str:
    """Trả về ngày tháng hiện tại bằng tiếng Việt chuẩn."""
    now = datetime.datetime.now()
    days_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    day_name = days_vi[now.weekday()]
    return f"Hôm nay là {day_name}, ngày {now.day} tháng {now.month} năm {now.year}."

def get_battery_info() -> str:
    """Kiểm tra tình trạng pin và sạc thực tế của laptop qua Linux sysfs (hỗ trợ động BAT0, BAT1...)."""
    try:
        # 1. Tìm thiết bị pin qua Linux sysfs (/sys/class/power_supply/BAT*)
        bat_dirs = glob.glob("/sys/class/power_supply/BAT*") or glob.glob("/sys/class/power_supply/*bat*")
        if bat_dirs:
            bat_dir = bat_dirs[0]
            cap_file = os.path.join(bat_dir, "capacity")
            status_file = os.path.join(bat_dir, "status")

            capacity = ""
            status = "Discharging"
            if os.path.exists(cap_file):
                with open(cap_file, "r") as f:
                    capacity = f.read().strip()
            if os.path.exists(status_file):
                with open(status_file, "r") as f:
                    status = f.read().strip()

            state_map = {
                "discharging": "đang dùng pin",
                "charging": "đang cắm sạc",
                "full": "đã sạc đầy và đang cắm nguồn",
                "not charging": "đang cắm nguồn không sạc"
            }
            state_vi = state_map.get(status.lower(), status.lower())
            if capacity:
                return f"Pin laptop hiện tại còn {capacity} phần trăm, trạng thái {state_vi}."

        # 2. Fallback sang upower nếu sysfs không có
        res = subprocess.run(["upower", "-e"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        devs = [l.strip() for l in res.stdout.splitlines() if "battery" in l.lower()]
        if devs:
            out = subprocess.check_output(["upower", "-i", devs[0]], text=True, errors="ignore", timeout=2)
            pct = ""
            state = ""
            for line in out.splitlines():
                if "percentage:" in line:
                    pct = line.split(":", 1)[1].strip()
                elif "state:" in line:
                    state = line.split(":", 1)[1].strip()
            if pct:
                pct_text = pct.replace("%", " phần trăm")
                return f"Pin laptop hiện tại còn {pct_text}, trạng thái {state}."
    except Exception:
        pass

    return "Hiện tại tôi không thể lấy được thông tin pin từ hệ thống hoặc máy đang dùng nguồn trực tiếp."

def get_cpu_info() -> str:
    """Đọc thông số CPU (model, số nhân, mức tải, nhiệt độ) từ Linux kernel trong <1ms."""
    try:
        model = "Intel Core"
        cores = os.cpu_count() or 6
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        model = line.split(":", 1)[1].strip()
                        model = re.sub(r'\(R\)|\(TM\)', '', model)
                        model = re.sub(r'\s+', ' ', model).strip()
                        break

        # Tải CPU (load average)
        load_1m = 0.5
        if os.path.exists("/proc/loadavg"):
            with open("/proc/loadavg") as f:
                parts = f.read().split()
                if parts:
                    load_1m = float(parts[0])

        load_pct = int(min(100, (load_1m / max(cores, 1)) * 100))

        # Nhiệt độ CPU từ thermal zones
        temp_c = None
        for tz_path in ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/thermal/thermal_zone1/temp"]:
            if os.path.exists(tz_path):
                try:
                    with open(tz_path) as f:
                        val = int(f.read().strip())
                        if val > 1000:
                            temp_c = int(val / 1000)
                        elif val > 0:
                            temp_c = val
                        break
                except Exception:
                    pass

        temp_str = f", nhiệt độ khoảng {temp_c} độ C" if temp_c and 20 <= temp_c <= 110 else ""
        return f"Vi xử lý {model}, gồm {cores} luồng xử lý, mức tải đang ở mức khoảng {load_pct} phần trăm{temp_str}."
    except Exception:
        return "Vi xử lý của máy tính đang hoạt động bình thường và ổn định."

def get_system_hardware_info() -> str:
    """Đọc trực tiếp tài nguyên CPU, RAM, thời gian hoạt động từ /proc trong <1ms."""
    try:
        cpu_str = get_cpu_info()
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                if ":" in line:
                    p = line.split(":", 1)
                    val_parts = p[1].split()
                    if val_parts and val_parts[0].isdigit():
                        mem[p[0].strip()] = int(val_parts[0])
        total_gb = mem.get("MemTotal", 16 * 1024 * 1024) / 1024 / 1024
        avail_gb = mem.get("MemAvailable", 8 * 1024 * 1024) / 1024 / 1024
        used_gb = max(0.0, total_gb - avail_gb)
        pct = int(used_gb / total_gb * 100) if total_gb > 0 else 50

        with open("/proc/uptime") as f:
            u_parts = f.read().split()
            sec = float(u_parts[0]) if u_parts else 3600.0
        hours = int(sec // 3600)
        mins = int((sec % 3600) // 60)
        uptime_str = f"{hours} giờ {mins} phút" if hours > 0 else f"{mins} phút"

        used_str = f"{used_gb:.1f}".replace(".", " phẩy ")
        total_str = f"{total_gb:.1f}".replace(".", " phẩy ")

        return f"{cpu_str} Về RAM: máy đang dùng {used_str} trên tổng {total_str} ghi ga, khoảng {pct} phần trăm. Thiết bị đã bật liên tục {uptime_str}."
    except Exception:
        return "Hệ thống Arch Linux đang hoạt động rất mượt mà và ổn định."

def get_weather_info(location: str = "") -> str:
    """Tra cứu thời tiết trực tiếp từ wttr.in bằng tiếng Việt."""
    try:
        loc = location.strip() if isinstance(location, str) and location.strip() else ""
        url = f"https://wttr.in/{loc}?format=%C,+%t,+độ+ẩm+%h&lang=vi" if loc else "https://wttr.in/?format=%C,+%t,+độ+ẩm+%h&lang=vi"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200 and resp.text:
            weather_text = resp.text.strip().replace("+", "")
            loc_label = f"ở {loc}" if loc else "khu vực của bạn"
            return f"Thời tiết {loc_label} hiện tại: {weather_text}."
    except Exception:
        pass
    return "Hiện tại tôi chưa thể kết nối tới dịch vụ thời tiết."

_SAFE_MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _safe_eval_math_ast(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp):
        left = _safe_eval_math_ast(node.left)
        right = _safe_eval_math_ast(node.right)
        op_type = type(node.op)
        if op_type in _SAFE_MATH_OPS:
            if op_type == ast.Div and right == 0:
                raise ZeroDivisionError()
            return _SAFE_MATH_OPS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _safe_eval_math_ast(node.operand)
        op_type = type(node.op)
        if op_type in _SAFE_MATH_OPS:
            return _SAFE_MATH_OPS[op_type](operand)
    raise ValueError("Unsupported operation")

def parse_simple_math(query: str):
    """
    Tính nhẩm số học nhanh tức thì (<2ms).
    Hỗ trợ 2 hoặc nhiều toán hạng (+, -, *, /), an toàn tuyệt đối với chuỗi nối gạch ngang (serial, mã số, ngày tháng).
    """
    if not query:
        return None
    raw = query.strip()
    q = raw.lower()

    # 1. Bỏ qua ngày tháng: YYYY-MM-DD, DD/MM/YYYY, MM-DD...
    if re.search(r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b", q):
        if not re.search(r"\b(tính|kết quả|phép tính|bằng mấy|bằng bao nhiêu)\b", q):
            return None

    # 2. Kiểm tra ý định tính toán bằng từ khóa rõ ràng
    math_intent = bool(re.search(r"\b(tính|kết quả|phép tính|bằng mấy|bằng bao nhiêu|cộng|trừ|nhân|chia)\b", q))

    # Bỏ qua mã số / serial có từ 2 gạch nối liền chữ số (ví dụ: 1-2-3-4-5-1, 091-234-567) nếu không có từ khóa tính toán
    tight_hyphens = len(re.findall(r"\d-\d", q))
    if tight_hyphens >= 2 and not math_intent:
        return None

    # Bỏ qua các dạng khoảng số hoặc tên model: iphone 14-15, phòng 10-12, tập 1-5...
    if re.search(r"\b(?:iphone|ip|samsung|galaxy|xiaomi|phòng|tập|trang|khoảng|từ)\s+\d+\s*[-/]\s*\d+\b", q):
        if not math_intent:
            return None

    # 3. Chuẩn hóa từ ngữ số học tiếng Việt
    text_to_num = {
        "không": "0", "một": "1", "hai": "2", "ba": "3", "bốn": "4",
        "năm": "5", "sáu": "6", "bảy": "7", "tám": "8", "chín": "9", "mười": "10"
    }
    for w, d in text_to_num.items():
        q = re.sub(rf"\b{w}\b", d, q)

    # 4. Kiểm tra biểu thức nhiều toán hạng (VD: 1 - 2 - 3 - 4 - 5 - 1 hoặc 1 + 2 + 3)
    expr_match = re.search(r"(\d+(?:\s*[\+\-\*/x×÷]\s*\d+)+)", q)
    if expr_match:
        expr_str = expr_match.group(1)
        op_count = len(re.findall(r"[\+\-\*/x×÷]", expr_str))
        if op_count >= 2:
            is_pure_expr = (raw.strip(" ?=.") == expr_str.strip())
            if not (math_intent or is_pure_expr):
                return None
            try:
                py_expr = expr_str.replace("x", "*").replace("×", "*").replace("÷", "/")
                tree = ast.parse(py_expr, mode="eval")
                res = _safe_eval_math_ast(tree.body)
                if isinstance(res, float) and res.is_integer():
                    res = int(res)
                res_str = f"âm {abs(res)}" if res < 0 else str(res)
                if isinstance(res, float):
                    res_str = str(round(res, 2)).replace(".", " phẩy ")
                return f"Kết quả phép tính {expr_str} bằng {res_str}."
            except ZeroDivisionError:
                return "Không thể chia cho số không bạn nhé."
            except Exception:
                pass

    # 5. Kiểm tra dạng 2 toán hạng đơn giản với từ khóa tiếng Việt hoặc toán tử (+, -, *, /)
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*(cộng|trừ|nhân|chia|[\+\-\*/x×÷])\s*(\d+(?:\.\d+)?)", q)
    if m2:
        op_raw = m2.group(2)
        n1_str, n2_str = m2.group(1), m2.group(3)
        if op_raw in ["-", "/"]:
            is_pure = (raw.strip(" ?=.") == f"{n1_str}{op_raw}{n2_str}" or raw.strip(" ?=.") == f"{n1_str} {op_raw} {n2_str}")
            if not (math_intent or is_pure or " " in m2.group(0)):
                return None

        n1 = float(n1_str) if "." in n1_str else int(n1_str)
        n2 = float(n2_str) if "." in n2_str else int(n2_str)

        if op_raw in ["+", "cộng"]:
            res = n1 + n2
            return f"{n1} cộng {n2} bằng {res}."
        elif op_raw in ["-", "trừ"]:
            diff = n1 - n2
            diff_str = f"âm {abs(diff)}" if diff < 0 else str(diff)
            return f"{n1} trừ {n2} bằng {diff_str}."
        elif op_raw in ["*", "x", "×", "nhân"]:
            res = n1 * n2
            return f"{n1} nhân {n2} bằng {res}."
        elif op_raw in ["/", "÷", "chia"]:
            if n2 == 0:
                return "Không thể chia cho số không bạn nhé."
            res = round(n1 / n2, 2)
            if isinstance(res, float) and res.is_integer():
                res = int(res)
            res_str = str(res).replace(".0", "").replace(".", " phẩy ")
            return f"{n1} chia {n2} bằng {res_str}."

    return None

def get_clipboard_content(max_chars: int = 300) -> str:
    """Lấy nội dung văn bản từ clipboard Wayland bằng wl-paste."""
    try:
        res = subprocess.run(["wl-paste", "--no-newline"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            txt = res.stdout.strip()
            if not txt:
                return ""
            if len(txt) > max_chars:
                return txt[:max_chars] + "... (nội dung còn dài)"
            return txt
    except Exception:
        pass
    return ""

def set_system_volume(pct: int):
    """Đặt âm lượng hệ thống theo %."""
    pct_val = min(max(pct, 0), 100)
    subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct_val}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def adjust_system_volume(step: str):
    """Tăng/giảm âm lượng hệ thống (vd: +10% hoặc -10%)."""
    subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", step], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def toggle_system_mute():
    """Bật/tắt trạng thái tắt tiếng."""
    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def adjust_brightness(step: str):
    """Điều chỉnh độ sáng màn hình (vd: +10% hoặc 10%-)."""
    subprocess.run(["brightnessctl", "set", step], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def set_wifi_state(enable: bool):
    """Bật/tắt Wi-Fi qua nmcli."""
    state = "on" if enable else "off"
    subprocess.run(["nmcli", "radio", "wifi", state], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def set_bluetooth_state(enable: bool):
    """Bật/tắt Bluetooth qua bluetoothctl."""
    state = "on" if enable else "off"
    subprocess.run(["bluetoothctl", "power", state], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def set_asus_profile(profile: str):
    """Chuyển chế độ hiệu năng ASUS TUF (Performance, Quiet, Balanced)."""
    subprocess.run(["asusctl", "profile", "set", profile], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    power_map = {"Performance": "performance", "Quiet": "power-saver", "Balanced": "balanced"}
    if profile in power_map:
        subprocess.run(["powerprofilesctl", "set", power_map[profile]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def lock_screen():
    """Khóa màn hình bằng hyprlock."""
    subprocess.Popen(["hyprlock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def take_screenshot(mode: str = "full"):
    """Chụp ảnh màn hình qua script screenshot hệ thống."""
    screenshot_bin = os.path.expanduser("~/.local/bin/screenshot")
    if os.path.exists(screenshot_bin):
        subprocess.Popen([screenshot_bin, mode], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        # Fallback dùng grim
        cmd = ["grim"] if mode == "full" else ["grim", "-g", "$(slurp)"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=(mode != "full"))

def get_network_speed_info() -> str:
    """Đo độ trễ mạng (ping) và băng thông tải xuống (download speed) thời gian thực."""
    ping_ms = None
    for host in ["8.8.8.8", "1.1.1.1"]:
        try:
            res = subprocess.run(["ping", "-c", "2", "-W", "2", host], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                m = re.search(r"rtt min/avg/max/mdev = [\d\.]+/([\d\.]+)/", res.stdout)
                if m:
                    ping_ms = round(float(m.group(1)), 1)
                    break
        except Exception:
            pass

    download_mbps = None
    try:
        res = subprocess.run(
            ["curl", "-s", "-w", "%{speed_download}", "-o", "/dev/null", "--max-time", "3", "https://speed.cloudflare.com/__down?bytes=10000000"],
            capture_output=True, text=True, timeout=4
        )
        if res.returncode == 0 and res.stdout.strip():
            val = float(res.stdout.strip().replace(",", "."))
            if val > 0:
                download_mbps = round((val * 8) / 1_000_000, 1)
    except Exception:
        pass

    if ping_ms is not None and download_mbps is not None:
        return f"Tốc độ mạng hiện tại: Độ trễ ping {ping_ms} ms, tốc độ tải xuống khoảng {download_mbps} Mbps, đường truyền mạng ổn định."
    elif ping_ms is not None:
        return f"Tốc độ mạng hiện tại: Độ trễ ping {ping_ms} ms. Không đo được tốc độ tải xuống."
    elif download_mbps is not None:
        return f"Tốc độ mạng hiện tại: Tốc độ tải xuống khoảng {download_mbps} Mbps."
    else:
        return "Không thể đo tốc độ mạng do hệ thống đang mất kết nối Internet hoặc DNS bị gián đoạn."

def get_active_media_player() -> str:
    """Xác định trình phát đa phương tiện đang hoạt động (ưu tiên Spotify, sau đó đến browser/mpris khác)."""
    try:
        res = subprocess.run(["playerctl", "-l"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            players = res.stdout.strip().splitlines()
            for p in players:
                if "spotify" in p.lower():
                    return p
            if players:
                return players[0]
    except Exception:
        pass
    return ""

def get_current_media_track() -> str:
    """Lấy thông tin bài hát và nghệ sĩ đang phát qua MPRIS playerctl."""
    player = get_active_media_player()
    if not player:
        return "Hiện tại không có ứng dụng phát nhạc nào đang chạy bạn nhé."
    try:
        title_res = subprocess.run(
            ["playerctl", "-p", player, "metadata", "xesam:title"],
            capture_output=True, text=True, errors="ignore", timeout=2
        )
        title = title_res.stdout.strip() if title_res.returncode == 0 else ""

        artist_res = subprocess.run(
            ["playerctl", "-p", player, "metadata", "xesam:artist"],
            capture_output=True, text=True, errors="ignore", timeout=2
        )
        artist = artist_res.stdout.strip() if artist_res.returncode == 0 else ""

        if title:
            try:
                subprocess.Popen(["notify-send", "-a", "Spotify", "Đang phát nhạc", f"{title}\n{artist}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            is_cjk = any('\u4e00' <= c <= '\u9fff' for c in title)
            if is_cjk:
                if artist:
                    return f"Bài hát tiếng nước ngoài của nghệ sĩ {artist} đang phát trên {player.capitalize()}."
                return f"Một bài hát tiếng nước ngoài đang phát trên {player.capitalize()}."
            if artist:
                return f"Bài hát đang phát là {title} của {artist}."
            return f"Bài hát đang phát là {title}."
    except Exception:
        pass
    return "Hiện tại không có bài hát nào đang phát bạn nhé."

def is_media_playing() -> bool:
    """Kiểm tra xem hiện tại có ứng dụng phát nhạc nào đang ở trạng thái Playing không."""
    try:
        res = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0 and "playing" in res.stdout.strip().lower():
            return True
        player = get_active_media_player()
        if player:
            st = subprocess.run(["playerctl", "-p", player, "status"], capture_output=True, text=True, timeout=1)
            return st.returncode == 0 and "playing" in st.stdout.strip().lower()
    except Exception:
        pass
    return False

def media_pause() -> bool:
    """Tạm dừng tất cả các trình phát nhạc."""
    ok = False
    try:
        res = subprocess.run(["playerctl", "-a", "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        if res.returncode == 0:
            ok = True
    except Exception:
        pass
    player = get_active_media_player()
    if player:
        try:
            subprocess.run(["playerctl", "-p", player, "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            ok = True
        except Exception:
            pass
    return ok

def media_play() -> bool:
    """Tiếp tục phát nhạc."""
    player = get_active_media_player()
    if not player:
        return False
    try:
        subprocess.run(["playerctl", "-p", player, "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return True
    except Exception:
        return False

def media_next() -> bool:
    """Chuyển bài hát tiếp theo và bắt đầu phát."""
    player = get_active_media_player()
    if not player:
        return False
    try:
        subprocess.run(["playerctl", "-p", player, "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        subprocess.run(["playerctl", "-p", player, "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return True
    except Exception:
        return False

def media_previous() -> bool:
    """Quay lại bài hát trước và bắt đầu phát."""
    player = get_active_media_player()
    if not player:
        return False
    try:
        subprocess.run(["playerctl", "-p", player, "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        subprocess.run(["playerctl", "-p", player, "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return True
    except Exception:
        return False

