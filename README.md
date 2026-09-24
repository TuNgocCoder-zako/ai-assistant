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

## 📁 Cấu Trúc Dự Án

```
voice-ai/
├── assistant.py             # Script chính xử lý luồng Voice AI Assistant
├── requirements.txt         # Danh sách thư viện Python cần thiết
├── overlay/
│   └── VoiceOverlay.qml     # Giao diện QML Overlay hiển thị trạng thái trợ lý
└── training/                # Công cụ và tài liệu fine-tune mô hình
    ├── dataset.json         # Bộ dữ liệu mẫu hội thoại tiếng Việt
    ├── generate_dataset.py  # Script mở rộng bộ dữ liệu
    ├── Modelfile.custom     # Cấu hình Ollama Modelfile
    ├── Modelfile.template   # Template cấu hình Ollama
    ├── Train_Alexa_Llama3_2_Colab.ipynb  # Notebook huấn luyện trên Colab GPU
    └── README.md            # Hướng dẫn chi tiết quy trình fine-tuning
```

---

## 🚀 Cài Đặt & Khởi Chạy

### 1. Chuẩn bị môi trường
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Cài đặt và chuẩn bị Ollama
Đảm bảo Ollama đang chạy trên máy và tải các model cần thiết:
```bash
ollama run qwen2.5:3b
ollama run qwen2.5-coder:7b
```

### 3. Chạy trợ lý ảo
```bash
python assistant.py
```

---

## 🛠️ Huấn luyện mô hình tùy chỉnh
Xem hướng dẫn chi tiết tại [`training/README.md`](training/README.md) để tự huấn luyện mô hình phong cách riêng trên Google Colab.
