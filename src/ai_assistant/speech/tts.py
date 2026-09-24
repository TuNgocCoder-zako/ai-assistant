"""
Tổng hợp giọng nói tiếng Việt bằng Edge-TTS và chuẩn hóa ngữ âm.
"""

import os
import re
import time
import asyncio
import subprocess
import edge_tts
from ai_assistant.config import DEFAULT_VOICE
from ai_assistant.core.state import set_assistant_state
from ai_assistant.speech import player

def sanitize_text_for_voice(text: str) -> str:
    """
    Chuẩn hóa văn bản thành tiếng Việt ngữ âm tự nhiên trước khi đưa vào TTS:
    - Chuyển đổi số học, phần trăm (100% -> 100 phần trăm).
    - Chuyển đổi đơn vị (GB -> ghi ga, °C -> độ C).
    - Chuyển đổi thời gian (14:30 -> 14 giờ 30 phút).
    - Chuyển đổi số thập phân (5.1 -> 5 phẩy 1).
    - Loại bỏ hoàn toàn markdown (*, **, #, `), URL và ký tự lạ.
    """
    t = text
    # Loại bỏ các cụm từ đệm rườm rà, văn mẫu sách vở ở đầu câu
    t = re.sub(r'^(?:theo tôi thì|theo ý kiến của tôi thì|theo mình thì|theo tôi thấy thì|như tôi đã nói thì)\s*', '', t, flags=re.IGNORECASE)
    # Xóa ký tự chữ Hán / CJK nếu có
    t = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', '', t)
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

def speak_edge_tts(text: str, voice: str = DEFAULT_VOICE) -> bool:
    """Phát âm thanh bằng Edge-TTS AI truyền trực tiếp vào mpv qua pipe có hỗ trợ cắt lời (Barge-in)."""
    clean = sanitize_text_for_voice(text)
    if not clean or not re.search(r'[\w\d]', clean):
        return True

    if player.interrupt_speech_event.is_set():
        return False

    set_assistant_state("speaking", text=clean)
    for attempt in range(2):
        if player.interrupt_speech_event.is_set():
            set_assistant_state("idle")
            return False
        try:
            proc = subprocess.Popen(
                ["mpv", "--no-video", "--really-quiet", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            with player._tts_proc_lock:
                player.current_tts_proc = proc

            async def _stream():
                communicate = edge_tts.Communicate(clean, voice)
                async for chunk in communicate.stream():
                    if player.interrupt_speech_event.is_set():
                        break
                    if chunk["type"] == "audio":
                        try:
                            proc.stdin.write(chunk["data"])
                        except Exception:
                            break
                try:
                    proc.stdin.close()
                except Exception:
                    pass

            asyncio.run(_stream())
            proc.wait(timeout=25)
            player.set_last_tts_end_time(time.time())
            with player._tts_proc_lock:
                player.current_tts_proc = None
            if player.interrupt_speech_event.is_set():
                set_assistant_state("idle")
                return False
            if proc.returncode == 0:
                set_assistant_state("idle")
                return True
        except Exception as e:
            with player._tts_proc_lock:
                player.current_tts_proc = None
            player.set_last_tts_end_time(time.time())
            if player.interrupt_speech_event.is_set():
                set_assistant_state("idle")
                return False
            if attempt == 0:
                time.sleep(0.2)
                continue
            print(f"⚠️ Lỗi Edge-TTS: {e}")
            set_assistant_state("idle")
            return False
    set_assistant_state("idle")
    return False

def speak(text: str, voice: str = DEFAULT_VOICE):
    """Đọc văn bản ra loa: Sử dụng DUY NHẤT một giọng đọc Edge-TTS chuẩn tiếng Việt tự nhiên 100%."""
    if player.interrupt_speech_event.is_set():
        return
    clean = sanitize_text_for_voice(text)
    if not clean or not re.search(r'[\w\d]', clean):
        return
    send_notification("Alexa", clean)
    speak_edge_tts(clean, voice=voice)
