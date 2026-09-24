"""
Unit tests kiểm thử TaskCompletionEvaluator & Retry logic (V2.2).
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.core.evaluator import task_evaluator, EvaluationResult

class TestTaskCompletionEvaluator(unittest.TestCase):
    def test_evaluate_build_success(self):
        # Mục tiêu: "Kiểm tra project Spring Boot nếu build lỗi thì tìm nguyên nhân"
        # Khi build thành công:
        res = task_evaluator.evaluate_step(
            goal="Mở IntelliJ, kiểm tra project Spring Boot của tôi, nếu build lỗi thì tìm nguyên nhân",
            tool_name="run_terminal_command",
            args={"command": "./mvnw clean compile"},
            observation={"success": True, "stdout": "BUILD SUCCESS"},
            step_index=2,
            max_steps=8
        )
        self.assertTrue(res.is_goal_met)
        self.assertFalse(res.should_continue)
        self.assertIn("thành công", res.reason)

    def test_evaluate_build_failure_triggers_diagnosis(self):
        # Khi build thất bại:
        res = task_evaluator.evaluate_step(
            goal="Mở IntelliJ, kiểm tra project Spring Boot của tôi, nếu build lỗi thì tìm nguyên nhân",
            tool_name="run_terminal_command",
            args={"command": "./mvnw clean compile"},
            observation={"success": False, "stderr": "Compilation failure: cannot find symbol"},
            step_index=2,
            max_steps=8
        )
        self.assertFalse(res.is_goal_met)
        self.assertTrue(res.should_continue)  # Cần tiếp tục để tìm nguyên nhân!
        self.assertIn("tìm nguyên nhân", res.reason)
        self.assertIn("tìm nguyên nhân", res.suggested_feedback or "")

    def test_evaluate_recoverable_error_triggers_retry(self):
        # Lỗi tham số thiếu hoặc sai:
        res = task_evaluator.evaluate_step(
            goal="Kiểm tra trạng thái dự án",
            tool_name="find_files_or_projects",
            args={},
            observation={"success": False, "error": "Lỗi xác thực tham số: không tìm thấy"},
            step_index=1,
            max_steps=8
        )
        self.assertFalse(res.is_goal_met)
        self.assertTrue(res.should_retry)
        self.assertTrue(res.should_continue)

    def test_evaluate_security_block_aborts(self):
        # Lỗi do chính sách bảo mật chặn:
        res = task_evaluator.evaluate_step(
            goal="Thử xóa hệ thống",
            tool_name="run_terminal_command",
            args={"command": "rm -rf /"},
            observation={"success": False, "error": "CHÍNH SÁCH BẢO MẬT TỪ CHỐI"},
            step_index=1,
            max_steps=8
        )
        self.assertFalse(res.is_goal_met)
        self.assertFalse(res.should_continue)
        self.assertFalse(res.should_retry)
        self.assertIn("bảo mật", res.reason)

if __name__ == "__main__":
    unittest.main()
