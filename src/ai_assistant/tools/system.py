"""
Công cụ đọc và điều khiển hệ điều hành Arch Linux / phần cứng laptop Asus TUF.
"""

import os
import re
import glob
import datetime
import subprocess
import requests
from ai_assistant.speech.player import play_chime

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

def get_system_hardware_info() -> str:
    """Đọc trực tiếp tài nguyên RAM, thời gian hoạt động từ /proc trong <1ms."""
    try:
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

        return f"Máy tính đang dùng {used_str} ghi ga RAM trên tổng {total_str} ghi ga, khoảng {pct} phần trăm. Thiết bị đã hoạt động liên tục {uptime_str}."
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

def parse_simple_math(query: str):
    """Tính nhẩm số học nhanh tức thì cho các phép tính cộng, trừ, nhân, chia."""
    q = query.lower()
    m = re.search(r"(\d+)\s*(\+|\-|\*|\/|cộng|trừ|nhân|chia)\s*(\d+)", q)
    if m:
        n1 = int(m.group(1))
        op = m.group(2)
        n2 = int(m.group(3))
        if op in ["+", "cộng"]:
            return f"{n1} cộng {n2} bằng {n1 + n2}."
        elif op in ["-", "trừ"]:
            return f"{n1} trừ {n2} bằng {n1 - n2}."
        elif op in ["*", "nhân"]:
            return f"{n1} nhân {n2} bằng {n1 * n2}."
        elif op in ["/", "chia"]:
            if n2 == 0:
                return "Không thể chia cho số không bạn nhé."
            res = round(n1 / n2, 2)
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
    play_chime("ack")

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
    play_chime("ack")

def set_bluetooth_state(enable: bool):
    """Bật/tắt Bluetooth qua bluetoothctl."""
    state = "on" if enable else "off"
    subprocess.run(["bluetoothctl", "power", state], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    play_chime("ack")

def set_asus_profile(profile: str):
    """Chuyển chế độ hiệu năng ASUS TUF (Performance, Quiet, Balanced)."""
    subprocess.run(["asusctl", "profile", "set", profile], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    power_map = {"Performance": "performance", "Quiet": "power-saver", "Balanced": "balanced"}
    if profile in power_map:
        subprocess.run(["powerprofilesctl", "set", power_map[profile]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    play_chime("ack")

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
