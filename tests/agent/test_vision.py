"""
Unit tests cho Vision Module (Chế độ 3B — chỉ giữ capture_screen).
Kiểm thử công cụ capture_screen, schema chuẩn Ollama, phân tầng bảo mật và xử lý region Wayland/Hyprland.
"""

import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock

from ai_assistant.tools.registry import tool_registry, COMMON_TOOL_ALIASES
from ai_assistant.tools.permission import TOOL_PERMISSION_MAP, PermissionLevel
from ai_assistant.ai.model_router import MODEL_ROLES
from ai_assistant.config import SCREENSHOTS_DIR
from ai_assistant.tools.vision import (
    _parse_region,
    capture_screen_wayland,
    capture_screen,
)


class TestVisionModule(unittest.TestCase):
    """Test Vision Module (chỉ capture_screen cho 3B) integration into existing codebase."""

    def test_capture_screen_tool_registered(self):
        """capture_screen phải được đăng ký trong tool registry."""
        self.assertIn("capture_screen", tool_registry._tools)
        tool = tool_registry._tools["capture_screen"]
        self.assertEqual(tool.name, "capture_screen")
        self.assertIn("save_path", tool.parameters["properties"])
        self.assertIn("region", tool.parameters["properties"])

    def test_capture_screen_schema_format(self):
        """Schema của capture_screen phải đúng chuẩn Ollama function calling."""
        schema = tool_registry._tools["capture_screen"].to_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "capture_screen")
        self.assertIn("parameters", schema["function"])
        self.assertEqual(schema["function"]["parameters"]["type"], "object")

    def test_vision_aliases_registered(self):
        """Các alias của capture_screen phải trỏ đúng công cụ tương ứng."""
        self.assertEqual(COMMON_TOOL_ALIASES["save_screenshot"], "capture_screen")
        self.assertEqual(COMMON_TOOL_ALIASES["screenshot_to_file"], "capture_screen")
        self.assertEqual(COMMON_TOOL_ALIASES["take_screen_capture"], "capture_screen")

    def test_vision_permission_levels(self):
        """Phân loại permission cho capture_screen đúng nguyên tắc bảo mật."""
        self.assertEqual(TOOL_PERMISSION_MAP["capture_screen"], PermissionLevel.SYSTEM_ACTION)

    def test_vision_model_role_in_router(self):
        """MODEL_ROLES phải có key 'vision' (None trên 3B)."""
        self.assertIn("vision", MODEL_ROLES)
        self.assertIsNone(MODEL_ROLES["vision"])

    def test_get_relevant_schemas_capture_screen(self):
        """get_relevant_schemas phải trả về đúng capture_screen cho ý định chụp màn hình lưu file."""
        res_cap = [s["function"]["name"] for s in tool_registry.get_relevant_schemas("lưu ảnh màn hình vào máy")]
        self.assertIn("capture_screen", res_cap)

    def test_region_parsing(self):
        """Hàm parse_region phải xử lý đúng tọa độ, Hyprland window và ném lỗi khi định dạng sai."""
        # 1. Tọa độ số chuẩn
        r1 = _parse_region("10,20 800x600")
        self.assertEqual(r1, {"x": 10, "y": 20, "width": 800, "height": 600})

        # 2. Hyprland active window mock
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout='{"at": [100, 200], "size": [1200, 800]}')
            r_active = _parse_region("active")
            self.assertEqual(r_active, {"x": 100, "y": 200, "width": 1200, "height": 800})

        # 3. Slurp interactive mock
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout="50,60 400x300\n")
            r_slurp = _parse_region("slurp")
            self.assertEqual(r_slurp, {"x": 50, "y": 60, "width": 400, "height": 300})

        # 4. Định dạng sai
        with self.assertRaises(ValueError):
            _parse_region("invalid_format_xyz")

    @patch("ai_assistant.tools.vision.subprocess.run")
    def test_capture_screen_grim_not_found(self, mock_run):
        """Nếu grim chưa cài, phải trả lỗi rõ ràng."""
        mock_run.return_value = MagicMock(returncode=1)
        b64, meta = capture_screen_wayland()
        self.assertIsNone(b64)
        self.assertIn("error", meta)
        self.assertIn("grim", meta["error"])

    def test_tool_count_is_17(self):
        """Tổng số tool đăng ký phải là 17 (14 core + 2 web/net + 1 capture_screen)."""
        total = len(tool_registry._tools)
        self.assertEqual(total, 17,
                         f"Kỳ vọng 17 tools (14 core + 2 web/net + 1 capture_screen), nhưng có {total}: "
                         f"{list(tool_registry._tools.keys())}")


if __name__ == "__main__":
    unittest.main()
