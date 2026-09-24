"""
Unit tests kiểm thử ToolRegistry và Agent Core Orchestrator.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.tools.registry import tool_registry, run_terminal_command, find_files_or_projects
from ai_assistant.core.orchestrator import agent_orchestrator

class TestAgentOrchestrator(unittest.TestCase):
    def test_tool_registry_schemas(self):
        schemas = tool_registry.get_schemas()
        self.assertGreaterEqual(len(schemas), 10)
        tool_names = [s["function"]["name"] for s in schemas]
        self.assertIn("run_terminal_command", tool_names)
        self.assertIn("find_files_or_projects", tool_names)
        self.assertIn("launch_application", tool_names)
        self.assertIn("control_system_hardware", tool_names)

    def test_run_terminal_command_safe(self):
        # Lệnh an toàn
        res = run_terminal_command("echo 'Hello Arch Linux Agent'")
        self.assertTrue(res["success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("Hello Arch Linux Agent", res["stdout"])

    def test_run_terminal_command_forbidden(self):
        # Lệnh nguy hiểm bị chặn
        res = run_terminal_command("rm -rf /")
        self.assertFalse(res["success"])
        self.assertIn("LỆNH BỊ CHẶN", res["stderr"])

    def test_find_files_or_projects(self):
        # Tìm thử thư mục voice-ai trong ~/Projects
        res = find_files_or_projects("voice-ai")
        self.assertIsInstance(res, list)
        self.assertTrue(any("voice-ai" in p for p in res))

    def test_tool_registry_fuzzy_and_aliases(self):
        # Kiểm tra fuzzy match với tên lệch / khoảng trắng
        res1 = tool_registry.execute("find_filesor projects", {"query": "voice-ai"})
        self.assertTrue(res1["success"])
        self.assertTrue(any("voice-ai" in p for p in res1["result"]))

        # Kiểm tra alias search_project
        res2 = tool_registry.execute("search_project", {"project_name": "voice-ai"})
        self.assertTrue(res2["success"])
        self.assertTrue(any("voice-ai" in p for p in res2["result"]))

    def test_get_relevant_schemas(self):
        # Lọc công cụ liên quan theo từ khóa
        schemas_dev = tool_registry.get_relevant_schemas("Kiểm tra cổng 8080 xem có bị chiếm không")
        tool_names = [s["function"]["name"] for s in schemas_dev]
        self.assertIn("check_and_manage_port", tool_names)
        self.assertIn("run_terminal_command", tool_names)

        schemas_spring = tool_registry.get_relevant_schemas("Mở IntelliJ kiểm tra project Spring Boot")
        spring_tool_names = [s["function"]["name"] for s in schemas_spring]
        self.assertIn("find_files_or_projects", spring_tool_names)
        self.assertIn("launch_application", spring_tool_names)

    def test_parse_tool_calls_from_text(self):
        # 1. Cú pháp JSON chuẩn
        text_json = '```json\n{"tool": "check_and_manage_port", "arguments": {"port": 8080}}\n```'
        calls_json = agent_orchestrator._parse_tool_calls_from_text(text_json)
        self.assertEqual(len(calls_json), 1)
        self.assertEqual(calls_json[0]["function"]["name"], "check_and_manage_port")
        self.assertEqual(calls_json[0]["function"]["arguments"]["port"], 8080)

        # 2. Cú pháp CLI
        text_cli = 'Hãy chạy: check_and_manage_port --action check --port 8080'
        calls_cli = agent_orchestrator._parse_tool_calls_from_text(text_cli)
        self.assertEqual(len(calls_cli), 1)
        self.assertEqual(calls_cli[0]["function"]["name"], "check_and_manage_port")
        self.assertEqual(calls_cli[0]["function"]["arguments"]["port"], 8080)

    def test_is_complex_request(self):
        # Các câu lệnh phức tạp / đa bước / có điều kiện
        self.assertTrue(agent_orchestrator.is_complex_request("Mở IntelliJ, kiểm tra project Spring Boot của tôi, nếu build lỗi thì tìm nguyên nhân và nói cho tôi biết."))
        self.assertTrue(agent_orchestrator.is_complex_request("Kiểm tra Docker xem container nào đang chạy và tắt container redis đi"))
        self.assertTrue(agent_orchestrator.is_complex_request("Tắt nhạc và sau đó giảm độ sáng màn hình"))
        self.assertTrue(agent_orchestrator.is_complex_request("Nếu pin dưới 20% thì bật chế độ tiết kiệm pin"))

        # Các câu hỏi đơn giản / đàm thoại thông thường
        self.assertFalse(agent_orchestrator.is_complex_request("Thời tiết Hà Nội hôm nay thế nào?"))
        self.assertFalse(agent_orchestrator.is_complex_request("Bạn là ai?"))
        self.assertFalse(agent_orchestrator.is_complex_request("Giải thích cho tôi về JVM Memory Model"))

if __name__ == "__main__":
    unittest.main()
