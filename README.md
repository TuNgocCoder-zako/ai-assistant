# 🎙️ Local AI Operating-System Assistant (Alexa V2.2) 🤖⚡
> **Trợ lý ảo điều khiển hệ điều hành Arch Linux & Hyprland bằng Giọng nói, Phím tắt và Trí tuệ Nhân tạo Cục bộ (Local AI OS Agent).**

[![Arch Linux](https://img.shields.io/badge/OS-Arch_Linux-1793d1?logo=arch-linux&logoColor=white)](https://archlinux.org/)
[![Hyprland](https://img.shields.io/badge/WM-Hyprland_v0.56.2-00b4d8?logo=wayland&logoColor=white)](https://hyprland.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama_Local-black?logo=ollama&logoColor=white)](https://ollama.ai/)
[![Faster-Whisper](https://img.shields.io/badge/STT-Faster--Whisper-orange)](https://github.com/SYSTRAN/faster-whisper)
[![Quickshell](https://img.shields.io/badge/UI-Quickshell_QML-green)](https://quickshell.outfoxxed.me/)
[![Tests](https://img.shields.io/badge/Tests-47%20Passed-brightgreen)](tests/)

---

## 🌟 Giới Thiệu Tổng Quan

**Voice AI Assistant (Alexa V2.2)** không chỉ là một bot đàm thoại thông thường, mà là một **Local AI OS Agent** nằm ngay trên hệ điều hành Arch Linux / Hyprland của bạn. Trợ lý kết hợp giữa khả năng **nhận diện âm thanh thời gian thực**, **phản xạ Fast-Path siêu tốc (Median 0.02ms, P90 < 4ms)**, **suy luận LLM cục bộ (Ollama)** và **bộ công cụ điều khiển hệ thống chuyên sâu**.

Kiến trúc **V2.2 ("Governed Agent Core & Multi-layered Governance")** hoàn thiện toàn bộ các tầng quản trị tác tử khắt khe nhất:
- **Tách biệt rõ ràng UI State & Agent Runtime State:**
  - `core/ui_state.py`: Chuyên trách trạng thái trực quan hiển thị trên Quickshell Overlay (`idle`, `listening`, `thinking`, `speaking`).
  - `core/agent_state.py`: Runtime State đầy đủ của bộ não (`goal`, `plan`, `current_step`, `steps`, `tool_history`, `observations`, `errors`, `retry_count`, `completion`).
- **Cây Vết Thực Thi Phân Cấp (Hierarchical Execution Trace Tree):** Trực quan hóa toàn bộ chu trình hành động dạng cây và lưu vết chi tiết ra file JSON chuẩn hóa (`logs/agent/`).
- **Phân Tầng Quản Trị Bảo Mật Đa Lớp (Multi-layered Security Governance):**
  $$\text{LLM} \longrightarrow \text{Tool Registry} \longrightarrow \text{Permission Policy} \longrightarrow \text{Argument Validator} \longrightarrow \text{Executor} \longrightarrow \text{OS}$$
  Ngăn chặn triệt để Path Traversal, đọc tệp nhạy cảm (`/etc/shadow`, `id_rsa`), tắt tiến trình cốt lõi hệ thống (`systemd`, `hyprland`), hay chạy lệnh phá hoại (`rm -rf /`, `mkfs`, fork bomb).
- **Hybrid Tool Calling Pipeline:** Tự động kết hợp native tool schema của Ollama với bộ bóc tách cứu trợ đa cú pháp (`_parse_tool_calls_from_text`: JSON markdown, XML `<tool_call>`, CLI flags, python calls), đảm bảo độ ổn định 100% trên mọi mô hình local.
- **Task Completion Evaluator:** Tự động phát hiện rẽ nhánh theo điều kiện (*"nếu build lỗi thì tìm nguyên nhân"*), phát hiện lỗi công cụ có thể tự sửa để kích hoạt cơ chế Retry thông minh.

---

## 🏛️ Sơ Đồ Kiến Trúc Hệ Thống (V2.2 Architecture)

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
       (Không tốn LLM inference)                   - Task Completion Evaluator
                 │                                 - Retry / Abort Controller
                 │                                 - Hybrid Tool Calling Engine
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │   MULTI-LAYER GOVERNANCE    │
                         ├─────────────────────────────┤
                         │ 1. Tool Registry (Schemas)  │
                         │ 2. Permission Policy Layer  │
                         │ 3. Argument Validator       │
                         │ 4. Safe Executor Sandbox    │
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
                        │     TRACE & RESPONSE PIPELINE │
                        ├───────────────────────────────┤
                        │ 🌳 Hierarchical Trace Tree    │
                        │ 📁 JSON Logs (logs/agent/)    │
                        │ 🔊 Sentence-Streaming TTS     │
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
  - **Throughput:** `463.7 queries/giây`
  - Xử lý tức thì các lệnh thông dụng (âm lượng, độ sáng, Wi-Fi, nhạc, app, git, port, timer...) mà **hoàn toàn không cần gọi LLM**.
- **Smart Model Routing (Task Specialization):**
  - **Fast / Daily (`qwen2.5:3b`):** Phản xạ hội thoại và tác vụ nhẹ với độ trễ token đầu tiên < 0.3s.
  - **Coder (`qwen2.5-coder:7b`):** Tự động điều hướng khi phát hiện từ khóa kỹ thuật (Java, Spring Boot, Hibernate, Docker, Git, Bug, Query, Refactor).
  - **Reasoning (`qwen3:8b` / `deepseek-r1:8b`):** Suy luận logic sâu và phân tích đa bước.

### 3. Bộ Não Điều Phối & Quản Trị Tác Tử (Governed Agent Core)
- **Tách biệt rõ ràng UI State & Agent Runtime State:**
  - Giao diện người dùng Quickshell theo dõi trạng thái `idle / listening / thinking / speaking` qua [`core/ui_state.py`](src/ai_assistant/core/ui_state.py).
  - Bộ não tác tử quản lý vòng đời tác vụ đầy đủ qua [`core/agent_state.py`](src/ai_assistant/core/agent_state.py).
- **Phân tầng Quản trị & Bảo mật Đa lớp ([`tools/permission.py`](src/ai_assistant/tools/permission.py)):**
  - **`PermissionPolicy`:** Phân loại 5 cấp độ quyền (`READ_ONLY`, `SYSTEM_ACTION`, `SENSITIVE_WRITE`, `TERMINAL_EXEC`, `DANGEROUS_BLOCKED`). Chặn đứng ý đồ kill tiến trình hệ điều hành (`systemd`, `hyprland`, `dbus`, `pipewire`).
  - **`ArgumentValidator`:** Ngăn chặn tấn công Path Traversal, cấm truy cập file nhạy cảm (`/etc/shadow`, `/etc/sudoers`, SSH keys), kiểm tra giới hạn cổng mạng (1 - 65535).
- **Đánh Giá Mục Tiêu & Cơ Chế Thử Lại ([`core/evaluator.py`](src/ai_assistant/core/evaluator.py)):**
  - Đánh giá thông minh các câu lệnh rẽ nhánh: *"Nếu build lỗi thì tìm nguyên nhân"* $\rightarrow$ nếu compile thành công thì dừng lại báo tin mừng; nếu compile thất bại thì tự động kích hoạt bước đọc log / đọc mã nguồn tìm nguyên nhân.
  - Ghi nhận `retry_count` và tự động bổ sung gợi ý điều phối khi công cụ gặp lỗi có thể tự sửa.
- **Cây Vết Thực Thi Trực Quan (Hierarchical Agent Trace):**
  Mỗi phiên làm việc của Agent tự động in cây vết thực thi ra terminal và lưu tệp JSON đầy đủ tại `logs/agent/`:
  ```
  📋 Task: Mở IntelliJ, kiểm tra project Spring Boot của tôi, nếu build lỗi thì tìm nguyên nhân
   ├─ [Step 1] Decision: Tìm kiếm thư mục dự án Spring Boot
   │   ├─ Tool Call: find_files_or_projects(query='demo')
   │   └─ Result (5.2ms, success): {"found": ["/home/tu/Projects/demo-spring"]}
   ├─ [Step 2] Decision: Chạy lệnh compile kiểm tra project
   │   ├─ Tool Call: run_terminal_command(command='javac UserController.java')
   │   ├─ Result (42.1ms, failed): error: ';' expected
   │   └─ Error: error: ';' expected
   ├─ [Step 3] Decision: Đọc nội dung UserController.java để xác định dòng lỗi
   │   ├─ Tool Call: read_file_content(path='/path/to/UserController.java')
   │   └─ Result (3.8ms, success): {"lines_read": 10}
   └─ Final Result (success, 1.45s): Project Spring Boot bị lỗi cú pháp thiếu dấu chấm phẩy tại tệp UserController.java.
  ```

---

## 📁 Cấu Trúc Dự Án (Kiến Trúc V2.2 Modular)

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
├── src/ai_assistant/            # Package mã nguồn chính V2.2
│   ├── __init__.py              # Khởi tạo package V2.2
│   ├── config.py                # Cấu hình tập trung, hằng số, aliases, regex
│   ├── app.py                   # Runtime chính & CLI command parser
│   │
│   ├── core/                    # Trọng tâm điều phối Agent
│   │   ├── orchestrator.py      # BỘ NÃO ĐIỀU PHỐI (ReAct Loop: Plan-Act-Observe-Reflect)
│   │   ├── agent_state.py       # RUNTIME AGENT STATE (Goal, Plan, Steps, History, Trace Tree)
│   │   ├── ui_state.py          # UI STATE (Trạng thái hiển thị Quickshell Overlay)
│   │   ├── state.py             # Facade tương thích ngược
│   │   ├── evaluator.py         # TASK COMPLETION EVALUATOR & Retry Decision Engine
│   │   ├── agent.py             # Vòng lặp tương tác đa lượt & Push-to-Talk
│   │   ├── nlu.py               # Fast-Path NLU (P90 < 4ms) & phân tích intent
│   │   └── memory.py            # Quản lý fact người dùng & ghi chú
│   │
│   ├── tools/                   # Bộ công cụ thực thi tác vụ hệ thống
│   │   ├── registry.py          # UNIVERSAL TOOL REGISTRY (14+ Tools, Schemas & Fuzzy Match)
│   │   ├── permission.py        # PERMISSION POLICY & ARGUMENT VALIDATOR
│   │   ├── system.py            # Âm lượng, độ sáng, pin, RAM, Wi-Fi, Bluetooth, ASUS
│   │   ├── apps.py              # Quét .desktop, đóng/mở cửa sổ Hyprland v0.56.2
│   │   ├── dev.py               # Tiện ích Git, Docker, Java, giải phóng port
│   │   ├── web.py               # Tra cứu DuckDuckGo, tải & mở ảnh, mở browser
│   │   └── timer.py             # Quản lý hẹn giờ đếm ngược & báo thức nền
│   │
│   ├── audio/                   # Xử lý âm thanh đầu vào (VAD, AGC, STT)
│   ├── speech/                  # Giọng nói đầu ra (Edge-TTS, Streaming MPV)
│   ├── ai/                      # Lớp suy luận (Model Router, Prompts, Ollama Client)
│   └── ipc/                     # Giao tiếp liên tiến trình (Unix Socket)
│
├── tests/                       # Bộ kiểm thử tự động phân lớp (39 tests)
│   ├── unit/                    # 18 Unit Tests: NLU, Router, System Tools, Safety, Permission
│   ├── agent/                   # 17 Agent Tests: ReAct Loop, State, Stall, Trace Tree, Evaluator
│   └── integration/             # 4 Integration Tests: Fast-Path E2E & Spring Boot Flow Audit
│
└── training/                    # Tài liệu & Notebook fine-tune mô hình
```

---

## 🚀 Cài Đặt & Khởi Chạy

```bash
# Di chuyển vào thư mục dự án
cd ~/Projects/python/voice-ai

# Tạo và kích hoạt môi trường ảo
python -m venv venv
source venv/bin/activate

# Cài đặt thư viện phụ thuộc và cài đặt gói V2.2 ở chế độ editable
pip install -r requirements.txt
pip install -e .
```

### Khởi chạy trợ lý ảo
```bash
# Chạy ở chế độ lắng nghe Wake Word ("Alexa" hoặc "Hey Jarvis")
ai-assistant

# Chạy ở chế độ bấm phím nói (Push-to-Talk)
ai-assistant -p

# Chạy tương tác một lượt rồi thoát hoàn toàn
ai-assistant --once
```

---

## 🧪 Kiểm Thử & Đo Lường Hiệu Năng (Testing & Benchmarks)

### 1. Chạy bộ kiểm thử tự động (39 tests)

```bash
# Chạy toàn bộ 47 tests (Unit, Agent, Integration)
python -m unittest discover tests

# Chạy riêng từng nhóm test
python -m unittest discover tests/unit        # 26 tests: NLU, Tools, Safety Guard, Permission, Bug Fixes
python -m unittest discover tests/agent       # 17 tests: ReAct Loop, State, Stall, Evaluator
python -m unittest discover tests/integration # 4 tests: End-to-End Flow & Spring Boot Flow Audit
```

### 2. Chạy Benchmark đo độ trễ Fast-Path NLU

```bash
python benchmarks/bench_nlu.py
```

*Kết quả đo kiểm thực tế trên máy:*
- **Median:** `0.020 ms`
- **Mean:** `2.157 ms`
- **P90:** `3.819 ms`
- **Throughput:** `463.7 QPS`

---

## 🗺️ Lộ Trình Phát Triển (Roadmap)

- [x] **V2.0 — Modular Architecture & Universal Tool Registry:** Tái cấu trúc sạch sẽ, đóng gói package, 14+ công cụ, Fast-Path NLU, Quickshell UI.
- [x] **V2.1 — The Reliable Agent Core:** Cấu trúc trạng thái, kiểm soát tài nguyên (`AgentBudget`), chặn lặp vô tận (`Stall Detection`), ghi vết minh bạch (`logs/agent/`), benchmark thực tế (<4ms).
- [x] **V2.2 — Governed Agent Core & Multi-layered Governance:** Tách biệt rõ UI State vs Agent State, Cây vết thực thi (`render_tree`), Phân tầng quản trị (`PermissionPolicy` & `ArgumentValidator`), Đánh giá mục tiêu (`TaskCompletionEvaluator`), Flow Audit Spring Boot.
- [ ] **V2.3 — Vision & Screen Awareness:** Tích hợp chụp màn hình Wayland (`grim`/`slurp`) và phân tích giao diện người dùng qua mô hình Vision đa phương thức (`llama3.2-vision` / `qwen2.5-vl`).
- [ ] **V2.4 — Autonomous Computer Use:** Tổng hợp phím bấm và trỏ chuột trên Wayland (`wlrctl` / `ydotool`), thực thi tác vụ đồ họa tự động có vòng lặp kiểm tra trực quan.
- [ ] **V3.0 — The Local AI Operating System:** Trợ lý chủ động (proactive agent daemon), phân tích ngữ cảnh làm việc liên tục và tương tác thông minh toàn diện.
