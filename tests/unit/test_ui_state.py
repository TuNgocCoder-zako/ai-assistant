"""
Unit tests cho UI State (Quickshell Overlay State & Long Response Card detection).
"""

import os
import unittest
import tempfile
from unittest.mock import patch

import ai_assistant.core.ui_state as ui_state_mod
from ai_assistant.core.ui_state import (
    set_assistant_state,
    get_assistant_state,
    assistant_state,
)

class TestUIState(unittest.TestCase):
    def setUp(self):
        # Dùng tempfile để test KHÔNG BAO GIỜ ghi đè lên file runtime thực tế của người dùng
        self.tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(self.tmp_fd)
        self.patcher = patch.object(ui_state_mod, "STATE_FILE_PATH", self.tmp_path)
        self.patcher.start()
        set_assistant_state("idle", clear_card=True)

    def tearDown(self):
        # Luôn đảm bảo trạng thái kết thúc ở idle và dọn dẹp file tạm
        set_assistant_state("idle", clear_card=True)
        self.patcher.stop()
        if os.path.exists(self.tmp_path):
            try:
                os.remove(self.tmp_path)
            except Exception:
                pass
        if os.path.exists(self.tmp_path + ".tmp"):
            try:
                os.remove(self.tmp_path + ".tmp")
            except Exception:
                pass

    def test_action_command_does_not_trigger_card(self):
        # 1. Câu lệnh mở ứng dụng
        set_assistant_state("speaking", text="Đã mở trình duyệt Google Chrome thành công trên hệ thống desktop của bạn.")
        st = get_assistant_state()
        self.assertFalse(st.get("is_long_text", False))
        self.assertEqual(st.get("long_answer", ""), "")

        # 2. Câu lệnh đặt âm lượng
        set_assistant_state("speaking", text="Đã đặt âm lượng hệ thống lên 80% theo yêu cầu của bạn.")
        st = get_assistant_state()
        self.assertFalse(st.get("is_long_text", False))

        # 3. Câu lệnh đóng cửa sổ
        set_assistant_state("speaking", text="Đã đóng cửa sổ hiện tại theo yêu cầu.")
        st = get_assistant_state()
        self.assertFalse(st.get("is_long_text", False))

    def test_short_answer_does_not_trigger_card(self):
        set_assistant_state("speaking", text="Bây giờ là 19 giờ 45 phút.")
        st = get_assistant_state()
        self.assertFalse(st.get("is_long_text", False))
        self.assertEqual(st.get("long_answer", ""), "")

    def test_long_explanatory_text_triggers_card(self):
        long_text = (
            "Buổi sáng sớm mang lại một không gian tĩnh lặng tuyệt đẹp, "
            "những hạt sương mai đọng trên từng tán lá non, "
            "ánh mặt trời rọi qua khe cửa mang theo một nguồn năng lượng trong lành và tươi mới."
        )
        set_assistant_state("speaking", text=long_text, query="viết đoạn văn về buổi sáng")
        st = get_assistant_state()
        self.assertTrue(st.get("is_long_text", False))
        self.assertEqual(st.get("long_answer"), long_text)
        self.assertEqual(st.get("query"), "viết đoạn văn về buổi sáng")

    def test_card_persists_during_idle_until_cleared(self):
        long_text = "Đây là một đoạn phân tích rất dài về kiến trúc Wayland so với X11, giải thích chi tiết cơ chế socket và compositor buffer sharing."
        set_assistant_state("speaking", text=long_text, query="phân tích wayland")
        
        # Khi chuyển sang idle (phát xong giọng nói), card vẫn phải giữ nguyên để người dùng đọc
        set_assistant_state("idle")
        st = get_assistant_state()
        self.assertEqual(st.get("status"), "idle")
        self.assertTrue(st.get("is_long_text", False))
        self.assertEqual(st.get("long_answer"), long_text)

        # Khi người dùng bắt đầu câu lệnh mới (clear_card=True)
        set_assistant_state("thinking", "Bạn: \"Mở chrome\"", query="Mở chrome", clear_card=True)
        st = get_assistant_state()
        self.assertFalse(st.get("is_long_text", False))
        self.assertEqual(st.get("long_answer"), "")

if __name__ == "__main__":
    unittest.main()
