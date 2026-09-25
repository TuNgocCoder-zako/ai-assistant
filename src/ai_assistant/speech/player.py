"""
Trình quản lý phát âm thanh, hiệu ứng chime (earcons) và cắt lời (Barge-in).
"""

import time
import queue
import threading
import subprocess
import numpy as np
import sounddevice as sd
from ai_assistant.config import SAMPLE_RATE

trigger_event = threading.Event()
interrupt_speech_event = threading.Event()

current_tts_proc = None
_tts_proc_lock = threading.Lock()
_tts_last_end_time = 0.0
tts_queue = queue.Queue()

def get_last_tts_end_time() -> float:
    return _tts_last_end_time

def set_last_tts_end_time(t: float = None):
    global _tts_last_end_time
    _tts_last_end_time = time.time() if t is None else t

def make_chime_wav(freqs: list, durs: list, decay: float = 10.0, volume: float = 0.25) -> np.ndarray:
    """
    Tổng hợp âm thanh phản hồi dạng sóng sin ấm áp (Acoustic Tone), êm dịu, không chói gắt:
    - Frequencies dải trung ấm (G4-C5 ~ 392Hz - 523Hz) tạo cảm giác dễ chịu, gần gũi.
    - Attack ramp 10ms loại bỏ hoàn toàn tiếng click/pop mở đầu.
    - Hài âm mềm mại (85% fundamental, 12% 2nd, 3% 3rd) mô phỏng tiếng marimba / phím đàn Rhodes.
    - Âm lượng tối ưu vừa đủ nghe (volume ~ 0.20 - 0.25) không gây giật mình.
    """
    chunks = []
    attack_samples = int(SAMPLE_RATE * 0.010)  # 10ms fade-in êm mượt
    for f, d in zip(freqs, durs):
        n_samples = int(SAMPLE_RATE * d)
        t = np.linspace(0, d, n_samples, False)
        wave = 0.85 * np.sin(2 * np.pi * f * t) + 0.12 * np.sin(4 * np.pi * f * t) + 0.03 * np.sin(6 * np.pi * f * t)
        env = np.exp(-decay * t)
        if n_samples > attack_samples:
            env[:attack_samples] *= np.linspace(0.0, 1.0, attack_samples)
        chunks.append(volume * wave * env)
    return np.concatenate(chunks).astype(np.float32)

CHIMES = {
    # 1. Wake Chime: Hai nốt tăng dần ấm áp G4 (392Hz) -> C5 (523.25Hz), êm dịu phong cách Google / Siri
    "wake": make_chime_wav([392.0, 523.25], [0.08, 0.15], decay=9.0, volume=0.24),
    # 2. Sleep / Cancel Chime: Hai nốt hạ dần êm ái C5 (523.25Hz) -> G4 (392Hz)
    "sleep": make_chime_wav([523.25, 392.0], [0.07, 0.13], decay=12.0, volume=0.20),
    # 3. Ack Chime: Nốt C5 nhẹ nhàng (80ms) êm tai thay thế hoàn toàn tiếng bíp cao tần chói tai
    "ack": make_chime_wav([523.25], [0.08], decay=15.0, volume=0.20),
    # 4. Alarm Chime: Hợp âm rải C-Major ấm áp vui tươi (C4 -> E4 -> G4 -> C5)
    "alarm": make_chime_wav([261.63, 329.63, 392.0, 523.25], [0.10, 0.10, 0.10, 0.22], decay=8.0, volume=0.25)
}

def play_chime(name: str):
    """Phát âm thanh earcon trực tiếp qua sounddevice trong vài mili-giây mà không chặn."""
    audio = CHIMES.get(name)
    if audio is not None:
        try:
            sd.play(audio, samplerate=SAMPLE_RATE, blocking=False)
        except Exception:
            pass

def reap_process(proc, timeout: float = 1.0):
    """
    Thu hồi và dọn sạch tiến trình con (chống rò rỉ Zombie process mpv).
    Đảm bảo PID được giải phóng hoàn toàn khỏi kernel.
    """
    if proc is None:
        return
    try:
        if proc.poll() is None:
            if proc.stdin and not proc.stdin.closed:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=timeout)
        else:
            proc.poll()
    except Exception:
        pass

def stop_current_speech():
    """Cắt lời ngay lập tức: Dừng tiến trình phát âm thanh và dọn sạch hàng đợi câu nói."""
    global current_tts_proc
    interrupt_speech_event.set()

    with _tts_proc_lock:
        proc = current_tts_proc
        current_tts_proc = None

    reap_process(proc, timeout=1.0)

    # Xả sạch tts_queue
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except Exception:
            break
    play_chime("sleep")
    try:
        from ai_assistant.core.state import set_assistant_state
        set_assistant_state("idle")
    except Exception:
        pass
