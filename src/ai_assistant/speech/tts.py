"""
Tổng hợp giọng nói tiếng Việt bằng Piper TTS Fine-tuned (Offline 100%) và chuẩn hóa ngữ âm.
"""

import os
import re
import time
import threading
import subprocess
import numpy as np
import sounddevice as sd
from ai_assistant.config import DEFAULT_VOICE, DEFAULT_VOICE_MALE, PIPER_MODEL_PATH, PIPER_MODEL_MALE_PATH
from ai_assistant.core.state import set_assistant_state
from ai_assistant.speech import player

_piper_voices = {}
_piper_lock = threading.Lock()

def get_piper_voice(voice_or_path: str = None):
    """
    Nạp và lưu cache singleton mô hình Piper TTS tiếng Việt chạy ngoại tuyến (offline).
    Hỗ trợ cả giọng nữ phổ thông và giọng nam thanh niên tự tin fine-tuned.
    """
    global _piper_voices
    target_path = PIPER_MODEL_PATH
    if voice_or_path:
        v_low = str(voice_or_path).lower()
        if any(k in v_low for k in ["nam", "male", "thanh_nien", "boy"]):
            target_path = PIPER_MODEL_MALE_PATH
        elif os.path.exists(str(voice_or_path)):
            target_path = str(voice_or_path)

    with _piper_lock:
        if target_path not in _piper_voices:
            if os.path.exists(target_path):
                try:
                    from piper import PiperVoice
                    config_path = f"{target_path}.json" if os.path.exists(f"{target_path}.json") else None
                    _piper_voices[target_path] = PiperVoice.load(target_path, config_path=config_path)
                except Exception as e:
                    print(f"⚠️ Không thể nạp Piper TTS ({target_path}): {e}")
                    return None
            else:
                print(f"⚠️ Không tìm thấy tệp mô hình Piper tại: {target_path}")
                return None
        return _piper_voices.get(target_path)

UPPER_CHARS = 'A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴĐ'
LOWER_CHARS = 'a-zàáảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ'

STICKY_PARTICLES = [
    'là', 'và', 'của', 'được', 'có', 'trong', 'với', 'cho', 'đã', 'sẽ',
    'đang', 'thì', 'mà', 'ở', 'về', 'ra', 'vào', 'lại', 'một', 'các',
    'những', 'như', 'này', 'đó', 'khi', 'để', 'bởi', 'do', 'từ', 'lên',
    'xuống', 'rất', 'quá', 'nhiều', 'hơn', 'nhất', 'không', 'nhưng', 'cũng'
]
STICKY_PARTICLES.sort(key=len, reverse=True)
_STICKY_REGEX = re.compile(rf'([{LOWER_CHARS}{UPPER_CHARS}])(' + '|'.join(STICKY_PARTICLES) + r')\b')
_CAMEL_REGEX = re.compile(f'([{LOWER_CHARS}])([{UPPER_CHARS}])')

def fix_vietnamese_sticky_tokens(text: str) -> str:
    """
    Tự động chèn dấu cách nếu BPE tokenizer vô tình xuất dính trợ từ (Đấtlà -> Đất là)
    cho cả giao diện Dynamic Island lẫn giọng đọc Piper.
    """
    if not text:
        return text
    t = _CAMEL_REGEX.sub(r'\1 \2', text)
    t = _STICKY_REGEX.sub(r'\1 \2', t)
    return re.sub(r'\s+', ' ', t).strip()

def trim_incomplete_sentence(text: str) -> str:
    """
    Nếu model lỡ chạm trần token thì tự động tỉa sạch về dấu câu gần nhất (. ! ?),
    không bao giờ để lọt đuôi lửng lơ như 'vận tốc ...'.
    """
    if not text:
        return text
    t = text.strip()
    if re.search(r'[.!?][\"\'\)]*$', t):
        return t

    matches = list(re.finditer(r'[.!?](?:\s+|$)', t))
    if matches:
        last_match = matches[-1]
        trimmed = t[:last_match.end()].strip()
        if len(trimmed) > 0:
            return trimmed

    t = re.sub(r'[,;:\s\-]+$', '', t)
    t = re.sub(r'\s+(?:và|hoặc|với|của|là|trong|cho|ở|về|để|như|thì|mà|do|bởi)$', '', t, flags=re.IGNORECASE)
    t = t.strip()
    if t and not t.endswith('.'):
        t += '.'
    return t

def sanitize_text_for_voice(text: str) -> str:
    """
    Chuẩn hóa văn bản thành tiếng Việt ngữ âm tự nhiên trước khi đưa vào TTS:
    - Chuyển đổi số học, phần trăm (100% -> 100 phần trăm).
    - Chuyển đổi đơn vị (GB -> ghi ga, °C -> độ C).
    - Chuyển đổi thời gian (14:30 -> 14 giờ 30 phút).
    - Chuyển đổi số thập phân (5.1 -> 5 phẩy 1).
    - Loại bỏ hoàn toàn markdown (*, **, #, `), URL và ký tự lạ.
    """
    t = fix_vietnamese_sticky_tokens(text)
    # Chuẩn hóa từ mở đầu hoặc lỗi chính tả LLM tiếng Việt (Dà -> Dạ)
    t = re.sub(r'\b[Dd]à\b', 'Dạ', t)
    # Loại bỏ các cụm từ đệm rườm rà, văn mẫu sách vở ở đầu câu
    t = re.sub(r'^(?:theo tôi thì|theo ý kiến của tôi thì|theo mình thì|theo tôi thấy thì|như tôi đã nói thì)\s*', '', t, flags=re.IGNORECASE)
    # Xóa ký tự chữ Hán / CJK và emoji nếu có
    t = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', '', t)
    t = re.sub(r'[\U00010000-\U0010ffff]', '', t)
    # Xóa URL
    t = re.sub(r'https?://\S+', '', t)
    # Bóc tách định dạng markdown
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = re.sub(r'[#*_~>]', '', t)
    # Chuẩn hóa phần trăm
    t = re.sub(r'(\d+)\s*%', r'\1 phần trăm', t)
    # Chuẩn hóa nhiệt độ
    t = re.sub(r'(\d+)\s*°[Cc]', r'\1 độ C', t)
    # Chuẩn hóa thời gian 14:30
    t = re.sub(r'\b(\d{1,2}):(\d{2})\b', r'\1 giờ \2 phút', t)
    # Chuẩn hóa dung lượng bộ nhớ
    t = re.sub(r'(\d+(?:\.\d+)?)\s*GB\b', r'\1 ghi ga', t, flags=re.IGNORECASE)
    t = re.sub(r'(\d+(?:\.\d+)?)\s*MB\b', r'\1 mê ga', t, flags=re.IGNORECASE)
    # Chuẩn hóa số thập phân
    t = re.sub(r'(\d+)\.(\d+)', r'\1 phẩy \2', t)
    # Xóa ngoặc đơn, ngoặc vuông để đọc liền mạch
    t = re.sub(r'[\[\]\(\)\{\}]', ', ', t)
    # Dọn dẹp khoảng trắng và dấu phẩy thừa
    t = re.sub(r',\s*,+', ',', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def send_notification(title: str, message: str):
    """Gửi notification lên desktop Hyprland qua notify-send (nếu có)."""
    try:
        subprocess.Popen(
            ["notify-send", "-a", "Alexa AI", "-i", "audio-headset", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

def speak_piper_tts(text: str, voice: str = None) -> bool:
    """Phát âm thanh ngoại tuyến 100% bằng Piper TTS ONNX trực tiếp qua sounddevice có hỗ trợ cắt lời (Barge-in)."""
    clean = sanitize_text_for_voice(text)
    if not clean or not re.search(r'[\w\d]', clean):
        return True

    if player.interrupt_speech_event.is_set():
        return False

    voice_model = get_piper_voice(voice)
    if not voice_model:
        return False

    set_assistant_state("speaking", text=clean)
    try:
        chunks = []
        for chunk in voice_model.synthesize(clean):
            if player.interrupt_speech_event.is_set():
                set_assistant_state("idle")
                return False
            chunks.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16))

        if not chunks or player.interrupt_speech_event.is_set():
            set_assistant_state("idle")
            return False

        audio_raw = np.concatenate(chunks)
        audio = audio_raw.astype(np.float32) / 32768.0
        sr = getattr(voice_model.config, "sample_rate", 22050)

        # Khử triệt để xoẹt / pop: 5ms fade-in và 35ms cosine fade-out
        fade_in = int(sr * 0.005)
        fade_out = int(sr * 0.035)
        if len(audio) > fade_in:
            audio[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
        if len(audio) > fade_out:
            audio[-fade_out:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fade_out, dtype=np.float32)))
        audio[-1] = 0.0

        silence = np.zeros(int(sr * 0.030), dtype=np.float32)
        final_audio = np.concatenate([audio, silence])

        sd.play(final_audio, samplerate=sr)
        dur = len(final_audio) / sr
        start_t = time.time()
        while time.time() - start_t < dur:
            if player.interrupt_speech_event.is_set():
                sd.stop()
                set_assistant_state("idle")
                return False
            time.sleep(0.02)

        player.set_last_tts_end_time(time.time())
        set_assistant_state("idle")
        return True
    except Exception as e:
        print(f"⚠️ Lỗi Piper TTS: {e}")
    finally:
        set_assistant_state("idle")

    return False

def speak(text: str, voice: str = DEFAULT_VOICE) -> bool:
    """
    Đọc văn bản ra loa bằng Piper TTS Fine-Tuned Local Offline 100% (<80ms, không cần mạng).
    """
    if player.interrupt_speech_event.is_set():
        return False
    clean = sanitize_text_for_voice(text)
    if not clean or not re.search(r'[\w\d]', clean):
        return True
    send_notification("Alexa", clean)
    return speak_piper_tts(clean, voice=voice)
