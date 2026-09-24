"""
Cấu hình tập trung cho Voice AI Assistant (V2)
"""

import os
from pathlib import Path

# Thư mục gốc của dự án (voice-ai/)
BASE_DIR = str(Path(__file__).resolve().parent.parent.parent)
OVERLAY_QML_PATH = os.path.join(BASE_DIR, "overlay", "VoiceOverlay.qml")

# Cấu hình Ollama LLM
OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_FAST_MODEL = "qwen2.5:3b"
DEFAULT_CODER_MODEL = "qwen2.5-coder:7b"
DEFAULT_REASONING_MODEL = "qwen3:8b"

# Cấu hình giọng đọc & nhận diện giọng nói
DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # Nữ nhẹ nhàng
DEFAULT_VOICE_MALE = "vi-VN-NamMinhNeural"  # Nam
DEFAULT_STT_MODEL = "small"

# Cấu hình DSP âm thanh
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80ms chunk cho openWakeWord (16000 * 0.08)
DEFAULT_THRESHOLD = 0.52
DEFAULT_FOLLOWUP_TIMEOUT = 3.5
TTS_ECHO_GUARD_SECONDS = 0.8

# Đường dẫn lưu trữ dữ liệu & trạng thái
STATE_FILE_PATH = os.path.join(os.getenv("XDG_RUNTIME_DIR", "/tmp"), "alexa_state.json")
MEMORY_FILE = os.path.expanduser("~/.config/voice-ai/memory.json")
TIMERS_FILE = os.path.expanduser("~/.config/voice-ai/timers.json")
NOTES_FILE = os.path.expanduser("~/Documents/voice_notes.txt")
PICTURES_DIR = os.path.expanduser("~/Pictures")

# Prompt định hướng từ vựng công nghệ và tên phần mềm cho Whisper
WHISPER_INITIAL_PROMPT = (
    "Chào bạn, tôi là trợ lý ảo tiếng Việt Alexa điều khiển máy tính Arch Linux. "
    "Mở ứng dụng Zalo, VS Code, Visual Studio Code, YouTube, Spotify, Kitty Terminal, "
    "Thunar, IntelliJ IDEA, Discord, Telegram, Brave, Chrome, Postman, Docker, DBeaver, OnlyOffice, Android Studio."
)

# Bảng alias ánh xạ tên gọi ứng dụng
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

PROTECTED_CLASSES = {"quickshell", "qs", "waybar", "dunst", "swaync"}

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
