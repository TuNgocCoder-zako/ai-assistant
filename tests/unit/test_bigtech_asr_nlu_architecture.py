"""
Unit test kiểm thử kiến trúc 4 tầng chuẩn Big Tech (Google, Samsung, Zalo, VinAI):
1. Contextual Biasing cho Whisper (WHISPER_INITIAL_PROMPT)
2. Multi-Pronunciation & Phonetic Aliasing (Dị âm 3 miền & từ mượn công nghệ)
3. State-Aware Dialogue (Theo dõi ngữ cảnh máy khi đang phát nhạc)
4. Anti-Leak Guard (Chặn đứng câu lệnh cụt lủn / méo tiếng rò rỉ xuống LLM)
"""

import unittest
from unittest.mock import patch
from ai_assistant.config import WHISPER_INITIAL_PROMPT
from ai_assistant.core.nlu import clean_user_input, fast_path_nlu

class TestBigTechAsrNluArchitecture(unittest.TestCase):
    def test_1_whisper_contextual_biasing_prompt(self):
        """Kiểm tra WHISPER_INITIAL_PROMPT đã chứa đầy đủ từ khóa định hướng bối cảnh."""
        self.assertIn("workspace", WHISPER_INITIAL_PROMPT.lower())
        self.assertIn("hyprland", WHISPER_INITIAL_PROMPT.lower())
        self.assertIn("cửa sổ nổi", WHISPER_INITIAL_PROMPT.lower())
        self.assertIn("chuyển nhạc", WHISPER_INITIAL_PROMPT.lower())
        self.assertIn("đổi nhạc", WHISPER_INITIAL_PROMPT.lower())

    def test_2_multi_pronunciation_lexicon(self):
        """Kiểm tra từ điển đa phiên âm vùng miền và từ mượn công nghệ trong clean_user_input."""
        # 1. Âm cuối /k/ -> /t/ (Nam Bộ) và nhầm lẫn 'nhạc' -> 'nhạt' / 'nhác'
        self.assertEqual(clean_user_input("bật nhạt lên"), "bật nhạc lên")
        self.assertEqual(clean_user_input("mở nhác"), "mở nhạc")
        self.assertEqual(clean_user_input("tắt nhạt đi"), "tắt nhạc đi")
        self.assertEqual(clean_user_input("chuyển nhạt"), "chuyển nhạc")
        self.assertEqual(clean_user_input("chuyến đi"), "chuyển bài hát")
        self.assertEqual(clean_user_input("chuyến nhạc"), "chuyển bài hát")

        # 2. Từ mượn công nghệ
        self.assertEqual(clean_user_input("đóng tháp này"), "đóng tab này")
        self.assertEqual(clean_user_input("tắt táp này"), "tắt tab này")
        self.assertEqual(clean_user_input("bật noa lên"), "bật loa lên")
        self.assertEqual(clean_user_input("chuyển sang uốc sờ bây 2"), "chuyển sang workspace 2")
        self.assertEqual(clean_user_input("qua quốc xây 3"), "qua workspace 3")

    def test_3_media_commands_direct(self):
        """Kiểm tra các lệnh chuyển nhạc / đổi nhạc trực tiếp qua Fast-Path NLU."""
        handled, rep = fast_path_nlu("chuyển nhạc", {}, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("bài tiếp theo", rep)

        handled, rep = fast_path_nlu("đổi nhạc", {}, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("bài tiếp theo", rep)

    @patch("ai_assistant.core.nlu.is_media_playing", return_value=True)
    def test_4_state_aware_media_control(self, mock_is_media_playing):
        """Kiểm tra cơ chế State-Aware khi máy đang phát nhạc (is_media_playing = True)."""
        # Khi đang nghe nhạc, nói các từ cộc lốc -> tự động chuyển bài
        handled, rep = fast_path_nlu("tiếp", {}, dry_run=False)
        self.assertTrue(handled)
        self.assertIn("bài tiếp theo", rep)

        handled, rep = fast_path_nlu("tiếp đi", {}, dry_run=False)
        self.assertTrue(handled)
        self.assertIn("bài tiếp theo", rep)

        handled, rep = fast_path_nlu("đổi đi", {}, dry_run=False)
        self.assertTrue(handled)
        self.assertIn("bài tiếp theo", rep)

        # Lệnh dừng ngắn khi đang nghe nhạc
        handled, rep = fast_path_nlu("dừng đi", {}, dry_run=False)
        self.assertTrue(handled)
        self.assertIn("tạm dừng", rep)

    def test_5_anti_leak_guard_blocks_isolated_fragments(self):
        """Kiểm tra Smart Anti-Leak Guard chặn đứng các mệnh lệnh hỏng / không rõ đối tượng."""
        fragment_cases = [
            "mở đi", "bật lên", "tắt", "đóng lại", "cửa sổ", "ứng dụng",
            "mở phai phốc lạ hoắc",  # App lạ chưa có trong máy
            "tắt cái phần mềm vớ vẩn này",
            "chuyển cái này đi",
        ]
        for frag in fragment_cases:
            with self.subTest(frag=frag):
                handled, rep = fast_path_nlu(frag, {}, dry_run=True)
                self.assertTrue(handled, f"Lệnh cụt/hỏng '{frag}' phải bị Smart Anti-Leak Guard chặn")
                self.assertIn("chưa nghe rõ", rep.lower())

    def test_6_anti_leak_guard_allows_real_questions(self):
        """Đảm bảo Anti-Leak Guard KHÔNG chặn các câu hỏi tri thức hợp lệ."""
        real_questions = [
            "Trái Đất là gì?",
            "Tại sao trời mưa?",
            "Viết code python",
            "Ai là tổng thống Mỹ?",
            "Làm sao để học giỏi?",
        ]
        for q in real_questions:
            with self.subTest(q=q):
                handled, rep = fast_path_nlu(q, {}, dry_run=True)
                self.assertFalse(handled, f"Câu hỏi tri thức '{q}' phải được cho qua để chuyển sang LLM")

    def test_7_spotify_and_solo_app_launch(self):
        """Kiểm tra xử lý 'm ở spotify', 'vào spotify', 'nghe spotify' và gọi độc tên ứng dụng."""
        # 1. Gộp m ở, em ở
        self.assertEqual(clean_user_input("m ở spotify"), "mở spotify")
        self.assertEqual(clean_user_input("em ở spotify"), "mở spotify")
        self.assertEqual(clean_user_input("ê ở vs code"), "mở vs code")

        # 2. Mock app_index với spotify và zalo
        app_index = {
            "spotify": {"name": "Spotify", "desktop_id": "spotify.desktop", "exec": "spotify"},
            "zalo": {"name": "Zalo", "desktop_id": "zalo.desktop", "exec": "zalo"},
            "visual studio code": {"name": "Visual Studio Code", "desktop_id": "code.desktop", "exec": "code"},
        }

        # 3. Mở với các dạng câu khác nhau
        test_phrases = [
            ("m ở spotify", "Spotify"),
            ("vào spotify", "Spotify"),
            ("nghe spotify", "Spotify"),
            ("spotify", "Spotify"),
            ("zalo", "Zalo"),
        ]
        for phrase, expected_app in test_phrases:
            with self.subTest(phrase=phrase):
                handled, rep = fast_path_nlu(phrase, app_index, dry_run=True)
                self.assertTrue(handled, f"Lệnh '{phrase}' phải được Fast-Path mở app xử lý")
                self.assertIn(f"Đã mở {expected_app}", rep)

    def test_8_phonetic_timer_and_short_timer(self):
        app_index = {}
        cases = [
            ("một 5 phút", "15 phút"),
            ("1 5 phút", "15 phút"),
            ("hẹn 5 phút", "5 phút"),
            ("hẹn giờ 10 phút", "10 phút"),
            ("15 phút", "15 phút"),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                ok, rep = fast_path_nlu(inp, app_index, dry_run=True)
                self.assertTrue(ok, f"Lệnh '{inp}' phải khớp Fast-Path hẹn giờ")
                self.assertIn(expected, rep)

    def test_9_firefox_phonetic_variations_and_launch(self):
        """Kiểm tra nhận diện toàn diện các dị âm và tên gọi của Firefox."""
        app_index = {
            "firefox": {"name": "Firefox", "desktop_id": "firefox.desktop", "exec": "firefox"},
        }
        cases = [
            "mở phai phốc",
            "mở 5 phút",
            "mở năm phút",
            "mở 5p",
            "mở firefox",
            "m ở firefox",
            "mở fire fox",
            "mở phai fox",
            "mở phai phót",
            "mở phai phó",
            "mở file fox",
            "mở fay fox",
            "mở cáo lửa",
            "bật firefox lên",
            "firefox",
            "phai fox",
            "cáo lửa",
        ]
        for phrase in cases:
            with self.subTest(phrase=phrase):
                ok, rep = fast_path_nlu(phrase, app_index, dry_run=True)
                self.assertTrue(ok, f"Lệnh '{phrase}' phải được Fast-Path mở Firefox")
                self.assertIn("Đã mở Firefox", rep)

    def test_10_volume_phonetics_recovery(self):
        """Kiểm tra phục hồi các dị âm của câu lệnh tăng/giảm âm lượng."""
        app_index = {}
        cases = [
            ("tính âm lượng", "tăng âm lượng"),
            ("tinh, âm lương", "tăng âm lượng"),
            ("thanh âm lường", "tăng âm lượng"),
            ("tênh âm lưỡng", "tăng âm lượng"),
            ("tánh âm lường", "tăng âm lượng"),
            ("giảm âm nương", "giảm âm lượng"),
        ]
        for phrase, _ in cases:
            with self.subTest(phrase=phrase):
                ok, rep = fast_path_nlu(phrase, app_index, dry_run=True)
                self.assertTrue(ok, f"Lệnh '{phrase}' phải được Fast-Path âm lượng xử lý")
                self.assertTrue(
                    any(w in rep for w in ["tăng âm lượng", "tăng thêm", "cho loa to lên", "giảm âm lượng", "nhỏ bớt", "cho loa nhỏ lại"]),
                    f"Phản hồi '{rep}' không phải là phản hồi âm lượng hợp lệ"
                )

    def test_11_music_phonetics_recovery(self):
        """Kiểm tra phục hồi các dị âm của câu lệnh phát nhạc."""
        app_index = {}
        cases = [
            ("phát nghiệm", "tiếp tục phát nhạc"),
            ("các nhiệm", "tiếp tục phát nhạc"),
            ("thác nhạc", "tiếp tục phát nhạc"),
            ("phát nhạt", "tiếp tục phát nhạc"),
        ]
        for phrase, _ in cases:
            with self.subTest(phrase=phrase):
                ok, rep = fast_path_nlu(phrase, app_index, dry_run=True)
                self.assertTrue(ok, f"Lệnh '{phrase}' phải được Fast-Path phát nhạc xử lý")
                self.assertIn("tiếp tục phát nhạc", rep)

if __name__ == "__main__":
    unittest.main()

