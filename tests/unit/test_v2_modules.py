"""
Unit test kiểm thử các module cơ bản của Voice AI V2.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.config import APP_ALIASES, EXIT_PHRASES
from ai_assistant.core.nlu import is_exit_phrase, clean_user_input, fast_path_nlu
from ai_assistant.ai.model_router import route_task
from ai_assistant.tools.system import get_vietnamese_time, get_vietnamese_date, parse_simple_math
from ai_assistant.speech.tts import sanitize_text_for_voice
from ai_assistant.ipc.server import get_socket_path

class TestVoiceAIV2(unittest.TestCase):
    def test_nlu_exit_phrases(self):
        self.assertTrue(is_exit_phrase("tạm biệt nhé"))
        self.assertTrue(is_exit_phrase("cảm ơn bạn"))
        self.assertTrue(is_exit_phrase("dừng lại"))
        self.assertFalse(is_exit_phrase("cảm ơn, giờ giúp tôi mở Zalo lên ngay"))

    def test_clean_user_input(self):
        self.assertEqual(clean_user_input("Alexa ơi mấy giờ rồi?"), "mấy giờ rồi?")
        self.assertEqual(clean_user_input("Ê Jarvis mở VS Code giúp tôi"), "mở VS Code giúp tôi")
        self.assertEqual(clean_user_input("Chào Alexa, mở trình duyệt lên"), "mở trình duyệt lên")

    def test_model_router(self):
        model, role, opts = route_task("Fix bug Hibernate N+1 query trong Spring Boot giúp tôi")
        self.assertIn("Coder", role)
        self.assertEqual(opts["temperature"], 0.2)

        model, role, opts = route_task("Hãy phân tích logic và so sánh chuyên sâu ưu nhược điểm")
        self.assertIn("Logic", role)

        model, role, opts = route_task("Mở trình duyệt lên")
        self.assertIn("Fast", role)

    def test_system_time_date(self):
        t_str = get_vietnamese_time()
        self.assertTrue("Bây giờ là" in t_str and "giờ" in t_str)

        d_str = get_vietnamese_date()
        self.assertTrue("Hôm nay là" in d_str and "tháng" in d_str)

    def test_math_calculation(self):
        self.assertEqual(parse_simple_math("15 cộng 27"), "15 cộng 27 bằng 42.")
        self.assertEqual(parse_simple_math("100 chia 4"), "100 chia 4 bằng 25.")

    def test_sanitize_voice(self):
        text = "**Thông báo**: CPU đang chạy 85% và 16GB RAM lúc 14:30!"
        cleaned = sanitize_text_for_voice(text)
        self.assertNotIn("**", cleaned)
        self.assertIn("85 phần trăm", cleaned)
        self.assertIn("16 ghi ga", cleaned)
        self.assertIn("14 giờ 30 phút", cleaned)

    def test_fast_path_dry_run(self):
        app_index = {"visual studio code": {"name": "Visual Studio Code", "desktop_id": "code.desktop", "exec": "code"}}
        handled, reply = fast_path_nlu("mấy giờ rồi", app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Bây giờ là", reply)

        handled, reply = fast_path_nlu("mở vs code", app_index, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Visual Studio Code", reply)

        handled, reply = fast_path_nlu("hôm nay thời tiết thế nào tại Hà Nội", app_index, dry_run=True)
        self.assertTrue(handled)

if __name__ == "__main__":
    unittest.main()
