# 🎙️ Local AI Operating-System Assistant (Alexa V2) 🤖⚡
> **Trợ lý ảo điều khiển hệ điều hành Arch Linux & Hyprland bằng Giọng nói, Phím tắt và Trí tuệ Nhân tạo Cục bộ (Local AI OS Agent).**

[![Arch Linux](https://img.shields.io/badge/OS-Arch_Linux-1793d1?logo=arch-linux&logoColor=white)](https://archlinux.org/)
[![Hyprland](https://img.shields.io/badge/WM-Hyprland_v0.56.2-00b4d8?logo=wayland&logoColor=white)](https://hyprland.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama_Local-black?logo=ollama&logoColor=white)](https://ollama.ai/)
[![Faster-Whisper](https://img.shields.io/badge/STT-Faster--Whisper-orange)](https://github.com/SYSTRAN/faster-whisper)
[![Quickshell](https://img.shields.io/badge/UI-Quickshell_QML-green)](https://quickshell.outfoxxed.me/)

---

## 🌟 Giới Thiệu Tổng Quan

**Voice AI Assistant (Alexa V2)** không chỉ là một bot đàm thoại thông thường, mà là một **Local AI OS Agent** nằm ngay trên hệ điều hành Arch Linux / Hyprland của bạn. Trợ lý kết hợp giữa khả năng **nhận diện âm thanh thời gian thực**, **phản xạ Fast-Path không tốn tài nguyên (<5ms)**, **suy luận LLM cục bộ (Ollama)** và **bộ công cụ điều khiển hệ thống chuyên sâu**.

Kiến trúc V2 được tái cấu trúc hoàn toàn theo mô hình **phân lớp module (Modular Layered Architecture)**: giải quyết triệt để vấn đề "God Object", chuẩn hóa đóng gói Python package (`pyproject.toml`) và sẵn sàng cho các mở rộng tiếp theo như Vision hay Computer Use.

---

## 🏛️ Sơ Đồ Kiến Trúc Hệ Thống (V2 Architecture)

```
                            ┌────────────────────────┐
                            │          USER          │
                            │ Voice / Hotkey / CLI   │
                            └───────────┬────────────┘
                                        │
           ┌────────────────────────────┼───────────────────────────┐
           ▼                            ▼                           ▼
   [ Wake Word Engine ]          [ IPC Socket ]             [ CLI / Text ]
    openWakeWord (80ms)         Unix Domain Socket         ai-assistant / hey
           │                            │                           │
           ▼                            │                           │
   [ Microphone + VAD ]                 │                           │
    Schmitt Trigger + AGC               │                           │
           │                            │                           │
           ▼                            │                           │
   [ STT Faster-Whisper ]               │                           │
    Anti-hallucination Filter           │                           │
           │                            │                           │
           └────────────────────────────┼───────────────────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │         AGENT CORE          │
                         │   Hybrid NLU & Router       │
                         └──────────────┬──────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
       [ Fast-Path NLU (<5ms) ]                    [ Deep-Path LLM (Ollama) ]
       Deterministic Regex Match                   Smart Task Specialization:
       (Không tốn inference)                        - Fast (3B): Phản xạ thường ngày
                 │                                  - Coder (7B): Java, Linux, Debug
                 │                                  - Reasoning (8B): Suy luận logic
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │        TOOL SYSTEM          │
                         │   Registry & Execution      │
                         └──────────────┬──────────────┘
                                        │
     ┌──────────────┬───────────────────┼───────────────────┬──────────────┐
     ▼              ▼                   ▼                   ▼              ▼
[ System Tools ] [ App/Window ]   [ Developer ]       [ Web/Image ]   [ Timers ]
- Âm lượng/Mute  - .desktop index - Git status        - DuckDuckGo    - Hẹn giờ
- Độ sáng màn    - Hyprland 0.56  - Docker containers - Tải ảnh mạng  - Báo thức
- Wi-Fi/BT       - Close window   - Port (fuser/ss)   - Mở URL        - Ghi chú
- ASUS Profiles  - Fullscreen     - Java/JVM info     - YouTube search
     │              │                   │                   │              │
     └──────────────┴───────────────────┼───────────────────┴──────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │      RESPONSE & FEEDBACK      │
                        ├───────────────────────────────┤
                        │ 🔊 Sentence-Streaming TTS     │
                        │ 🔔 Earcons Chimes (Acoustic)  │
                        │ 🛑 Barge-in Cắt lời tức thì   │
                        │ 🖥️ Dynamic Island QML Overlay  │
                        └───────────────────────────────┘
```

---

## ✨ Tính Năng Nổi Bật

### 1. Thuật toán NGHE chuẩn xác (Audio DSP & Faster-Whisper)
- **Pre-roll Ring Buffer (400ms):** Lưu trước âm thanh đệm để không bị nuốt mất phụ âm đầu câu.
- **Lọc thông cao 85Hz (Butterworth):** Khử triệt để tiếng ù rung cơ học từ quạt tản nhiệt laptop và rung bàn phím.
- **Schmitt Trigger Dynamic VAD:** Tự động đo độ ồn phòng trong 400ms đầu tiên và thích ứng ngưỡng kích hoạt giọng nói theo thời gian thực.
- **Automatic Gain Control (AGC) có Noise Ceiling:** Tự cân bằng âm lượng micro khi nói xa/nói nhỏ mà không làm vỡ tiếng ồn nền.
- **Faster-Whisper trên CUDA RTX:** Tối ưu lượng tử hóa `int8_float16` trên GPU NVIDIA với bộ lọc khử ảo giác (Hallucination Guard) và khử spam pattern nghiêm ngặt.

### 2. Thuật toán HIỂU (Hybrid NLU & Smart Router)
- **Fast-Path Deterministic NLU:** Phản hồi **dưới 5 mili-giây** cho hơn 80% lệnh điều khiển hệ thống thông thường (âm lượng, độ sáng, Wi-Fi, nhạc, app, git, port, timer...) mà **hoàn toàn không cần gọi LLM**.
- **Smart Model Routing (Task Specialization):**
  - **Fast / Daily (`qwen2.5:3b`):** Phản xạ hội thoại và tác vụ nhẹ với độ trễ token đầu tiên < 0.3s.
  - **Coder (`qwen2.5-coder:7b`):** Tự động điều hướng khi phát hiện từ khóa kỹ thuật (Java, Spring Boot, Hibernate, Docker, Git, Bug, Query, Refactor).
  - **Reasoning (`qwen3:8b` / `deepseek-r1:8b`):** Suy luận logic sâu và phân tích đa bước.

### 3. Thuật toán NÓI (Sentence-Level Streaming TTS & Barge-in)
- **Truyền luồng trực tiếp vào MPV (Streaming Pipeline):** Ngay khi LLM sinh ra mệnh đề đầu tiên (khoảng 3–5 từ hoặc sau dấu phẩy), âm thanh đã bắt đầu phát ra loa (< 0.4s).
- **Chuẩn hóa phát âm tiếng Việt (Phonetic Sanitizer):** Chuyển đổi thông minh số học, đơn vị đo (16GB -> 16 ghi ga), nhiệt độ (35°C -> 35 độ C), giờ phút (14:30 -> 14 giờ 30 phút), phần trăm (100% -> 100 phần trăm).
- **Cắt lời tức thì (Barge-in / Echo Guard):** Người dùng có thể ngắt lời bất cứ lúc nào qua câu lệnh giọng nói (*"im đi"*, *"dừng lại"*), phím tắt, hoặc IPC signal mà không gây race condition.

### 4. Tích hợp sâu vào Arch Linux & Hyprland
- **Quản lý cửa sổ Hyprland 0.56.2:** Đóng/mở cửa sổ theo hex address qua dispatcher chuẩn, phóng to/thu nhỏ, đóng ứng dụng cụ thể (Zalo, Chrome, VS Code, Kitty Terminal...), bảo vệ an toàn cho terminal đang chạy.
- **Điều khiển phần cứng ASUS TUF:** Chuyển đổi nhanh các profile quạt và hiệu năng (`asusctl` & `powerprofilesctl`: Turbo, Balanced, Quiet).
- **Cài đặt hệ thống nhanh:** Bật/tắt Wi-Fi (`nmcli`), Bluetooth (`bluetoothctl`), độ sáng màn hình (`brightnessctl`), âm lượng (`pactl`), khóa máy (`hyprlock`).
- **Giao diện Dynamic Island Overlay (Quickshell):** Hiển thị thanh trạng thái động trên màn hình (Listening, Thinking, Speaking) đồng bộ thời gian thực qua state file.

### 5. Bộ công cụ dành cho Kỹ sư Lập trình (Developer Tools)
- **Kiểm tra & Giải phóng Port:** Kiểm tra tiến trình đang chiếm port (`ss -tulpn`) và giải phóng nhanh cổng bị kẹt như 8080 (`fuser -k`).
- **Quản lý Docker & Git:** Xem nhanh trạng thái các container đang chạy (`docker ps`) và kiểm tra nhánh Git, tệp tin chưa commit (`git status`) của project hiện tại.
- **Thông tin Java / JVM:** Kiểm tra nhanh phiên bản runtime Java 21 LTS trên hệ thống.

---

## 📁 Cấu Trúc Dự Án (Kiến Trúc V2 Modular)

Toàn bộ mã nguồn đã được module hóa chuẩn mực dưới thư mục `src/ai_assistant/`:

```
voice-ai/
├── pyproject.toml               # Đóng gói chuẩn PEP 621 (pip install -e .)
├── requirements.txt             # Danh sách thư viện Python
├── assistant.py                 # File shim cầu nối tương thích ngược 100%
├── overlay/
│   └── VoiceOverlay.qml         # Giao diện Dynamic Island QML Overlay (Quickshell)
│
├── src/ai_assistant/            # Package mã nguồn chính V2
│   ├── __init__.py              # Khởi tạo package V2
│   ├── config.py                # Cấu hình tập trung, hằng số, aliases, regex
│   ├── app.py                   # Runtime chính & CLI command parser
│   │
│   ├── core/                    # Trọng tâm điều phối Agent
│   │   ├── agent.py             # Vòng lặp tương tác đa lượt & Push-to-Talk
│   │   ├── nlu.py               # Fast-Path NLU (<5ms) & phân tích intent
│   │   ├── state.py             # Đồng bộ trạng thái Quickshell UI
│   │   └── memory.py            # Quản lý fact người dùng & ghi chú
│   │
│   ├── audio/                   # Xử lý âm thanh đầu vào
│   │   ├── capture.py           # Thu âm micro, Schmitt Trigger VAD, AGC
│   │   ├── wakeword.py          # Nạp mô hình nhận diện từ khóa (openWakeWord)
│   │   └── stt.py               # Faster-Whisper STT & bộ lọc khử ảo giác
│   │
│   ├── speech/                  # Giọng nói đầu ra
│   │   ├── tts.py               # Tổng hợp giọng đọc Edge-TTS & chuẩn hóa ngữ âm
│   │   └── player.py            # Quản lý MPV stream, Earcons chime, Barge-in
│   │
│   ├── ai/                      # Lớp suy luận trí tuệ nhân tạo
│   │   ├── model_router.py      # Bộ định tuyến tác vụ thông minh (Fast/Coder/Reasoning)
│   │   ├── prompts.py           # System prompt & Persona Java Senior Backend
│   │   └── ollama_client.py     # Streaming TTS pipeline kết nối Ollama
│   │
│   ├── tools/                   # Bộ công cụ thực thi tác vụ hệ thống
│   │   ├── system.py            # Âm lượng, độ sáng, pin, RAM, Wi-Fi, Bluetooth, ASUS
│   │   ├── apps.py              # Quét .desktop, đóng/mở cửa sổ Hyprland v0.56.2
│   │   ├── dev.py               # Tiện ích Git, Docker, Java, giải phóng port
│   │   ├── web.py               # Tra cứu DuckDuckGo, tải & mở ảnh, mở browser
│   │   └── timer.py             # Quản lý hẹn giờ đếm ngược & báo thức nền
│   │
│   └── ipc/                     # Giao tiếp liên tiến trình
│       ├── server.py            # Unix Domain Socket Server daemon
│       └── client.py            # Gửi tín hiệu điều khiển (--trigger, --stop, --status)
│
├── tests/                       # Bộ kiểm thử đơn vị tự động
│   └── test_v2_modules.py       # Unit tests kiểm tra NLU, Router, Tools, Audio
└── training/                    # Tài liệu & Notebook fine-tune mô hình
```

---

## 🚀 Cài Đặt & Khởi Chạy

### 1. Chuẩn bị môi trường & Cài đặt Package V2

```bash
# Di chuyển vào thư mục dự án
cd ~/Projects/python/voice-ai

# Tạo và kích hoạt môi trường ảo
python -m venv venv
source venv/bin/activate

# Cài đặt thư viện phụ thuộc và cài đặt gói V2 ở chế độ editable
pip install -r requirements.txt
pip install -e .
```

### 2. Cài đặt các mô hình Ollama trên máy

Đảm bảo tiến trình Ollama đang hoạt động và tải sẵn các model cần thiết:
```bash
# Model Fast phản xạ hàng ngày
ollama run qwen2.5:3b

# Model Lập trình & Kỹ thuật
ollama run qwen2.5-coder:7b
```

### 3. Khởi chạy trợ lý ảo

Bạn có thể chạy trợ lý thông qua lệnh mới `ai-assistant` hoặc script tương thích `assistant.py`:

```bash
# Chạy ở chế độ lắng nghe Wake Word ("Alexa" hoặc "Hey Jarvis")
ai-assistant

# Chạy ở chế độ bấm phím nói (Push-to-Talk)
ai-assistant -p

# Chạy tương tác một lượt rồi thoát hoàn toàn
ai-assistant --once
```

---

## ⌨️ Phím Tắt & Tích Hợp Hyprland

Dự án cung cấp sẵn cơ chế IPC Unix Socket cho phép kích hoạt hoặc cắt lời trợ lý từ phím tắt bàn phím trên Hyprland.

Thêm vào file cấu hình `~/.config/hypr/hyprland.conf`:

```ini
# Đánh thức Alexa tức thì bằng phím Super + Space
bind = SUPER, SPACE, exec, ~/.local/bin/alexa-trigger

# Cắt lời / Dừng phát âm ngay lập tức bằng phím Super + Escape
bind = SUPER, ESCAPE, exec, ~/.local/bin/alexa-stop
```

### Các script tiện ích trong `~/.local/bin/`:
- `alexa-trigger`: Đánh thức trợ lý ngay lập tức (tự động bật daemon nếu chưa chạy).
- `alexa-stop`: Dừng phát âm và xóa sạch hàng đợi câu nói.
- `alexa`: Chạy trực tiếp trợ lý từ terminal.
- `hey`: Cho phép gõ lệnh thoại nhanh trong terminal (vd: `hey mở visual studio code`).
- `ai-assistant`: Lệnh CLI chính thức của gói V2.

---

## ⚙️ Tự Động Chạy Nền với Systemd User Service

Để trợ lý luôn túc trực chạy nền khi bạn đăng nhập vào hệ thống:

```bash
# Kích hoạt và bật dịch vụ chạy cùng người dùng
systemctl --user daemon-reload
systemctl --user enable alexa.service
systemctl --user start alexa.service

# Kiểm tra trạng thái hoạt động
systemctl --user status alexa.service
```

---

## 🧪 Kiểm Thử Tự Động (Unit Testing)

Chạy bộ kiểm thử tự động để xác nhận toàn bộ các module V2 hoạt động trơn tru:

```bash
python -m unittest discover tests
```

---

## 🛠️ Huấn Luyện Mô Hình Tùy Chỉnh (Fine-tuning)

Xem hướng dẫn chi tiết quy trình fine-tuning mô hình đàm thoại riêng trên Google Colab GPU miễn phí tại thư mục [`training/README.md`](training/README.md).
