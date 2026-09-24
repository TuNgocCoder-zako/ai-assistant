# 🎙️ Local AI Operating-System Assistant (Alexa V2.1) 🤖⚡
> **Trợ lý ảo điều khiển hệ điều hành Arch Linux & Hyprland bằng Giọng nói, Phím tắt và Trí tuệ Nhân tạo Cục bộ (Local AI OS Agent).**

[![Arch Linux](https://img.shields.io/badge/OS-Arch_Linux-1793d1?logo=arch-linux&logoColor=white)](https://archlinux.org/)
[![Hyprland](https://img.shields.io/badge/WM-Hyprland_v0.56.2-00b4d8?logo=wayland&logoColor=white)](https://hyprland.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama_Local-black?logo=ollama&logoColor=white)](https://ollama.ai/)
[![Faster-Whisper](https://img.shields.io/badge/STT-Faster--Whisper-orange)](https://github.com/SYSTRAN/faster-whisper)
[![Quickshell](https://img.shields.io/badge/UI-Quickshell_QML-green)](https://quickshell.outfoxxed.me/)
[![Tests](https://img.shields.io/badge/Tests-27%20Passed-brightgreen)](tests/)

---

## 🌟 Giới Thiệu Tổng Quan

**Voice AI Assistant (Alexa V2.1)** không chỉ là một bot đàm thoại thông thường, mà là một **Local AI OS Agent** nằm ngay trên hệ điều hành Arch Linux / Hyprland của bạn. Trợ lý kết hợp giữa khả năng **nhận diện âm thanh thời gian thực**, **phản xạ Fast-Path siêu tốc (Median 0.02ms, P90 < 4ms)**, **suy luận LLM cục bộ (Ollama)** và **bộ công cụ điều khiển hệ thống chuyên sâu**.

Kiến trúc **V2.1 ("The Reliable Agent Core")** mang đến những cải tiến vượt bậc:
- **Phân lớp module chuẩn hóa (Modular Layered Architecture):** Xóa bỏ hoàn toàn "God Object", cấu trúc package chuẩn PEP 621 (`pyproject.toml`).
- **Structured Agent State & Budget:** Kiểm soát chặt chẽ chu trình ReAct, giới hạn số bước, timeout thời gian thực thi.
- **Stall Detection:** Cơ chế tự động phát hiện và chặn đứng tình trạng model LLM bị kẹt trong vòng lặp vô tận (infinite loop).
- **Execution Trace Logging:** Mọi hành động suy luận và thực thi công cụ đều được ghi vết minh bạch ra tệp JSON (`logs/agent/`).
- **Ollama Tool Calling + Compatibility Parser:** Hỗ trợ linh hoạt cả schema công cụ chuẩn của Ollama lẫn bộ bóc tách đa định dạng (JSON, CLI flags, python syntax), giúp hoạt động ổn định trên mọi mô hình cục bộ.

---

## 🏛️ Sơ Đồ Kiến Trúc Hệ Thống (V2.1 Architecture)

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
       [ Fast-Path NLU (<4ms) ]                    [ Agent Core Orchestrator ]
       Deterministic Regex Match                   Structured State + Budget Guard
       (P90: 3.84ms | Median: 0.02ms)              - Stall Detection (Chống lặp vô tận)
       (Không tốn LLM inference)                   - Execution Trace Log (logs/agent/)
                 │                                 Ollama Tool Calling + Compat Parser:
                 │                                 - Fast (3B): Phản xạ thường ngày
                 │                                 - Coder (7B): Multi-step / Code / Terminal
                 │                                 - Reasoning (8B): Phân tích logic sâu
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │   UNIVERSAL TOOL REGISTRY   │
                         │  14+ Tools & Safety Guard   │
                         └──────────────┬──────────────┘
                                        │
     ┌──────────────┬───────────────────┼───────────────────┬──────────────┐
     ▼              ▼                   ▼                   ▼              ▼
[ System Tools ] [ App/Window ]   [ Terminal & Code ] [ Web/Image ]   [ Timers ]
- Âm lượng/Mute  - .desktop index - run_terminal_cmd  - DuckDuckGo    - Hẹn giờ
- Độ sáng màn    - Hyprland 0.56  - find_files_proj   - Tải ảnh mạng  - Báo thức
- Wi-Fi/BT       - Close window   - Git & Docker      - Mở URL        - Ghi chú
- ASUS Profiles  - Fullscreen     - Port ss / fuser   - YouTube search
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

### 2. Thuật toán HIỂU (Fast-Path NLU & Smart Router)
- **Fast-Path Deterministic NLU (Thực nghiệm đo đạc qua 5.000 truy vấn):**
  - **Median Latency:** `0.020 ms` (20 micro-giây)
  - **Mean Latency:** `2.162 ms`
  - **P90 Latency:** `3.841 ms` (< 5ms theo đúng cam kết)
  - **Throughput:** `462.6 queries/giây`
  - Xử lý tức thì các lệnh thông dụng (âm lượng, độ sáng, Wi-Fi, nhạc, app, git, port, timer...) mà **hoàn toàn không cần gọi LLM**.
- **Smart Model Routing (Task Specialization):**
  - **Fast / Daily (`qwen2.5:3b`):** Phản xạ hội thoại và tác vụ nhẹ với độ trễ token đầu tiên < 0.3s.
  - **Coder (`qwen2.5-coder:7b`):** Tự động điều hướng khi phát hiện từ khóa kỹ thuật (Java, Spring Boot, Hibernate, Docker, Git, Bug, Query, Refactor).
  - **Reasoning (`qwen3:8b` / `deepseek-r1:8b`):** Suy luận logic sâu và phân tích đa bước.

### 3. Bộ não điều phối Đa nhiệm (Agent Core Orchestrator - ReAct Loop)
- **Hoàn toàn Tech-Agnostic / Đa nền tảng:** Không giới hạn ở một IDE hay một ngôn ngữ. Trợ lý có khả năng làm việc với mọi công cụ (IntelliJ, VS Code, Java Spring Boot, Python, Node.js, Go, Rust, Docker, Git, Linux administration, v.v.).
- **Chu trình ReAct an toàn (Plan $\rightarrow$ Act $\rightarrow$ Observe $\rightarrow$ Reflect):**
  - **Plan:** Tự động phân tích câu lệnh phức tạp hoặc có điều kiện (*"nếu... thì...", "và sau đó...", "kiểm tra build nếu lỗi thì tìm nguyên nhân"*).
  - **Structured State & Agent Budget:** Giới hạn tối đa 8 bước suy luận, timeout 60 giây, kiểm soát tài nguyên chặt chẽ.
  - **Stall Detection:** Tự động phát hiện khi mô hình gọi lặp đi lặp lại cùng một công cụ với cùng một tham số, ngăn chặn hoàn toàn hiện tượng kẹt tài nguyên.
  - **Agent Execution Trace:** Tự động xuất vết thực thi đầy đủ ra tệp JSON dạng `logs/agent/YYYY-MM-DD_HH-MM-SS_{session_id}_{status}.json` phục vụ việc gỡ lỗi và kiểm toán.
  - **Ollama Tool Calling + Compatibility Parser:** Kết hợp linh hoạt giữa schema chuẩn của Ollama và parser cứu trợ đa cú pháp (JSON markdown, CLI style, python call), tương thích hoàn hảo với mọi model local.
- **Universal Tool Registry & Safety Guard:**
  - Tự động sinh JSON Schema từ Python type hints (`@tool_registry.register`).
  - **Safety Guard:** Ngăn chặn các lệnh bash phá hoại hệ thống nguy hiểm (`rm -rf /`, `mkfs`, ghi đè trực tiếp ổ cứng raw disk, fork bomb...).
  - Cung cấp sẵn 14+ công cụ mạnh mẽ: thực thi lệnh terminal bash an toàn, tìm kiếm project/file toàn máy, đọc nội dung file, đóng/mở app, liệt kê cửa sổ Hyprland, quản lý cổng mạng, Docker, Git, điều khiển phần cứng, tra cứu DuckDuckGo, hẹn giờ.

### 4. Thuật toán NÓI (Sentence-Level Streaming TTS & Barge-in)
- **Truyền luồng trực tiếp vào MPV (Streaming Pipeline):** Ngay khi LLM sinh ra mệnh đề đầu tiên (khoảng 3–5 từ hoặc sau dấu phẩy), âm thanh đã bắt đầu phát ra loa (< 0.4s).
- **Chuẩn hóa phát âm tiếng Việt (Phonetic Sanitizer):** Chuyển đổi thông minh số học, đơn vị đo (16GB -> 16 ghi ga), nhiệt độ (35°C -> 35 độ C), giờ phút (14:30 -> 14 giờ 30 phút), phần trăm (100% -> 100 phần trăm).
- **Cắt lời tức thì (Barge-in / Echo Guard):** Người dùng có thể ngắt lời bất cứ lúc nào qua câu lệnh giọng nói (*"im đi"*, *"dừng lại"*), phím tắt, hoặc IPC signal mà không gây race condition.

### 5. Tích hợp sâu vào Arch Linux & Hyprland
- **Quản lý cửa sổ Hyprland 0.56.2:** Đóng/mở cửa sổ theo hex address qua dispatcher chuẩn, phóng to/thu nhỏ, đóng ứng dụng cụ thể (Zalo, Chrome, VS Code, Kitty Terminal...), bảo vệ an toàn cho terminal đang chạy.
- **Điều khiển phần cứng ASUS TUF:** Chuyển đổi nhanh các profile quạt và hiệu năng (`asusctl` & `powerprofilesctl`: Turbo, Balanced, Quiet).
- **Cài đặt hệ thống nhanh:** Bật/tắt Wi-Fi (`nmcli`), Bluetooth (`bluetoothctl`), độ sáng màn hình (`brightnessctl`), âm lượng (`pactl`), khóa máy (`hyprlock`).
- **Giao diện Dynamic Island Overlay (Quickshell):** Hiển thị thanh trạng thái động trên màn hình (Listening, Thinking, Speaking) đồng bộ thời gian thực qua state file.

---

## 📁 Cấu Trúc Dự Án (Kiến Trúc V2.1 Modular)

Toàn bộ mã nguồn đã được module hóa chuẩn mực dưới thư mục `src/ai_assistant/`:

```
voice-ai/
├── pyproject.toml               # Đóng gói chuẩn PEP 621 (pip install -e .)
├── requirements.txt             # Danh sách thư viện Python
├── assistant.py                 # File shim cầu nối tương thích ngược 100%
├── overlay/
│   └── VoiceOverlay.qml         # Giao diện Dynamic Island QML Overlay (Quickshell)
│
├── benchmarks/                  # Bộ công cụ đo kiểm hiệu năng thực tế
│   ├── bench_nlu.py             # Script đo độ trễ & throughput Fast-Path NLU
│   └── results_nlu.json         # Kết quả đo kiểm 5.000 truy vấn
│
├── logs/
│   └── agent/                   # Agent Execution Traces (JSON có cấu trúc)
│
├── src/ai_assistant/            # Package mã nguồn chính V2.1
│   ├── __init__.py              # Khởi tạo package V2.1
│   ├── config.py                # Cấu hình tập trung, hằng số, aliases, regex
│   ├── app.py                   # Runtime chính & CLI command parser
│   │
│   ├── core/                    # Trọng tâm điều phối Agent
│   │   ├── orchestrator.py      # BỘ NÃO ĐIỀU PHỐI (ReAct Loop: Plan-Act-Observe-Reflect)
│   │   ├── agent_state.py       # Cấu trúc trạng thái, AgentBudget, Stall Detection & Trace Log
│   │   ├── agent.py             # Vòng lặp tương tác đa lượt & Push-to-Talk
│   │   ├── nlu.py               # Fast-Path NLU (P90 < 4ms) & phân tích intent
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
│   │   ├── registry.py          # UNIVERSAL TOOL REGISTRY (14+ Tools, Schemas & Safety Guard)
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
├── tests/                       # Bộ kiểm thử tự động phân lớp (27 tests)
│   ├── unit/                    # Kiểm thử đơn vị các module cơ bản & Safety Guard
│   │   ├── test_v2_modules.py   # Test NLU, Model Router, Audio, System Tools
│   │   └── test_safety.py       # Test Safety Guard chặn rm -rf, mkfs, fork bomb
│   ├── agent/                   # Kiểm thử logic suy luận Agent & Tool Calling
│   │   ├── test_orchestrator.py # Test Registry, Schemas, Complex Request Intent
│   │   └── test_agent_state.py  # Test State, Budget, Stall Detection, Trace Log
│   └── integration/             # Kiểm thử tích hợp toàn trình
│       └── test_end_to_end.py   # Test luồng Fast-Path -> Complex Intent -> Agent Trace
│
└── training/                    # Tài liệu & Notebook fine-tune mô hình
```

---

## 🚀 Cài Đặt & Khởi Chạy

### 1. Chuẩn bị môi trường & Cài đặt Package V2.1

```bash
# Di chuyển vào thư mục dự án
cd ~/Projects/python/voice-ai

# Tạo và kích hoạt môi trường ảo
python -m venv venv
source venv/bin/activate

# Cài đặt thư viện phụ thuộc và cài đặt gói V2.1 ở chế độ editable
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
- `ai-assistant`: Lệnh CLI chính thức của gói V2.1.

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

## 🧪 Kiểm Thử & Đo Lường Hiệu Năng (Testing & Benchmarks)

### 1. Chạy bộ kiểm thử tự động (27 tests)

```bash
# Chạy toàn bộ 27 tests (Unit, Agent, Integration)
python -m unittest discover tests

# Chạy riêng từng nhóm test
python -m unittest discover tests/unit        # 12 tests: NLU, Tools, Safety Guard
python -m unittest discover tests/agent       # 12 tests: ReAct Loop, State, Stall Detection
python -m unittest discover tests/integration # 3 tests: End-to-End Flow & Trace File
```

### 2. Chạy Benchmark đo độ trễ Fast-Path NLU

```bash
# Chạy 5.000 truy vấn đo lường độ trễ & throughput thực tế
python benchmarks/bench_nlu.py
```

*Kết quả đo kiểm thực tế trên máy:*
- **Median:** `0.020 ms`
- **Mean:** `2.162 ms`
- **P90:** `3.841 ms`
- **Throughput:** `462.6 QPS`

---

## 🗺️ Lộ Trình Phát Triển (Roadmap)

Dự án tuân theo định hướng tiến hóa từng bước chắc chắn (Step-by-step Pragmatic Evolution):

- [x] **V2.0 — Modular Architecture & Universal Tool Registry:** Tái cấu trúc sạch sẽ, đóng gói package, 14+ công cụ, Fast-Path NLU, Quickshell UI.
- [x] **V2.1 — The Reliable Agent Core:** Cấu trúc trạng thái chuẩn mực (`StructuredAgentState`), kiểm soát tài nguyên (`AgentBudget`), chặn lặp vô tận (`Stall Detection`), ghi vết minh bạch (`logs/agent/`), benchmark thực tế (<4ms) và tổ chức lại bộ test.
- [ ] **V2.2 — The Developer Agent:** Mở rộng khả năng lập trình sâu (đọc/sửa file diff, chạy test, phân tích log compiler Java/Rust/Node, quản lý tiến trình nền).
- [ ] **V2.3 — Vision & Screen Awareness:** Tích hợp chụp màn hình Wayland (`grim`/`slurp`) và phân tích giao diện người dùng qua mô hình Vision đa phương thức (`llama3.2-vision` / `qwen2.5-vl`).
- [ ] **V2.4 — Autonomous Computer Use:** Tổng hợp phím bấm và trỏ chuột trên Wayland (`wlrctl` / `ydotool`), thực thi tác vụ đồ họa tự động có vòng lặp kiểm tra trực quan.
- [ ] **V3.0 — The Local AI Operating System:** Trợ lý chủ động (proactive agent daemon), phân tích ngữ cảnh làm việc liên tục và tương tác thông minh toàn diện.

---

## 🛠️ Huấn Luyện Mô Hình Tùy Chỉnh (Fine-tuning)

Xem hướng dẫn chi tiết quy trình fine-tuning mô hình đàm thoại riêng trên Google Colab GPU miễn phí tại thư mục [`training/README.md`](training/README.md).
