"""
Unit test kiểm thử các module cơ bản của Voice AI V2.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.config import APP_ALIASES, EXIT_PHRASES
from ai_assistant.core.nlu import is_exit_phrase, clean_user_input, fast_path_nlu
from ai_assistant.ai.model_router import route_task, get_dynamic_num_predict
from ai_assistant.tools.system import get_vietnamese_time, get_vietnamese_date, parse_simple_math
from ai_assistant.speech.tts import sanitize_text_for_voice, fix_vietnamese_sticky_tokens, trim_incomplete_sentence
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
        self.assertTrue(role.startswith("Fast"))
        self.assertIn(opts["temperature"], [0.3, 0.6])

        model, role, opts = route_task("Hãy phân tích logic và so sánh chuyên sâu ưu nhược điểm")
        self.assertTrue(role.startswith("Fast"))

        model, role, opts = route_task("Mở trình duyệt lên")
        self.assertTrue(role.startswith("Fast"))

        # Kiểm tra cấp phát token động
        self.assertEqual(get_dynamic_num_predict("Trái đất là gì"), 260)
        self.assertEqual(get_dynamic_num_predict("Cảm ơn bạn nhé"), 80)
        self.assertEqual(get_dynamic_num_predict("Hôm nay trời đẹp không"), 140)
        self.assertEqual(get_dynamic_num_predict("Trái đất là gì", model_name="qwen3:4b"), 2048)
        self.assertEqual(get_dynamic_num_predict("Cảm ơn bạn nhé", model_name="qwen3:4b"), 1024)
        self.assertEqual(get_dynamic_num_predict("Hôm nay trời đẹp không", model_name="qwen3:4b"), 1500)

    def test_system_time_date(self):
        t_str = get_vietnamese_time()
        self.assertTrue("Bây giờ là" in t_str and "giờ" in t_str)

        d_str = get_vietnamese_date()
        self.assertTrue("Hôm nay là" in d_str and "tháng" in d_str)

    def test_math_calculation(self):
        self.assertEqual(parse_simple_math("15 cộng 27"), "15 cộng 27 bằng 42.")
        self.assertEqual(parse_simple_math("100 chia 4"), "100 chia 4 bằng 25.")
        self.assertEqual(parse_simple_math("1 trừ 3"), "1 trừ 3 bằng âm 2.")
        self.assertEqual(parse_simple_math("một trừ ba bằng bao nhiêu"), "1 trừ 3 bằng âm 2.")
        self.assertEqual(parse_simple_math("1 - 3"), "1 trừ 3 bằng âm 2.")
        self.assertEqual(parse_simple_math("1-3"), "1 trừ 3 bằng âm 2.")
        # Chuỗi nối gạch ngang hoặc ngày tháng không phải là phép tính nếu không có câu hỏi tính toán
        self.assertIsNone(parse_simple_math("1-2-3-4-5-1"))
        self.assertIsNone(parse_simple_math("2026-10-01"))
        self.assertIsNone(parse_simple_math("iPhone 14-15"))
        self.assertIsNone(parse_simple_math("phòng 10-12"))
        # Khi có câu hỏi hoặc biểu thức nhiều số hạng rõ ràng
        self.assertEqual(parse_simple_math("tính 1 - 2 - 3 - 4 - 5 - 1"), "Kết quả phép tính 1 - 2 - 3 - 4 - 5 - 1 bằng âm 14.")
        self.assertEqual(parse_simple_math("1 - 2 - 3 - 4 - 5 - 1 bằng mấy"), "Kết quả phép tính 1 - 2 - 3 - 4 - 5 - 1 bằng âm 14.")
        self.assertEqual(parse_simple_math("1 - 2 - 3 - 4 - 5 - 1"), "Kết quả phép tính 1 - 2 - 3 - 4 - 5 - 1 bằng âm 14.")
        self.assertEqual(parse_simple_math("tính 1-2-3-4-5-1"), "Kết quả phép tính 1-2-3-4-5-1 bằng âm 14.")

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

    def test_dynamic_num_predict(self):
        # 1. Câu hỏi khái niệm / tại sao / giải thích: 260 tokens
        self.assertEqual(get_dynamic_num_predict("Trái đất là gì?"), 260)
        self.assertEqual(get_dynamic_num_predict("Tại sao bầu trời màu xanh?"), 260)
        self.assertEqual(get_dynamic_num_predict("Giải thích nguyên lý hoạt động của Docker"), 260)
        self.assertEqual(get_dynamic_num_predict("Hãy phân tích ưu nhược điểm"), 260)

        # 2. Câu xã giao / chào hỏi / cảm ơn ngắn: 80 tokens
        self.assertEqual(get_dynamic_num_predict("Chào bạn nhé"), 80)
        self.assertEqual(get_dynamic_num_predict("Cảm ơn bạn nhiều"), 80)
        self.assertEqual(get_dynamic_num_predict("Tạm biệt"), 80)
        self.assertEqual(get_dynamic_num_predict("Ok được rồi"), 80)

        # 3. Câu thông thường: 140 tokens
        self.assertEqual(get_dynamic_num_predict("Mở trình duyệt lên giúp tôi"), 140)
        self.assertEqual(get_dynamic_num_predict("Bật quạt lên mức cao"), 140)

    def test_fix_vietnamese_sticky_tokens(self):
        # Test tách trợ từ / từ nối dính liền
        self.assertEqual(fix_vietnamese_sticky_tokens("Trái Đấtlà một hành tinh"), "Trái Đất là một hành tinh")
        self.assertEqual(fix_vietnamese_sticky_tokens("Hệ MặtTrờivà các hành tinh"), "Hệ Mặt Trời và các hành tinh")
        self.assertEqual(fix_vietnamese_sticky_tokens("Tôi đã làmđược bài này"), "Tôi đã làm được bài này")
        self.assertEqual(fix_vietnamese_sticky_tokens("ViệtNam là quê hương"), "Việt Nam là quê hương")
        self.assertEqual(fix_vietnamese_sticky_tokens("thếgiớinày"), "thếgiới này")

    def test_trim_incomplete_sentence(self):
        # Test tỉa câu lửng lơ về dấu chấm gần nhất
        raw1 = "Trái Đất là hành tinh thứ ba tính từ Mặt Trời. Đây là nơi duy nhất có sự sống với vận tốc"
        self.assertEqual(trim_incomplete_sentence(raw1), "Trái Đất là hành tinh thứ ba tính từ Mặt Trời.")

        # Test câu hoàn chỉnh giữ nguyên
        raw2 = "Trái Đất là hành tinh thứ ba! Bạn có biết điều này không?"
        self.assertEqual(trim_incomplete_sentence(raw2), raw2)

        # Test câu đơn không có dấu chấm tự động thêm chấm
        raw3 = "Tôi hiểu rồi"
        self.assertEqual(trim_incomplete_sentence(raw3), "Tôi hiểu rồi.")

        # Test câu đơn kết thúc bằng từ nối bị cắt bỏ từ nối
        raw4 = "Hệ thống đang hoạt động bình thường với"
        self.assertEqual(trim_incomplete_sentence(raw4), "Hệ thống đang hoạt động bình thường.")

    def test_hyprland_workspace_nlu(self):
        from ai_assistant.core.nlu import fast_path_nlu
        # Kiểm thử dry_run không gọi subprocess thật
        handled, rep = fast_path_nlu("chuyển sang workspace 2", {}, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("không gian làm việc số 2", rep)

        handled, rep = fast_path_nlu("đưa cửa sổ này sang workspace 3", {}, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("không gian làm việc số 3", rep)

        handled, rep = fast_path_nlu("chuyển thành cửa sổ nổi", {}, dry_run=True)
        self.assertTrue(handled)
        self.assertIn("cửa sổ nổi", rep)

if __name__ == "__main__":
    unittest.main()

