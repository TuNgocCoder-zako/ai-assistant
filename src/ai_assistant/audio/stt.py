"""
Nhận diện giọng nói siêu tốc tiếng Việt bằng Faster-Whisper & Silero VAD.
"""

import os
import re
import numpy as np
import ctranslate2
from scipy.signal import sosfilt
from faster_whisper import WhisperModel
from faster_whisper.vad import get_speech_timestamps, VadOptions

from ai_assistant.config import SAMPLE_RATE, WHISPER_INITIAL_PROMPT, SPAM_PATTERNS
from ai_assistant.audio.capture import SOS_FILTER

# Preload NVIDIA CUDA cuBLAS/cuDNN nếu có trong virtualenv
try:
    import ctypes
    import nvidia.cublas.lib
    cublas_dir = list(nvidia.cublas.lib.__path__)[0]
    for lib_name in ["libcublasLt.so.12", "libcublas.so.12"]:
        p = os.path.join(cublas_dir, lib_name)
        if os.path.exists(p):
            ctypes.CDLL(p, mode=ctypes.RTLD_GLOBAL)
except Exception:
    pass

def load_whisper_model(selected_model: str = "small") -> tuple[WhisperModel, str, str]:
    """Khởi tạo mô hình Faster-Whisper (tự động ưu tiên CUDA GPU RTX)."""
    has_cuda = ctranslate2.get_cuda_device_count() > 0
    stt_device = "cuda" if has_cuda else "cpu"
    stt_compute_type = "int8_float16" if has_cuda else "int8"
    stt_threads = 1 if has_cuda else 4

    stt_model = WhisperModel(selected_model, device=stt_device, compute_type=stt_compute_type, cpu_threads=stt_threads)
    return stt_model, stt_device, stt_compute_type

def filter_speech_with_vad(audio: np.ndarray) -> np.ndarray:
    """Lọc thông cao và áp dụng Silero VAD để chỉ giữ lại phần có tiếng người nói."""
    if len(audio) == 0:
        return np.array([], dtype=np.float32)

    filtered_audio = sosfilt(SOS_FILTER, audio).astype(np.float32)
    vad_opts = VadOptions(
        threshold=0.55,
        min_speech_duration_ms=250,
        min_silence_duration_ms=300,
        speech_pad_ms=150
    )
    speech_timestamps = get_speech_timestamps(filtered_audio, vad_opts)
    total_speech_ms = sum(ts['end'] - ts['start'] for ts in speech_timestamps) / (SAMPLE_RATE / 1000)

    if not speech_timestamps or total_speech_ms < 250:
        return np.array([], dtype=np.float32)

    speech_chunks = [filtered_audio[ts['start']:ts['end']] for ts in speech_timestamps]
    return np.concatenate(speech_chunks)

def is_whisper_hallucination(text: str) -> bool:
    """Kiểm tra xem kết quả Whisper có phải là ảo giác hoặc lặp từ không."""
    if not text or len(text) < 2:
        return True

    t = text.lower().strip()
    if t in [".", "..", "...", "!", "xin chào.", "hẹn gặp lại."]:
        return True

    if any(re.search(p, t, re.IGNORECASE) for p in SPAM_PATTERNS):
        return True

    words = t.split()
    if len(words) >= 4:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.4:
            return True

    return False

def transcribe_audio(stt_model: WhisperModel, audio: np.ndarray) -> str:
    """Chuyển đổi âm thanh thành văn bản với bộ lọc khử ảo giác nghiêm ngặt."""
    segments, _ = stt_model.transcribe(
        audio,
        language="vi",
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        no_speech_threshold=0.50,
        repetition_penalty=1.15,
        initial_prompt=WHISPER_INITIAL_PROMPT,
        vad_filter=True,
        vad_parameters=dict(threshold=0.55, min_speech_duration_ms=250)
    )

    valid_segments = []
    for s in segments:
        if s.no_speech_prob < 0.45 and s.avg_logprob > -0.90:
            t_str = s.text.strip()
            if t_str and len(t_str) > 1:
                valid_segments.append(t_str)

    raw_text = " ".join(valid_segments).strip()
    return raw_text
