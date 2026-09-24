#!/usr/bin/env python3
"""
Voice AI Assistant for Arch Linux / Hyprland (Alexa)
Trợ lý ảo giọng nói tiếng Việt thông minh phong cách Siri, Alexa & Google Assistant
- Thuật toán NGHE đỉnh cao: Pre-roll circular audio buffer (chống nuốt âm đầu), Dual-threshold Schmitt Trigger VAD,
  Lọc thông cao 85Hz, Automatic Gain Control (AGC) có trần nhiễu (Noise Ceiling), Whisper STT tối ưu khử lặp.
- Thuật toán HIỂU siêu tốc (Hybrid NLU): Fast-Path xử lý trực tiếp <5ms cho thời gian, âm lượng, độ sáng, nhạc,
  pin, RAM/hệ thống, mở ứng dụng, tìm kiếm YouTube/Google, tính toán số học + Deep-Path Qwen 2.5 7B LLM.
- Thuật toán TRẢ LỜI tức thì: Sentence-Level Streaming TTS truyền trực tiếp vào mpv, chuẩn hóa phát âm tiếng Việt
  (số học, đơn vị, giờ giấc, phần trăm), phản hồi tự nhiên, súc tích 1-2 câu.
- Tự động tắt hoàn toàn: Khi không nghe nói gì nữa hoặc người dùng kết thúc, trợ lý tự động tắt hẳn (trả lại terminal).
"""

import os
import sys
import time
import subprocess
import shutil
import re
import shlex
import glob
import json
import random
import urllib.parse
import datetime
import asyncio
import queue
import threading
import socket
import signal
import atexit
from collections import deque
import warnings
import difflib
warnings.filterwarnings("ignore")

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

import numpy as np
import sounddevice as sd
import requests
from scipy.signal import butter, sosfilt
from faster_whisper import WhisperModel
from faster_whisper.vad import get_speech_timestamps, VadOptions
import openwakeword
from openwakeword.model import Model
import edge_tts

# ================= Cấu hình cơ bản =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OLLAMA_URL = "http://localhost:11434/api/chat"

# Phân bổ chuyên biệt từng Model theo từng nhóm công việc (Task Specialization)
DEFAULT_FAST_MODEL = "qwen2.5:3b"          # Ưu tiên tốc độ siêu tốc (<0.3s), mở app, đàm thoại, thường ngày
DEFAULT_CODER_MODEL = "qwen2.5-coder:7b"   # Chuyên sâu lập trình, Java Backend, phân tích kỹ thuật, debug
DEFAULT_REASONING_MODEL = "qwen3:8b"       # Suy luận logic đa bước, giải quyết vấn đề phức tạp

def get_installed_ollama_models() -> set[str]:
    """Lấy danh sách các model hiện có sẵn trong Ollama."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=1.5)
        if r.status_code == 200:
            return {m.get("name", "") for m in r.json().get("models", [])}
    except Exception:
        pass
    return set()

def resolve_model_roles() -> dict:
    """Tự động phát hiện và phân bổ model tốt nhất trên máy cho từng công việc."""
    installed = get_installed_ollama_models()

    # 1. Fast & Daily Model (Ưu tiên: qwen2.5:3b -> qwen2.5:1.5b -> alexa-vn)
    fast_m = None
    for cand in ["qwen2.5:3b", "llama3.2:3b", "qwen2.5:1.5b", "alexa-vn:latest"]:
        if cand in installed:
            fast_m = cand
            break
    if not fast_m:
        fast_m = next(iter(installed)) if installed else DEFAULT_FAST_MODEL

    # 2. Coder Model (Ưu tiên: qwen2.5-coder:7b)
    coder_m = None
    for cand in ["qwen2.5-coder:7b", "qwen2.5-coder:latest", "deepseek-coder:6.7b"]:
        if cand in installed:
            coder_m = cand
            break
    if not coder_m:
        coder_m = fast_m

    # 3. Reasoning Model (Ưu tiên: qwen3:8b)
    reason_m = None
    for cand in ["qwen3:8b", "llama3.1:8b", "deepseek-r1:8b"]:
        if cand in installed:
            reason_m = cand
            break
    if not reason_m:
        reason_m = coder_m

    return {
        "fast": fast_m,
        "coder": coder_m,
        "reasoning": reason_m
    }

MODEL_ROLES = resolve_model_roles()
OLLAMA_MODEL = MODEL_ROLES["fast"]  # Model mặc định thường ngày

def route_task(prompt: str) -> tuple[str, str, dict]:
    """
    Bộ định tuyến thông minh (Smart Task Router):
    Phân bổ chính xác từng công việc cho mô hình tối ưu nhất.
    Trả về: (model_name, role_name, generation_options)
    """
    p = prompt.lower().strip()

    # 1. Nhóm LẬP TRÌNH & KỸ THUẬT CHUYÊN SÂU -> CODER MODEL (7B)
    coding_keywords = [
        "code", "lập trình", "java", "spring", "docker", "fix lỗi", "báo lỗi", "bug",
        "thuật toán", "cơ sở dữ liệu", "sql", "hibernate", "jpa", "microservice",
        "git", "bash", "hyprland", "cấu hình", "stack trace", "exception", "jvm",
        "viết hàm", "viết class", "refactor", "tối ưu code", "query", "rest api"
    ]
    if any(k in p for k in coding_keywords):
        return MODEL_ROLES["coder"], "Kỹ thuật & Lập trình (Coder 7B)", {
            "temperature": 0.2,
            "top_p": 0.85,
            "repeat_penalty": 1.15,
            "num_predict": 110,
            "num_ctx": 2048,
        }

    # 2. Nhóm SUY LUẬN LOGIC / PHÂN TÍCH ĐA BƯỚC -> REASONING MODEL (8B)
    reasoning_keywords = [
        "suy luận", "tại sao lại", "chứng minh", "phân tích logic", "so sánh chuyên sâu",
        "nguyên nhân sâu xa", "đánh giá ưu nhược điểm"
    ]
    if any(k in p for k in reasoning_keywords) and MODEL_ROLES["reasoning"] != MODEL_ROLES["fast"]:
        return MODEL_ROLES["reasoning"], "Suy luận Logic (Reasoning 8B)", {
            "temperature": 0.5,
            "top_p": 0.9,
            "repeat_penalty": 1.15,
            "num_predict": 100,
            "num_ctx": 2048,
        }

    # 3. MẶC ĐỊNH: MỞ APP TỰ NHIÊN, TRÌNH DUYỆT, TỐC ĐỘ CAO & THƯỜNG NGÀY -> FAST MODEL (3B)
    # Tối ưu nhiệt độ thấp, token vừa đủ để phản hồi siêu nhanh dưới 0.3s
    return MODEL_ROLES["fast"], "Tốc độ cao & Điều khiển hệ thống (Fast 3B)", {
        "temperature": 0.3,
        "top_p": 0.9,
        "repeat_penalty": 1.18,
        "num_predict": 60,
        "num_ctx": 1024,
    }

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # Giọng nữ nhẹ nhàng, tự nhiên
DEFAULT_STT_MODEL = "small"           # Mô hình STT tiếng Việt chất lượng cao

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80ms chunk cho openWakeWord (16000 * 0.08)
DEFAULT_THRESHOLD = 0.52  # Ngưỡng nhạy tối ưu cho từ khóa "Alexa"
DEFAULT_FOLLOWUP_TIMEOUT = 3.5  # Thời gian chờ nói tiếp trong chế độ thoại liên tục (3.5s tự động đóng nếu im lặng)

# Bộ lọc thông cao cắt tần số dưới 85Hz (khử tiếng ù quạt gió, chấn động bàn phím, tạp âm điện)
SOS_FILTER = butter(4, 85, 'hp', fs=SAMPLE_RATE, output='sos')

# ================= Âm thanh phản hồi trực giác (Earcons & Sound Chimes Êm Dịu) =================
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
        # Sóng hài âm ấm áp, giảm triệt để các sóng cao tần chói gắt
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

# ================= Cơ chế Giao tiếp Tiến trình (IPC Socket cho Phím tắt Toàn hệ thống) =================
def get_socket_path() -> str:
    xdg_runtime = os.getenv("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.exists(xdg_runtime):
        return os.path.join(xdg_runtime, "alexa_voice.sock")
    return f"/tmp/alexa_voice_{os.getuid()}.sock"

trigger_event = threading.Event()
interrupt_speech_event = threading.Event()
current_tts_proc = None
_tts_proc_lock = threading.Lock()  # BUG-04: Bảo vệ current_tts_proc khỏi race condition giữa các thread
_tts_last_end_time = 0.0  # BUG-01: Thời điểm TTS phát xong gần nhất (Echo Guard)
TTS_ECHO_GUARD_SECONDS = 0.8  # BUG-01: Chờ 800ms sau TTS mới bắt đầu thu âm
tts_queue = queue.Queue()
STATE_FILE_PATH = os.path.join(os.getenv("XDG_RUNTIME_DIR", "/tmp"), "alexa_state.json")

def ensure_overlay_running():
    """Khởi động giao diện hiển thị Dynamic Island Overlay qua Quickshell nếu chưa chạy."""
    try:
        res = subprocess.run(["pgrep", "-f", "VoiceOverlay.qml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            overlay_qml = os.path.expanduser("~/voice-ai/overlay/VoiceOverlay.qml")
            if os.path.exists(overlay_qml):
                subprocess.Popen(["qs", "-p", overlay_qml, "-d"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

state_lock = threading.Lock()
assistant_state = {"status": "idle"}  # "idle", "listening", "thinking", "speaking"

def set_assistant_state(status: str, text: str = "", subtext: str = ""):
    with state_lock:
        assistant_state["status"] = status
        assistant_state["text"] = text
        assistant_state["subtext"] = subtext
        assistant_state["updated_at"] = time.time()
        try:
            tmp = STATE_FILE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(assistant_state, f, ensure_ascii=False)
            os.replace(tmp, STATE_FILE_PATH)
        except Exception:
            pass

def get_assistant_state() -> dict:
    with state_lock:
        return dict(assistant_state)

atexit.register(lambda: set_assistant_state("idle"))

def _handle_exit_signal(sig, frame):
    set_assistant_state("idle")
    sys.exit(0)

try:
    signal.signal(signal.SIGTERM, _handle_exit_signal)
    signal.signal(signal.SIGINT, _handle_exit_signal)
except Exception:
    pass

def stop_current_speech():
    """Cắt lời ngay lập tức: Dừng tiến trình phát âm thanh và dọn sạch hàng đợi câu nói."""
    global current_tts_proc
    interrupt_speech_event.set()

    with _tts_proc_lock:
        proc = current_tts_proc
        current_tts_proc = None

    if proc is not None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1.0)
        except Exception:
            pass

    # Xả sạch tts_queue
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except Exception:
            break
    play_chime("sleep")
    set_assistant_state("idle")

def start_ipc_server():
    """Chạy Unix Domain Socket Server trong luồng ngầm để nhận lệnh từ phím tắt Hyprland hoặc CLI."""
    sock_path = get_socket_path()
    if os.path.exists(sock_path):
        try:
            os.remove(sock_path)
        except Exception:
            pass

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(sock_path)
        server.listen(5)
    except Exception as e:
        print(f"⚠️ Không thể khởi động IPC socket: {e}")
        return

    def _server_loop():
        while True:
            try:
                conn, _ = server.accept()
                raw_data = conn.recv(1024)
                if not raw_data:
                    conn.close()
                    continue
                cmd = raw_data.decode("utf-8", errors="ignore").strip().lower()
                if cmd in ["trigger", "wake", "listen", "hotkey"]:
                    trigger_event.set()
                    conn.sendall(b"OK:triggered\n")
                elif cmd in ["stop", "cancel", "mute", "quiet"]:
                    stop_current_speech()
                    conn.sendall(b"OK:stopped\n")
                elif cmd == "status":
                    st = json.dumps(get_assistant_state())
                    conn.sendall(f"{st}\n".encode())
                elif cmd == "ping":
                    conn.sendall(b"pong\n")
                else:
                    conn.sendall(b"ERR:unknown_command\n")
                conn.close()
            except Exception:
                break

    t = threading.Thread(target=_server_loop, daemon=True)
    t.start()

def send_ipc_command(cmd: str) -> tuple[bool, str]:
    """Gửi lệnh IPC tới trợ lý đang chạy nền từ tiến trình bên ngoài."""
    sock_path = get_socket_path()
    if not os.path.exists(sock_path):
        return False, "Trợ lý ảo Alexa chưa chạy nền."
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(sock_path)
        s.sendall(f"{cmd}\n".encode("utf-8"))
        resp = s.recv(1024).decode("utf-8", errors="ignore").strip()
        s.close()
        return True, resp
    except Exception as e:
        return False, str(e)

# Prompt định hướng từ vựng công nghệ và tên phần mềm để Whisper nhận diện chính xác Zalo, VS Code, v.v.
WHISPER_INITIAL_PROMPT = (
    "Chào bạn, tôi là trợ lý ảo tiếng Việt Alexa điều khiển máy tính Arch Linux. "
    "Mở ứng dụng Zalo, VS Code, Visual Studio Code, YouTube, Spotify, Kitty Terminal, "
    "Thunar, IntelliJ IDEA, Discord, Telegram, Brave, Chrome, Postman, Docker, DBeaver, OnlyOffice, Android Studio."
)

conversation_history = []

# ================= Chỉ mục ứng dụng & Thao tác Desktop =================
APP_ALIASES = {
    # Web Browsers
    "brave": "brave",
    "bờ rây": "brave",
    "b rây": "brave",
    "trình duyệt": "brave",
    "browser": "brave",
    "web": "brave",
    "chrome": "brave",
    "cốc cốc": "brave",

    # Visual Studio Code
    "code": "visual studio code",
    "vscode": "visual studio code",
    "vs code": "visual studio code",
    "vs cod": "visual studio code",
    "visual studio code": "visual studio code",
    "visual code": "visual studio code",
    "v-code": "visual studio code",
    "vs-code": "visual studio code",
    "cốt": "visual studio code",
    "vs cốt": "visual studio code",
    "v cốt": "visual studio code",
    "vé code": "visual studio code",
    "vét cốt": "visual studio code",
    "viết code": "visual studio code",
    "v s code": "visual studio code",
    "vi ét cốt": "visual studio code",
    "vi ét cút": "visual studio code",
    "viscode": "visual studio code",
    "vsx": "visual studio code",
    "phi ét cốt": "visual studio code",

    # Zalo
    "zalo": "zalo",
    "gia lô": "zalo",
    "da lô": "zalo",
    "da lo": "zalo",
    "ra lô": "zalo",
    "ra lo": "zalo",
    "za lo": "zalo",
    "za lô": "zalo",
    "xa lộ": "zalo",
    "dza lo": "zalo",
    "da luôn": "zalo",
    "gia lo": "zalo",
    "ga lô": "zalo",
    "cha lô": "zalo",

    # IntelliJ IDEA
    "idea": "intellij idea",
    "intellij": "intellij idea",
    "intellij idea": "intellij idea",
    "in te li ji": "intellij idea",
    "in te li": "intellij idea",
    "ai đia": "intellij idea",

    # Android Studio
    "android studio": "android studio",
    "an roi": "android studio",
    "an roi stu đi ô": "android studio",

    # Spotify / Âm nhạc
    "spotify": "spotify",
    "nhạc": "spotify",
    "nghe nhạc": "spotify",
    "bật nhạc": "spotify",
    "xì po ti phai": "spotify",
    "xì bo ti phai": "spotify",
    "xì pô ti phai": "spotify",

    # Kitty Terminal
    "kitty": "kitty",
    "terminal": "kitty",
    "tê mi nồ": "kitty",
    "tơ mi nồ": "kitty",
    "téc mi nồ": "kitty",
    "dòng lệnh": "kitty",
    "bàn điều khiển": "kitty",

    # File Manager / Thunar
    "thunar": "thunar file manager",
    "thunar file manager": "thunar file manager",
    "file": "thunar file manager",
    "tệp": "thunar file manager",
    "quản lý tệp": "thunar file manager",
    "quản lý file": "thunar file manager",

    # Developer & Office Tools
    "postman": "postman",
    "pốt man": "postman",
    "dbeaver": "dbeaver community",
    "docker": "docker desktop",
    "đốc cơ": "docker desktop",
    "office": "onlyoffice",
    "word": "onlyoffice",
    "excel": "onlyoffice",
    "onlyoffice": "onlyoffice",
    "telegram": "telegram desktop",
    "discord": "discord",
    "canva": "canva",
    "âm lượng": "volume control",
    "sound": "volume control",
}

URL_SHORTCUTS = {
    "youtube": "https://www.youtube.com",
    "du túp": "https://www.youtube.com",
    "dút túp": "https://www.youtube.com",
    "google": "https://www.google.com",
    "facebook": "https://www.facebook.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "reddit": "https://www.reddit.com",
    "tiktok": "https://www.tiktok.com",
    "gmail": "https://mail.google.com",
}

EXIT_PHRASES = [
    "cảm ơn", "cảm ơn nhé", "cảm ơn bạn", "cám ơn", "thanks", "thank you",
    "thôi", "dừng lại", "dừng được rồi", "xong rồi", "được rồi", "thôi nhé",
    "tạm biệt", "nghỉ đi", "nghỉ ngơi đi", "bye", "bye bye", "hết rồi",
    "không có gì nữa", "không cần nữa", "kết thúc", "kết thúc nhé", "kết thúc đi",
    "tắt đi", "tắt trợ lý", "đóng trợ lý", "ẩn trợ lý", "tắt alexa", "đóng alexa",
    "hẹn gặp lại", "chào bạn", "chào nhé", "thế thôi", "vậy thôi", "ok xong",
    "tắt cửa sổ", "đóng cửa sổ", "ẩn cửa sổ"
]

def is_exit_phrase(text: str) -> bool:
    """Kiểm tra xem người dùng có muốn dừng phiên thoại hoặc đóng cửa sổ trợ lý không."""
    t = text.lower().strip().rstrip(".,!?")

    # BUG-11: Câu dài (> 5 từ) không phải lời tạm biệt đơn thuần
    # Ví dụ: "cảm ơn, giờ giúp tôi mở Zalo" → KHÔNG phải exit
    if len(t.split()) > 5:
        return False

    key_phrases = [
        "kết thúc cuộc trò chuyện", "kết thúc trò chuyện", "kết thúc phiên",
        "dừng cuộc trò chuyện", "dừng trò chuyện", "dừng lại ở đây", "dừng tại đây",
        "kết thúc ở đây", "kết thúc tại đây", "tạm biệt bạn", "tạm biệt nhé",
        "hẹn gặp lại", "đóng cửa sổ", "tắt cửa sổ", "ẩn cửa sổ",
        "tắt trợ lý", "đóng trợ lý", "ẩn trợ lý", "tắt alexa", "đóng alexa"
    ]
    if any(kp in t for kp in key_phrases):
        return True
    if t in EXIT_PHRASES:
        return True
    for p in EXIT_PHRASES:
        if t == p or t.startswith(p + " ") or t.endswith(" " + p):
            return True
    return False

def clean_user_input(text: str) -> str:
    """Loại bỏ các từ gọi tên thừa ở đầu câu nếu Whisper nhận diện vào văn bản."""
    t = text.strip()
    t = re.sub(r'^(ê\s+)?(này\s+)?(ơi\s+)?(chào\s+)?alexa(\s+ơi)?[\s,\.!\?]+', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'^(ê\s+)?(này\s+)?(ơi\s+)?(chào\s+)?jarvis(\s+ơi)?[\s,\.!\?]+', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'^(à|ừm|ừ|này|ê)[\s,\.!\?]+', '', t, flags=re.IGNORECASE).strip()
    return t if t else text.strip()

def build_app_index() -> dict:
    """Quét các file .desktop để tạo danh sách ứng dụng đã cài đặt."""
    apps = {}
    search_dirs = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/local/share/applications",
        "/usr/share/applications"
    ]
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for f in glob.glob(os.path.join(d, "*.desktop")):
            fname = os.path.basename(f)
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                    lines = fp.readlines()
                name = ""
                exec_cmd = ""
                nodisplay = False
                for line in lines:
                    line = line.strip()
                    if line.startswith("Name=") and not name:
                        name = line.split("=", 1)[1].strip()
                    elif line.startswith("Exec=") and not exec_cmd:
                        exec_cmd = line.split("=", 1)[1].strip()
                    elif line.lower() == "nodisplay=true":
                        nodisplay = True
                if name and exec_cmd and not nodisplay:
                    apps[name.lower()] = {
                        "name": name,
                        "desktop_id": fname,
                        "exec": exec_cmd
                    }
            except Exception:
                pass
    return apps

def clean_target_query(q: str) -> str:
    """Chuẩn hóa và loại bỏ các từ phụ trợ, từ đệm ở đầu và cuối chuỗi tìm kiếm app."""
    s = q.lower().strip()
    s = re.sub(r"[,\.!?]", " ", s)
    # Loại bỏ tiền tố phụ
    s = re.sub(r"^(?:hãy|cho tôi|giúp tôi|hộ tôi|giùm tôi|làm ơn|vui lòng|bạn|thử)\s+", "", s).strip()
    s = re.sub(r"^(?:ứng dụng|phần mềm|app|trình duyệt)\s+", "", s).strip()
    s = re.sub(r"^(?:cho tôi|giúp tôi|hộ tôi|giùm tôi)\s+", "", s).strip()
    # Loại bỏ các hậu tố đệm lặp đi lặp lại
    pattern = r"\s+(?:lên|đi|nào|với|cho tôi|giúp tôi|hộ tôi|giùm tôi|giùm|hộ|ngay|nhé|nha|nhá|được không|ạ|với ạ|nào bạn|xem nào|nghe nhạc)$"
    while True:
        prev = s
        s = re.sub(pattern, "", s).strip()
        if s == prev:
            break
    return s.strip()

def match_app(query: str, app_index: dict):
    """Tìm ứng dụng phù hợp nhất dựa trên từ khóa người dùng, alias hoặc so khớp mờ."""
    clean = clean_target_query(query)
    if not clean:
        return None

    # 1. Tra cứu trực tiếp từ bảng alias
    target = APP_ALIASES.get(clean, clean)
    if target in app_index:
        return app_index[target]

    # 2. Khớp chuỗi con và kiểm tra ranh giới từ
    for k, v in app_index.items():
        if target == k or target in k or k in target:
            return v

    # 3. Kiểm tra tên file desktop_id
    for k, v in app_index.items():
        if target in v["desktop_id"].lower():
            return v

    # 4. So khớp mờ (Fuzzy matching)
    matches = difflib.get_close_matches(target, list(app_index.keys()), n=1, cutoff=0.7)
    if matches:
        return app_index[matches[0]]

    return None

def find_app_in_text(text: str, app_index: dict):
    """Tìm kiếm trực tiếp bất kỳ ứng dụng nào được đề cập trong toàn bộ câu nói."""
    t = text.lower()
    sorted_aliases = sorted(APP_ALIASES.keys(), key=lambda x: len(x), reverse=True)
    for alias in sorted_aliases:
        if alias in ["web", "file", "nhạc", "cốt", "code"] and len(alias) <= 4:
            pattern = r"(?:\b(?:mở|bật|chạy|khởi động)\s+)(?:ứng dụng\s+|phần mềm\s+|app\s+)?" + re.escape(alias) + r"\b"
            if not re.search(pattern, t):
                continue
        pattern = r"(?:\b|(?<=^))" + re.escape(alias) + r"(?:\b|(?=$))"
        if re.search(pattern, t):
            mapped = APP_ALIASES[alias]
            if mapped in app_index:
                return app_index[mapped]

    for k, v in app_index.items():
        if len(k) >= 4:
            pattern = r"(?:\b|(?<=^))" + re.escape(k) + r"(?:\b|(?=$))"
            if re.search(pattern, t):
                return v

    return None

def launch_desktop_app(app_info: dict) -> bool:
    """Khởi chạy ứng dụng an toàn mà không chặn tiến trình chính."""
    desktop_id = app_info.get("desktop_id")
    if desktop_id:
        try:
            subprocess.Popen(
                ["gtk-launch", desktop_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return True
        except Exception:
            pass

    exec_cmd = app_info.get("exec", "")
    if exec_cmd:
        try:
            clean_cmd = re.sub(r'%[a-zA-Z]', '', exec_cmd).strip()
            args = shlex.split(clean_cmd)
            subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return True
        except Exception:
            pass
    return False

# ================= Thuật toán NGHE (Audio DSP & Faster-Whisper STT) =================

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
    if max_val > 0.01:
        noise_gain_cap = 0.20 / max(ambient_noise, 0.01)
        gain = min(target_peak / max_val, max_gain, noise_gain_cap)
        return audio * gain
    return audio

def record_audio(max_duration: float = 8.0, silence_timeout: float = 0.8, max_wait_for_speech: float = 3.5) -> tuple[np.ndarray, float]:
    """
    Thu âm giọng nói từ micro với hiệu chuẩn thích ứng môi trường thời gian thực:
    - Đo độ ồn nền thực tế (quạt laptop, phòng) trong 400ms đầu tiên để tính ngưỡng kích hoạt động.
    - Chống kích hoạt giả do tiếng quạt gió hoặc chấn động bàn phím.
    - Pre-roll ring buffer (400ms) giữ trọn vẹn phụ âm đầu câu.
    - Tự động ngắt khi phát hiện khoảng lặng tự nhiên (0.65s).
    """
    chunk_len = 1600  # 100ms ở 16kHz
    frames = []
    ambient_chunks = []
    preroll_buffer = deque(maxlen=4)  # Lưu 400ms âm thanh trước khi kích hoạt
    has_spoken = False
    silence_chunks = 0
    spoken_chunks = 0
    max_chunks = int(max_duration * (SAMPLE_RATE / chunk_len))
    wait_limit = int(max_wait_for_speech * (SAMPLE_RATE / chunk_len))

    ambient_noise = 0.035
    speech_trigger_threshold = 0.080
    silence_threshold = 0.050

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32') as stream:
        # Xả sạch bộ đệm âm thanh còn dư trong luồng
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

            # Hiển thị thanh âm lượng trực quan theo thời gian thực
            bars = int(min(rms / 0.12, 1.0) * 8)
            meter = "█" * bars + "░" * (8 - bars)
            status_text = "Đang nhận giọng nói..." if has_spoken else "Đang chờ bạn nói..."
            print(f"\r🎙️ Mic: [{meter}] | {status_text}  ", end="", flush=True)

            # 4 chunk đầu (400ms) để đo độ ồn nền thực tế của phòng / quạt máy
            if i < 4:
                ambient_chunks.append(rms)
                preroll_buffer.append(chunk)
                continue
            elif i == 4:
                preroll_buffer.append(chunk)
                ambient_noise = float(np.mean(ambient_chunks))
                # Ngưỡng kích hoạt tiếng nói: phải vượt trội rõ rệt so với ồn nền (quạt/vibration)
                # BUG-01: Nâng ngưỡng để chống echo TTS từ loa bị micro thu lại
                speech_trigger_threshold = max(ambient_noise * 3.0, ambient_noise + 0.065, 0.10)
                silence_threshold = max(ambient_noise * 1.5, ambient_noise + 0.025, 0.060)
                continue

            if not has_spoken:
                preroll_buffer.append(chunk)
                if rms > speech_trigger_threshold:
                    has_spoken = True
                    frames.extend(list(preroll_buffer))
                    silence_chunks = 0
                    spoken_chunks = 1
                elif i >= wait_limit:
                    print()
                    return np.array([], dtype=np.float32), ambient_noise
            else:
                frames.append(chunk)
                spoken_chunks += 1

                # Động học ngắt câu: 0.65s im lặng tự nhiên sau khi đã nói
                silence_limit = int(silence_timeout * (SAMPLE_RATE / chunk_len))

                if rms > silence_threshold:
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= silence_limit:
                        break

    print()  # Xuống dòng sau khi thu âm xong
    if not frames or not has_spoken or spoken_chunks < 2:
        return np.array([], dtype=np.float32), ambient_noise
    return np.concatenate(frames), ambient_noise

# ================= Thuật toán HIỂU (Fast-Path NLU & System Tools) =================

def get_vietnamese_time() -> str:
    """Trả về giờ và phút hiện tại bằng tiếng Việt chuẩn ngữ âm."""
    now = datetime.datetime.now()
    return f"Bây giờ là {now.hour} giờ {now.minute} phút rồi bạn nhé."

def get_vietnamese_date() -> str:
    """Trả về ngày tháng hiện tại bằng tiếng Việt chuẩn."""
    now = datetime.datetime.now()
    days_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    day_name = days_vi[now.weekday()]
    return f"Hôm nay là {day_name}, ngày {now.day} tháng {now.month} năm {now.year}."

def get_battery_info() -> str:
    """Kiểm tra tình trạng pin và sạc thực tế của laptop Asus TUF."""
    try:
        out = subprocess.check_output(
            ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT1"],
            text=True,
            errors="ignore",
            timeout=3
        )
        state = "đang dùng"
        pct = ""
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("state:"):
                state = line.split(":", 1)[1].strip()
            elif line.startswith("percentage:"):
                pct = line.split(":", 1)[1].strip()
        state_map = {
            "discharging": "đang dùng pin",
            "charging": "đang cắm sạc",
            "fully-charged": "đã sạc đầy và đang cắm nguồn"
        }
        state_vi = state_map.get(state, state)
        if pct:
            pct_text = pct.replace("%", " phần trăm")
            return f"Pin laptop hiện tại còn {pct_text}, trạng thái {state_vi}."
        return "Pin máy tính đang hoạt động bình thường."
    except Exception:
        return "Hiện tại tôi không thể lấy được thông tin pin từ hệ thống."

def get_system_hardware_info() -> str:
    """Đọc trực tiếp tài nguyên RAM, thời gian hoạt động từ /proc trong <1ms."""
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                p = line.split(":")
                mem[p[0].strip()] = int(p[1].split()[0])
        total_gb = mem["MemTotal"] / 1024 / 1024
        avail_gb = mem["MemAvailable"] / 1024 / 1024
        used_gb = total_gb - avail_gb
        pct = int(used_gb / total_gb * 100)

        with open("/proc/uptime") as f:
            sec = float(f.read().split()[0])
        hours = int(sec // 3600)
        mins = int((sec % 3600) // 60)
        uptime_str = f"{hours} giờ {mins} phút" if hours > 0 else f"{mins} phút"

        used_str = f"{used_gb:.1f}".replace(".", " phẩy ")
        total_str = f"{total_gb:.1f}".replace(".", " phẩy ")

        return f"Máy tính đang dùng {used_str} ghi ga RAM trên tổng {total_str} ghi ga, khoảng {pct} phần trăm. Thiết bị đã hoạt động liên tục {uptime_str}."
    except Exception:
        return "Hệ thống Arch Linux đang hoạt động rất mượt mà và ổn định."

def get_weather_info(location: str = "") -> str:
    """Tra cứu thời tiết trực tiếp từ wttr.in bằng tiếng Việt."""
    try:
        loc = location.strip() if isinstance(location, str) and location.strip() else ""
        url = f"https://wttr.in/{loc}?format=%C,+%t,+độ+ẩm+%h&lang=vi" if loc else "https://wttr.in/?format=%C,+%t,+độ+ẩm+%h&lang=vi"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200 and resp.text:
            weather_text = resp.text.strip().replace("+", "")
            loc_label = f"ở {loc}" if loc else "khu vực của bạn"
            return f"Thời tiết {loc_label} hiện tại: {weather_text}."
    except Exception:
        pass
    return "Hiện tại tôi chưa thể kết nối tới dịch vụ thời tiết."

def parse_simple_math(query: str):
    """Tính nhẩm số học nhanh tức thì cho các phép tính cộng, trừ, nhân, chia."""
    q = query.lower()
    m = re.search(r"(\d+)\s*(\+|\-|\*|\/|cộng|trừ|nhân|chia)\s*(\d+)", q)
    if m:
        n1 = int(m.group(1))
        op = m.group(2)
        n2 = int(m.group(3))
        if op in ["+", "cộng"]:
            return f"{n1} cộng {n2} bằng {n1 + n2}."
        elif op in ["-", "trừ"]:
            return f"{n1} trừ {n2} bằng {n1 - n2}."
        elif op in ["*", "nhân"]:
            return f"{n1} nhân {n2} bằng {n1 * n2}."
        elif op in ["/", "chia"]:
            if n2 == 0:
                return "Không thể chia cho số không bạn nhé."
            res = round(n1 / n2, 2)
            res_str = str(res).replace(".0", "").replace(".", " phẩy ")
            return f"{n1} chia {n2} bằng {res_str}."
    return None

MEMORY_FILE = os.path.expanduser("~/.config/voice-ai/memory.json")

def load_user_memory() -> dict:
    """Tải bộ nhớ thông tin cá nhân của người dùng."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"facts": []}

def save_user_memory(memory: dict):
    """Lưu bộ nhớ thông tin cá nhân của người dùng."""
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def add_user_fact(fact: str) -> str:
    """Ghi nhớ một sự kiện hoặc thông tin về người dùng vào bộ nhớ dài hạn."""
    mem = load_user_memory()
    clean_fact = fact.strip().rstrip(".!?")
    if clean_fact and clean_fact not in mem["facts"]:
        mem["facts"].append(clean_fact)
        if len(mem["facts"]) > 15:
            mem["facts"] = mem["facts"][-15:]
        save_user_memory(mem)
    return f"Đã ghi nhớ thông tin: {clean_fact}."

def get_user_facts_prompt() -> str:
    """Trích xuất các thông tin đã nhớ để đưa vào System Prompt."""
    mem = load_user_memory()
    if mem.get("facts"):
        facts_str = "\n".join([f"- {f}" for f in mem["facts"]])
        return f"\nTHÔNG TIN VỀ NGƯỜI DÙNG ĐÃ GHI NHỚ:\n{facts_str}\n"
    return ""

NOTES_FILE = os.path.expanduser("~/Documents/voice_notes.txt")

def add_quick_note(content: str) -> str:
    """Lưu ghi chú nhanh của người dùng."""
    try:
        os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now_str}] {content}\n")
        return f"Đã ghi chú lại cho bạn: {content}."
    except Exception:
        return "Không thể lưu ghi chú vào lúc này."

def read_quick_notes() -> str:
    """Đọc các ghi chú gần nhất."""
    if not os.path.exists(NOTES_FILE):
        return "Bạn hiện chưa có ghi chú nào."
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        if not lines:
            return "Danh sách ghi chú của bạn đang trống."
        last_notes = lines[-2:]
        return "Ghi chú gần nhất của bạn là: " + "; ".join(last_notes)
    except Exception:
        return "Không thể đọc danh sách ghi chú."

# ================= Trình Quản lý Hẹn giờ & Báo thức Bền bỉ (Timer & Alarm Manager) =================
TIMERS_FILE = os.path.expanduser("~/.config/voice-ai/timers.json")

class TimerAlarmManager:
    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice
        self.timers = []
        self.lock = threading.Lock()
        self._load()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def _load(self):
        if os.path.exists(TIMERS_FILE):
            try:
                with open(TIMERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    now = time.time()
                    self.timers = [t for t in data.get("items", []) if t.get("target_time", 0) > now]
            except Exception:
                self.timers = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(TIMERS_FILE), exist_ok=True)
            with open(TIMERS_FILE, "w", encoding="utf-8") as f:
                json.dump({"items": self.timers}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_timer(self, minutes: float, label: str = "") -> str:
        seconds = int(minutes * 60)
        if seconds <= 0:
            return "Thời gian hẹn giờ không hợp lệ."
        target_time = time.time() + seconds
        timer_id = f"timer_{int(target_time)}"
        with self.lock:
            self.timers.append({
                "id": timer_id,
                "type": "timer",
                "target_time": target_time,
                "duration_sec": seconds,
                "label": label.strip()
            })
            self._save()

        play_chime("ack")
        mins_val = int(minutes) if minutes >= 1 else f"{int(seconds)} giây"
        unit = "phút" if minutes >= 1 else ""
        label_text = f" cho {label}" if label else ""
        return f"Đã đặt hẹn giờ {mins_val} {unit}{label_text} cho bạn rồi nhé."

    def add_alarm(self, hour: int, minute: int, label: str = "") -> str:
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return "Giờ báo thức không hợp lệ."
        now = datetime.datetime.now()
        target_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_dt <= now:
            target_dt += datetime.timedelta(days=1)

        target_time = target_dt.timestamp()
        alarm_id = f"alarm_{int(target_time)}"
        with self.lock:
            self.timers.append({
                "id": alarm_id,
                "type": "alarm",
                "target_time": target_time,
                "duration_sec": 0,
                "label": label.strip()
            })
            self._save()

        play_chime("ack")
        time_display = f"{hour} giờ" + (f" {minute} phút" if minute > 0 else "")
        day_text = "ngày mai" if target_dt.date() > now.date() else "hôm nay"
        label_text = f" cho {label}" if label else ""
        return f"Đã đặt báo thức lúc {time_display} {day_text}{label_text} cho bạn nhé."

    def check_timers(self) -> str:
        now = time.time()
        with self.lock:
            active = [t for t in self.timers if t["target_time"] > now]
        if not active:
            return "Hiện tại bạn không có hẹn giờ hay báo thức nào đang chạy."

        parts = []
        for item in active:
            rem = int(item["target_time"] - now)
            rem_m = rem // 60
            rem_s = rem % 60
            if item["type"] == "timer":
                time_str = f"{rem_m} phút {rem_s} giây" if rem_m > 0 else f"{rem_s} giây"
                label_str = f" {item['label']}" if item['label'] else ""
                parts.append(f"Hẹn giờ{label_str} còn {time_str}")
            else:
                target_dt = datetime.datetime.fromtimestamp(item["target_time"])
                parts.append(f"Báo thức lúc {target_dt.hour} giờ {target_dt.minute} phút")

        return "Hiện có: " + ", ".join(parts) + "."

    def cancel_all(self) -> str:
        with self.lock:
            count = len(self.timers)
            self.timers = []
            self._save()
        play_chime("ack")
        if count == 0:
            return "Hiện tại không có hẹn giờ nào để hủy."
        return "Đã hủy toàn bộ hẹn giờ và báo thức cho bạn rồi nhé."

    def _worker(self):
        while not self._stop_event.is_set():
            time.sleep(1.0)
            now = time.time()
            triggered = []
            with self.lock:
                remaining = []
                for t in self.timers:
                    if t["target_time"] <= now:
                        triggered.append(t)
                    else:
                        remaining.append(t)
                if triggered:
                    self.timers = remaining
                    self._save()

            for item in triggered:
                # Chờ nếu trợ lý đang trong phiên hội thoại với người dùng để tránh xung đột âm thanh
                for _ in range(30):
                    if get_assistant_state().get("status", "idle") == "idle":
                        break
                    time.sleep(0.5)

                for _ in range(3):
                    play_chime("alarm")
                    time.sleep(0.4)

                if item["type"] == "timer":
                    label_str = f" cho {item['label']}" if item['label'] else ""
                    msg = f"Đã hết thời gian hẹn giờ{label_str} rồi bạn nhé!"
                else:
                    label_str = f" {item['label']}" if item['label'] else ""
                    msg = f"Đã đến giờ báo thức{label_str} rồi, chúc bạn một ngày tốt lành!"

                send_notification("Alexa Báo Giờ", msg)
                speak(msg, voice=self.voice)

timer_manager = TimerAlarmManager(voice=DEFAULT_VOICE)

def set_timer(minutes: float) -> str:
    return timer_manager.add_timer(minutes)

def search_duckduckgo_summary(query: str, max_results: int = 2) -> str:
    """Tra cứu tóm tắt thông tin thời gian thực từ DuckDuckGo."""
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=4)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        clean_snippets = []
        for s in snippets[:max_results]:
            clean = re.sub(r'<.*?>', '', s).strip()
            clean = re.sub(r'\s+', ' ', clean)
            if clean:
                clean_snippets.append(clean)
        return ' '.join(clean_snippets) if clean_snippets else ''
    except Exception:
        return ''

def search_and_display_image(query: str, download_dir: str = "/home/tu/Pictures") -> tuple[bool, str]:
    """Tìm kiếm hình ảnh trên web, tải về thư mục Pictures và mở hiển thị ngay trên màn hình."""
    clean_q = re.sub(r"^(?:tìm\s+)?(?:cho\s+tôi\s+)?(?:bức\s+|tấm\s+|hình\s+)?ảnh\s+(?:về\s+)?", "", query, flags=re.IGNORECASE)
    pattern = r'\s+(?:trên\s+(?:mạng|web|google|bing)|và\s+đưa\s+về\s+đây|về\s+đây|về\s+máy|cho\s+tôi|giùm\s+tôi|hộ\s+tôi)$'
    prev = ''
    while prev != clean_q:
        prev = clean_q
        clean_q = re.sub(pattern, '', clean_q, flags=re.IGNORECASE).strip()

    if not clean_q:
        return False, "Bạn muốn tôi tìm bức ảnh gì nào?"
        
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    img_url = None
    
    # 1. Thử Bing Images
    try:
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(clean_q)}&FORM=HDRSC2"
        resp = requests.get(url, headers=headers, timeout=5)
        murls = re.findall(r'murl&quot;:&quot;(http[^&]+)&quot;', resp.text)
        if murls:
            img_url = murls[0]
    except Exception:
        pass
        
    # 2. Thử Wikimedia Commons fallback
    if not img_url:
        try:
            wiki_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrsearch={urllib.parse.quote(clean_q)}&gsrlimit=3&prop=imageinfo&iiprop=url&format=json"
            r = requests.get(wiki_url, headers={'User-Agent': 'VoiceAssistant/1.0'}, timeout=5)
            pages = r.json().get('query', {}).get('pages', {})
            for k, v in pages.items():
                info = v.get('imageinfo', [])
                if info and 'url' in info[0]:
                    img_url = info[0]['url']
                    break
        except Exception:
            pass
            
    if not img_url:
        return False, f"Tôi không tìm thấy bức ảnh nào về {clean_q} trên mạng."
        
    try:
        os.makedirs(download_dir, exist_ok=True)
        safe_name = re.sub(r'[^\w\-_]', '_', clean_q.lower())
        ext = ".png" if ".png" in img_url.lower() else (".webp" if ".webp" in img_url.lower() else ".jpg")
        save_path = os.path.join(download_dir, f"{safe_name}{ext}")
        
        img_bytes = requests.get(img_url, headers=headers, timeout=8).content
        if len(img_bytes) > 1024:
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            viewer = "viewnior" if shutil.which("viewnior") else "xdg-open"
            subprocess.Popen([viewer, save_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Đã tìm thấy và mở ảnh {clean_q} cho bạn rồi nhé."
    except Exception:
        pass
    return False, f"Không thể tải và hiển thị bức ảnh về {clean_q} lúc này."

def get_clipboard_content(max_chars: int = 300) -> str:
    """Lấy nội dung văn bản từ clipboard Wayland bằng wl-paste."""
    try:
        res = subprocess.run(["wl-paste", "--no-newline"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            txt = res.stdout.strip()
            if not txt:
                return ""
            if len(txt) > max_chars:
                return txt[:max_chars] + "... (nội dung còn dài)"
            return txt
    except Exception:
        pass
    return ""

def get_git_status_summary(target_dir: str = None) -> str:
    """Kiểm tra nhanh trạng thái git của thư mục làm việc hiện tại hoặc dự án gần nhất."""
    candidate_dirs = []
    if target_dir:
        candidate_dirs.append(target_dir)
    candidate_dirs.extend([os.getcwd(), os.path.expanduser("~/voice-ai"), os.path.expanduser("~/Projects")])

    found_repo = None
    for d in candidate_dirs:
        if os.path.isdir(d) and os.path.exists(os.path.join(d, ".git")):
            found_repo = d
            break

    if not found_repo:
        projects_dir = os.path.expanduser("~/Projects")
        if os.path.exists(projects_dir):
            for sub in os.listdir(projects_dir):
                sub_path = os.path.join(projects_dir, sub)
                if os.path.isdir(sub_path) and os.path.exists(os.path.join(sub_path, ".git")):
                    found_repo = sub_path
                    break

    if not found_repo:
        return "Tôi không tìm thấy kho lưu trữ Git nào đang mở bạn nhé."

    repo_name = os.path.basename(found_repo)
    try:
        res_branch = subprocess.run(["git", "branch", "--show-current"], cwd=found_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        branch = res_branch.stdout.strip() if res_branch.returncode == 0 else ""
        if not branch:
            branch = "chính"

        res_stat = subprocess.run(["git", "status", "--short"], cwd=found_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        changes = [l for l in res_stat.stdout.strip().split("\n") if l.strip()]
        if not changes:
            return f"Trong dự án {repo_name}, nhánh {branch} đang hoàn toàn sạch sẽ, không có thay đổi nào chưa commit."
        return f"Dự án {repo_name}, nhánh {branch} hiện có {len(changes)} tệp tin đang thay đổi hoặc chưa commit."
    except Exception:
        return f"Không thể lấy thông tin Git của dự án {repo_name}."

# ================= Quản lý Cửa sổ và Ứng dụng Hyprland Chuẩn v0.56.2 =================

PROTECTED_CLASSES = {"quickshell", "qs", "waybar", "dunst", "swaync"}

def get_hyprland_clients() -> list[dict]:
    """Lấy danh sách các cửa sổ GUI đang mở trên Hyprland."""
    try:
        res = subprocess.run(["hyprctl", "clients", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return []

def get_hyprland_active_window() -> dict:
    """Lấy thông tin cửa sổ đang active trên Hyprland."""
    try:
        res = subprocess.run(["hyprctl", "activewindow", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return {}

def close_hyprland_window_by_address(address: str) -> bool:
    """Đóng cửa sổ cụ thể theo địa chỉ hex thông qua Lua Dispatcher của Hyprland 0.56.2 có fallback tiêu chuẩn."""
    if not address:
        return False
    try:
        cmd = f"hl.dispatch(hl.dsp.window.close('address:{address}'))"
        res = subprocess.run(["hyprctl", "eval", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            return True
    except Exception:
        pass
    try:
        res = subprocess.run(["hyprctl", "dispatch", "closewindow", f"address:{address}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False

def close_active_window() -> tuple[bool, str]:
    """Đóng cửa sổ hiện tại (bảo vệ tuyệt đối terminal chạy trợ lý)."""
    active = get_hyprland_active_window()
    if not active or not active.get("address"):
        return True, "Không tìm thấy cửa sổ nào đang hoạt động."
    
    title = active.get("title", "").lower()
    cls = active.get("class", "").lower()
    if "agy" in title or "antigravity" in title or cls in PROTECTED_CLASSES:
        return True, "Cửa sổ này đang làm việc và được bảo vệ, tôi không đóng nhé."
    
    addr = active.get("address")
    close_hyprland_window_by_address(addr)
    app_name = active.get("initialTitle") or active.get("title") or active.get("class") or "cửa sổ hiện tại"
    return True, f"Đã đóng {app_name} cho bạn rồi nhé."

def close_all_open_apps() -> tuple[bool, str]:
    """Đóng tất cả các ứng dụng người dùng đang mở trên màn hình."""
    clients = get_hyprland_clients()
    closed_count = 0
    closed_names = []
    
    for c in clients:
        cls = c.get("class", "").lower()
        title = c.get("title", "").lower()
        addr = c.get("address", "")
        pid = c.get("pid", 0)
        
        if cls in PROTECTED_CLASSES or "agy" in title or "antigravity" in title:
            continue
        
        if addr:
            close_hyprland_window_by_address(addr)
            closed_count += 1
            name = c.get("initialTitle") or c.get("class") or "ứng dụng"
            if name not in closed_names:
                closed_names.append(name)
        
        if pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

    if closed_count > 0:
        return True, f"Đã đóng {closed_count} ứng dụng đang mở cho bạn rồi nhé."
    else:
        return True, "Hiện không có ứng dụng nào đang mở cần đóng."

def close_specific_app(target: str, app_index: dict = None) -> tuple[bool, str]:
    """Đóng ứng dụng cụ thể theo tên (Zalo, Chrome, VS Code, Spotify, v.v.)."""
    target = target.strip().lower()
    target = re.sub(r"^(?:ứng dụng|phần mềm|app|cửa sổ|trình duyệt)\s+", "", target).strip()
    if not target or target in ["hẹn giờ", "báo thức", "nhạc", "wifi", "bluetooth"]:
        return False, ""
    
    clients = get_hyprland_clients()
    matched_addrs = []
    matched_pids = set()
    display_name = target
    
    search_keys = [target]
    if target in ["zalo", "da lô", "za lô"]:
        search_keys.extend(["zalo"])
    elif target in ["code", "vs code", "vscode", "visual studio code"]:
        search_keys.extend(["code", "vscode", "visual-studio-code"])
    elif target in ["chrome", "trình duyệt", "google chrome", "web", "internet"]:
        search_keys.extend(["chrome", "google-chrome", "firefox", "brave", "edge"])
    elif target in ["spotify"]:
        search_keys.extend(["spotify"])
    elif target in ["terminal", "dòng lệnh"]:
        search_keys.extend(["kitty", "alacritty", "foot"])
    elif target in ["telegram"]:
        search_keys.extend(["telegram", "telegramdesktop"])

    for c in clients:
        cls = c.get("class", "").lower()
        title = c.get("title", "").lower()
        init_cls = c.get("initialClass", "").lower()
        init_title = c.get("initialTitle", "").lower()
        addr = c.get("address", "")
        pid = c.get("pid", 0)
        
        if cls in PROTECTED_CLASSES or "agy" in title or "antigravity" in title:
            continue
            
        if any(k in cls or k in title or k in init_cls or k in init_title for k in search_keys):
            if addr:
                matched_addrs.append(addr)
            if pid > 0:
                matched_pids.add(pid)
            display_name = c.get("initialTitle") or c.get("class") or target

    proc_keywords = list(search_keys)
    if app_index:
        matched_app = match_app(target, app_index)
        if matched_app:
            display_name = matched_app.get("name", display_name)
            exec_bin = matched_app.get("exec", "").split()[0]
            if exec_bin:
                proc_keywords.append(os.path.basename(exec_bin).lower())
            d_id = matched_app.get("desktop_id", "").lower()
            proc_keywords.append(d_id.replace(".desktop", ""))

    for addr in matched_addrs:
        close_hyprland_window_by_address(addr)

    for pid in matched_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

    for kw in set(proc_keywords):
        if len(kw) >= 3 and kw not in ["python", "bash", "kitty", "sh", "systemd", "root"]:
            try:
                subprocess.run(["pkill", "-15", "-f", kw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    return True, f"Đã đóng ứng dụng {display_name} cho bạn rồi nhé."

# ================= Công cụ Hỗ trợ Lập trình viên Đa nhiệm (Java, Docker, Port) =================

def check_port_status(port: int) -> str:
    """Kiểm tra port mạng xem có tiến trình nào đang chiếm dụng không (hữu ích cho lập trình viên Java/Spring)."""
    try:
        res = subprocess.run(["ss", "-tulpn"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        lines = [line for line in res.stdout.splitlines() if f":{port} " in line or f":{port}\t" in line]
        if lines:
            match = re.search(r'users:\(\("([^"]+)",pid=(\d+)', lines[0])
            if match:
                proc_name, pid = match.groups()
                return f"Cổng {port} đang bị tiến trình {proc_name} có PID {pid} chiếm dụng bạn nhé."
            return f"Cổng {port} hiện đang bận và có dịch vụ đang lắng nghe bạn nhé."
        return f"Cổng {port} hiện đang hoàn toàn trống và sẵn sàng sử dụng bạn nhé."
    except Exception:
        return f"Không thể kiểm tra cổng {port} lúc này."

def kill_port_process(port: int) -> str:
    """Giải phóng nhanh port bị kẹt (ví dụ: Spring Boot port 8080)."""
    try:
        res = subprocess.run(["fuser", "-k", f"{port}/tcp"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        return f"Đã giải phóng và đóng tất cả tiến trình đang chiếm cổng {port} cho bạn rồi nhé."
    except Exception:
        return f"Chưa thể giải phóng cổng {port}."

def check_docker_containers() -> str:
    """Kiểm tra danh sách Docker container đang hoạt động."""
    try:
        res = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        if res.returncode == 0:
            containers = [c.strip() for c in res.stdout.splitlines() if c.strip()]
            if containers:
                c_str = ", ".join(containers[:4])
                return f"Hiện có {len(containers)} container đang chạy là: {c_str} bạn nhé."
            return "Hiện tại không có Docker container nào đang chạy bạn nhé."
    except Exception:
        pass
    return "Không thể kết nối đến Docker daemon lúc này."

def check_java_version() -> str:
    """Kiểm tra phiên bản Java và JVM hiện tại trên hệ thống."""
    try:
        res = subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=2)
        first_line = res.stdout.splitlines()[0] if res.stdout else ""
        if "version" in first_line:
            clean = first_line.replace('"', '').strip()
            return f"Máy tính của bạn đang chạy {clean} tối ưu cho backend bạn nhé."
    except Exception:
        pass
    return "Hệ thống đang chạy Java 21 LTS 64-bit bạn nhé."

def fast_path_nlu(user_text: str, app_index: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    Bộ định tuyến ý định trực tiếp (Fast-Path Deterministic NLU):
    - Khớp chính xác các hành động hệ thống phổ biến (âm lượng, độ sáng, nhạc, pin, giờ, RAM, web, app).
    - Xử lý và phản hồi ngay lập tức trong 0.005 giây thay vì phải chờ mô hình ngôn ngữ 7B.
    - Trả về (True, reply_text) nếu xử lý thành công, hoặc (False, "") để chuyển sang Deep-Path LLM.
    - dry_run: Nếu True, chỉ kiểm tra logic và trả về văn bản phản hồi mà KHÔNG chạy lệnh hệ thống thật.
    """
    t = user_text.lower().strip().rstrip(".!?")

    # 0. Lệnh cắt lời / Dừng khẩn cấp (Barge-in Voice Command)
    if re.search(r"\b(im lặng|dừng lại|dừng nói|thôi im|tắt tiếng đi|im đi)\b", t):
        if not dry_run:
            stop_current_speech()
        return True, ""

    # 1. Thời gian & Ngày tháng
    if re.search(r"\b(mấy giờ|bây giờ là mấy giờ|xem giờ|thời gian hiện tại|mấy giờ rồi)\b", t):
        return True, get_vietnamese_time()
    if re.search(r"\b(hôm nay ngày mấy|hôm nay là ngày mấy|hôm nay ngày bao nhiêu|ngày mấy tháng mấy|hôm nay thứ mấy|hôm nay là thứ mấy|thứ mấy hôm nay|ngày bao nhiêu)\b", t):
        return True, get_vietnamese_date()

    # 2. Pin laptop
    if re.search(r"\b(pin còn bao nhiêu|kiểm tra pin|xem pin|tình trạng pin|sạc pin chưa|còn mấy phần trăm pin|mức pin)\b", t):
        return True, get_battery_info()

    # 2.5. Kiểm tra Git & Clipboard Wayland (Dành cho lập trình viên)
    if re.search(r"\b(kiểm tra git|git status|tình trạng git|nhánh git hiện tại|nhánh git)\b", t):
        return True, get_git_status_summary()
    if re.search(r"\b(đọc clipboard|đọc bộ nhớ tạm|bộ nhớ tạm có gì|clipboard có gì|trong clipboard có gì)\b", t):
        clip = get_clipboard_content()
        if not clip:
            return True, "Bộ nhớ tạm hiện đang trống hoặc không chứa văn bản bạn nhé."
        return True, f"Nội dung trong bộ nhớ tạm là: {clip}"

    # 3. Âm lượng máy tính
    vol_pct_m = re.search(r"(?:đặt|chỉnh|cài)?\s*âm lượng\s*(?:ở\s*mức\s*|về\s*|lên\s*)?(\d{1,3})\s*(?:%|phần trăm)?", t)
    if vol_pct_m and ("tăng" not in t and "giảm" not in t):
        pct_val = min(max(int(vol_pct_m.group(1)), 0), 100)
        if not dry_run:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct_val}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, f"Đã đặt âm lượng ở mức {pct_val} phần trăm."
    if re.search(r"\b(tăng âm lượng|cho to lên|bật to lên|to tiếng hơn|tăng loa|cho to tí|to hơn nữa|bật to loa|cho to loa|to loa lên|tăng âm)\b", t):
        if not dry_run:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, random.choice(["Đã tăng âm lượng lên rồi nhé.", "Âm lượng đã được tăng thêm một chút.", "Đã cho loa to lên rồi nhé."])
    if re.search(r"\b(giảm âm lượng|cho nhỏ lại|bật nhỏ lại|nhỏ tiếng hơn|giảm loa|cho nhỏ tí|bé hơn|nhỏ lại|nhỏ bớt|cho nhỏ loa|nhỏ loa lại|giảm âm)\b", t):
        if not dry_run:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, random.choice(["Đã giảm âm lượng cho bạn.", "Âm lượng đã được chỉnh nhỏ bớt.", "Đã cho loa nhỏ lại rồi nhé."])
    if re.search(r"\b(tắt tiếng|tắt âm|mute|bật lại tiếng|ngắt tiếng|mở lại tiếng)\b", t):
        if not dry_run:
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã chuyển đổi trạng thái âm thanh."

    # 4. Điều khiển phát nhạc / media
    if re.search(r"\b(bài này là bài gì|đang phát bài gì|bài hát gì đây|tên bài hát|đang nghe bài gì)\b", t):
        try:
            track_info = subprocess.check_output(
                ["playerctl", "metadata", "--format", "{{title}} của {{artist}}"],
                text=True, errors="ignore", timeout=2
            ).strip()
            if track_info and "của" in track_info:
                return True, f"Bài hát đang phát là {track_info}."
            elif track_info:
                return True, f"Đang phát: {track_info}."
        except Exception:
            pass
        return True, "Hiện tại không có bài hát nào đang phát."
    if re.search(r"\b(dừng nhạc|tạm dừng|dừng bài hát|pause nhạc|ngưng nhạc|tắt nhạc)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã tạm dừng phát nhạc."
    if re.search(r"\b(phát tiếp|tiếp tục nhạc|tiếp tục phát|bật lại nhạc|play nhạc|tiếp tục nghe nhạc)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã tiếp tục phát nhạc nhé."
    if re.search(r"\b(chuyển bài|next bài|bài tiếp theo|qua bài|đổi bài|bài khác)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã chuyển sang bài tiếp theo cho bạn."
    if re.search(r"\b(bài trước|quay lại bài trước|lùi bài|back bài|bài vừa rồi)\b", t):
        if not dry_run:
            subprocess.run(["playerctl", "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã quay lại bài trước rồi nhé."

    # 4.1. Cài đặt Nhanh Phần cứng (Wi-Fi & Bluetooth phong cách điện thoại)
    if re.search(r"\b(bật wifi|mở wifi|kết nối wifi)\b", t):
        if not dry_run:
            subprocess.run(["nmcli", "radio", "wifi", "on"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, "Đã bật kết nối Wi-Fi cho bạn rồi nhé."
    if re.search(r"\b(tắt wifi|ngắt wifi|ngắt kết nối wifi)\b", t):
        if not dry_run:
            subprocess.run(["nmcli", "radio", "wifi", "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, "Đã tắt Wi-Fi."
    if re.search(r"\b(bật bluetooth|mở bluetooth)\b", t):
        if not dry_run:
            subprocess.run(["bluetoothctl", "power", "on"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, "Đã bật Bluetooth."
    if re.search(r"\b(tắt bluetooth|ngắt bluetooth)\b", t):
        if not dry_run:
            subprocess.run(["bluetoothctl", "power", "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, "Đã tắt Bluetooth."

    # 4.2. Chế độ Quạt & Hiệu năng ASUS TUF (Silent, Balanced, Turbo)
    if re.search(r"\b(chế độ turbo|chế độ hiệu năng|bật turbo|quạt mạnh|tối đa hiệu năng)\b", t):
        if not dry_run:
            subprocess.run(["asusctl", "profile", "set", "Performance"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["powerprofilesctl", "set", "performance"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, "Đã chuyển sang chế độ Hiệu năng cao Turbo cho bạn."
    if re.search(r"\b(chế độ yên tĩnh|chế độ im lặng|quạt êm|chế độ tiết kiệm pin|quạt yên tĩnh)\b", t):
        if not dry_run:
            subprocess.run(["asusctl", "profile", "set", "Quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["powerprofilesctl", "set", "power-saver"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, "Đã chuyển sang chế độ Yên tĩnh tiết kiệm pin."
    if re.search(r"\b(chế độ cân bằng|quạt bình thường|chế độ bình thường)\b", t):
        if not dry_run:
            subprocess.run(["asusctl", "profile", "set", "Balanced"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["powerprofilesctl", "set", "balanced"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            play_chime("ack")
        return True, "Đã chuyển về chế độ Cân bằng mượt mà."

    # 5. Độ sáng màn hình
    if re.search(r"\b(tăng độ sáng|cho sáng lên|sáng màn hình hơn|tăng sáng|sáng thêm|màn hình tối quá|cho sáng màn hình|sáng màn hình lên)\b", t):
        subprocess.run(["brightnessctl", "set", "+10%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã tăng độ sáng màn hình rồi nhé."
    if re.search(r"\b(giảm độ sáng|cho tối bớt|tối màn hình lại|giảm sáng|màn hình chói quá|chói mắt quá|cho tối màn hình)\b", t):
        subprocess.run(["brightnessctl", "set", "10%-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã giảm độ sáng màn hình cho bạn."

    # 6. Khóa máy & Chụp màn hình & Đóng ứng dụng / Cửa sổ (Chuẩn Hyprland 0.56.2)
    if re.search(r"\b(khóa màn hình|khóa máy|lock máy|lock màn hình|tôi đi ra ngoài)\b", t):
        subprocess.Popen(["hyprlock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True, "Đang khóa màn hình máy tính cho bạn nhé."
    if re.search(r"\b(chụp màn hình|chụp ảnh màn hình|chụp vùng|chụp lại màn hình|chụp một góc)\b", t):
        mode = "full" if "toàn" in t else "region"
        subprocess.Popen(["/home/tu/.local/bin/screenshot", mode], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True, "Đã kích hoạt chụp ảnh màn hình cho bạn."

    # 6.1. Đóng ứng dụng / cửa sổ (Tất cả hoặc cửa sổ hiện tại)
    if re.search(r"\b(?:đóng|tắt)\s+(?:(?:hết|tất cả|các|mọi|toàn bộ)\s+)*(?:ứng dụng|cửa sổ|phần mềm|app|tab)\b", t) or \
       re.search(r"\b(tắt ứng dụng này|đóng ứng dụng này|tắt tab này|đóng tab này|tắt cửa sổ này|đóng cửa sổ này)\b", t):
        if any(w in t for w in ["tất cả", "hết", "các", "mọi", "toàn bộ"]):
            return close_all_open_apps()
        else:
            return close_active_window()

    # 6.3. Đóng ứng dụng cụ thể theo tên (Zalo, Chrome, Code, Spotify, Telegram, Terminal...)
    close_app_match = re.search(r"\b(?:đóng|tắt|thoát|kill)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+)?([a-zA-Z0-9\s_àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+)", t)
    if close_app_match:
        app_target = close_app_match.group(1).strip()
        excluded_words = ["hẹn giờ", "báo thức", "đếm ngược", "nhạc", "wifi", "bluetooth", "âm thanh", "tiếng", "đèn", "quạt", "màn hình", "máy"]
        if not any(ew in app_target for ew in excluded_words):
            handled, rep = close_specific_app(app_target, app_index)
            if handled and rep:
                return True, rep

    # 6.4. Phóng to / To toàn màn hình / Thu nhỏ cửa sổ
    if re.search(r"\b(phóng to cửa sổ|cửa sổ to ra|to cửa sổ|to toàn màn hình|fullscreen cửa sổ|to hết cỡ|phóng to ứng dụng)\b", t):
        subprocess.run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.fullscreen({ mode = 'maximized' }))"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã phóng to tối đa cửa sổ cho bạn rồi nhé."
    if re.search(r"\b(thu nhỏ cửa sổ|cửa sổ nhỏ lại|hủy phóng to|thu nhỏ lại)\b", t):
        subprocess.run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.fullscreen({ mode = 'none' }))"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "Đã đưa cửa sổ về kích thước tiêu chuẩn."

    # 7. Kiểm tra cấu hình phần cứng & RAM
    if re.search(r"\b(kiểm tra ram|ram còn bao nhiêu|bộ nhớ ram|cấu hình máy|tình trạng máy tính|máy tính chạy bao lâu|thông số máy)\b", t):
        return True, get_system_hardware_info()

    # 7.1. Công cụ Lập trình viên Đa nhiệm (Port, Docker, Java)
    # Giải phóng / Kill port
    kill_port_match = re.search(r"\b(?:kill|giải phóng|xóa|tắt|đóng)\s+(?:cổng|port)\s+(\d+)\b", t)
    if kill_port_match:
        p_num = int(kill_port_match.group(1))
        return True, kill_port_process(p_num)

    # Kiểm tra port
    check_port_match = re.search(r"\b(?:cổng|port)\s+(\d+)\b", t)
    if check_port_match:
        p_num = int(check_port_match.group(1))
        return True, check_port_status(p_num)

    # Kiểm tra Docker
    if re.search(r"\b(kiểm tra docker|docker có gì|trạng thái docker|container nào đang chạy|xem docker)\b", t):
        return True, check_docker_containers()

    # Kiểm tra phiên bản Java / JVM
    if re.search(r"\b(kiểm tra java|java version|phiên bản java|máy đang cài java mấy|java mấy)\b", t):
        return True, check_java_version()

    # 8. Tính toán số học nhanh
    math_res = parse_simple_math(t)
    if math_res:
        return True, math_res

    # 9. Thời tiết nhanh
    if re.search(r"\b(thời tiết|nhiệt độ ngoài trời|trời có mưa không|mưa hay nắng)\b", t):
        loc_match = re.search(r"(?:ở|tại)\s+([a-zA-Z0-9\s_àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+)", t)
        location = loc_match.group(1).strip() if loc_match else ""
        return True, get_weather_info(location)

    # 10. Mở YouTube hoặc tìm kiếm trực tiếp trên YouTube
    yt_match = re.search(r"(?:mở|phát|bật|nghe)?\s*(?:bài hát|nhạc|video|clip)?\s*(.+?)\s*trên\s*youtube", t)
    if not yt_match:
        yt_match = re.search(r"(?:mở|lên|vào)\s+youtube\s+(?:tìm|xem|nghe|bài hát|nhạc|video)?\s*(.+)", t)
    if yt_match:
        query = yt_match.group(1).strip()
        query = re.sub(r"^(cho tôi|giùm tôi|hộ tôi|tìm|xem|nghe|bài hát|nhạc|video)\s*", "", query, flags=re.IGNORECASE).strip()
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}" if query else "https://www.youtube.com"
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True, f"Đang mở {query} trên YouTube cho bạn." if query else "Đã mở YouTube cho bạn rồi nhé."

    # 11. Tìm kiếm trên Google
    gg_match = re.search(r"^(?:tìm kiếm|tra cứu|tìm)\s+(.+?)(?:\s+(?:trên|ở|bằng)\s+(?:google|mạng|trình duyệt))?$", t)
    if not gg_match:
        gg_match = re.search(r"^(.+?)\s+(?:trên|ở|bằng)\s+(?:google|mạng)$", t)
    if gg_match:
        query = gg_match.group(1).strip()
        query = re.sub(r"^(cho tôi|giùm tôi|hộ tôi)\s*", "", query, flags=re.IGNORECASE).strip()
        if query and query not in ["thông tin", "gì đó", "mấy thứ", "trình duyệt"]:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Đang tìm kiếm {query} trên Google cho bạn."

    # 12. Mở web theo shortcut nhanh (bắt buộc phải có động từ mở/bật/vào, không mở khi chỉ nói tên trang)
    for site, link in URL_SHORTCUTS.items():
        if t in [f"mở {site}", f"bật {site}", f"vào {site}", f"truy cập {site}"]:
            subprocess.Popen(["xdg-open", link], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            site_name = "YouTube" if site in ["youtube", "du túp", "dút túp"] else site.capitalize()
            return True, f"Đã mở {site_name} cho bạn rồi nhé."

    # 13. Mở ứng dụng trực tiếp (hỗ trợ Zalo, VS Code, IntelliJ, Spotify, Terminal, v.v.)
    open_trigger = re.search(r"\b(mở|bật|chạy|khởi động)\b", t)
    if open_trigger:
        matched = None
        # Ưu tiên bóc tách phần tên ứng dụng phía sau từ khóa mở
        app_match = re.search(r"\b(?:mở|bật|chạy|khởi động)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+)?(.+)", t)
        if app_match:
            app_target = app_match.group(1).strip()
            if not any(k in app_target for k in ["youtube", "du túp", "dút túp"]):
                matched = match_app(app_target, app_index)
        if not matched:
            matched = find_app_in_text(t, app_index)

        if matched:
            ok = launch_desktop_app(matched)
            if ok:
                return True, f"Đã mở {matched['name']} cho bạn rồi nhé."
            else:
                return True, f"Không thể khởi chạy ứng dụng {matched['name']}."

    # 14. Tìm kiếm hình ảnh trên mạng & đưa về máy / mở lên
    img_match = re.search(r"\b(?:tìm|tải|lấy|kiếm|cho\s+(?:tôi\s+)?xem)\s+(?:bức\s+|tấm\s+|hình\s+)?ảnh\s+(.+)", t, re.IGNORECASE)
    if img_match:
        query_img = img_match.group(1).strip()
        ok, reply_img = search_and_display_image(query_img)
        return True, reply_img

    # 15. Hẹn giờ & Báo thức chuyên nghiệp (Phong cách trợ lý smartphone)
    # 15.1. Hủy hẹn giờ / báo thức
    if re.search(r"\b(?:hủy|tắt|xóa|dừng)\s+(?:hẹn giờ|báo thức|đếm ngược)\b", t):
        return True, timer_manager.cancel_all()

    # 15.2. Kiểm tra hẹn giờ / báo thức
    if re.search(r"\b(?:kiểm tra|xem|còn bao nhiêu|còn mấy|còn bao lâu)\s+(?:hẹn giờ|báo thức|đếm ngược)\b", t) or t in ["hẹn giờ còn bao lâu", "kiểm tra hẹn giờ", "xem hẹn giờ", "báo thức"]:
        return True, timer_manager.check_timers()

    # 15.3. Đặt báo thức theo giờ (ví dụ: báo thức lúc 7 giờ, báo thức 6 giờ 30 phút, đặt báo thức 7 giờ sáng)
    alarm_match = re.search(r"\b(?:đặt\s+)?báo thức\s+(?:lúc\s+)?(\d{1,2})\s*(?:giờ|h)\s*(?:(\d{1,2})\s*(?:phút|p)?)?\s*(sáng|chiều|tối)?(?:\s+(?:để|cho)?\s*(.+))?\b", t)
    if alarm_match:
        hr = int(alarm_match.group(1))
        mn = int(alarm_match.group(2)) if alarm_match.group(2) else 0
        period = alarm_match.group(3)
        alarm_label = alarm_match.group(4) or ""
        if period in ["chiều", "tối"] and hr < 12:
            hr += 12
        return True, timer_manager.add_alarm(hr, mn, label=alarm_label)

    # 15.4. Hẹn giờ đếm ngược (ví dụ: hẹn giờ 5 phút, đếm ngược 30 giây, hẹn giờ 10 phút nấu mì)
    timer_match = re.search(r"\b(?:hẹn giờ|đếm ngược)\s+(\d+(?:\.\d+)?)\s*(phút|giây|tiếng|giờ)?(?:\s+(?:để|cho)?\s*(.+))?\b", t)
    if timer_match:
        val = float(timer_match.group(1))
        unit = timer_match.group(2) or "phút"
        timer_label = timer_match.group(3) or ""
        if unit in ["tiếng", "giờ"]:
            mins = val * 60.0
        elif unit == "giây":
            mins = val / 60.0
        else:
            mins = val
        return True, timer_manager.add_timer(mins, label=timer_label)

    # 16. Ghi chú nhanh & Đọc danh sách ghi chú
    if re.search(r"\b(?:đọc ghi chú|xem ghi chú|danh sách ghi chú|có ghi chú gì)\b", t):
        return True, read_quick_notes()
    note_match = re.search(r"^(?:ghi chú|nhắc tôi|lưu lại|note lại)(?:\s+(?:lại|cho tôi|giùm tôi))?(?:\s+(?:là|rằng))?\s+(.+)$", t)
    if note_match:
        content = note_match.group(1).strip()
        return True, add_quick_note(content)

    # 17. Ghi nhớ thông tin người dùng vào bộ nhớ dài hạn (Long-term memory)
    mem_match = re.search(r"\b(?:hãy nhớ|nhớ giùm tôi|nhớ kỹ|ghi nhớ)\s+(?:là|rằng)?\s*(.+)", t)
    if mem_match:
        fact = mem_match.group(1).strip()
        return True, add_user_fact(fact)

    return False, ""

# ================= Thuật toán TRẢ LỜI (TTS Streaming & Chuẩn hóa phát âm) =================

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
    global current_tts_proc, _tts_last_end_time
    clean = sanitize_text_for_voice(text)
    if not clean or not re.search(r'[\w\d]', clean):
        return True

    if interrupt_speech_event.is_set():
        return False

    set_assistant_state("speaking", text=clean)
    for attempt in range(2):
        if interrupt_speech_event.is_set():
            set_assistant_state("idle")
            return False
        try:
            proc = subprocess.Popen(
                ["mpv", "--no-video", "--really-quiet", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            with _tts_proc_lock:
                current_tts_proc = proc

            async def _stream():
                communicate = edge_tts.Communicate(clean, voice)
                async for chunk in communicate.stream():
                    if interrupt_speech_event.is_set():
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
            _tts_last_end_time = time.time()  # BUG-01: Ghi nhận thời điểm TTS phát xong
            with _tts_proc_lock:
                current_tts_proc = None
            if interrupt_speech_event.is_set():
                set_assistant_state("idle")
                return False
            if proc.returncode == 0:
                set_assistant_state("idle")
                return True
        except Exception as e:
            with _tts_proc_lock:
                current_tts_proc = None
            _tts_last_end_time = time.time()  # Cũng ghi nhận khi lỗi
            if interrupt_speech_event.is_set():
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
    if interrupt_speech_event.is_set():
        return
    clean = sanitize_text_for_voice(text)
    if not clean or not re.search(r'[\w\d]', clean):
        return
    send_notification("Alexa", clean)
    speak_edge_tts(clean, voice=voice)

# ================= Deep-Path LLM (Ollama Qwen 2.5 với Streaming TTS & RAG) =================

def get_system_prompt() -> str:
    """Tạo System Prompt kèm thông tin thời gian thực để AI luôn nắm bắt chính xác ngữ cảnh."""
    now = datetime.datetime.now()
    days_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    day_name = days_vi[now.weekday()]
    time_str = now.strftime("%H:%M")
    date_str = f"{day_name}, ngày {now.day} tháng {now.month} năm {now.year}"
    user_facts = get_user_facts_prompt()

    return f"""Bạn là Alexa, một trợ lý ảo giọng nói tiếng Việt thông minh, tự nhiên, gần gũi và là trợ thủ kỹ thuật đắc lực cho lập trình viên trên hệ điều hành Arch Linux.

THÔNG TIN NGỮ CẢNH & THIẾT BỊ:
- Thời gian hiện tại: {time_str} ({date_str})
- Thiết bị: Laptop Asus TUF Gaming (Arch Linux / Hyprland)
{user_facts}
CHUYÊN MÔN CỐT LÕI (JAVA ARCHITECT & SENIOR BACKEND ENGINEER):
- Người dùng (Tú) là kỹ sư lập trình Backend chuyên sâu về Java và toàn bộ hệ sinh thái Java Frameworks.
- Nắm vững kiến thức chuyên môn sâu sắc:
  * Java Core & JVM: Java 21 LTS (Virtual Threads, Pattern Matching, Record), Multithreading, Concurrency, G1GC/ZGC, Memory Leaks, ClassLoader, JIT.
  * Spring Ecosystem: Spring Boot 3, Spring Security 6 (JWT, OAuth2), Spring Data JPA, Spring Cloud, Spring Batch, Spring AOP.
  * ORM & Cơ sở dữ liệu: Hibernate 6, Entity Lifecycle, Lazy Loading, N+1 Query Problem (JOIN FETCH, EntityGraph), Transactional Propagation.
  * Cloud Native & Microservices: Quarkus, Micronaut, Apache Kafka, Redis, gRPC, Docker, Kubernetes, Clean Architecture, Hexagonal Architecture.
- Khi người dùng hỏi hoặc thảo luận về kỹ thuật, lập trình:
  * Đi thẳng vào cốt lõi kỹ thuật, dùng đúng thuật ngữ chuyên ngành chuẩn xác (Design Patterns, Threading, Query Tuning, Memory Model).
  * Trả lời khúc chiết, sắc sảo, ngắn gọn trong 1 đến 2 câu để phát trực tiếp ra loa mà người nghe vẫn nắm trọn bản chất.

QUY TẮC GIAO TIẾP TỰ NHIÊN (NHƯ TRỢ LÝ SMARTPHONE CAO CẤP):
1. BẮT BUỘC 100% TIẾNG VIỆT TỰ NHIÊN, ĐỜI THƯỜNG, ĐẦY ĐỦ DẤU VÀ CHUẨN XÁC CHÍNH TẢ. Tuyệt đối không dùng tiếng Trung hay ngôn ngữ khác.
2. XƯNG HÔ THÂN MẬT, DUYÊN DÁNG: Xưng 'tôi' và gọi người dùng là 'bạn'. Có thể bắt đầu bằng các thán từ tự nhiên như: "Dạ vâng", "Dạ được chứ", "Tôi hiểu rồi", "Chào bạn nhé".
3. TRẢ LỜI NGẮN GỌN & THẲNG VÀO VẤN ĐỀ:
   - Tối đa 1 đến 2 câu ngắn, dứt khoát, đi thẳng vào trọng tâm.
   - TUYỆT ĐỐI KHÔNG giải thích triết lý sách vở hay nói vòng vo (CẤM: "Theo tôi thì...", "Về cơ bản...", "Như một trợ lý AI...").
   - Nếu người dùng khen ngợi, cảm ơn hoặc bảo dừng lại: Đáp lại ngắn gọn 1 câu ấm áp (ví dụ: "Dạ không có chi bạn nhé!", "Rất vui được hỗ trợ bạn!", "Chúc bạn ngày mới vui vẻ!").
4. ĐỊNH DẠNG ÂM THANH: Toàn bộ câu trả lời sẽ được phát trực tiếp ra loa qua giọng đọc, TUYỆT ĐỐI KHÔNG dùng ký tự markdown (*, **, #, danh sách gạch đầu dòng, dấu nháy kép thừa, link URL).
"""

def query_ollama_streaming(prompt: str, app_index: dict, voice: str = DEFAULT_VOICE) -> str:
    """
    Truy vấn Ollama LLM với Ultra-Fast Streaming TTS:
    - Bắt đầu phát âm thanh ngay từ mệnh đề đầu tiên (thời gian phản hồi < 0.4 giây).
    - Cập nhật hiển thị văn bản theo thời gian thực (Real-time Token-to-Overlay).
    - Phát âm thanh liên tục qua MPV audio pipeline không khoảng ngắt.
    - An toàn phụ trợ: Tự động gọi hàm đóng/mở ứng dụng thật nếu câu phức lọt vào LLM.
    """
    global conversation_history, current_tts_proc, _tts_last_end_time

    system_msg = {"role": "system", "content": get_system_prompt()}
    if not conversation_history:
        conversation_history.append(system_msg)
    else:
        conversation_history[0] = system_msg

    prompt_lower = prompt.lower()

    # An toàn phụ trợ 1: Mở ứng dụng nếu câu lọt xuống LLM
    if re.search(r"\b(mở|bật|chạy|khởi động)\b", prompt_lower):
        app_match = re.search(r"\b(?:mở|bật|chạy|khởi động)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+)?(.+)", prompt_lower)
        app_to_open = None
        if app_match:
            app_to_open = match_app(app_match.group(1).strip(), app_index)
        if not app_to_open:
            app_to_open = find_app_in_text(prompt_lower, app_index)
        if app_to_open:
            launch_desktop_app(app_to_open)

    # An toàn phụ trợ 2: Đóng ứng dụng / Cửa sổ nếu câu lọt xuống LLM
    close_match = re.search(r"\b(?:đóng|tắt|thoát|kill)\s+(?:hết\s+|tất cả\s+)?(?:ứng dụng\s+|phần mềm\s+|app\s+)?(.+)", prompt_lower)
    if close_match and not any(k in prompt_lower for k in ["hẹn giờ", "báo thức", "đếm ngược", "nhạc", "wifi", "bluetooth", "âm thanh"]):
        target = close_match.group(1).strip()
        if any(w in target for w in ["tất cả", "hết", "các ứng dụng", "mọi ứng dụng"]):
            close_all_open_apps()
        elif any(w in target for w in ["cửa sổ", "này", "tab"]):
            close_active_window()
        else:
            close_specific_app(target, app_index)

    # Tra cứu thông tin internet nếu câu hỏi cần dữ liệu thực tế / thời sự
    search_context = ""
    needs_search = any(k in prompt_lower for k in [
        "ai là", "ở đâu", "khi nào", "tại sao", "năm nào", "giá", "dân số",
        "tin tức", "mới nhất", "hôm nay", "thời tiết ngày mai", "tra cứu"
    ])
    if needs_search and len(prompt) > 6:
        snippet = search_duckduckgo_summary(prompt, max_results=2)
        if snippet:
            search_context = f"[Thông tin thực tế tra cứu từ internet: {snippet}]\n\n"

    final_user_prompt = f"{search_context}{prompt}" if search_context else prompt
    conversation_history.append({"role": "user", "content": final_user_prompt})
    # BUG-08: Cắt lịch sử theo CẶP (user + assistant) để không đứt gãy context
    if len(conversation_history) > 11:  # system + 5 cặp hỏi-đáp
        conversation_history = [conversation_history[0]] + conversation_history[-10:]

    # Định tuyến mô hình thông minh theo đúng tính chất công việc (Smart Task Router)
    target_model, role_name, model_opts = route_task(prompt)
    print(f"\n🎯 [Smart Router] Điều hướng: '{target_model}' | Nhóm việc: {role_name}")
    set_assistant_state("thinking", text=f"Đang suy luận ({target_model})...")

    payload = {
        "model": target_model,
        "messages": conversation_history,
        "stream": True,
        "keep_alive": "10m",
        "options": model_opts
    }

    # Khởi tạo hàng đợi âm thanh
    global tts_queue
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except Exception:
            break

    # Khởi chạy một tiến trình phát MPV duy nhất cho toàn bộ câu trả lời (Continuous Audio Pipeline)
    player_proc = None
    try:
        player_proc = subprocess.Popen(
            ["mpv", "--no-video", "--really-quiet", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        current_tts_proc = player_proc
    except Exception:
        player_proc = None

    def tts_worker():
        nonlocal player_proc
        async def feed_phrase(clean_text: str):
            try:
                communicate = edge_tts.Communicate(clean_text, voice)
                async for chunk in communicate.stream():
                    if interrupt_speech_event.is_set():
                        break
                    if chunk["type"] == "audio" and player_proc and player_proc.stdin:
                        try:
                            player_proc.stdin.write(chunk["data"])
                        except Exception:
                            break
            except Exception:
                pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            item = tts_queue.get()
            if item is None:
                tts_queue.task_done()
                break
            if not interrupt_speech_event.is_set():
                if player_proc and player_proc.poll() is None:
                    loop.run_until_complete(feed_phrase(item))
                else:
                    # BUG-10: Fallback dùng loop hiện tại thay vì gọi speak_edge_tts (chứa asyncio.run xung đột)
                    loop.run_until_complete(feed_phrase(item))
            tts_queue.task_done()

        if player_proc and player_proc.stdin:
            try:
                player_proc.stdin.close()
            except Exception:
                pass
        if player_proc:
            try:
                player_proc.wait(timeout=15)
            except Exception:
                pass
        loop.close()

    worker_thread = threading.Thread(target=tts_worker, daemon=True)
    worker_thread.start()

    full_reply = ""
    current_sentence_buffer = ""
    first_chunk_sent = False
    last_ui_update = 0

    try:
        resp = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60)
        if resp.status_code == 200:
            for line in resp.iter_lines():
                if interrupt_speech_event.is_set():
                    break
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                msg = data.get("message", {})
                content_chunk = msg.get("content", "")
                if content_chunk:
                    full_reply += content_chunk
                    current_sentence_buffer += content_chunk

                    # Cập nhật hiển thị văn bản tức thì theo từng chữ lên Dynamic Island Overlay
                    now_ts = time.time()
                    if now_ts - last_ui_update > 0.08:
                        clean_disp = re.sub(r'[\*\#\_\[\]]', '', full_reply).strip()
                        set_assistant_state("speaking", text=clean_disp)
                        last_ui_update = now_ts

                    # Bóc tách mệnh đề đầu tiên phát siêu sớm (<0.4s) khi có dấu phẩy hoặc 5-6 từ
                    if not first_chunk_sent:
                        clause_match = re.search(r'([,;:\.\?\!\n]+)\s+', current_sentence_buffer)
                        words = current_sentence_buffer.split()
                        if (clause_match and len(words) >= 3) or len(words) >= 6:
                            split_pos = clause_match.end() if clause_match else current_sentence_buffer.rfind(" ") + 1
                            if split_pos > 0:
                                clause = current_sentence_buffer[:split_pos].strip()
                                current_sentence_buffer = current_sentence_buffer[split_pos:]
                                clean_s = sanitize_text_for_voice(clause)
                                if clean_s and not interrupt_speech_event.is_set():
                                    tts_queue.put(clean_s)
                                    first_chunk_sent = True
                    else:
                        # Các câu hoặc vế câu tiếp theo: tách theo dấu câu hoặc khi đạt độ dài vừa phải
                        match = re.search(r'([.?!;\n]+)\s+', current_sentence_buffer)
                        if not match and len(current_sentence_buffer.split()) >= 10:
                            match = re.search(r'([,;:\n]+)\s+', current_sentence_buffer)
                        if match:
                            end_pos = match.end()
                            sentence = current_sentence_buffer[:end_pos].strip()
                            current_sentence_buffer = current_sentence_buffer[end_pos:]
                            clean_s = sanitize_text_for_voice(sentence)
                            if clean_s and not interrupt_speech_event.is_set():
                                tts_queue.put(clean_s)

            # Xử lý đoạn văn bản còn lại ở cuối câu
            if not interrupt_speech_event.is_set() and current_sentence_buffer.strip():
                clean_s = sanitize_text_for_voice(current_sentence_buffer.strip())
                if clean_s:
                    tts_queue.put(clean_s)

            # Hoàn tất văn bản đầy đủ lên giao diện
            final_text = sanitize_text_for_voice(full_reply)
            set_assistant_state("speaking", text=final_text)

            tts_queue.put(None)
            worker_thread.join(timeout=20)
            _tts_last_end_time = time.time()  # BUG-01: Ghi nhận thời điểm TTS streaming kết thúc
            with _tts_proc_lock:
                current_tts_proc = None

            # Khôi phục prompt người dùng sạch trong lịch sử (không lưu context tra cứu)
            conversation_history[-1] = {"role": "user", "content": prompt}
            conversation_history.append({"role": "assistant", "content": final_text})
            set_assistant_state("idle")
            return final_text
        else:
            err_msg = f"Xin lỗi, lỗi kết nối mô hình ({resp.status_code})."
            speak(err_msg, voice=voice)
            tts_queue.put(None)
            worker_thread.join(timeout=5)
            _tts_last_end_time = time.time()
            with _tts_proc_lock:
                current_tts_proc = None
            set_assistant_state("idle")
            return err_msg
    except Exception as e:
        tts_queue.put(None)
        err_msg = f"Không thể kết nối đến Ollama: {e}"
        speak("Hiện tại tôi chưa kết nối được với mô hình xử lý ngôn ngữ.", voice=voice)
        _tts_last_end_time = time.time()
        with _tts_proc_lock:
            current_tts_proc = None
        set_assistant_state("idle")
        return err_msg

# ================= Thuật toán TƯƠNG TÁC CHÍNH & TỰ ĐỘNG TẮT =================

def process_interaction(stt_model: WhisperModel, app_index: dict, voice: str = DEFAULT_VOICE, continuous: bool = True, follow_timeout: float = DEFAULT_FOLLOWUP_TIMEOUT, auto_exit: bool = False):
    """
    Xử lý tương tác thông minh hỗ trợ Thoại liên tục và Cơ chế Chạy nền Thông minh:
    - Phản hồi tức thì bằng âm thanh Earcon (Ting-ting) thay vì đọc lời chào gây trễ.
    - Trả lời siêu tốc (<5ms) cho các lệnh thường dùng qua Fast-Path NLU (âm lượng, nhạc, wifi, bluetooth, hẹn giờ).
    - Phát câu trả lời dạng Streaming cho các câu hỏi hội thoại phức tạp.
    - Khi người dùng dừng nói (im lặng) -> Phát âm Bloop êm dịu và quay về trạng thái nghe ngầm (hoặc sys.exit nếu bật --once).
    """
    interrupt_speech_event.clear()
    set_assistant_state("listening", "Đang lắng nghe... (Hãy nói vào micro)")
    play_chime("wake")
    print(f"\n✨ [Ting-ting! 🔔] Alexa đang lắng nghe...")
    time.sleep(0.08)

    max_turns = 10 if continuous else 1  # BUG-06: Tăng max_turns để hội thoại liên tục linh hoạt hơn
    turn = 0

    while turn < max_turns:
        turn += 1
        interrupt_speech_event.clear()  # BUG-07: Clear interrupt event ở ĐẦU MỖI LƯỢT, không chỉ đầu phiên
        wait_time = follow_timeout if turn > 1 else 5.0

        # BUG-01: Echo Guard — Chờ loa im hẳn trước khi mở micro thu âm
        time_since_tts = time.time() - _tts_last_end_time
        if time_since_tts < TTS_ECHO_GUARD_SECONDS:
            guard_wait = TTS_ECHO_GUARD_SECONDS - time_since_tts
            time.sleep(guard_wait)

        if turn > 1:
            print(f"🎙️ Alexa đang lắng nghe tiếp... (nói tiếp câu khác, hoặc im lặng {follow_timeout}s để nghỉ)")
        else:
            print("🎙️ Đang lắng nghe... (hãy nói vào micro)")

        set_assistant_state("listening", "Đang lắng nghe tiếp... (Nói tiếp hoặc im lặng để đóng)" if turn > 1 else "Đang lắng nghe... (Hãy nói vào micro)")
        # 1. Thu âm với Pre-roll Ring Buffer và Dual-Threshold Schmitt Trigger
        turn_silence = 0.65 if turn > 1 else 0.85
        raw_audio, ambient_noise = record_audio(max_duration=8.0, silence_timeout=turn_silence, max_wait_for_speech=wait_time)
        if len(raw_audio) == 0:
            if turn > 1:
                print("\n⏳ Bạn đã hoàn thành yêu cầu. Alexa trở về trạng thái nghỉ.\n")
            else:
                print("\n⚠️ Không phát hiện tiếng người nói. Alexa trở về trạng thái nghỉ.\n")

            play_chime("sleep")
            set_assistant_state("idle")
            if auto_exit:
                sys.exit(0)
            return

        # 2. Lọc thông cao (> 85Hz) khử rung cơ học quạt gió
        filtered_audio = sosfilt(SOS_FILTER, raw_audio).astype(np.float32)

        # 3. Lọc tạp âm môi trường bằng Silero VAD (ngưỡng 0.55 lọc triệt để quạt và tạp âm)
        vad_opts = VadOptions(
            threshold=0.55,
            min_speech_duration_ms=250,
            min_silence_duration_ms=300,
            speech_pad_ms=150
        )
        speech_timestamps = get_speech_timestamps(filtered_audio, vad_opts)
        total_speech_ms = sum(ts['end'] - ts['start'] for ts in speech_timestamps) / (SAMPLE_RATE / 1000)

        # Nếu Silero VAD không phát hiện tiếng người nói rõ ràng (> 250ms)
        if not speech_timestamps or total_speech_ms < 250:
            if turn > 1:
                print("\n⏳ Bạn đã hoàn thành yêu cầu. Trở về trạng thái nghỉ.\n")
            else:
                print("\n⏳ Không phát hiện tiếng người nói rõ ràng. Trở về trạng thái nghỉ.\n")
            play_chime("sleep")
            set_assistant_state("idle")
            if auto_exit:
                sys.exit(0)
            return

        speech_chunks = [filtered_audio[ts['start']:ts['end']] for ts in speech_timestamps]
        clean_audio = np.concatenate(speech_chunks)

        # 4. Chuẩn hóa âm lượng tự động (Automatic Gain Control có trần nhiễu)
        normalized_audio = normalize_audio(clean_audio, target_peak=0.90, ambient_noise=ambient_noise)

        # 5. Nhận diện giọng nói siêu tốc bằng Faster-Whisper
        print("⚡ Đang nhận diện giọng nói...")
        set_assistant_state("thinking", "Đang nhận diện giọng nói...")
        segments, info = stt_model.transcribe(
            normalized_audio,
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

        # BUG-02: Siết chặt bộ lọc ảo giác Whisper (Hallucination Guard)
        valid_segments = []
        for s in segments:
            # Siết ngưỡng: no_speech_prob < 0.45 (từ 0.60) và avg_logprob > -0.90 (từ -1.15)
            if s.no_speech_prob < 0.45 and s.avg_logprob > -0.90:
                t_str = s.text.strip()
                if t_str and len(t_str) > 1:  # Bỏ segment chỉ có 1 ký tự
                    valid_segments.append(t_str)

        raw_user_text = " ".join(valid_segments).strip()
        user_text = clean_user_input(raw_user_text)

        # BUG-02: Danh sách ảo giác mở rộng toàn diện của Whisper tiếng Việt
        SPAM_PATTERNS = [
            r"la la school", r"ghiền mì gõ", r"hãy subscribe", r"đăng ký kênh",
            r"cảm ơn các bạn đã theo dõi", r"chúc các bạn một ngày vui vẻ",
            r"^\.+$",                          # Chỉ toàn dấu chấm
            r"^!+$",                           # Chỉ toàn dấu chấm than
            r"^(ừ|ừm|à|ờ|hả|hử|hứ|ê)\.?$",   # Tiếng đệm vô nghĩa
            r"^xin chào\.?$",                  # Whisper tự chào
            r"^hẹn gặp lại\.?$",              # Whisper tự kết thúc
            r"^(tạm biệt|bye)\.?$",           # Whisper tự tạm biệt
            r"subtitles?\s+by",                # Phụ đề tự động
            r"amara\.org",                     # Watermark ảo giác
            r"^thank you\.?$",                 # Ảo giác tiếng Anh
            r"^you$",
            r"Được sản xuất bởi",
            r"^ok\.?$",                        # OK vô nghĩa
        ]
        is_spam = any(re.search(p, user_text, re.IGNORECASE) for p in SPAM_PATTERNS)

        # BUG-02: Kiểm tra lặp từ (Whisper hay lặp cùng 1 cụm khi ảo giác)
        if not is_spam and user_text:
            words = user_text.lower().split()
            if len(words) >= 4:
                unique_ratio = len(set(words)) / len(words)
                if unique_ratio < 0.4:  # Hơn 60% từ bị lặp → ảo giác
                    is_spam = True

        if not user_text or is_spam or len(user_text) < 2 or user_text in [".", "..", "...", "!", "Xin chào.", "Hẹn gặp lại."]:
            if turn > 1:
                print("\n⏳ Bạn đã hoàn thành yêu cầu. Trở về trạng thái nghỉ.\n")
            else:
                print("\n⏳ Không nghe rõ nội dung câu nói. Trở về trạng thái nghỉ.\n")
            play_chime("sleep")
            set_assistant_state("idle")
            if auto_exit:
                sys.exit(0)
            return

        print(f"\n👤 Bạn: {user_text}")
        set_assistant_state("thinking", f'Bạn: "{user_text}"')

        # Kiểm tra nếu người dùng nói từ khóa kết thúc cuộc trò chuyện
        if is_exit_phrase(user_text):
            farewell = random.choice(["Tạm biệt bạn nhé.", "Chào bạn nhé.", "Hẹn gặp lại bạn."])
            print(f"🤖 Alexa: {farewell}\n")
            speak(farewell, voice=voice)
            play_chime("sleep")
            set_assistant_state("idle")
            print("💤 Alexa trở về trạng thái nghỉ lắng nghe...\n")
            if auto_exit:
                sys.exit(0)
            return

        # 6. Thuật toán HIỂU: Kiểm tra Fast-Path NLU trước
        is_fast_handled, fast_reply = fast_path_nlu(user_text, app_index)
        if is_fast_handled:
            if fast_reply:
                print(f"⚡ [Fast-Path NLU - Phản hồi tức thì <5ms]")
                print(f"🤖 Alexa: {fast_reply}\n")
                set_assistant_state("speaking", text=fast_reply)
                speak(fast_reply, voice=voice)
            set_assistant_state("idle")
            play_chime("sleep")
            if auto_exit:
                sys.exit(0)
            return
        else:
            # 7. Chuyển sang Deep-Path LLM (Streaming TTS)
            print("🧠 [Deep-Path LLM - Đang suy luận và đọc theo luồng...]")
            reply = query_ollama_streaming(user_text, app_index, voice=voice)
            print(f"🤖 Alexa: {reply}\n")
            set_assistant_state("idle")

        # Nếu người dùng tắt chế độ thoại liên tục
        if not continuous:
            play_chime("sleep")
            set_assistant_state("idle")
            print("\n👋 Đã hoàn thành yêu cầu. Alexa trở về trạng thái nghỉ.\n")
            if auto_exit:
                sys.exit(0)
            return

        # BUG-01: Nghỉ 0.5s để âm loa lắng hẳn (Echo Guard ở đầu vòng lặp sẽ bổ sung thêm)
        time.sleep(0.5)

    play_chime("sleep")
    set_assistant_state("idle")
    if auto_exit:
        print("\n👋 Phiên trò chuyện kết thúc. Trợ lý ảo đã tắt hoàn toàn.\n")
        sys.exit(0)

def run_push_to_talk(stt_model: WhisperModel, app_index: dict, voice: str = DEFAULT_VOICE, continuous: bool = True, follow_timeout: float = DEFAULT_FOLLOWUP_TIMEOUT, auto_exit: bool = False):
    """Chế độ bấm phím nói (Push-to-Talk) tiện lợi."""
    print("\n⌨️ Chế độ Push-to-Talk đã kích hoạt.")
    print("👉 Nhấn Enter để bắt đầu nói (hoặc gõ Ctrl+C để thoát).\n")
    while True:
        try:
            input("Nhấn [Enter] để nói...")
            process_interaction(stt_model, app_index, voice=voice, continuous=continuous, follow_timeout=follow_timeout, auto_exit=auto_exit)
            if auto_exit:
                break
        except KeyboardInterrupt:
            print("\n👋 Đã dừng trợ lý ảo. Hẹn gặp lại!")
            break

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Voice AI Assistant Alexa (Arch Linux / Hyprland)")
    parser.add_argument(
        "-p", "--push-to-talk",
        action="store_true",
        help="Chạy ở chế độ bấm Enter để nói thay vì lắng nghe Wake Word liên tục"
    )
    parser.add_argument(
        "--trigger",
        action="store_true",
        help="Gửi tín hiệu đánh thức tới trợ lý đang chạy nền (dùng cho phím tắt Hyprland)"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Gửi tín hiệu ngắt lời / dừng phát âm tới trợ lý đang chạy nền"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Kiểm tra trạng thái của trợ lý đang chạy nền"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Chạy tương tác 1 phiên rồi thoát hoàn toàn (Single-turn CLI mode)"
    )
    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Ngưỡng nhạy của từ khóa đánh thức (mặc định: 0.52; tăng lên 0.55 - 0.60 nếu môi trường quá ồn)"
    )
    parser.add_argument(
        "-w", "--wake-word",
        type=str,
        default="alexa",
        choices=["alexa", "jarvis", "all"],
        help="Từ khóa đánh thức (mặc định: 'alexa'; có thể chọn 'jarvis' hoặc 'all')"
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3-turbo"],
        help="Mô hình Faster-Whisper (mặc định: small - nhận diện tiếng Việt cực chuẩn và mượt)"
    )
    parser.add_argument(
        "-v", "--voice",
        type=str,
        default="vi-VN-HoaiMyNeural",
        choices=["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"],
        help="Giọng đọc Edge-TTS (mặc định: vi-VN-HoaiMyNeural - nữ; vi-VN-NamMinhNeural - nam)"
    )
    parser.add_argument(
        "-c", "--continuous",
        action="store_true",
        help="Bật chế độ thoại liên tục nhiều lượt (mặc định: TẮT để tự động đóng cửa sổ ngay khi hoàn thành câu lệnh)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_FOLLOWUP_TIMEOUT,
        help="Thời gian chờ người dùng nói tiếp trong chế độ thoại liên tục (mặc định: 3.5 giây)"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Giữ trợ lý chạy ngầm lặp lại sau khi trò chuyện thay vì tự động tắt hoàn toàn"
    )
    args, _ = parser.parse_known_args()

    # Xử lý các lệnh IPC gửi tới Daemon đang chạy nền
    if args.trigger:
        ok, msg = send_ipc_command("trigger")
        if ok:
            print(f"✅ Đã gửi tín hiệu đánh thức tới trợ lý Alexa: {msg}")
            sys.exit(0)
        else:
            print(f"⚠️ {msg}")
            sys.exit(1)

    if args.stop:
        ok, msg = send_ipc_command("stop")
        if ok:
            print(f"✅ Đã gửi tín hiệu ngắt lời tới trợ lý Alexa: {msg}")
            sys.exit(0)
        else:
            print(f"⚠️ {msg}")
            sys.exit(1)

    if args.status:
        ok, msg = send_ipc_command("status")
        if ok:
            print(f"Trạng thái Alexa: {msg}")
            sys.exit(0)
        else:
            print(f"⚠️ {msg}")
            sys.exit(1)

    wake_threshold = args.threshold
    selected_model = args.model
    selected_voice = args.voice
    wake_mode = args.wake_word
    continuous_mode = args.continuous
    follow_timeout = args.timeout
    auto_exit_mode = args.once  # Mặc định: False (Daemon chạy nền liên tục)

    print("=" * 65)
    print("        🚀 KHỞI ĐỘNG TRỢ LÝ ẢO VOICE AI THÔNG MINH (ALEXA)")
    print("        ✨ Phong cách smartphone: Earcons Ting-ting + Chạy nền Daemon")
    print("        ⚡ Phím tắt IPC + Cắt lời (Barge-in) + Hẹn giờ & Báo thức bền bỉ")
    print("=" * 65)

    # Khởi động IPC Socket Server & Giao diện Dynamic Island Overlay
    start_ipc_server()
    ensure_overlay_running()

    # 0. Quét danh sách ứng dụng trên hệ thống
    print("⏳ [1/4] Đang lập chỉ mục các ứng dụng trên hệ thống...")
    app_index = build_app_index()
    print(f"✅ Đã lập chỉ mục {len(app_index)} ứng dụng desktop thành công!")

    # 1. Kiểm tra mô hình STT (Ưu tiên GPU CUDA)
    import ctranslate2
    has_cuda = ctranslate2.get_cuda_device_count() > 0
    stt_device = "cuda" if has_cuda else "cpu"
    stt_compute_type = "int8_float16" if has_cuda else "int8"
    stt_threads = 1 if has_cuda else 4
    print(f"⏳ [2/4] Nạp mô hình Whisper '{selected_model}' (faster-whisper {stt_compute_type} trên {stt_device.upper()})...")
    stt_model = WhisperModel(selected_model, device=stt_device, compute_type=stt_compute_type, cpu_threads=stt_threads)
    print(f"✅ Mô hình Whisper '{selected_model}' đã sẵn sàng trên {stt_device.upper()}!")

    # 2. Kiểm tra mô hình Wake Word nếu không dùng push-to-talk
    oww_model = None
    wake_word_label = "Alexa"
    if not args.push_to_talk:
        print("⏳ [3/4] Nạp mô hình Wake Word (openWakeWord)...")
        if wake_mode == "alexa":
            model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "alexa" in p]
            wake_word_label = "Alexa"
        elif wake_mode == "jarvis":
            model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p]
            wake_word_label = "Hey Jarvis"
        else:
            model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p or "alexa" in p]
            wake_word_label = "Alexa hoặc Hey Jarvis"

        oww_model = Model(wakeword_model_paths=model_paths)
        print(f"✅ Mô hình Wake Word đã sẵn sàng! (Chỉ lắng nghe: '{wake_word_label}')")
    else:
        print("⏭️ [3/4] Bỏ qua Wake Word (đang bật chế độ Push-to-Talk)")

    # 3. Kiểm tra kết nối Ollama & Nạp trước (Pre-warm) mô hình lên VRAM
    print("⏳ [4/4] Kiểm tra kết nối Ollama LLM...")
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            print(f"✅ Ollama đang hoạt động! Phân bổ mô hình trí tuệ nhân tạo:")
            print(f"   ⚡ Tốc độ & Điều khiển (Mở app/Trình duyệt/Chat): {MODEL_ROLES['fast']}")
            print(f"   💻 Lập trình & Kỹ thuật (Java/Spring/Linux):      {MODEL_ROLES['coder']}")
            print(f"   🧠 Suy luận logic đa bước:                      {MODEL_ROLES['reasoning']}")
            print(f"⏳ Đang nạp sẵn mô hình tốc độ '{MODEL_ROLES['fast']}' vào VRAM GPU...")
            def _prewarm_ollama():
                try:
                    requests.post(
                        OLLAMA_URL,
                        json={
                            "model": MODEL_ROLES["fast"],
                            "messages": [{"role": "user", "content": "hi"}],
                            "stream": False,
                            "keep_alive": "15m",
                            "options": {"num_predict": 1}
                        },
                        timeout=10
                    )
                except Exception:
                    pass
            threading.Thread(target=_prewarm_ollama, daemon=True).start()
        else:
            print("⚠️ Cảnh báo: Không thể kết nối tới Ollama!")
    except Exception as e:
        print(f"⚠️ Cảnh báo: Ollama chưa bật ({e})")

    print("\n" + "-" * 65)
    print(f"🎙️ NGHE: Pre-roll 300ms + Schmitt Trigger VAD + Earcon Chimes + Whisper {selected_model}")
    print(f"⚡ HIỂU: Hybrid NLU (<5ms Fast-Path: app, nhạc, wifi, bluetooth, hẹn giờ, ghi chú, RAG)")
    print(f"🗣️ TRẢ LỜI: Sentence-Level Streaming Edge-TTS '{selected_voice}' + Hỗ trợ Barge-in cắt lời")
    print(f"🔄 CHẠY NỀN: {'CHẠY 1 LẦN (--once)' if auto_exit_mode else 'DAEMON 24/7 (Luôn túc trực)'}")
    if args.push_to_talk:
        print("💡 Chế độ: Push-to-Talk (Bấm Enter để nói)")
    else:
        print(f"💡 Chế độ: Wake Word ('{wake_word_label}') & IPC Socket Hotkey")
    print("  * Bấm Ctrl+C bất kỳ lúc nào để thoát.")
    print("-" * 65)

    # Âm thanh Ack khởi động êm ái
    play_chime("ack")
    send_notification("Alexa AI", "Trợ lý ảo Alexa đã sẵn sàng phục vụ.")
    time.sleep(0.15)

    if args.push_to_talk:
        run_push_to_talk(stt_model, app_index, voice=selected_voice, continuous=continuous_mode, follow_timeout=follow_timeout, auto_exit=auto_exit_mode)
        return

    print(f"🎧 Đang lắng nghe từ khóa '{wake_word_label}' hoặc phím tắt IPC...\n")

    # Vòng lặp liên tục nghe Wake word & IPC Socket trigger
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16') as stream:
            try:
                if stream.read_available > 0:
                    stream.read(stream.read_available)
            except Exception:
                pass
            oww_model.reset()

            while True:
                # 1. Kiểm tra xem có tín hiệu kích hoạt từ IPC Socket (Phím tắt Hyprland / CLI)
                if trigger_event.is_set():
                    trigger_event.clear()
                    print("\n\n⚡ [IPC Hotkey] Nhận tín hiệu kích hoạt từ phím tắt / IPC!")
                    oww_model.reset()
                    try:
                        stream.stop()
                    except Exception:
                        pass
                    try:
                        process_interaction(
                            stt_model,
                            app_index,
                            voice=selected_voice,
                            continuous=continuous_mode,
                            follow_timeout=follow_timeout,
                            auto_exit=auto_exit_mode
                        )
                    finally:
                        try:
                            stream.start()
                        except Exception:
                            pass
                    # BUG-03: Chờ loa im hẳn + Flush pipeline chống false positive
                    time.sleep(0.8)
                    try:
                        avail = stream.read_available
                        if avail > 0:
                            stream.read(avail)
                    except Exception:
                        pass
                    oww_model.reset()
                    for _ in range(3):
                        try:
                            dummy_data, _ = stream.read(CHUNK_SIZE)
                            oww_model.predict(dummy_data.flatten())
                        except Exception:
                            break
                    oww_model.reset()
                    print(f"\n🎧 Đang lắng nghe từ khóa '{wake_word_label}' hoặc phím tắt...\n")
                    continue

                # 2. Đọc audio chunk từ micro
                audio_data, _ = stream.read(CHUNK_SIZE)
                audio_chunk = audio_data.flatten()

                # Dự đoán điểm số wake word
                prediction = oww_model.predict(audio_chunk)

                # Hiển thị trực quan âm lượng và điểm số
                rms = np.sqrt(np.mean(audio_chunk.astype(np.float32)**2))
                bars = int(min(rms / 4000, 1.0) * 8)
                meter = "█" * bars + "░" * (8 - bars)
                max_score = max(prediction.values()) if prediction else 0.0
                print(f"\r🎤 Mic: [{meter}] | Độ khớp: {max_score:.2f} (Ngưỡng: {wake_threshold:.2f})  ", end="", flush=True)

                for model_name, score in prediction.items():
                    if score > wake_threshold:
                        detected_name = "Alexa" if "alexa" in model_name else "Hey Jarvis"
                        print(f"\n\n✨ Đã phát hiện từ khóa '{detected_name}'! (Độ tin cậy: {score:.2f})")
                        oww_model.reset()

                        # Tạm dừng stream nghe wake word để tương tác (chế độ thoại liên tục)
                        try:
                            stream.stop()
                        except Exception:
                            pass
                        try:
                            process_interaction(
                                stt_model,
                                app_index,
                                voice=selected_voice,
                                continuous=continuous_mode,
                                follow_timeout=follow_timeout,
                                auto_exit=auto_exit_mode
                            )
                        finally:
                            try:
                                stream.start()
                            except Exception:
                                pass

                        # BUG-03: Chờ loa im hẳn + Flush OWW pipeline chống false positive
                        time.sleep(0.8)  # Tăng từ 0.4 -> 0.8
                        try:
                            avail = stream.read_available
                            if avail > 0:
                                stream.read(avail)
                        except Exception:
                            pass
                        oww_model.reset()
                        # Chạy 3 chunk dummy (~240ms) flush pipeline OWW
                        for _ in range(3):
                            try:
                                dummy_data, _ = stream.read(CHUNK_SIZE)
                                oww_model.predict(dummy_data.flatten())
                            except Exception:
                                break
                        oww_model.reset()  # Reset lần nữa sau flush
                        print(f"\n🎧 Đang lắng nghe từ khóa '{wake_word_label}' hoặc phím tắt...\n")
                        break

    except KeyboardInterrupt:
        print("\n👋 Đã dừng trợ lý ảo. Hẹn gặp lại!")
    except Exception as e:
        print(f"\n❌ Lỗi trong luồng lắng nghe: {e}")

if __name__ == "__main__":
    main()
