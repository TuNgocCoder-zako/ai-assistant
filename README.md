# Voice AI Assistant (Alexa Tiếng Việt) 🎙️🤖

Trợ lý ảo điều khiển bằng giọng nói tiếng Việt thông minh, phản hồi siêu tốc dựa trên mô hình ngôn ngữ cục bộ (Ollama) và giao diện trực quan QML Overlay.

---

## ✨ Tính Năng Nổi Bật

- **Đánh thức bằng giọng nói (Wake Word):** Hỗ trợ nhận diện wake-word tức thì thông qua `openWakeWord`.
- **Nhận diện giọng nói (STT):** Sử dụng `faster-whisper` với khả năng xử lý nhanh và độ chính xác cao.
- **Phân bổ mô hình thông minh (Task Specialization via Ollama):**
  - **Fast / Daily:** `qwen2.5:3b` / `alexa-vn` - phản xạ đàm thoại hàng ngày cực nhanh (<0.3s).
  - **Coder:** `qwen2.5-coder:7b` - hỗ trợ lập trình, debug, kỹ thuật.
  - **Reasoning:** `qwen3:8b` - suy luận logic đa bước và giải quyết tác vụ phức tạp.
- **Giọng đọc tự nhiên (TTS):** Chuyển đổi văn bản thành giọng nói mượt mà qua Microsoft `edge-tts`.
- **Giao diện trực quan (QML Overlay):** Hiển thị trạng thái lắng nghe, phản hồi và nội dung trực tiếp trên màn hình theo thời gian thực.
- **Tác vụ hệ thống & Tiện ích:**
  - Mở ứng dụng, tìm kiếm web (DuckDuckGo, YouTube, Google).
  - Tra cứu thời tiết, tạo lời nhắc, bấm giờ, ghi nhớ thông tin người dùng.
  - Tự động điều khiển âm lượng, media và các tiến trình hệ thống.
- **Huấn luyện mô hình tùy biến:** Đi kèm bộ dữ liệu và Jupyter Notebook để fine-tune mô hình trong thư mục `training/`.

---

## 📁 Cấu Trúc Dự Án (Kiến Trúc V2 Modular)

```
voice-ai/
├── assistant.py                 # Cầu nối tương thích ngược (Shim wrapper)
├── pyproject.toml               # Đóng gói chuẩn PEP 621 (pip install -e .)
├── requirements.txt             # Danh sách thư viện Python
├── overlay/
│   └── VoiceOverlay.qml         # Giao diện Dynamic Island QML Overlay (Quickshell)
├── src/ai_assistant/            # Gói mã nguồn chính V2
│   ├── config.py                # Cấu hình tập trung, hằng số, aliases
│   ├── app.py                   # Điểm khởi chạy chính CLI & Daemon
│   ├── core/                    # Trọng tâm điều phối Agent & Trạng thái
│   │   ├── agent.py             # Vòng lặp tương tác chính (interaction loop)
│   │   ├── nlu.py               # Bộ phân tích ý định & Fast-Path NLU (<5ms)
│   │   ├── state.py             # Quản lý trạng thái Quickshell Overlay
│   │   └── memory.py            # Ghi nhớ fact người dùng & ghi chú
│   ├── audio/                   # Lớp thu âm & nhận diện giọng nói
│   │   ├── capture.py           # Thu âm micro, Schmitt Trigger VAD, AGC
│   │   ├── wakeword.py          # Nạp & nhận diện từ khóa (openWakeWord)
│   │   └── stt.py               # Faster-Whisper & bộ lọc khử ảo giác
│   ├── speech/                  # Lớp giọng nói & phát âm
│   │   ├── tts.py               # Tổng hợp giọng đọc tự nhiên (Edge-TTS)
│   │   └── player.py            # Quản lý MPV stream, Earcons chime, Barge-in
│   ├── ai/                      # Lớp suy luận trí tuệ nhân tạo
│   │   ├── model_router.py      # Định tuyến model thông minh (Fast/Coder/Reasoning)
│   │   ├── prompts.py           # System prompt & Persona Java Senior Backend
│   │   └── ollama_client.py     # Streaming TTS pipeline kết nối Ollama
│   ├── tools/                   # Bộ công cụ điều khiển hệ thống & tiện ích
│   │   ├── system.py            # Âm lượng, độ sáng, pin, RAM, Wi-Fi, Bluetooth, ASUS
│   │   ├── apps.py              # Khởi chạy app, đóng/mở cửa sổ Hyprland v0.56.2
│   │   ├── dev.py               # Kiểm tra Git, Docker, Java, giải phóng port
│   │   ├── web.py               # DuckDuckGo search, tải ảnh mạng, mở trình duyệt
│   │   └── timer.py             # Hẹn giờ đếm ngược & Báo thức bền bỉ
│   └── ipc/                     # Giao tiếp liên tiến trình
│       ├── server.py            # Unix Domain Socket Server daemon
│       └── client.py            # Gửi tín hiệu đánh thức/cắt lời (--trigger, --stop)
├── tests/                       # Bộ kiểm thử đơn vị tự động
│   └── test_v2_modules.py
└── training/                    # Tài liệu & Notebook fine-tune mô hình
```

---

## 🚀 Cài Đặt & Khởi Chạy

### 1. Chuẩn bị môi trường & Cài đặt Package V2
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Cài đặt và chuẩn bị Ollama
Đảm bảo Ollama đang chạy trên máy và tải các model cần thiết:
```bash
ollama run qwen2.5:3b
ollama run qwen2.5-coder:7b
```

### 3. Khởi chạy trợ lý ảo
Có thể khởi chạy trực tiếp qua lệnh hệ thống hoặc file shim:
```bash
# Cách 1: Sử dụng lệnh CLI mới của gói V2
ai-assistant

# Cách 2: Chạy qua script tương thích ngược
python assistant.py
```

---

## 🛠️ Huấn luyện mô hình tùy chỉnh
Xem hướng dẫn chi tiết tại [`training/README.md`](training/README.md) để tự huấn luyện mô hình phong cách riêng trên Google Colab.
