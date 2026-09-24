"""
Universal Tool Registry cho Local AI OS Agent.
Chuẩn hóa mọi công cụ hệ thống, terminal, quản lý file, app, window thành Ollama JSON Schema.
"""

import os
import re
import shlex
import inspect
import subprocess
import json
import difflib
from typing import Callable, Any
from pathlib import Path

from ai_assistant.config import BASE_DIR, PROTECTED_CLASSES
from ai_assistant.tools import system, apps, dev, web, timer

# Danh sách các lệnh nguy hiểm bị chặn để bảo vệ hệ điều hành
FORBIDDEN_COMMAND_PATTERNS = [
    r"\brm\s+(?:-[a-zA-Z0-9-]+\s+)*(?:/(?:\s|$|\*|\.\.)|/home/\.\./|/etc(?:\s|/|$)|/boot(?:\s|/|$)|/sys(?:\s|/|$)|/dev(?:\s|/|$)|/proc(?:\s|/|$)|/root(?:\s|/|$))", # rm nguy hiểm vào root/system
    r"\bmkfs\b",                            # Định dạng phân vùng ổ đĩa
    r"\bdd\s+if=.*of=/dev/(?:sd|nvme|vd)",  # Ghi đè trực tiếp ổ cứng vật lý
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",# Fork bomb
    r">\s*/dev/(?:sd|nvme|vd)[a-z0-9]*",   # Chuyển hướng ghi đè raw disk
    r"\bchmod\s+-R\s+777\s+/(?:\s|$)",      # Phá vỡ phân quyền root
]

class Tool:
    def __init__(self, name: str, description: str, func: Callable, parameters: dict):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

COMMON_TOOL_ALIASES = {
    "search_project": "find_files_or_projects",
    "find_project": "find_files_or_projects",
    "search_files": "find_files_or_projects",
    "find_files": "find_files_or_projects",
    "run_command": "run_terminal_command",
    "exec_command": "run_terminal_command",
    "terminal": "run_terminal_command",
    "bash": "run_terminal_command",
    "open_app": "launch_application",
    "launch_app": "launch_application",
    "close_app": "close_application",
    "kill_app": "close_application",
    "check_port": "check_and_manage_port",
    "manage_port": "check_and_manage_port",
    "read_file": "read_file_content",
    "git_status": "get_git_repository_status",
    "docker_ps": "check_docker_containers",
    "system_status": "get_system_status",
}

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str = None, description: str = None):
        """Decorator đăng ký hàm thành công cụ có JSON schema tương thích Ollama."""
        def decorator(func: Callable):
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "").strip()
            
            sig = inspect.signature(func)
            properties = {}
            required = []

            type_map = {
                str: "string",
                int: "integer",
                float: "number",
                bool: "boolean",
                list: "array",
                dict: "object",
            }

            for param_name, param in sig.parameters.items():
                if param_name in ["self", "app_index"]:
                    continue
                p_type = type_map.get(param.annotation, "string")
                properties[param_name] = {
                    "type": p_type,
                    "description": f"Tham số {param_name}"
                }
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            parameters_schema = {
                "type": "object",
                "properties": properties,
                "required": required
            }

            self._tools[tool_name] = Tool(
                name=tool_name,
                description=tool_desc,
                func=func,
                parameters=parameters_schema
            )
            return func
        return decorator

    def get_schemas(self) -> list[dict]:
        """Lấy danh sách JSON schema của toàn bộ công cụ đã đăng ký."""
        return [t.to_schema() for t in self._tools.values()]

    def get_relevant_schemas(self, query: str) -> list[dict]:
        """
        Lọc động danh sách công cụ liên quan nhất đến câu lệnh người dùng (Tool Retrieval),
        giúp mô hình cục bộ tập trung tối đa, giảm thiểu context size và triệt tiêu ảo giác.
        """
        q = query.lower()
        selected = ["run_terminal_command"]
        
        if any(k in q for k in ["tìm", "file", "thư mục", "project", "dự án", "đọc", "code", "spring", "build", "maven", "gradle"]):
            selected.extend(["find_files_or_projects", "read_file_content"])
        if any(k in q for k in ["mở", "bật", "tắt", "đóng", "cửa sổ", "app", "ứng dụng", "intellij", "code", "terminal", "zalo", "chrome", "firefox"]):
            selected.extend(["launch_application", "close_application", "list_open_windows"])
        if any(k in q for k in ["port", "cổng", "8080", "fuser", "kẹt"]):
            selected.append("check_and_manage_port")
        if any(k in q for k in ["docker", "container"]):
            selected.append("check_docker_containers")
        if any(k in q for k in ["git", "commit", "push", "branch", "nhánh"]):
            selected.append("get_git_repository_status")
        if any(k in q for k in ["pin", "battery", "ram", "cpu", "wifi", "bluetooth", "độ sáng", "âm lượng", "loa", "quạt", "asus", "turbo"]):
            selected.extend(["control_system_hardware", "get_system_status"])
        if any(k in q for k in ["tìm trên mạng", "tra cứu mạng", "google", "duckduckgo", "tin tức"]):
            selected.append("search_web_duckduckgo")
        if any(k in q for k in ["ảnh", "hình", "xem ảnh"]):
            selected.append("search_and_show_image")
        if any(k in q for k in ["hẹn giờ", "báo thức", "phút", "chuông"]):
            selected.append("manage_timer_and_alarm")

        res = []
        seen = set()
        for name in selected:
            if name not in seen and name in self._tools:
                seen.add(name)
                res.append(self._tools[name].to_schema())
                
        if len(res) <= 1:
            for fallback in ["find_files_or_projects", "launch_application", "get_system_status"]:
                if fallback in self._tools and fallback not in seen:
                    seen.add(fallback)
                    res.append(self._tools[fallback].to_schema())
        return res

    def execute(self, name: str, arguments: dict = None) -> dict:
        """Thực thi công cụ an toàn và trả về kết quả cấu trúc chuẩn."""
        arguments = arguments or {}
        
        # 1. Tìm công cụ (exact match -> alias match -> normalized match -> difflib fuzzy match)
        tool = self._tools.get(name)
        if not tool and name in COMMON_TOOL_ALIASES:
            tool = self._tools.get(COMMON_TOOL_ALIASES[name])

        if not tool:
            norm_name = re.sub(r"[\s_-]+", "", name.lower())
            for t_k, t_v in self._tools.items():
                if re.sub(r"[\s_-]+", "", t_k.lower()) == norm_name:
                    tool = t_v
                    break

        if not tool:
            close_matches = difflib.get_close_matches(name, list(self._tools.keys()) + list(COMMON_TOOL_ALIASES.keys()), n=1, cutoff=0.5)
            if close_matches:
                m_name = close_matches[0]
                tool = self._tools.get(COMMON_TOOL_ALIASES.get(m_name, m_name))

        if not tool:
            return {"success": False, "error": f"Không tìm thấy công cụ '{name}'."}

        # 2. Lọc & ánh xạ arguments theo signature hàm
        try:
            sig = inspect.signature(tool.func)
            filtered_args = {k: v for k, v in arguments.items() if k in sig.parameters}

            # Ánh xạ alias thông minh cho các tham số phổ biến đề phòng LLM gọi lệch tên tham số
            for target_param in sig.parameters:
                if target_param not in filtered_args:
                    if target_param == "query":
                        for a in ["search", "keyword", "name", "target", "project_name", "project", "folder", "file_name", "filename"]:
                            if a in arguments:
                                filtered_args["query"] = arguments[a]
                                break
                    elif target_param == "command":
                        for a in ["cmd", "shell", "bash", "instruction"]:
                            if a in arguments:
                                filtered_args["command"] = arguments[a]
                                break
                    elif target_param == "app_name":
                        for a in ["app", "name", "application", "appname"]:
                            if a in arguments:
                                filtered_args["app_name"] = arguments[a]
                                break
                    elif target_param == "path":
                        for a in ["file", "file_path", "target", "filepath"]:
                            if a in arguments:
                                filtered_args["path"] = arguments[a]
                                break
                    elif target_param == "port":
                        for a in ["cổng", "port_number", "target_port"]:
                            if a in arguments:
                                filtered_args["port"] = int(arguments[a]) if str(arguments[a]).isdigit() else arguments[a]
                                break
                    elif target_param == "action":
                        for a in ["act", "mode", "operation"]:
                            if a in arguments:
                                filtered_args["action"] = arguments[a]
                                break

            res = tool.func(**filtered_args)
            return {"success": True, "result": res}
        except Exception as e:
            return {"success": False, "error": f"Lỗi khi thực thi '{name}': {str(e)}"}

# Khởi tạo Registry toàn cục
tool_registry = ToolRegistry()

# ================= 1. Công cụ Shell & Terminal Đa Năng =================

@tool_registry.register(
    name="run_terminal_command",
    description="Thực thi một lệnh terminal bash an toàn trên Arch Linux (vd: git, docker, npm, python, cargo, ls, v.v.), trả về stdout, stderr và exit_code."
)
def run_terminal_command(command: str, cwd: str = "") -> dict:
    cmd_clean = command.strip()
    # Kiểm tra an toàn: ngăn chặn lệnh phá hoại hệ thống
    for pattern in FORBIDDEN_COMMAND_PATTERNS:
        if re.search(pattern, cmd_clean, re.IGNORECASE):
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "LỆNH BỊ CHẶN: Phát hiện lệnh có nguy cơ gây mất an toàn hệ thống.",
                "success": False
            }

    work_dir = os.path.expanduser(cwd) if cwd else os.getcwd()
    if not os.path.exists(work_dir):
        work_dir = os.getcwd()

    try:
        proc = subprocess.run(
            cmd_clean,
            shell=True,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=35
        )
        # Giới hạn output nếu quá dài để không làm tràn context của mô hình
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        if len(out) > 2500:
            out = out[:1200] + "\n... [Output bị cắt bớt do quá dài] ...\n" + out[-1200:]
        if len(err) > 2500:
            err = err[:1200] + "\n... [Stderr bị cắt bớt do quá dài] ...\n" + err[-1200:]

        return {
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
            "success": proc.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "stdout": "", "stderr": "Lệnh thực thi quá thời gian cho phép (35s timeout).", "success": False}
    except Exception as e:
        return {"exit_code": 1, "stdout": "", "stderr": str(e), "success": False}

# ================= 2. Công cụ Quản lý File & Tìm kiếm Dự án =================

@tool_registry.register(
    name="find_files_or_projects",
    description="Tìm kiếm thư mục dự án hoặc tệp tin trong hệ thống theo từ khóa (mặc định tìm trong ~/Projects)."
)
def find_files_or_projects(query: str = "", search_dir: str = "~/Projects", **kwargs) -> list[str]:
    target_root = Path(os.path.expanduser(search_dir))
    if not target_root.exists():
        target_root = Path.home()

    raw_q = query or kwargs.get("search") or kwargs.get("project_name") or kwargs.get("name") or kwargs.get("keyword") or ""
    q_lower = raw_q.lower().strip()
    matches = []
    
    # 1. Tìm các thư mục trước (Project directories)
    for p in target_root.rglob("*"):
        if any(ignored in p.parts for ignored in [".git", "node_modules", "target", ".idea", "venv", "__pycache__"]):
            continue
        if q_lower in p.name.lower():
            matches.append(str(p))
            if len(matches) >= 8:
                break
    return matches

@tool_registry.register(
    name="read_file_content",
    description="Đọc nội dung tệp tin văn bản (code, log, config) với giới hạn số dòng tối đa."
)
def read_file_content(path: str, max_lines: int = 50) -> str:
    f_path = os.path.expanduser(path)
    if not os.path.exists(f_path):
        return f"Không tìm thấy tệp tin: {path}"
    try:
        with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [f.readline() for _ in range(max_lines)]
        return "".join(lines)
    except Exception as e:
        return f"Lỗi đọc tệp tin: {e}"

# ================= 3. Công cụ Điều khiển Ứng dụng & Cửa sổ Hyprland =================

@tool_registry.register(
    name="launch_application",
    description="Khởi chạy một ứng dụng desktop theo tên (vd: IntelliJ, VS Code, Chrome, Kitty, Zalo, Spotify...)."
)
def launch_application(app_name: str) -> dict:
    app_index = apps.build_app_index()
    matched = apps.match_app(app_name, app_index)
    if not matched:
        matched = apps.find_app_in_text(app_name, app_index)
    if matched:
        ok = apps.launch_desktop_app(matched)
        return {"launched": ok, "app_name": matched.get("name", app_name)}
    # Thử chạy trực tiếp lệnh nếu là binary có sẵn trong PATH
    if subprocess.run(["which", app_name.split()[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.Popen(app_name.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"launched": True, "app_name": app_name}
    return {"launched": False, "error": f"Không tìm thấy ứng dụng '{app_name}' trên hệ thống."}

@tool_registry.register(
    name="close_application",
    description="Đóng ứng dụng theo tên hoặc đóng cửa sổ đang làm việc hiện tại."
)
def close_application(app_name: str = "") -> dict:
    if not app_name or app_name in ["cửa sổ này", "hiện tại"]:
        ok, msg = apps.close_active_window()
        return {"success": ok, "message": msg}
    ok, msg = apps.close_specific_app(app_name)
    return {"success": ok, "message": msg}

@tool_registry.register(
    name="list_open_windows",
    description="Liệt kê danh sách tất cả các cửa sổ GUI đang mở trên màn hình Hyprland."
)
def list_open_windows() -> list[dict]:
    clients = apps.get_hyprland_clients()
    return [{
        "class": c.get("class"),
        "title": c.get("title"),
        "workspace": c.get("workspace", {}).get("name"),
        "pid": c.get("pid")
    } for c in clients if c.get("class") not in PROTECTED_CLASSES]

# ================= 4. Công cụ Lập trình viên & Tiến trình =================

@tool_registry.register(
    name="check_and_manage_port",
    description="Kiểm tra trạng thái cổng mạng TCP hoặc giải phóng cổng bị kẹt (action: 'check' hoặc 'kill')."
)
def check_and_manage_port(port: int, action: str = "check") -> str:
    if action == "kill":
        return dev.kill_port_process(port)
    return dev.check_port_status(port)

@tool_registry.register(
    name="check_docker_containers",
    description="Kiểm tra danh sách Docker containers đang chạy trên máy tính."
)
def check_docker_containers() -> str:
    return dev.check_docker_containers()

@tool_registry.register(
    name="get_git_repository_status",
    description="Kiểm tra nhánh git và các file thay đổi chưa commit của một thư mục dự án."
)
def get_git_repository_status(target_dir: str = "") -> str:
    return dev.get_git_status_summary(target_dir if target_dir else None)

# ================= 5. Công cụ Điều khiển Phần cứng & Hệ thống =================

@tool_registry.register(
    name="control_system_hardware",
    description="Điều khiển phần cứng: 'volume' (0-100, +10%, -10%, mute), 'brightness' (+10%, 10%-), 'wifi' (on/off), 'bluetooth' (on/off), 'asus_profile' (Performance/Balanced/Quiet), 'lock_screen', 'screenshot'."
)
def control_system_hardware(action: str, value: str = "") -> str:
    act = action.lower().strip()
    if act == "volume":
        if value.isdigit():
            system.set_system_volume(int(value))
            return f"Đã đặt âm lượng ở mức {value}%."
        elif value in ["+10%", "up", "tăng"]:
            system.adjust_system_volume("+10%")
            return "Đã tăng âm lượng."
        elif value in ["-10%", "down", "giảm"]:
            system.adjust_system_volume("-10%")
            return "Đã giảm âm lượng."
        elif value in ["mute", "toggle"]:
            system.toggle_system_mute()
            return "Đã chuyển đổi trạng thái tắt tiếng."
    elif act == "brightness":
        system.adjust_brightness(value if value else "+10%")
        return "Đã điều chỉnh độ sáng màn hình."
    elif act == "wifi":
        system.set_wifi_state(value.lower() in ["on", "true", "bật", "1"])
        return f"Đã {'bật' if value in ['on', 'true', 'bật'] else 'tắt'} Wi-Fi."
    elif act == "bluetooth":
        system.set_bluetooth_state(value.lower() in ["on", "true", "bật", "1"])
        return f"Đã {'bật' if value in ['on', 'true', 'bật'] else 'tắt'} Bluetooth."
    elif act == "asus_profile":
        prof = value.capitalize() if value else "Balanced"
        system.set_asus_profile(prof)
        return f"Đã chuyển cấu hình hiệu năng ASUS sang {prof}."
    elif act == "lock_screen":
        system.lock_screen()
        return "Đã khóa màn hình."
    elif act == "screenshot":
        system.take_screenshot("region" if "vùng" in value else "full")
        return "Đã chụp ảnh màn hình."
    return f"Không nhận diện được hành động phần cứng: {action}"

@tool_registry.register(
    name="get_system_status",
    description="Đọc thông tin trạng thái máy tính: 'battery', 'ram', 'time', 'date', 'weather'."
)
def get_system_status(metric: str = "all", location: str = "") -> str:
    m = metric.lower()
    if "pin" in m or "battery" in m:
        return system.get_battery_info()
    if "ram" in m or "hardware" in m or "cpu" in m:
        return system.get_system_hardware_info()
    if "thời tiết" in m or "weather" in m:
        return system.get_weather_info(location)
    if "giờ" in m or "time" in m:
        return system.get_vietnamese_time()
    if "ngày" in m or "date" in m:
        return system.get_vietnamese_date()
    # Mặc định kết hợp pin & ram
    return f"{system.get_battery_info()} {system.get_system_hardware_info()}"

# ================= 6. Công cụ Tra cứu Web & Media =================

@tool_registry.register(
    name="search_web_duckduckgo",
    description="Tra cứu thông tin tóm tắt trên internet bằng công cụ tìm kiếm DuckDuckGo."
)
def search_web_duckduckgo(query: str) -> str:
    res = web.search_duckduckgo_summary(query, max_results=3)
    return res if res else "Không tìm thấy thông tin trên mạng."

@tool_registry.register(
    name="search_and_show_image",
    description="Tìm kiếm một bức ảnh trên web theo từ khóa, tải về ~/Pictures và tự động mở lên màn hình."
)
def search_and_show_image(query: str) -> str:
    ok, msg = web.search_and_display_image(query)
    return msg

@tool_registry.register(
    name="manage_timer_and_alarm",
    description="Quản lý hẹn giờ và báo thức: action='timer' (minutes, label), action='alarm' (hour, minute, label), action='check', action='cancel'."
)
def manage_timer_and_alarm(action: str, minutes: float = 0, hour: int = 0, minute: int = 0, label: str = "") -> str:
    act = action.lower()
    if act == "timer" and minutes > 0:
        return timer.timer_manager.add_timer(minutes, label)
    if act == "alarm":
        return timer.timer_manager.add_alarm(hour, minute, label)
    if act == "cancel":
        return timer.timer_manager.cancel_all()
    return timer.timer_manager.check_timers()
