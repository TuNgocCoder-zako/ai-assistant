"""
Unit tests kiểm thử giả lập (Mock) cho Ollama Client và Audio Streaming.
Cho phép chạy kiểm thử độc lập mà không cần micro, GPU hay Ollama daemon thực tế.
"""

import unittest
from unittest.mock import patch, MagicMock
import numpy as np

from ai_assistant.config import assistant_config, AssistantConfig
from ai_assistant.ai.ollama_client import _ollama_session
from ai_assistant.audio.stt import filter_speech_with_vad

class TestMockedOllamaAndAudio(unittest.TestCase):
    def test_assistant_config_preflight_verifier(self):
        """Kiểm tra phương thức verify_required_assets hoạt động chuẩn xác."""
        cfg = AssistantConfig()
        missing = cfg.verify_required_assets()
        # Piper model đã có trong repo nên missing không chứa Piper TTS Model
        piper_missing = any("Piper TTS Model" in m for m in missing)
        self.assertFalse(piper_missing)

    def test_ollama_session_has_retry_and_timeout_adapters(self):
        """Kiểm tra session gọi Ollama được gắn adapter HTTP/HTTPS với retry."""
        http_adapter = _ollama_session.get_adapter("http://localhost:11434")
        self.assertIsNotNone(http_adapter)
        self.assertEqual(http_adapter.max_retries.total, 2)

    @patch("ai_assistant.ai.ollama_client._ollama_session.post")
    def test_query_ollama_streaming_mocked(self, mock_post):
        """Kiểm tra luồng xử lý phản hồi stream khi Ollama trả về dòng JSON hợp lệ."""
        from ai_assistant.ai.ollama_client import query_ollama_streaming
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = [
            b'{"message": {"role": "assistant", "content": "Xin ch\xc3\xa0o b\xe1\xba\xa1n."}}',
            b'{"message": {"role": "assistant", "content": " T\xc3\xb4i l\xc3\xa0 Alexa."}}',
        ]
        mock_post.return_value = mock_resp

        with patch("ai_assistant.ai.ollama_client.sd.play"):
            reply = query_ollama_streaming("Xin chào", app_index={})
            self.assertIn("Xin chào bạn", reply)

    def test_filter_speech_with_vad_empty_audio(self):
        """Kiểm tra hàm VAD xử lý mảng rỗng mà không văng ngoại lệ."""
        empty = np.array([], dtype=np.float32)
        out = filter_speech_with_vad(empty)
        self.assertEqual(len(out), 0)

    def test_filter_speech_with_vad_pure_silence(self):
        """Kiểm tra hàm VAD lọc bỏ hoàn toàn đoạn im lặng vô nghĩa."""
        silence = np.zeros(16000, dtype=np.float32)
        out = filter_speech_with_vad(silence)
        self.assertEqual(len(out), 0)

if __name__ == "__main__":
    unittest.main()
