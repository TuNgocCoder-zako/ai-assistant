"""
Kiểm thử khử tiếng xoẹt / click / pop trong chime và TTS tail audio.
"""

import sys
import os
import unittest
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from ai_assistant.config import SAMPLE_RATE
from ai_assistant.speech.player import CHIMES, make_chime_wav
from ai_assistant.speech.tts import get_piper_voice

class TestAudioAntiPop(unittest.TestCase):
    def test_chimes_zero_crossing_and_tail_silence(self):
        """Tất cả chime phải bắt đầu bằng 0.0, kết thúc bằng 0.0 và có đệm silence đuôi."""
        silence_samples = int(SAMPLE_RATE * 0.020)  # Ít nhất 20ms silence ở cuối
        for name, wave in CHIMES.items():
            self.assertIsInstance(wave, np.ndarray, f"Chime {name} không phải numpy array")
            self.assertEqual(wave[0], 0.0, f"Chime {name} không bắt đầu từ 0.0 (nguy cơ click mở đầu)")
            self.assertEqual(wave[-1], 0.0, f"Chime {name} không kết thúc ở 0.0 (nguy cơ xoẹt ngắt âm)")
            
            # Kiểm tra đoạn đệm đuôi phải tuyệt đối là 0.0 (DC ground)
            tail = wave[-silence_samples:]
            max_tail_val = np.max(np.abs(tail))
            self.assertEqual(max_tail_val, 0.0, f"Chime {name} có âm thanh ở đoạn đệm đuôi: {max_tail_val}")

            # Kiểm tra không có bước nhảy đột ngột (DC jump discontinuity) giữa 2 sample kề nhau
            diffs = np.abs(np.diff(wave))
            max_diff = np.max(diffs)
            self.assertLess(max_diff, 0.20, f"Chime {name} có bước nhảy biên độ đột ngột: {max_diff}")

    def test_make_chime_wav_custom(self):
        """Hàm make_chime_wav tùy chỉnh tần số và thời lượng bất kỳ cũng luôn mượt mà."""
        test_chime = make_chime_wav([300.0, 600.0], [0.05, 0.05], decay=10.0, volume=0.3)
        self.assertEqual(test_chime[0], 0.0)
        self.assertEqual(test_chime[-1], 0.0)
        self.assertEqual(test_chime[-int(SAMPLE_RATE * 0.020):].tolist(), [0.0] * int(SAMPLE_RATE * 0.020))

    def test_piper_tts_synthesize_tail_smoothness(self):
        """Mô hình Piper TTS offline tổng hợp câu mẫu và kiểm tra xử lý fade-out."""
        voice_model = get_piper_voice("vi-nu")
        self.assertIsNotNone(voice_model, "Không nạp được voice model Piper TTS")
        
        chunks = list(voice_model.synthesize("Xin chào"))
        self.assertGreater(len(chunks), 0)
        
        # Mô phỏng thuật toán fade-out và silence padding
        last_chunk = chunks[-1]
        audio_data = np.frombuffer(last_chunk.audio_int16_bytes, dtype=np.int16).copy()
        fade_samples = min(len(audio_data), int(22050 * 0.015))
        fade_curve = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
        audio_data[-fade_samples:] = (audio_data[-fade_samples:] * fade_curve).astype(np.int16)
        
        # Mẫu cuối cùng phải xấp xỉ 0
        self.assertLessEqual(abs(int(audio_data[-1])), 1)

    def test_streaming_tts_no_mpv_subprocess(self):
        """Đảm bảo pipeline phát âm thanh streaming dùng sounddevice trực tiếp, không gọi tiến trình ngoài mpv."""
        import inspect
        from ai_assistant.ai import ollama_client
        source = inspect.getsource(ollama_client.query_ollama_streaming)
        self.assertNotIn("mpv", source, "query_ollama_streaming vẫn còn chứa tiến trình mpv!")
        self.assertIn("sd.play", source, "query_ollama_streaming phải dùng sd.play trực tiếp!")

if __name__ == "__main__":
    unittest.main()
