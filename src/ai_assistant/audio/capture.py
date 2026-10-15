"""
Thu âm và tiền xử lý tín hiệu âm thanh microphone (DSP, Schmitt Trigger VAD, AGC).
"""

from collections import deque
import sys
import numpy as np
import sounddevice as sd
from scipy.signal import butter, sosfilt
from ai_assistant.config import SAMPLE_RATE
from ai_assistant.speech.player import interrupt_speech_event

# Bộ lọc thông cao cắt tần số dưới 85Hz (khử tiếng ù quạt gió, chấn động bàn phím, tạp âm điện)
SOS_FILTER = butter(4, 85, 'hp', fs=SAMPLE_RATE, output='sos')

def normalize_audio(audio: np.ndarray, target_peak: float = 0.90, max_gain: float = 6.0, ambient_noise: float = 0.015) -> np.ndarray:
    """
    Chuẩn hóa biên độ âm thanh thông minh (Automatic Gain Control có trần nhiễu):
    - Tự động khuếch đại giọng nói nếu nói nhỏ hoặc ngồi xa micro.
    - Giới hạn trần tăng âm lượng sao cho tiếng ồn nền (quạt gió, rung) không bị khuếch đại quá mức.
    - Giúp Whisper nhận diện tròn vành rõ chữ từng phụ âm và dấu thanh tiếng Việt.
    """
    if len(audio) == 0:
        return audio
    max_val = np.max(np.abs(audio))
    if max_val > 0.005:
        noise_gain_cap = 0.22 / max(ambient_noise, 0.01)
        gain = min(target_peak / max_val, max_gain, noise_gain_cap)
        return audio * gain
    return audio

def record_audio(max_duration: float = 8.0, silence_timeout: float = 1.2, max_wait_for_speech: float = 3.5) -> tuple[np.ndarray, float]:
    """
    Thu âm giọng nói từ micro với hiệu chuẩn thích ứng môi trường thời gian thực:
    - Đo độ ồn nền thực tế (quạt laptop, phòng) trong 400ms đầu tiên để tính ngưỡng kích hoạt động.
    - Chống kích hoạt giả do tiếng quạt gió hoặc chấn động bàn phím.
    - Pre-roll ring buffer (500ms) giữ trọn vẹn phụ âm đầu câu, không nuốt chữ.
    - Tự động ngắt khi phát hiện khoảng lặng tự nhiên.
    """
    chunk_len = 1600  # 100ms ở 16kHz
    frames = []
    ambient_chunks = []
    preroll_buffer = deque(maxlen=6)  # Lưu 600ms âm thanh trước khi kích hoạt (chống nuốt phụ âm đầu)
    has_spoken = False
    silence_chunks = 0
    spoken_chunks = 0
    max_chunks = int(max_duration * (SAMPLE_RATE / chunk_len))
    wait_limit = int(max_wait_for_speech * (SAMPLE_RATE / chunk_len))

    ambient_noise = 0.010
    speech_trigger_threshold = 0.028
    silence_threshold = 0.018

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32') as stream:
        try:
            if stream.read_available > 0:
                stream.read(stream.read_available)
        except Exception:
            pass

        for i in range(max_chunks):
            if interrupt_speech_event.is_set():
                print("\n🛑 Đã nhận tín hiệu hủy thu âm.")
                return np.array([], dtype=np.float32), ambient_noise

            data, _ = stream.read(chunk_len)
            chunk = data.flatten()

            # Lọc rung tần số thấp trước khi tính RMS
            filtered_chunk = sosfilt(SOS_FILTER, chunk).astype(np.float32)
            rms = np.sqrt(np.mean(filtered_chunk**2))

            if sys.stdout.isatty():
                bars = int(min(rms / 0.12, 1.0) * 8)
                meter = "█" * bars + "░" * (8 - bars)
                status_text = "Đang nhận giọng nói..." if has_spoken else "Đang chờ bạn nói..."
                print(f"\r🎙️ Mic: [{meter}] | {status_text}  ", end="", flush=True)

            if i < 4:
                ambient_chunks.append(rms)
                preroll_buffer.append(chunk)
                continue
            elif i == 4:
                preroll_buffer.append(chunk)
                ambient_noise = float(np.mean(ambient_chunks))
                speech_trigger_threshold = min(max(ambient_noise * 1.7, ambient_noise + 0.015, 0.024), 0.065)
                silence_threshold = min(max(ambient_noise * 1.25, ambient_noise + 0.008, 0.016), 0.045)
                continue

            if not has_spoken:
                preroll_buffer.append(chunk)
                if rms > speech_trigger_threshold:
                    has_spoken = True
                    frames.extend(list(preroll_buffer))
                    silence_chunks = 0
                    spoken_chunks = 1
                elif i >= wait_limit:
                    if sys.stdout.isatty():
                        print()
                    return np.array([], dtype=np.float32), ambient_noise
            else:
                frames.append(chunk)
                spoken_chunks += 1

                # Two-Phase Dynamic Silence Timeout:
                # - Câu dài (>= 1.5s): ngắt ngay sau 450ms im lặng để phản hồi tức thì (<0.5s)
                # - Câu trung bình (>= 0.8s): chờ 650ms
                # - Câu ngắn (< 0.8s): giữ silence_timeout tránh ngắt nhầm khi người dùng dừng suy nghĩ
                if spoken_chunks >= 15:
                    silence_limit = max(4, int(0.45 * (SAMPLE_RATE / chunk_len)))
                elif spoken_chunks >= 8:
                    silence_limit = max(6, int(0.65 * (SAMPLE_RATE / chunk_len)))
                else:
                    silence_limit = int(silence_timeout * (SAMPLE_RATE / chunk_len))

                if rms > silence_threshold:
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= silence_limit:
                        break

    if sys.stdout.isatty():
        print()
    if not frames or not has_spoken or spoken_chunks < 2:
        return np.array([], dtype=np.float32), ambient_noise
    return np.concatenate(frames), ambient_noise
