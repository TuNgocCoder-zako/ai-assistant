"""
Unit tests cho Vision Module (V2.3).
Kiểm tra đăng ký tool, screen capture logic, và xử lý lỗi.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from ai_assistant.tools.registry import tool_registry, COMMON_TOOL_ALIASES
from ai_assistant.tools.permission import TOOL_PERMISSION_MAP, PermissionLevel
from ai_assistant.ai.model_router import MODEL_ROLES
from ai_assistant.config import DEFAULT_VISION_MODEL, OLLAMA_BASE_URL


class TestVisionModule(unittest.TestCase):
    """Test Vision Module integration into existing codebase."""

    def test_see_screen_tool_registered(self):
        """see_screen phải được đăng ký trong tool registry."""
        self.assertIn("see_screen", tool_registry._tools)
        tool = tool_registry._tools["see_screen"]
        self.assertEqual(tool.name, "see_screen")
        self.assertIn("query", tool.parameters["properties"])
        self.assertIn("query", tool.parameters["required"])

    def test_see_screen_schema_format(self):
        """Schema phải đúng chuẩn Ollama function calling."""
        schema = tool_registry._tools["see_screen"].to_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "see_screen")
        self.assertIn("parameters", schema["function"])
        self.assertEqual(schema["function"]["parameters"]["type"], "object")

    def test_vision_aliases_registered(self):
        """Các alias vision phải trỏ đến see_screen."""
        vision_aliases = ["screenshot", "view_screen", "look_screen",
                          "observe_screen", "analyze_screen", "screen_capture"]
        for alias in vision_aliases:
            self.assertIn(alias, COMMON_TOOL_ALIASES)
            self.assertEqual(COMMON_TOOL_ALIASES[alias], "see_screen")

    def test_vision_permission_level(self):
        """see_screen phải có permission SYSTEM_ACTION."""
        self.assertIn("see_screen", TOOL_PERMISSION_MAP)
        self.assertEqual(TOOL_PERMISSION_MAP["see_screen"], PermissionLevel.SYSTEM_ACTION)

    def test_vision_model_role_in_router(self):
        """MODEL_ROLES phải có key 'vision'."""
        self.assertIn("vision", MODEL_ROLES)
        # vision có thể None nếu chưa pull model
        # Nhưng key phải tồn tại

    def test_vision_config_values(self):
        """Config vision phải có giá trị hợp lệ."""
        self.assertIsInstance(DEFAULT_VISION_MODEL, str)
        self.assertTrue(len(DEFAULT_VISION_MODEL) > 0)
        self.assertIsInstance(OLLAMA_BASE_URL, str)
        self.assertTrue(OLLAMA_BASE_URL.startswith("http"))

    def test_get_relevant_schemas_includes_vision(self):
        """get_relevant_schemas phải trả về see_screen khi có keyword vision."""
        vision_queries = [
            "đang hiện gì trên màn hình",
            "xem màn hình",
            "chụp màn hình phân tích",
            "nhìn thấy gì trên screen",
        ]
        for q in vision_queries:
            schemas = tool_registry.get_relevant_schemas(q)
            names = [s["function"]["name"] for s in schemas]
            self.assertIn("see_screen", names,
                          f"see_screen không được trả về cho query: '{q}'")

    def test_get_relevant_schemas_excludes_vision_for_unrelated(self):
        """Các query không liên quan vision không nên chứa see_screen."""
        non_vision_queries = [
            "mở brave browser",
            "kiểm tra port 8080",
            "hẹn giờ 5 phút",
        ]
        for q in non_vision_queries:
            schemas = tool_registry.get_relevant_schemas(q)
            names = [s["function"]["name"] for s in schemas]
            self.assertNotIn("see_screen", names,
                             f"see_screen không nên có trong query: '{q}'")

    @patch("ai_assistant.tools.vision.subprocess.run")
    def test_capture_screen_grim_not_found(self, mock_run):
        """Nếu grim chưa cài, phải trả lỗi rõ ràng."""
        mock_run.return_value = MagicMock(returncode=1)
        from ai_assistant.tools.vision import capture_screen_wayland
        b64, meta = capture_screen_wayland()
        self.assertIsNone(b64)
        self.assertIn("error", meta)
        self.assertIn("grim", meta["error"])

    @patch("ai_assistant.tools.vision._check_vision_model_available", return_value=False)
    def test_see_screen_no_vision_model(self, mock_check):
        """Nếu vision model chưa pull, phải trả lỗi hướng dẫn cài."""
        from ai_assistant.tools.vision import see_screen
        result = see_screen(query="test")
        self.assertFalse(result["success"])
        self.assertIn("ollama pull", result["error"])

    def test_see_screen_invalid_region(self):
        """Region format sai phải trả lỗi rõ ràng."""
        from ai_assistant.tools.vision import see_screen
        with patch("ai_assistant.tools.vision._check_vision_model_available", return_value=True):
            # "abc,def 100x200" has 4 parts after split but abc/def are not ints → ValueError
            result = see_screen(query="test", region="abc,def 100x200")
            self.assertFalse(result["success"])
            self.assertIn("Region", result["error"])

    def test_tool_count_is_15(self):
        """Tổng số tool đăng ký phải là 15 (14 cũ + see_screen)."""
        total = len(tool_registry._tools)
        self.assertEqual(total, 15,
                         f"Kỳ vọng 15 tools (14 cũ + see_screen), nhưng có {total}: "
                         f"{list(tool_registry._tools.keys())}")


if __name__ == "__main__":
    unittest.main()
