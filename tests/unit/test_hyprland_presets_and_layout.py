import unittest
from ai_assistant.core.nlu import fast_path_nlu

class TestHyprlandPresetsAndLayout(unittest.TestCase):
    def setUp(self):
        self.app_index = {}

    def test_toggle_split_phrases(self):
        phrases = [
            "đổi hướng chia màn hình",
            "đổi hướng chia",
            "chia ngang",
            "chia dọc",
            "đổi chiều chia",
            "xoay hướng chia",
            "toggle split",
        ]
        for p in phrases:
            with self.subTest(phrase=p):
                ok, reply = fast_path_nlu(p, self.app_index, dry_run=True)
                self.assertTrue(ok, f"Lệnh '{p}' phải được Fast-Path nhận diện")
                self.assertIn("đổi hướng chia màn hình", reply)

    def test_split_ratio_phrases(self):
        cases = [
            ("chia đều màn hình", "50 50"),
            ("chia lại cho đều màn hình", "50 50"),
            ("chia cho đều màn hình", "50 50"),
            ("chia đôi 50 50", "50 50"),
            ("chia 50 50", "50 50"),
            ("chia màn hình 70 30", "70%"),
            ("chia 70 30", "70%"),
            ("chia màn hình 30 70", "30%"),
            ("mở rộng cửa sổ", "mở rộng"),
            ("cho cửa sổ to hơn", "mở rộng"),
            ("thu hẹp cửa sổ", "thu hẹp"),
            ("cho cửa sổ nhỏ lại", "thu hẹp"),
        ]
        for p, expected_sub in cases:
            with self.subTest(phrase=p):
                ok, reply = fast_path_nlu(p, self.app_index, dry_run=True)
                self.assertTrue(ok, f"Lệnh '{p}' phải được Fast-Path nhận diện")
                self.assertIn(expected_sub, reply)

    def test_workspace_presets(self):
        cases = [
            ("chế độ lập trình", "chế độ lập trình"),
            ("bật chế độ code", "chế độ lập trình"),
            ("vào chế độ dev", "chế độ lập trình"),
            ("chế độ giải trí", "chế độ giải trí"),
            ("bật chế độ thư giãn", "chế độ giải trí"),
        ]
        for p, expected_sub in cases:
            with self.subTest(phrase=p):
                ok, reply = fast_path_nlu(p, self.app_index, dry_run=True)
                self.assertTrue(ok, f"Lệnh '{p}' phải được Fast-Path nhận diện")
                self.assertIn(expected_sub, reply)

if __name__ == "__main__":
    unittest.main()
