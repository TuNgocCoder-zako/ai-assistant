"""
Unit tests cho Vision Module (V2.3 — Screen Awareness & Multimodal AI).
Kiểm thử toàn diện 4 công cụ thị giác (see_screen, capture_screen, analyze_image, watch_camera),
schema chuẩn Ollama, phân tầng bảo mật, quản lý bộ đệm (caching) và xử lý region Wayland/Hyprland.
"""

import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock

from ai_assistant.tools.registry import tool_registry, COMMON_TOOL_ALIASES
from ai_assistant.tools.permission import TOOL_PERMISSION_MAP, PermissionLevel
from ai_assistant.ai.model_router import MODEL_ROLES
from ai_assistant.config import (
    DEFAULT_VISION_MODEL,
    OLLAMA_BASE_URL,
    WEBCAM_DEVICE_INDEX,
    VISION_CACHE_TTL_SEC,
)
from ai_assistant.tools.vision import (
    _parse_region,
    _get_cached_analysis,
    _store_cached_analysis,
    capture_screen_wayland,
    capture_webcam_frame,
    see_screen,
    capture_screen,
    analyze_image,
    watch_camera,
)


class TestVisionModule(unittest.TestCase):
    """Test Vision Module integration into existing codebase."""

    def test_see_screen_tool_registered(self):
        """see_screen phải được đăng ký trong tool registry."""
        self.assertIn("see_screen", tool_registry._tools)
        tool = tool_registry._tools["see_screen"]
        self.assertEqual(tool.name, "see_screen")
        self.assertIn("query", tool.parameters["properties"])
        self.assertIn("query", tool.parameters["required"])

    def test_capture_screen_tool_registered(self):
        """capture_screen phải được đăng ký trong tool registry."""
        self.assertIn("capture_screen", tool_registry._tools)
        tool = tool_registry._tools["capture_screen"]
        self.assertEqual(tool.name, "capture_screen")
        self.assertIn("save_path", tool.parameters["properties"])
        self.assertIn("region", tool.parameters["properties"])

    def test_analyze_image_tool_registered(self):
        """analyze_image phải được đăng ký trong tool registry."""
        self.assertIn("analyze_image", tool_registry._tools)
        tool = tool_registry._tools["analyze_image"]
        self.assertEqual(tool.name, "analyze_image")
        self.assertIn("image_path", tool.parameters["properties"])
        self.assertIn("image_path", tool.parameters["required"])

    def test_watch_camera_tool_registered(self):
        """watch_camera phải được đăng ký trong tool registry."""
        self.assertIn("watch_camera", tool_registry._tools)
        tool = tool_registry._tools["watch_camera"]
        self.assertEqual(tool.name, "watch_camera")
        self.assertIn("query", tool.parameters["properties"])
        self.assertIn("device_index", tool.parameters["properties"])

    def test_all_vision_schemas_format(self):
        """Mọi schema của 4 tools vision phải đúng chuẩn Ollama function calling."""
        for tool_name in ["see_screen", "capture_screen", "analyze_image", "watch_camera"]:
            schema = tool_registry._tools[tool_name].to_schema()
            self.assertEqual(schema["type"], "function")
            self.assertEqual(schema["function"]["name"], tool_name)
            self.assertIn("parameters", schema["function"])
            self.assertEqual(schema["function"]["parameters"]["type"], "object")

    def test_vision_aliases_registered(self):
        """Các alias vision phải trỏ đúng công cụ tương ứng."""
        see_screen_aliases = ["screenshot", "view_screen", "look_screen",
                              "observe_screen", "analyze_screen", "screen_capture"]
        for alias in see_screen_aliases:
            self.assertIn(alias, COMMON_TOOL_ALIASES)
            self.assertEqual(COMMON_TOOL_ALIASES[alias], "see_screen")

        self.assertEqual(COMMON_TOOL_ALIASES["save_screenshot"], "capture_screen")
        self.assertEqual(COMMON_TOOL_ALIASES["screenshot_to_file"], "capture_screen")
        self.assertEqual(COMMON_TOOL_ALIASES["read_image"], "analyze_image")
        self.assertEqual(COMMON_TOOL_ALIASES["inspect_image"], "analyze_image")
        self.assertEqual(COMMON_TOOL_ALIASES["look_webcam"], "watch_camera")
        self.assertEqual(COMMON_TOOL_ALIASES["check_webcam"], "watch_camera")

    def test_vision_permission_levels(self):
        """Phân loại permission cho 4 tools vision đúng nguyên tắc bảo mật."""
        self.assertEqual(TOOL_PERMISSION_MAP["see_screen"], PermissionLevel.SYSTEM_ACTION)
        self.assertEqual(TOOL_PERMISSION_MAP["capture_screen"], PermissionLevel.SYSTEM_ACTION)
        self.assertEqual(TOOL_PERMISSION_MAP["analyze_image"], PermissionLevel.READ_ONLY)
        self.assertEqual(TOOL_PERMISSION_MAP["watch_camera"], PermissionLevel.SENSITIVE_WRITE)

    def test_vision_model_role_in_router(self):
        """MODEL_ROLES phải có key 'vision'."""
        self.assertIn("vision", MODEL_ROLES)

    def test_vision_config_values(self):
        """Config vision phải có giá trị hợp lệ."""
        self.assertIsInstance(DEFAULT_VISION_MODEL, str)
        self.assertTrue(len(DEFAULT_VISION_MODEL) > 0)
        self.assertIsInstance(OLLAMA_BASE_URL, str)
        self.assertTrue(OLLAMA_BASE_URL.startswith("http"))
        self.assertEqual(WEBCAM_DEVICE_INDEX, 0)
        self.assertGreater(VISION_CACHE_TTL_SEC, 0)

    def test_get_relevant_schemas_multimodal(self):
        """get_relevant_schemas phải trả về đúng tool cho từng ý định thị giác."""
        # see_screen
        res_screen = [s["function"]["name"] for s in tool_registry.get_relevant_schemas("đang hiện gì trên màn hình")]
        self.assertIn("see_screen", res_screen)

        # watch_camera
        res_cam = [s["function"]["name"] for s in tool_registry.get_relevant_schemas("bật camera nhìn xem tôi đang làm gì")]
        self.assertIn("watch_camera", res_cam)

        # analyze_image
        res_img = [s["function"]["name"] for s in tool_registry.get_relevant_schemas("phân tích ảnh này cho tôi")]
        self.assertIn("analyze_image", res_img)

        # capture_screen
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

    def test_image_caching(self):
        """Bộ nhớ đệm Image Cache phải lưu và trả về kết quả quan sát đúng TTL."""
        test_hash = "mock_hash_123456"
        test_query = "Mô tả màn hình"
        test_desc = "Màn hình đang mở VS Code và terminal"

        # Chưa cache
        self.assertIsNone(_get_cached_analysis(test_hash, test_query))

        # Lưu cache
        _store_cached_analysis(test_hash, test_query, test_desc)

        # Đã cache
        cached = _get_cached_analysis(test_hash, test_query)
        self.assertEqual(cached, test_desc)

    @patch("ai_assistant.tools.vision.subprocess.run")
    def test_capture_screen_grim_not_found(self, mock_run):
        """Nếu grim chưa cài, phải trả lỗi rõ ràng."""
        mock_run.return_value = MagicMock(returncode=1)
        b64, meta = capture_screen_wayland()
        self.assertIsNone(b64)
        self.assertIn("error", meta)
        self.assertIn("grim", meta["error"])

    @patch("ai_assistant.tools.vision._check_vision_model_available", return_value=False)
    def test_see_screen_no_vision_model(self, mock_check):
        """Nếu vision model chưa pull, phải trả lỗi hướng dẫn cài."""
        result = see_screen(query="test")
        self.assertFalse(result["success"])
        self.assertIn("ollama pull", result["error"])

    def test_analyze_image_file_not_found(self):
        """analyze_image khi file không tồn tại phải trả lỗi rõ ràng."""
        with patch("ai_assistant.tools.vision._check_vision_model_available", return_value=True):
            res = analyze_image("/path/to/non_existent_image_123.jpg")
            self.assertFalse(res["success"])
            self.assertIn("không tồn tại", res["error"])

    def test_tool_count_is_18(self):
        """Tổng số tool đăng ký phải là 18 (14 cũ + 4 tools vision)."""
        total = len(tool_registry._tools)
        self.assertEqual(total, 18,
                         f"Kỳ vọng 18 tools (14 core + 4 vision), nhưng có {total}: "
                         f"{list(tool_registry._tools.keys())}")


if __name__ == "__main__":
    unittest.main()
