"""
Integration tests kiểm thử chu trình End-to-End của Voice AI V2.1.
Kiểm tra luồng: NLU Fast-Path -> Complex Intent Decision -> Agent Orchestrator State & Trace.
"""

import sys
import os
import unittest
import glob
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.core.nlu import fast_path_nlu
from ai_assistant.core.orchestrator import agent_orchestrator
from ai_assistant.core.agent_state import StructuredAgentState, AgentBudget

class TestEndToEndIntegration(unittest.TestCase):
    def setUp(self):
        self.app_index = {
            "intellij idea": {"name": "IntelliJ IDEA", "exec": "idea", "desktop_id": "idea.desktop"},
            "visual studio code": {"name": "Visual Studio Code", "exec": "code", "desktop_id": "code.desktop"}
        }

    def test_fast_path_bypasses_llm(self):
        # Yêu cầu đơn giản phải được NLU Fast-Path giải quyết ngay (< 5ms), không cần gọi LLM
        handled, reply = fast_path_nlu("mấy giờ rồi", self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Bây giờ là", reply)

    def test_complex_request_detected_and_routed_to_agent(self):
        # Yêu cầu phức tạp phải được đánh dấu is_complex_request
        query = "Mở IntelliJ, kiểm tra project Spring Boot của tôi, nếu build lỗi thì tìm nguyên nhân."
        self.assertTrue(agent_orchestrator.is_complex_request(query))

    def test_agent_state_lifecycle_and_trace_export(self):
        # Kiểm tra vòng đời hoàn chỉnh của StructuredAgentState: Tạo -> Ghi Step -> Hoàn tất -> Xuất Trace JSON
        budget = AgentBudget(max_steps=5, max_runtime_sec=10.0)
        state = StructuredAgentState(
            goal="Kiểm tra port 8080 và trạng thái hệ thống",
            model="qwen2.5:3b",
            budget=budget
        )
        
        # Step 1: Kiểm tra port
        state.add_step(
            tool_name="check_and_manage_port",
            arguments={"port": 8080, "action": "check"},
            observation={"port": 8080, "status": "free"},
            duration_ms=4.2,
            status="success"
        )
        self.assertEqual(state.current_step, 1)

        # Step 2: System status
        state.add_step(
            tool_name="get_system_status",
            arguments={"metric": "ram"},
            observation={"ram": "6.2GB / 15.3GB"},
            duration_ms=8.5,
            status="success"
        )
        self.assertEqual(state.current_step, 2)

        # Hoàn thành
        trace_file = state.complete("Cổng 8080 đang trống, RAM còn 60%.", status="success")
        self.assertTrue(os.path.exists(trace_file))

        # Đọc lại trace file để xác minh tính toàn vẹn dữ liệu
        with open(trace_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["goal"], "Kiểm tra port 8080 và trạng thái hệ thống")
            self.assertEqual(data["final_status"], "success")
            self.assertEqual(len(data["steps"]), 2)
            self.assertEqual(data["steps"][0]["tool_name"], "check_and_manage_port")
            self.assertEqual(data["steps"][1]["tool_name"], "get_system_status")

if __name__ == "__main__":
    unittest.main()
