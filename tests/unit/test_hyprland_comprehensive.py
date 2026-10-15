"""
Bài test lớn kiểm tra toàn diện các trường hợp điều khiển Hyprland v0.56.2 qua Fast-Path NLU:
1. Chuyển Workspace (Workspace Switching)
2. Di chuyển cửa sổ sang Workspace (Move window to workspace)
3. Cửa sổ nổi (Toggle Floating)
4. Ghim cửa sổ (Toggle Pin)
5. Các trường hợp biên & phủ định (Edge cases & Negative tests)
6. Đo lường hiệu năng độ trễ thực tế (< 3ms)
"""

import time
import unittest
from ai_assistant.core.nlu import fast_path_nlu
from ai_assistant.tools.apps import (
    switch_hyprland_workspace,
    move_active_window_to_workspace,
    toggle_window_floating,
    toggle_window_pin,
)

class TestHyprlandComprehensive(unittest.TestCase):
    def setUp(self):
        self.app_index = {}

    def test_1_workspace_switching_phrases(self):
        """Kiểm tra độ phủ từ vựng phong phú cho lệnh chuyển workspace."""
        phrases = [
            ("chuyển sang workspace 2", 2),
            ("chuyển sang không gian làm việc 3", 3),
            ("qua bàn làm việc 4", 4),
            ("vào không gian làm việc số 5", 5),
            ("tới workspace 1", 1),
            ("sang màn hình 2", 2),
            ("chuyển vào bàn làm việc 10", 10),
            ("qua không gian làm việc số 7", 7),
            ("tới bàn làm việc 8", 8),
        ]
        for phrase, expected_ws in phrases:
            with self.subTest(phrase=phrase):
                handled, reply = fast_path_nlu(phrase, self.app_index, dry_run=True)
                self.assertTrue(handled, f"Lệnh '{phrase}' phải được Fast-Path xử lý")
                self.assertIn(f"không gian làm việc số {expected_ws}", reply)

    def test_2_move_window_to_workspace_phrases(self):
        """Kiểm tra độ phủ từ vựng cho lệnh đưa cửa sổ sang workspace."""
        phrases = [
            ("đưa cửa sổ này sang workspace 3", 3),
            ("chuyển cửa sổ hiện tại sang không gian làm việc số 1", 1),
            ("ném ứng dụng này qua bàn làm việc 2", 2),
            ("mang cửa sổ qua workspace 4", 4),
            ("đưa cửa sổ sang màn hình 2", 2),
            ("chuyển cửa sổ này vào không gian làm việc 5", 5),
            ("ném cửa sổ hiện tại sang bàn làm việc số 6", 6),
        ]
        for phrase, expected_ws in phrases:
            with self.subTest(phrase=phrase):
                handled, reply = fast_path_nlu(phrase, self.app_index, dry_run=True)
                self.assertTrue(handled, f"Lệnh '{phrase}' phải được Fast-Path xử lý")
                self.assertIn(f"không gian làm việc số {expected_ws}", reply)

    def test_3_toggle_window_floating_phrases(self):
        """Kiểm tra độ phủ từ vựng cho tính năng cửa sổ nổi (float)."""
        phrases = [
            "chuyển thành cửa sổ nổi",
            "cửa sổ nổi",
            "bật cửa sổ nổi",
            "tắt cửa sổ nổi",
            "cửa sổ trôi nổi",
            "toggle float",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                handled, reply = fast_path_nlu(phrase, self.app_index, dry_run=True)
                self.assertTrue(handled, f"Lệnh '{phrase}' phải được Fast-Path xử lý")
                self.assertIn("cửa sổ nổi", reply)

    def test_4_toggle_window_pin_phrases(self):
        """Kiểm tra độ phủ từ vựng cho tính năng ghim cửa sổ (pin)."""
        phrases = [
            "ghim cửa sổ này",
            "ghim cửa sổ",
            "bỏ ghim cửa sổ",
            "ghim lên trên cùng",
            "pin cửa sổ",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                handled, reply = fast_path_nlu(phrase, self.app_index, dry_run=True)
                self.assertTrue(handled, f"Lệnh '{phrase}' phải được Fast-Path xử lý")
                self.assertIn("ghim cửa sổ này", reply)

    def test_5_negative_and_boundary_cases(self):
        """Kiểm tra trường hợp phủ định (không bị nhận diện nhầm) và biên giá trị."""
        # Các câu không phải lệnh điều khiển workspace:
        negative_phrases = [
            "chuyển bài tiếp theo",
            "chuyển bài hát",
            "mở cửa sổ ra cho thoáng",
            "không gian vũ trụ rộng lớn thế nào",
            "bàn làm việc của tôi rất đẹp",
        ]
        for phrase in negative_phrases:
            with self.subTest(phrase=phrase):
                handled, reply = fast_path_nlu(phrase, self.app_index, dry_run=True)
                # Không được xử lý như lệnh workspace
                if handled:
                    self.assertNotIn("không gian làm việc số", reply)

        # Kiểm tra biên workspace trong hàm tool
        ok, msg = switch_hyprland_workspace(0)
        self.assertFalse(ok)
        self.assertIn("không hợp lệ", msg)

        ok, msg = switch_hyprland_workspace(11)
        self.assertFalse(ok)
        self.assertIn("không hợp lệ", msg)

        ok, msg = move_active_window_to_workspace(-1)
        self.assertFalse(ok)
        self.assertIn("không hợp lệ", msg)

    def test_6_latency_benchmark(self):
        """Benchmark tốc độ phản xạ NLU (Yêu cầu < 3ms, thường đạt < 0.1ms)."""
        test_queries = [
            "chuyển sang workspace 2",
            "đưa cửa sổ này sang workspace 3",
            "chuyển thành cửa sổ nổi",
            "ghim cửa sổ này",
        ]
        total_runs = 1000
        start = time.perf_counter()
        for _ in range(total_runs):
            for q in test_queries:
                fast_path_nlu(q, self.app_index, dry_run=True)
        elapsed = time.perf_counter() - start
        avg_latency_ms = (elapsed / (total_runs * len(test_queries))) * 1000.0

        print(f"\n[Hyprland Fast-Path Benchmark] Độ trễ trung bình: {avg_latency_ms:.4f} ms / câu lệnh")
        self.assertLess(avg_latency_ms, 3.0, "Độ trễ xử lý phải nhỏ hơn 3ms")

    def test_7_tool_execution_safety(self):
        """Kiểm tra các hàm gọi tool không bị crash khi chạy trên môi trường thực."""
        # Gọi thử toggle_window_floating và toggle_window_pin (an toàn, trả về tuple[bool, str])
        ok1, msg1 = toggle_window_floating()
        self.assertIsInstance(ok1, bool)
        self.assertIsInstance(msg1, str)

        ok2, msg2 = toggle_window_pin()
        self.assertIsInstance(ok2, bool)
        self.assertIsInstance(msg2, str)

if __name__ == "__main__":
    unittest.main()
