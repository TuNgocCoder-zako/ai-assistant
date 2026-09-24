"""
Unit tests kiểm thử Permission Policy & Argument Validator (V2.2).
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.tools.permission import (
    permission_policy,
    argument_validator,
    PermissionLevel,
    TOOL_PERMISSION_MAP
)

class TestPermissionAndValidation(unittest.TestCase):
    def test_permission_levels(self):
        # 1. Read-only tools
        self.assertEqual(permission_policy.get_level("get_system_status"), PermissionLevel.READ_ONLY)
        self.assertEqual(permission_policy.get_level("find_files_or_projects"), PermissionLevel.READ_ONLY)
        self.assertEqual(permission_policy.get_level("read_file_content"), PermissionLevel.READ_ONLY)

        # 2. System action tools
        self.assertEqual(permission_policy.get_level("launch_application"), PermissionLevel.SYSTEM_ACTION)
        self.assertEqual(permission_policy.get_level("control_system_hardware"), PermissionLevel.SYSTEM_ACTION)

        # 3. Sensitive write tools
        self.assertEqual(permission_policy.get_level("check_and_manage_port"), PermissionLevel.SENSITIVE_WRITE)
        self.assertEqual(permission_policy.get_level("close_application"), PermissionLevel.SENSITIVE_WRITE)

        # 4. Terminal execution
        self.assertEqual(permission_policy.get_level("run_terminal_command"), PermissionLevel.TERMINAL_EXEC)

    def test_permission_check_read_only(self):
        allowed, reason, level = permission_policy.check("get_system_status", {})
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.READ_ONLY)

    def test_permission_check_critical_app_kill(self):
        # Ngăn chặn tắt app hệ thống cốt lõi
        for app in ["systemd", "hyprland", "dbus", "pipewire"]:
            allowed, reason, level = permission_policy.check("close_application", {"app_name": app})
            self.assertFalse(allowed)
            self.assertEqual(level, PermissionLevel.DANGEROUS_BLOCKED)
            self.assertIn("Chính sách bảo mật", reason)

        # Cho phép đóng app thông thường
        allowed, reason, level = permission_policy.check("close_application", {"app_name": "chrome"})
        self.assertTrue(allowed)

    def test_permission_check_terminal_commands(self):
        # Lệnh an toàn
        allowed, reason, level = permission_policy.check("run_terminal_command", {"command": "ls -la"})
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.TERMINAL_EXEC)

        # Lệnh nguy hiểm
        for bad_cmd in ["rm -rf /", "rm -r -f /", "mkfs.ext4 /dev/sda1", ":(){ :|:& };:", "shutdown -h now"]:
            allowed, reason, level = permission_policy.check("run_terminal_command", {"command": bad_cmd})
            self.assertFalse(allowed)
            self.assertEqual(level, PermissionLevel.DANGEROUS_BLOCKED)

    def test_argument_validator_paths(self):
        # Ngăn chặn đọc file nhạy cảm
        for sensitive in ["/etc/shadow", "/etc/sudoers", "~/.ssh/id_rsa"]:
            valid, _, err = argument_validator.validate("read_file_content", {"path": sensitive})
            self.assertFalse(valid)
            self.assertIn("nhạy cảm", err)

        # Đường dẫn an toàn
        valid, clean, err = argument_validator.validate("read_file_content", {"path": "~/Projects/voice-ai/README.md"})
        self.assertTrue(valid)
        self.assertNotIn("~", clean["path"])  # Đã expanduser

    def test_argument_validator_port(self):
        # Cổng hợp lệ
        valid, clean, _ = argument_validator.validate("check_and_manage_port", {"port": "8080"})
        self.assertTrue(valid)
        self.assertEqual(clean["port"], 8080)

        # Cổng ngoài phạm vi
        valid, _, err = argument_validator.validate("check_and_manage_port", {"port": 70000})
        self.assertFalse(valid)
        self.assertIn("không hợp lệ", err)

        # Cổng không phải số
        valid, _, err = argument_validator.validate("check_and_manage_port", {"port": "invalid_port"})
        self.assertFalse(valid)
        self.assertIn("phải là số nguyên", err)

if __name__ == "__main__":
    unittest.main()
