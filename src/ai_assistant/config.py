from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

# Thư mục gốc của dự án (voice-ai/)
BASE_DIR = str(Path(__file__).resolve().parent.parent.parent)
PROJECT_ROOT = Path(BASE_DIR)
DEFAULT_MODELS_DIR = Path(os.getenv("AI_ASSISTANT_MODELS_DIR", PROJECT_ROOT / "models"))

@dataclass(frozen=True)
class AssistantConfig:
    models_dir: Path = DEFAULT_MODELS_DIR
    whisper_model_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("AI_ASSISTANT_WHISPER_MODEL", DEFAULT_MODELS_DIR / "whisper" / "whisper-small-vietnamese-ct2")
        )
    )
    piper_model_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("AI_ASSISTANT_PIPER_MODEL", DEFAULT_MODELS_DIR / "piper" / "vi_VN-giong_nu_pho_thong-medium.onnx")
        )
    )
    wakeword_model_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("AI_ASSISTANT_WAKEWORD_MODEL", DEFAULT_MODELS_DIR / "wakeword" / "alexa_verifier.pkl")
        )
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("AI_ASSISTANT_LLM_MODEL", "qwen3:4b")
    )
    sample_rate: int = 16000
    channels: int = 1

    def verify_required_assets(self) -> list[str]:
        """Kiểm tra sự tồn tại của các tệp mô hình và cảnh báo trước khi khởi chạy."""
        missing: list[str] = []
        required_paths = {
            "Piper TTS Model": self.piper_model_path,
        }
        for name, path in required_paths.items():
            if not path.exists():
                missing.append(f"- {name}: Không tìm thấy tại '{path}'")
        return missing

# Khởi tạo instance cấu hình mặc định
assistant_config = AssistantConfig()

OVERLAY_QML_PATH = os.path.join(BASE_DIR, "overlay", "VoiceOverlay.qml")

# Cấu hình Ollama LLM
OLLAMA_URL = f"{assistant_config.ollama_base_url}/api/chat"
OLLAMA_BASE_URL = assistant_config.ollama_base_url
DEFAULT_FAST_MODEL = assistant_config.ollama_model
DEFAULT_CODER_MODEL = "qwen3:4b"
DEFAULT_REASONING_MODEL = "qwen3:4b"

# Cấu hình chụp màn hình (giữ cho capture_screen)
VISION_MAX_IMAGE_SIZE = 1280        # Chiều dài tối đa (px) — resize giữ tỷ lệ
VISION_JPEG_QUALITY = 85            # Chất lượng nén JPEG (1-100)
SCREENSHOTS_DIR = os.path.expanduser("~/Pictures/Screenshots")

# Cấu hình giọng đọc & nhận diện giọng nói (Piper TTS Offline)
DEFAULT_VOICE = "vi_VN-giong_nu_pho_thong-medium"  # Giọng nữ phổ thông tự nhiên
DEFAULT_VOICE_MALE = "vi_VN-thanh_nien_tu_tin-medium"  # Giọng nam thanh niên tự tin
DEFAULT_STT_MODEL = "small"
TTS_ENGINE = os.getenv("TTS_ENGINE", "piper")  # Piper Local 100% Offline (<80ms, không cần mạng)
PIPER_MODEL_PATH = str(assistant_config.piper_model_path)
PIPER_MODEL_MALE_PATH = os.path.expanduser("~/Projects/python/voice-ai/models/piper/vi_VN-thanh_nien_tu_tin-medium.onnx")

# Cấu hình DSP âm thanh
SAMPLE_RATE = assistant_config.sample_rate
CHUNK_SIZE = 1280  # 80ms chunk cho openWakeWord (16000 * 0.08)
DEFAULT_THRESHOLD = 0.55  # Ngưỡng nhạy cân bằng tối ưu (Max non-wake score = 0.147, Alexa >= 0.70)
MUSIC_WAKE_THRESHOLD_BOOST = 0.05  # Tăng nhẹ khi đang bật nhạc lớn (ngưỡng 0.60) để chặn hoàn toàn gai âm thanh (transients)
WAKE_PATIENCE_FRAMES = 2  # Yêu cầu 2 khung liên tiếp (160ms) để loại bỏ gai nhọn tạm thời từ nhạc nhưng vẫn cực nhạy khi người nói
WAKE_VAD_THRESHOLD = 0.0  # Tắt bộ đệm VAD trễ của openWakeWord (tránh nuốt từ khi gọi đột ngột từ khoảng lặng)
DEFAULT_FOLLOWUP_TIMEOUT = 3.5
TTS_ECHO_GUARD_SECONDS = 0.8

# Đường dẫn lưu trữ dữ liệu & trạng thái
STATE_FILE_PATH = os.path.join(os.getenv("XDG_RUNTIME_DIR", "/tmp"), "alexa_state.json")
MEMORY_FILE = os.path.expanduser("~/.config/voice-ai/memory.json")
TIMERS_FILE = os.path.expanduser("~/.config/voice-ai/timers.json")
NOTES_FILE = os.path.expanduser("~/Documents/voice_notes.txt")
PICTURES_DIR = os.path.expanduser("~/Pictures")

# Prompt định hướng từ vựng công nghệ, ngữ âm và tên phần mềm cho Whisper
WHISPER_INITIAL_PROMPT = (
    "Chào bạn, tôi là trợ lý ảo tiếng Việt Alexa điều khiển máy tính Arch Linux Hyprland. "
    "Phát nhạc, bật nhạc, tắt nhạc, nghe nhạc, tạm dừng nhạc, dừng nhạc, chuyển bài hát, bài tiếp theo, tăng âm lượng, giảm âm lượng, tắt tiếng, "
    "Mở ứng dụng Firefox, phai fox, fire fox, phai phốc, trình duyệt Firefox, Zalo, da lô, VS Code, vi ét cốt, YouTube, du túp, Spotify, xì po ti phai, Kitty Terminal, téc mi nan, "
    "Thunar, IntelliJ IDEA, Discord, Telegram, Brave, Chrome, gu gồ, Postman, Docker, DBeaver. "
    "Mở Gmail, GitHub, gít húp, Facebook, phây búc, Google, ChatGPT, trình duyệt web, đóng ứng dụng, tắt ứng dụng, tắt cửa sổ, đóng tab hiện tại. "
    "Phóng to cửa sổ, phóng to lên, cho ứng dụng to lên, thu nhỏ toàn màn hình, hủy phóng to, chia đều màn hình, chia 50 50, chia 70 30, chia dọc, chia ngang, chế độ lập trình, chế độ giải trí. "
    "Mở Gmail, mở hòm thư, check mail, mở email, mở Gmail cho tôi, mở YouTube và Gmail, mở Gmail và Facebook, mở Gmail trên Firefox, mở trình duyệt Firefox. "
    "Mở gờ meo, gờ mail, gờ-meo, g-meo, mở gờ meo cho tôi, mở YouTube và gờ meo, mở Facebook và gờ meo, check gờ meo, kiểm tra gờ meo, đọc gờ meo. "
    "Mở YouTube và Facebook, mở Zalo và VS Code, mở Spotify và Chrome. "
    "Chuyển sang workspace 2, qua bàn làm việc 3, không gian làm việc số 1, đưa cửa sổ này sang workspace 4, chuyển thành cửa sổ nổi, toggle float, ghim cửa sổ này. "
    "Đặt âm lượng 50%, tăng âm lượng, giảm âm lượng, tắt tiếng, tăng độ sáng, giảm độ sáng, chế độ turbo, quạt yên tĩnh. "
    "Tạm dừng nhạc, dừng phát nhạc, tạm dừng bài hát, phát tiếp, tiếp tục nhạc, phát bài nhạc tiếp, chuyển bài hát, chuyển nhạc, đổi nhạc, đổi bài, bài tiếp theo, bài trước, bài khác, bài này là bài gì, đang phát bài gì, ai đang hát, ca sĩ nào hát. "
    "Kiểm tra thông số CPU, RAM, GPU, pin còn bao nhiêu, nhiệt độ, kiểm tra tốc độ mạng, wifi, bluetooth, cổng 8080, docker, git status, thời tiết hôm nay, bây giờ là mấy giờ, hẹn giờ 5 phút, báo thức, "
    "1 cộng 1 bằng 2, 1 trừ 3 bằng âm 2, tính toán, cộng, trừ, nhân, chia, bằng bao nhiêu, bằng mấy."
)

# Bảng alias ánh xạ tên gọi ứng dụng
APP_ALIASES = {
    # Web Browsers (Ưu tiên Firefox - trình duyệt mặc định trên hệ thống)
    "firefox": "firefox",
    "fire fox": "firefox",
    "file fox": "firefox",
    "filefox": "firefox",
    "phai fox": "firefox",
    "phai fóc": "firefox",
    "phai pho": "firefox",
    "phai phóc": "firefox",
    "phai phốc": "firefox",
    "phai phót": "firefox",
    "phai phó": "firefox",
    "fai fox": "firefox",
    "fai pho": "firefox",
    "fai phóc": "firefox",
    "fay fox": "firefox",
    "phi fox": "firefox",
    "cáo lửa": "firefox",
    "cáo đỏ": "firefox",
    "brave": "firefox",
    "bờ rây": "firefox",
    "b rây": "firefox",
    "trình duyệt": "firefox",
    "trình duyệt web": "firefox",
    "trình diệt": "firefox",
    "trình diệt web": "firefox",
    "trình zuyệt": "firefox",
    "duyệt web": "firefox",
    "diệt web": "firefox",
    "browser": "firefox",
    "web": "firefox",
    "chrome": "firefox",
    "google chrome": "firefox",
    "cốc cốc": "firefox",

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
    "spotfy": "spotify",
    "spoty": "spotify",
    "spotifi": "spotify",
    "supportify": "spotify",
    "nhạc": "spotify",
    "nghe nhạc": "spotify",
    "bật nhạc": "spotify",
    "xì po ti phai": "spotify",
    "xì bo ti phai": "spotify",
    "xì pô ti phai": "spotify",
    "sì po ti phai": "spotify",
    "xì po ti": "spotify",
    "sì po ti": "spotify",
    "xì pô ti": "spotify",
    "sờ po ti phai": "spotify",
    "sở bớt đi phai": "spotify",
    "xa bờ tùy phai": "spotify",
    "bớt đi phai": "spotify",
    "sờ bo ti": "spotify",

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
    "diu túp": "https://www.youtube.com",
    "vô tấp": "https://www.youtube.com",
    "vô túp": "https://www.youtube.com",
    "dô túp": "https://www.youtube.com",
    "dô tấp": "https://www.youtube.com",
    "zu túp": "https://www.youtube.com",
    "du tốc": "https://www.youtube.com",
    "dưu tốc": "https://www.youtube.com",
    "diu tốc": "https://www.youtube.com",
    "google": "https://www.google.com",
    "facebook": "https://www.facebook.com",
    "phây búc": "https://www.facebook.com",
    "phây buk": "https://www.facebook.com",
    "phây": "https://www.facebook.com",
    "phe búc": "https://www.facebook.com",
    "phây-búc": "https://www.facebook.com",
    "fb": "https://www.facebook.com",
    "github": "https://github.com",
    "gít húp": "https://github.com",
    "git hup": "https://github.com",
    "gít háp": "https://github.com",
    "git hap": "https://github.com",
    "gít hub": "https://github.com",
    "gít-húp": "https://github.com",
    "gh": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "gemini": "https://gemini.google.com",
    "reddit": "https://www.reddit.com",
    "tiktok": "https://www.tiktok.com",
    "tóp tóp": "https://www.tiktok.com",
    "gmail": "https://mail.google.com",
    "gờ meo": "https://mail.google.com",
    "gờ-meo": "https://mail.google.com",
    "gở meo": "https://mail.google.com",
    "gở-meo": "https://mail.google.com",
    "gơ meo": "https://mail.google.com",
    "gơ-meo": "https://mail.google.com",
    "gừ meo": "https://mail.google.com",
    "g-meo": "https://mail.google.com",
    "gmeo": "https://mail.google.com",
    "gờ mail": "https://mail.google.com",
    "gờ-mail": "https://mail.google.com",
    "gở mail": "https://mail.google.com",
    "gơ mail": "https://mail.google.com",
    "g-mail": "https://mail.google.com",
    "gờ neo": "https://mail.google.com",
    "gờ-neo": "https://mail.google.com",
    "gờ leo": "https://mail.google.com",
    "gờ-leo": "https://mail.google.com",
    "g neo": "https://mail.google.com",
    "g leo": "https://mail.google.com",
    "gừa mêu": "https://mail.google.com",
    "gửa mêu": "https://mail.google.com",
    "gờ mêu": "https://mail.google.com",
    "gờ-mêu": "https://mail.google.com",
    "gơ mêu": "https://mail.google.com",
    "g-mêu": "https://mail.google.com",
    "gừ mail": "https://mail.google.com",
    "g mail": "https://mail.google.com",
    "di meo": "https://mail.google.com",
    "zi meo": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "e-mail": "https://mail.google.com",
    "hòm thư": "https://mail.google.com",
    "hộp thư": "https://mail.google.com",
    "gồm meo": "https://mail.google.com",
    "gôm meo": "https://mail.google.com",
    "gờ miêu": "https://mail.google.com",
    "miêu": "https://mail.google.com",
    "gmaill": "https://mail.google.com",
    "gmailll": "https://mail.google.com",
    "gồm nhau": "https://mail.google.com",
    "gôm nhau": "https://mail.google.com",
    "gờ nhau": "https://mail.google.com",
    "ca mèo": "https://mail.google.com",
    "gần miêu": "https://mail.google.com",
    "gourmiel": "https://mail.google.com",
    "gour miel": "https://mail.google.com",
    "gourmeo": "https://mail.google.com",
    "gourmail": "https://mail.google.com",
    "gồm yêu": "https://mail.google.com",
    "gôm yêu": "https://mail.google.com",
    "gờ yêu": "https://mail.google.com",
    "cơm meo": "https://mail.google.com",
    "cơm mail": "https://mail.google.com",
    "con meo": "https://mail.google.com",
    "com meo": "https://mail.google.com",
    "ca meo": "https://mail.google.com",
    "thư điện tử": "https://mail.google.com",
}

URL_DISPLAY_NAMES = {
    "youtube": "YouTube",
    "du túp": "YouTube",
    "dút túp": "YouTube",
    "diu túp": "YouTube",
    "vô tấp": "YouTube",
    "vô túp": "YouTube",
    "dô túp": "YouTube",
    "dô tấp": "YouTube",
    "zu túp": "YouTube",
    "du tốc": "YouTube",
    "dưu tốc": "YouTube",
    "diu tốc": "YouTube",
    "google": "Google",
    "facebook": "Facebook",
    "phây búc": "Facebook",
    "phây buk": "Facebook",
    "phây": "Facebook",
    "phe búc": "Facebook",
    "phây-búc": "Facebook",
    "fb": "Facebook",
    "github": "GitHub",
    "gít húp": "GitHub",
    "git hup": "GitHub",
    "gít háp": "GitHub",
    "git hap": "GitHub",
    "gít hub": "GitHub",
    "gít-húp": "GitHub",
    "gh": "GitHub",
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
    "reddit": "Reddit",
    "tiktok": "TikTok",
    "tóp tóp": "TikTok",
    "gmail": "Gmail",
    "gờ meo": "Gmail",
    "gờ-meo": "Gmail",
    "gở meo": "Gmail",
    "gở-meo": "Gmail",
    "gơ meo": "Gmail",
    "gơ-meo": "Gmail",
    "gừ meo": "Gmail",
    "g-meo": "Gmail",
    "gmeo": "Gmail",
    "gờ mail": "Gmail",
    "gờ-mail": "Gmail",
    "gở mail": "Gmail",
    "gơ mail": "Gmail",
    "g-mail": "Gmail",
    "gờ neo": "Gmail",
    "gờ-neo": "Gmail",
    "gờ leo": "Gmail",
    "gờ-leo": "Gmail",
    "g neo": "Gmail",
    "g leo": "Gmail",
    "gừa mêu": "Gmail",
    "gửa mêu": "Gmail",
    "gờ mêu": "Gmail",
    "gờ-mêu": "Gmail",
    "gơ mêu": "Gmail",
    "g-mêu": "Gmail",
    "gừ mail": "Gmail",
    "g mail": "Gmail",
    "di meo": "Gmail",
    "zi meo": "Gmail",
    "mail": "Gmail",
    "email": "Gmail",
    "e-mail": "Gmail",
    "hòm thư": "Gmail",
    "hộp thư": "Gmail",
    "gồm meo": "Gmail",
    "gôm meo": "Gmail",
    "gờ miêu": "Gmail",
    "miêu": "Gmail",
    "gmaill": "Gmail",
    "gmailll": "Gmail",
    "gồm nhau": "Gmail",
    "gôm nhau": "Gmail",
    "gờ nhau": "Gmail",
    "ca mèo": "Gmail",
    "gần miêu": "Gmail",
    "gourmiel": "Gmail",
    "gour miel": "Gmail",
    "gourmeo": "Gmail",
    "gourmail": "Gmail",
    "gồm yêu": "Gmail",
    "gôm yêu": "Gmail",
    "gờ yêu": "Gmail",
    "cơm meo": "Gmail",
    "cơm mail": "Gmail",
    "con meo": "Gmail",
    "com meo": "Gmail",
    "ca meo": "Gmail",
    "thư điện tử": "Gmail",
}

EXIT_PHRASES = [
    "cảm ơn", "cảm ơn nhé", "cảm ơn bạn", "cám ơn", "thanks", "thank you",
    "thôi", "dừng lại", "dừng được rồi", "xong rồi", "được rồi", "thôi nhé",
    "tạm biệt", "nghỉ đi", "nghỉ ngơi đi", "bye", "bye bye", "hết rồi",
    "không có gì nữa", "không cần nữa", "kết thúc", "kết thúc nhé", "kết thúc đi",
    "tắt đi", "tắt trợ lý", "đóng trợ lý", "ẩn trợ lý", "tắt alexa", "đóng alexa",
    "hẹn gặp lại", "chào bạn", "chào nhé", "thế thôi", "vậy thôi", "ok xong"
]

PROTECTED_CLASSES = {
    "quickshell", "qs", "waybar", "dunst", "swaync",
    "kitty", "alacritty", "foot", "wezterm", "gnome-terminal", "xterm"
}

SPAM_PATTERNS = [
    r"la la school", r"ghiền mì gõ", r"hãy subscribe", r"đăng ký kênh",
    r"cảm ơn các bạn đã theo dõi", r"chúc các bạn một ngày vui vẻ",
    r"^\.+$",                          # Chỉ toàn dấu chấm
    r"^!+$",                           # Chỉ toàn dấu chấm than
    r"^(ừ|ừm|à|ờ|hả|hử|hứ|ê)\.?$",   # Tiếng đệm vô nghĩa
    r"^hẹn gặp lại\.?$",              # Whisper tự kết thúc
    r"^(tạm biệt|bye)\.?$",           # Whisper tự tạm biệt
    r"subtitles?\s+by",                # Phụ đề tự động
    r"amara\.org",                     # Watermark ảo giác
    r"^thank you\.?$",                 # Ảo giác tiếng Anh
    r"^you$",
    r"Được sản xuất bởi",
    r"^ok\.?$",                        # OK vô nghĩa
]
