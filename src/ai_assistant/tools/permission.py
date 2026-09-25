"""
Permission Policy, Argument Validator & Execution Governance (V2.2).
Cung cấp phân tầng bảo mật cho Local AI OS Agent:
LLM -> Tool Registry -> Permission Policy -> Argument Validator -> Executor -> OS.
"""

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Tuple, Optional

class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"                # Chỉ đọc dữ liệu, an toàn tuyệt đối
    SYSTEM_ACTION = "system_action"        # Thao tác giao diện/phần cứng an toàn (độ sáng, volume, app)
    SENSITIVE_WRITE = "sensitive_write"    # Tác động tiến trình (kill app, free port)
    TERMINAL_EXEC = "terminal_exec"        # Thực thi lệnh terminal (cần kiểm tra câu lệnh)
    DANGEROUS_BLOCKED = "dangerous_blocked" # Bị chặn vĩnh viễn (rm -rf /, format ổ, fork bomb)

# Phân loại mức độ cho từng công cụ trong hệ thống
TOOL_PERMISSION_MAP: dict[str, PermissionLevel] = {
    "get_system_status": PermissionLevel.READ_ONLY,
    "list_hyprland_windows": PermissionLevel.READ_ONLY,
    "find_files_or_projects": PermissionLevel.READ_ONLY,
    "read_file_content": PermissionLevel.READ_ONLY,
    "check_docker_containers": PermissionLevel.READ_ONLY,
    "get_git_repository_status": PermissionLevel.READ_ONLY,
    "search_web_duckduckgo": PermissionLevel.READ_ONLY,
    "search_and_show_image": PermissionLevel.READ_ONLY,

    "control_system_hardware": PermissionLevel.SYSTEM_ACTION,
    "launch_application": PermissionLevel.SYSTEM_ACTION,
    "focus_hyprland_window": PermissionLevel.SYSTEM_ACTION,
    "manage_timer_and_alarm": PermissionLevel.SYSTEM_ACTION,

    "check_and_manage_port": PermissionLevel.SENSITIVE_WRITE,
    "close_application": PermissionLevel.SENSITIVE_WRITE,

    "run_terminal_command": PermissionLevel.TERMINAL_EXEC,
}

# Các mẫu câu lệnh hủy diệt hệ thống hoặc command injection bị chặn tuyệt đối
FORBIDDEN_BASH_PATTERNS = [
    r"\brm\s+(?:-[a-zA-Z0-9-]+\s+)*(?:/(?:\s|$|\*|\.\.)|/home/\.\./|/etc(?:\s|/|$)|/boot(?:\s|/|$)|/sys(?:\s|/|$)|/dev(?:\s|/|$)|/proc(?:\s|/|$)|/root(?:\s|/|$))",
    r"\bmkfs\b",                            # Format phân vùng ổ đĩa
    r"\bdd\s+if=.*of=/dev/(?:sd|nvme|vd)",  # Ghi đè trực tiếp raw block device
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",# Fork bomb làm sập RAM
    r">\s*/dev/(?:sd|nvme|vd)[a-z0-9]*",   # Ghi đè trực tiếp raw partition
    r"\bchmod\s+-R\s+777\s+/(?:\s|$)",      # Phá vỡ phân quyền hệ điều hành
    r"\bchown\s+-R\s+.*\s+/(?:\s|$)",       # Chiếm quyền sở hữu toàn bộ root
    r"\binit\s+0\b|\bshutdown\b|\breboot\b",# Tự ý tắt hoặc khởi động lại máy đột ngột
    r"\|\s*(?:sudo\s+)?(?:ba|z|da|k|c)?sh\b", # Pipe nguy hiểm vào shell interpreter (curl ... | bash)
    r"\bbase64\s+(?:-[a-zA-Z0-9-]*d|--decode)\b.*\|\s*(?:ba|z|da|k|c)?sh\b", # Base64 decode piped to shell
    r"\b(?:curl|wget)\b.*\|\s*(?:sudo\s+)?(?:ba|z|da|k|c)?sh\b", # Tải script từ xa thực thi trực tiếp
    r"\beval\s+[\"'\$`]",                   # Dynamic eval execution
]

# Danh sách các tệp/thư mục nhạy cảm tuyệt đối không được đọc nội dung trực tiếp
RESTRICTED_READ_PATHS = [
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/sudoers",
    "/etc/master.passwd",
    "/proc/kcore",
]

# Các mẫu tên file hoặc thư mục bí mật bị cấm đọc
RESTRICTED_FILE_PATTERNS = [
    r"id_[a-zA-Z0-9]+",         # SSH private keys: id_rsa, id_ed25519, id_ecdsa
    r"\.gnupg\b",               # GPG keys
    r"\.aws/credentials\b",     # AWS secrets
    r"\.docker/config\.json\b", # Docker secrets
    r"\.kube/config\b",         # Kubernetes secrets
    r"\.env(?:\.[a-zA-Z0-9_-]+)?$", # Environment secrets files (.env, .env.prod)
    r"\.(?:pem|key|pfx|p12)$",  # SSL / TLS Private Certificates
]

class ArgumentValidator:
    """
    Tầng kiểm tra và chuẩn hóa tham số đầu vào của mọi công cụ.
    Chống Path Traversal, lỗi kiểu dữ liệu, tràn số.
    """

    @staticmethod
    def validate(tool_name: str, args: dict) -> Tuple[bool, dict, str]:
        """
        Xác thực và làm sạch arguments.
        Trả về: (is_valid, sanitized_args, error_message)
        """
        clean_args = dict(args)

        # 1. Kiểm tra chống Path Traversal và truy cập file nhạy cảm
        for path_key in ["path", "file_path", "target", "search_dir"]:
            if path_key in clean_args and isinstance(clean_args[path_key], str):
                p_val = clean_args[path_key].strip()

                # Ngăn chặn tấn công Null Byte Injection
                if "\0" in p_val:
                    return False, {}, "Ký tự không hợp lệ trong đường dẫn (null byte detected)"

                # Chuẩn hóa triệt để: giải phóng symlink, dot-dot-slash (..) về real path thực tế
                real_p = os.path.realpath(os.path.expanduser(p_val))

                # Kiểm tra cấm truy cập file nhạy cảm hệ thống
                for restricted in RESTRICTED_READ_PATHS:
                    if real_p == restricted or real_p.startswith(restricted + "/"):
                        return False, {}, f"Truy cập tệp nhạy cảm bị từ chối: '{restricted}'"

                # Cấm truy cập raw hardware devices & kernel memory
                if real_p.startswith("/dev/") or real_p.startswith("/proc/kcore"):
                    return False, {}, "Truy cập thiết bị phần cứng thô hoặc bộ nhớ kernel bị từ chối."

                # Kiểm tra các mẫu secret, private keys, .env
                for pat in RESTRICTED_FILE_PATTERNS:
                    if re.search(pat, real_p, re.IGNORECASE):
                        return False, {}, f"Truy cập tệp nhạy cảm/bí mật bị từ chối (pattern: '{pat}')"

                # Đảm bảo đường dẫn đã chuẩn hóa được lưu lại
                clean_args[path_key] = real_p

        # 2. Kiểm tra giới hạn số cổng (Port)
        if "port" in clean_args:
            try:
                p = int(clean_args["port"])
                if p < 1 or p > 65535:
                    return False, {}, f"Cổng mạng không hợp lệ: {p} (phải nằm trong khoảng 1 - 65535)"
                clean_args["port"] = p
            except (ValueError, TypeError):
                return False, {}, f"Cổng mạng phải là số nguyên: {clean_args['port']}"

        # 3. Kiểm tra số dòng đọc file (max_lines)
        if "max_lines" in clean_args:
            try:
                lines = int(clean_args["max_lines"])
                clean_args["max_lines"] = max(1, min(lines, 2000))
            except (ValueError, TypeError):
                clean_args["max_lines"] = 200

        # 4. Kiểm tra lệnh terminal
        if "command" in clean_args:
            if not isinstance(clean_args["command"], str) or not clean_args["command"].strip():
                return False, {}, "Tham số 'command' không được để trống"
            clean_args["command"] = clean_args["command"].strip()

        return True, clean_args, ""

class PermissionPolicy:
    """
    Tầng chính sách phân quyền cho Agent Core.
    Quyết định một yêu cầu thực thi có được phép chạy trên OS hay không.
    """

    def __init__(self, allow_terminal: bool = True):
        self.allow_terminal = allow_terminal

    def get_level(self, tool_name: str) -> PermissionLevel:
        return TOOL_PERMISSION_MAP.get(tool_name, PermissionLevel.SYSTEM_ACTION)

    def check(self, tool_name: str, args: dict) -> Tuple[bool, str, PermissionLevel]:
        """
        Kiểm tra quyền thực thi của công cụ và tham số.
        Trả về: (is_allowed, reason, permission_level)
        """
        level = self.get_level(tool_name)

        # 1. Các công cụ chỉ đọc luôn luôn được phép
        if level == PermissionLevel.READ_ONLY:
            return True, "Thao tác chỉ đọc được phê duyệt tự động.", level

        # 2. Các hành động hệ thống an toàn
        if level == PermissionLevel.SYSTEM_ACTION:
            return True, "Hành động hệ thống tiêu chuẩn được phê duyệt.", level

        # 3. Tác động tiến trình (cần kiểm tra tên app không phải process cốt lõi)
        if level == PermissionLevel.SENSITIVE_WRITE:
            if tool_name == "close_application":
                app_target = str(args.get("app_name", "")).lower()
                critical_apps = ["systemd", "hyprland", "waybar", "dbus", "pipewire", "wireplumber"]
                if any(c in app_target for c in critical_apps):
                    return False, f"Chính sách bảo mật: Không được phép tắt tiến trình hệ thống cốt lõi '{app_target}'.", PermissionLevel.DANGEROUS_BLOCKED

            return True, "Hành động quản lý tiến trình được phê duyệt.", level

        # 4. Kiểm tra quyền thực thi lệnh Terminal (run_terminal_command)
        if level == PermissionLevel.TERMINAL_EXEC:
            if not self.allow_terminal:
                return False, "Chính sách bảo mật: Quyền thực thi lệnh Terminal đang bị vô hiệu hóa.", PermissionLevel.DANGEROUS_BLOCKED

            cmd = args.get("command", "")
            # Chuẩn hóa khử escape / quote obfuscation (vd r\m -rf / hoặc "rm" -rf /)
            normalized_cmd = re.sub(r"['\"\\]", "", cmd)
            for pattern in FORBIDDEN_BASH_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE) or re.search(pattern, normalized_cmd, re.IGNORECASE):
                    return False, f"CHÍNH SÁCH BẢO MẬT TỪ CHỐI: Phát hiện lệnh có nguy cơ phá hoại hệ thống (pattern: {pattern}).", PermissionLevel.DANGEROUS_BLOCKED

            return True, "Lệnh terminal đã qua kiểm duyệt an toàn.", level

        return False, "Công cụ không xác định hoặc không có quyền thực thi.", PermissionLevel.DANGEROUS_BLOCKED

# Instance đơn vị toàn cục
permission_policy = PermissionPolicy()
argument_validator = ArgumentValidator()
