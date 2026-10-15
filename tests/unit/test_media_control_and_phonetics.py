"""
Unit tests kiểm thử điều khiển nhạc đa phương tiện, sửa lỗi ngữ âm Whisper và vòng đời Auto-Pause.
"""

import unittest
from ai_assistant.core.nlu import clean_user_input, fast_path_nlu
from ai_assistant.core.orchestrator import agent_orchestrator
from ai_assistant.tools.system import is_media_playing

class TestMediaControlAndPhonetics(unittest.TestCase):
    def setUp(self):
        self.app_index = {}

    def test_whisper_phonetic_normalization_for_music(self):
        """Kiểm tra việc chuẩn hóa các từ bị dội âm / phát âm lệch do Whisper nghe nhầm."""
        cases = {
            "Chiếm bay hát": "chuyển bài hát",
            "Tám rung nhập": "tạm dừng",
            "Tạm dân nhét": "tạm dừng nhé",
            "Dương nhiệt": "dừng nhạc",
            "Dừng nhiệt": "dừng nhạc",
            "Nhạc tên dì": "nhạc tên gì",
            "Tạm dân": "tạm dừng",
            "Tạm dâng": "tạm dừng",
            "Bye, tiếp theo.": "bài tiếp theo",
            "Bài này là bài dì": "bài này là bài gì",
            "Đang phát bài dì": "đang phát bài gì",
        }
        for raw, expected in cases.items():
            cleaned = clean_user_input(raw)
            self.assertIn(expected.lower(), cleaned.lower(), f"Expected '{expected}' in cleaned text for raw '{raw}', got '{cleaned}'")

    def test_fast_path_music_intent_recognition(self):
        """Kiểm tra Fast-Path NLU nhận diện chính xác 100% các khẩu lệnh điều khiển nhạc."""
        # 1. Tra cứu thông tin bài hát
        track_queries = [
            "Bài này là bài gì?",
            "Đang phát bài gì?",
            "Bài hát tên gì?",
            "Tên bài hát là gì?",
            "Nhạc tên gì?",
            "Ai đang hát thế?",
            "Nhạc tên dì",  # Nghe lệch
        ]
        for q in track_queries:
            ok, reply = fast_path_nlu(q, self.app_index, dry_run=True)
            self.assertTrue(ok, f"Failed to match track query: '{q}'")
            self.assertTrue("bài hát" in reply.lower() or "đang phát" in reply.lower(), f"Unexpected reply: {reply}")

        # 2. Tạm dừng nhạc
        pause_queries = [
            "Tạm dừng",
            "Tạm dừng nhạc",
            "Tạm dừng bài hát",
            "Dừng nhạc",
            "Tắt nhạc",
            "Tạm dừng nhé",
            "Tám rung nhập",  # Nghe lệch từ mic dội
            "Dương nhiệt",    # Nghe lệch từ mic dội
        ]
        for q in pause_queries:
            ok, reply = fast_path_nlu(q, self.app_index, dry_run=True)
            self.assertTrue(ok, f"Failed to match pause query: '{q}'")
            self.assertIn("tạm dừng", reply.lower())

        # 2.1. Cắt lời khẩn cấp / Dừng lại (Barge-in: im lặng tức thì, không đọc lời đáp)
        ok_barge, reply_barge = fast_path_nlu("Dừng lại", self.app_index, dry_run=True)
        self.assertTrue(ok_barge)
        self.assertEqual(reply_barge, "")

        # 3. Tiếp tục / Phát nhạc
        resume_queries = [
            "Phát tiếp",
            "Tiếp tục nhạc",
            "Phát bài nhạc tiếp",
            "Phát bài tiếp",
            "Tiếp tục phát",
            "Bật lại nhạc",
            "Mở lại nhạc",
            "Nghe tiếp",
        ]
        for q in resume_queries:
            ok, reply = fast_path_nlu(q, self.app_index, dry_run=True)
            self.assertTrue(ok, f"Failed to match resume query: '{q}'")
            self.assertIn("tiếp tục phát", reply.lower())

        # 4. Chuyển bài tiếp theo
        next_queries = [
            "Chuyển bài",
            "Chuyển bài hát",
            "Bài tiếp theo",
            "Qua bài",
            "Next bài",
            "Đổi bài",
            "Chiếm bay hát",  # Nghe lệch
            "Bye, tiếp theo.", # Nghe lệch
        ]
        for q in next_queries:
            ok, reply = fast_path_nlu(q, self.app_index, dry_run=True)
            self.assertTrue(ok, f"Failed to match next query: '{q}'")
            self.assertIn("tiếp theo", reply.lower())

        # 5. Bài trước đó
        prev_queries = [
            "Bài trước",
            "Quay lại bài trước",
            "Lùi bài",
            "Back bài",
            "Bài vừa rồi",
            "Nghe lại bài trước",
        ]
        for q in prev_queries:
            ok, reply = fast_path_nlu(q, self.app_index, dry_run=True)
            self.assertTrue(ok, f"Failed to match prev query: '{q}'")
            self.assertIn("bài trước", reply.lower())

    def test_orchestrator_does_not_hijack_music_commands(self):
        """Đảm bảo Orchestrator không kích hoạt ReAct loop sai cho các lệnh nhạc ngắn."""
        music_commands = [
            "Bài tiếp theo",
            "Bye, tiếp theo.",
            "Bài trước",
            "Tạm dừng",
            "Dừng nhạc",
            "Phát tiếp",
            "Chuyển bài",
        ]
        for cmd in music_commands:
            self.assertFalse(
                agent_orchestrator.is_complex_request(cmd),
                f"is_complex_request should be False for '{cmd}'"
            )

    def test_is_media_playing_callable(self):
        """Đảm bảo hàm kiểm tra trạng thái media chạy an toàn và không gây crash."""
        res = is_media_playing()
        self.assertIsInstance(res, bool)

if __name__ == "__main__":
    unittest.main()
