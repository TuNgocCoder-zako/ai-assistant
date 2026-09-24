"""
Integration test: Kịch bản Audit thực tế theo tài liệu đánh giá V3:
'Kiểm tra project Spring Boot -> build -> nếu lỗi thì tìm nguyên nhân -> báo cáo/sửa'
Kiểm tra tính liên kết giữa:
StructuredAgentState -> PermissionPolicy -> ArgumentValidator -> TaskCompletionEvaluator -> AgentTrace.
"""

import sys
import os
import unittest
import json
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.core.agent_state import StructuredAgentState, AgentBudget
from ai_assistant.core.evaluator import task_evaluator
from ai_assistant.tools.registry import tool_registry

class TestSpringBootFlowAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="spring_test_")
        self.java_file = os.path.join(self.test_dir, "UserController.java")
        with open(self.java_file, "w", encoding="utf-8") as f:
            f.write("""package com.example.demo;
import org.springframework.web.bind.annotation.RestController;
// Missing annotation or syntax error
@RestController
public class UserController {
    // Intentionally missing semicolon
    private String name = "test"
}
""")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_spring_boot_multi_step_flow_audit(self):
        goal = "Kiểm tra project Spring Boot của tôi, nếu build lỗi thì tìm nguyên nhân và nói cho tôi biết."
        state = StructuredAgentState(goal=goal, model="qwen2.5-coder:7b", budget=AgentBudget(max_steps=5))

        # Bước 1: Tìm project
        res_find = tool_registry.execute("find_files_or_projects", {"query": "demo"})
        self.assertTrue(res_find["success"])
        state.add_step(
            tool_name="find_files_or_projects",
            arguments={"query": "demo"},
            observation=res_find,
            model_decision="Tìm kiếm thư mục dự án Spring Boot",
            status="success"
        )
        self.assertEqual(state.current_step, 1)

        # Bước 2: Build project (giả lập javac lỗi cú pháp)
        build_cmd = f"javac {self.java_file}"
        res_build = tool_registry.execute("run_terminal_command", {"command": build_cmd})
        self.assertFalse(res_build["result"]["success"])  # Có lỗi thiếu dấu chấm phẩy
        self.assertIn("error: ';' expected", res_build["result"]["stderr"])

        # Evaluator phát hiện lỗi build và hướng dẫn tìm nguyên nhân
        eval_build = task_evaluator.evaluate_step(
            goal=goal,
            tool_name="run_terminal_command",
            args={"command": build_cmd},
            observation=res_build["result"],
            step_index=state.current_step + 1,
            max_steps=5
        )
        self.assertFalse(eval_build.is_goal_met)
        self.assertTrue(eval_build.should_continue)
        self.assertIn("tìm nguyên nhân", eval_build.reason)

        state.add_step(
            tool_name="run_terminal_command",
            arguments={"command": build_cmd},
            observation=res_build,
            model_decision="Chạy lệnh compile kiểm tra project",
            status="failed",
            error=res_build["result"]["stderr"]
        )
        self.assertEqual(state.current_step, 2)

        # Bước 3: Đọc file code bị lỗi để tìm nguyên nhân chính xác
        res_read = tool_registry.execute("read_file_content", {"path": self.java_file, "max_lines": 50})
        self.assertTrue(res_read["success"])
        self.assertIn("UserController", res_read["result"])

        state.add_step(
            tool_name="read_file_content",
            arguments={"path": self.java_file},
            observation={"lines_read": 10},
            model_decision="Đọc nội dung UserController.java để xác định dòng lỗi cú pháp",
            status="success"
        )
        self.assertEqual(state.current_step, 3)

        # Hoàn tất tác vụ với câu trả lời chẩn đoán
        final_answer = "Project Spring Boot bị lỗi cú pháp thiếu dấu chấm phẩy tại tệp UserController.java."
        trace_file = state.complete(final_response=final_answer, status="success")

        # Kiểm tra tính toàn vẹn của Trace & Cây thực thi
        self.assertTrue(os.path.exists(trace_file))
        tree_text = state.render_tree()
        self.assertIn("Task: Kiểm tra project Spring Boot", tree_text)
        self.assertIn("[Step 1] Decision: Tìm kiếm thư mục dự án", tree_text)
        self.assertIn("[Step 2] Decision: Chạy lệnh compile kiểm tra project", tree_text)
        self.assertIn("[Step 3] Decision: Đọc nội dung UserController.java", tree_text)
        self.assertIn("Final Result (success", tree_text)

        # Đọc lại trace json
        with open(trace_file, "r", encoding="utf-8") as f:
            trace_json = json.load(f)
            self.assertEqual(trace_json["steps_count"], 3)
            self.assertEqual(trace_json["final_status"], "success")
            self.assertTrue(trace_json["completion"])

if __name__ == "__main__":
    unittest.main()
