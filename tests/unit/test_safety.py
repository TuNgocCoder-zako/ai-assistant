"""
Unit tests kiểm thử lớp bảo vệ Safety Guard (V2.1).
Ngăn chặn các lệnh bash phá hoại hệ thống (rm -rf /, mkfs, fork bomb, raw disk writes).
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.tools.registry import run_terminal_command, FORBIDDEN_COMMAND_PATTERNS

class TestSafetyGuard(unittest.TestCase):
    def test_safe_commands(self):
        # Lệnh an toàn hợp lệ
        res = run_terminal_command("echo 'Safety Guard Active'")
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("Safety Guard Active", res["stdout"])

    def test_forbidden_rm_rf(self):
        # rm -rf / hoặc biến thể
        for cmd in ["rm -rf /", "rm -r -f /", "rm -rf /home/../", "sudo rm -rf / "]:
            res = run_terminal_command(cmd)
            self.assertFalse(res["success"])
            self.assertIn("LỆNH BỊ CHẶN", res["stderr"])

    def test_forbidden_mkfs(self):
        # mkfs format ổ cứng
        for cmd in ["mkfs.ext4 /dev/nvme0n1p1", "mkfs /dev/sda1"]:
            res = run_terminal_command(cmd)
            self.assertFalse(res["success"])
            self.assertIn("LỆNH BỊ CHẶN", res["stderr"])

    def test_forbidden_raw_disk_write(self):
        # dd ghi đè raw disk
        res = run_terminal_command("dd if=/dev/zero of=/dev/sda bs=1M")
        self.assertFalse(res["success"])
        self.assertIn("LỆNH BỊ CHẶN", res["stderr"])

    def test_forbidden_fork_bomb(self):
        # Fork bomb
        res = run_terminal_command(":(){ :|:& };:")
        self.assertFalse(res["success"])
        self.assertIn("LỆNH BỊ CHẶN", res["stderr"])

if __name__ == "__main__":
    unittest.main()
