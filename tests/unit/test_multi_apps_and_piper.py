"""
Kiểm thử tính năng Mở/Đóng nhiều ứng dụng đồng thời và Piper TTS Fine-Tuned Offline (Loại bỏ Edge-TTS).
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.core.nlu import fast_path_nlu, clean_user_input
from ai_assistant.tools.apps import launch_multiple_targets, close_specific_app
from ai_assistant.speech.tts import get_piper_voice, sanitize_text_for_voice
from ai_assistant.config import TTS_ENGINE, DEFAULT_VOICE, DEFAULT_VOICE_MALE

class TestMultiAppsAndPiper(unittest.TestCase):
    def setUp(self):
        self.app_index = {
            "visual studio code": {"name": "Visual Studio Code", "desktop_id": "code.desktop", "exec": "code"},
            "zalo": {"name": "Zalo", "desktop_id": "zalo.desktop", "exec": "zalo"},
            "spotify": {"name": "Spotify", "desktop_id": "spotify.desktop", "exec": "spotify"},
            "brave": {"name": "Brave", "desktop_id": "brave.desktop", "exec": "brave"},
            "kitty": {"name": "Kitty", "desktop_id": "kitty.desktop", "exec": "kitty"},
        }

    def test_multi_app_open_web_and_web(self):
        handled, reply = fast_path_nlu("Mở Youtube và Facebook", self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("YouTube", reply)
        self.assertIn("Facebook", reply)

    def test_multi_app_open_app_and_app(self):
        handled, reply = fast_path_nlu("Mở Zalo và VS Code", self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Zalo", reply)
        self.assertIn("Visual Studio Code", reply)

    def test_multi_app_open_mixed_three_targets(self):
        handled, reply = fast_path_nlu("Mở YouTube, Facebook và GitHub", self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("YouTube", reply)
        self.assertIn("Facebook", reply)
        self.assertIn("GitHub", reply)

    def test_multi_app_open_with_conjunction(self):
        handled, reply = fast_path_nlu("Bật Spotify với Visual Studio Code", self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Spotify", reply)
        self.assertIn("Visual Studio Code", reply)

    def test_multi_app_close_two_targets(self):
        handled, reply = fast_path_nlu("Đóng Youtube và Facebook", self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("YouTube", reply)
        self.assertIn("Facebook", reply)

    def test_multi_app_close_desktop_apps(self):
        handled, reply = fast_path_nlu("Tắt Zalo và VS Code", self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Zalo", reply)
        self.assertTrue("Visual Studio Code" in reply or "VS Code" in reply)

    def test_whisper_phoneme_auto_correction(self):
        # Kiểm tra tự động sửa lỗi nhận diện của Whisper
        cleaned = clean_user_input("Tạch tân duyệt")
        self.assertEqual(cleaned, "tắt trình duyệt")
        handled, reply = fast_path_nlu(cleaned, self.app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Đã đóng", reply)

    def test_piper_tts_offline_engine_configured(self):
        self.assertEqual(TTS_ENGINE, "piper")
        # Nạp mô hình nữ
        v_female = get_piper_voice(DEFAULT_VOICE)
        self.assertIsNotNone(v_female)
        # Nạp mô hình nam
        v_male = get_piper_voice(DEFAULT_VOICE_MALE)
        self.assertIsNotNone(v_male)

    def test_edge_tts_removed(self):
        # Đảm bảo không còn module edge_tts nào trong ai_assistant
        with self.assertRaises(ImportError):
            import edge_tts  # edge_tts đã bị gỡ khỏi venv hoàn toàn

if __name__ == "__main__":
    unittest.main()
