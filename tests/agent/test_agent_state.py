"""
Unit tests kiểm thử StructuredAgentState, AgentBudget và Stall Detection (V2.1).
"""

import sys
import os
import unittest
import time
import glob

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.core.agent_state import StructuredAgentState, AgentBudget, AgentStep

class TestAgentState(unittest.TestCase):
    def test_state_creation_and_steps(self):
        state = StructuredAgentState(goal="Kiểm tra hệ thống", model="qwen2.5:3b")
        self.assertEqual(state.goal, "Kiểm tra hệ thống")
        self.assertEqual(state.model, "qwen2.5:3b")
        self.assertEqual(state.current_step, 0)
        self.assertEqual(len(state.steps), 0)

        step = state.add_step(
            tool_name="get_system_status",
            arguments={"metric": "all"},
            observation={"cpu": "15%", "ram": "45%"},
            duration_ms=12.5,
            status="success"
        )
        self.assertEqual(state.current_step, 1)
        self.assertEqual(len(state.steps), 1)
        self.assertEqual(step.tool_name, "get_system_status")
        self.assertEqual(step.duration_ms, 12.5)

    def test_stall_detection(self):
        budget = AgentBudget(max_consecutive_identical_calls=2)
        state = StructuredAgentState(goal="Test loop", model="test", budget=budget)

        # Lần gọi 1
        state.add_step("check_and_manage_port", {"port": 8080}, {"result": "busy"})
        self.assertFalse(state.is_stalled("check_and_manage_port", {"port": 8080}))

        # Lần gọi 2 giống hệt -> Kích hoạt Stall
        state.add_step("check_and_manage_port", {"port": 8080}, {"result": "busy"})
        self.assertTrue(state.is_stalled("check_and_manage_port", {"port": 8080}))

        # Tham số khác -> Không stall
        self.assertFalse(state.is_stalled("check_and_manage_port", {"port": 9000}))

    def test_budget_exceeded(self):
        budget = AgentBudget(max_steps=3, max_runtime_sec=0.1, max_tool_calls=2)
        state = StructuredAgentState(goal="Test budget", model="test", budget=budget)

        # Chưa vượt
        exceeded, _ = state.check_budget_exceeded()
        self.assertFalse(exceeded)

        # Vượt quá timeout
        time.sleep(0.15)
        exceeded, reason = state.check_budget_exceeded()
        self.assertTrue(exceeded)
        self.assertIn("Quá thời gian cho phép", reason)

    def test_save_trace(self):
        state = StructuredAgentState(goal="Test trace", model="qwen2.5:3b")
        state.add_step("run_terminal_command", {"command": "echo test"}, {"success": True})
        trace_path = state.complete("Đã hoàn thành", status="success")

        self.assertTrue(os.path.exists(trace_path))
        self.assertIn(state.session_id, trace_path)

if __name__ == "__main__":
    unittest.main()
