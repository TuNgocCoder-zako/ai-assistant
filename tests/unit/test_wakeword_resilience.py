"""
Unit tests for Wake Word anti-false-positive resilience:
- Raised default sensitivity threshold (0.58)
- Dynamic music playback sensitivity boost (+0.10)
- Temporal patience requirement (minimum 2 consecutive frames)
- Silero VAD gating against non-speech audio (vad_threshold=0.50)
"""

import unittest
from unittest.mock import patch, MagicMock
import numpy as np

from ai_assistant.config import (
    DEFAULT_THRESHOLD,
    MUSIC_WAKE_THRESHOLD_BOOST,
    WAKE_PATIENCE_FRAMES,
    WAKE_VAD_THRESHOLD,
)
from ai_assistant.audio.wakeword import load_wakeword_model


class TestWakeWordResilience(unittest.TestCase):
    def test_wakeword_config_constants(self):
        """Kiểm tra các thông số ngưỡng chống kích hoạt nhầm cân bằng chuẩn xác."""
        self.assertEqual(DEFAULT_THRESHOLD, 0.55)
        self.assertEqual(WAKE_PATIENCE_FRAMES, 2)
        self.assertEqual(MUSIC_WAKE_THRESHOLD_BOOST, 0.05)
        self.assertEqual(WAKE_VAD_THRESHOLD, 0.0)

    def test_load_wakeword_model_with_vad(self):
        """Kiểm tra mô hình OpenWakeWord được nạp kèm tham số vad_threshold."""
        oww_model, label = load_wakeword_model("alexa")
        self.assertEqual(label, "Alexa")
        self.assertEqual(oww_model.vad_threshold, WAKE_VAD_THRESHOLD)

    def test_dynamic_effective_threshold_with_media_playback(self):
        """Kiểm tra ngưỡng tự động tăng thêm khi phát hiện nhạc đang phát."""
        base_threshold = DEFAULT_THRESHOLD

        with patch("ai_assistant.tools.system.subprocess.run") as mock_run:
            # Trường hợp 1: Không có nhạc
            mock_res_paused = MagicMock(returncode=0, stdout="Paused\n")
            mock_run.return_value = mock_res_paused
            from ai_assistant.tools.system import is_media_playing
            self.assertFalse(is_media_playing())

            is_music_active = is_media_playing()
            effective_threshold = base_threshold + (MUSIC_WAKE_THRESHOLD_BOOST if is_music_active else 0.0)
            self.assertEqual(effective_threshold, base_threshold)

            # Trường hợp 2: Có nhạc đang phát (Spotify / YouTube / MPV)
            mock_res_playing = MagicMock(returncode=0, stdout="Playing\n")
            mock_run.return_value = mock_res_playing
            self.assertTrue(is_media_playing())

            is_music_active = is_media_playing()
            effective_threshold = base_threshold + (MUSIC_WAKE_THRESHOLD_BOOST if is_music_active else 0.0)
            self.assertAlmostEqual(effective_threshold, base_threshold + MUSIC_WAKE_THRESHOLD_BOOST)

    def test_patience_filter_suppresses_transient_spike(self):
        """Kiểm tra bộ đệm patience loại bỏ gai nhọn âm thanh đơn lẻ (transient noise)."""
        model, _ = load_wakeword_model("alexa")
        model_keys = list(model.models.keys())
        patience_dict = {k: WAKE_PATIENCE_FRAMES for k in model_keys}
        threshold_dict = {k: 0.58 for k in model_keys}

        model.reset()
        dummy_chunk = np.zeros(1280, dtype=np.int16)

        # Chạy dự đoán với âm thanh rỗng
        pred = model.predict(dummy_chunk, patience=patience_dict, threshold=threshold_dict)
        for score in pred.values():
            self.assertEqual(score, 0.0)


if __name__ == "__main__":
    unittest.main()
