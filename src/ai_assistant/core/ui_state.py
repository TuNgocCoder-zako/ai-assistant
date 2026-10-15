"""
Quản lý trạng thái giao diện UI (Quickshell Dynamic Island Overlay).
Chuyên biệt cho các trạng thái trực quan: idle, listening, thinking, speaking.
(Đối với trạng thái suy luận và thực thi của Agent Core, xem `ai_assistant.core.agent_state`).
"""

import os
import sys
import time
import json
import signal
import atexit
import subprocess
import threading
from ai_assistant.config import STATE_FILE_PATH, OVERLAY_QML_PATH

state_lock = threading.Lock()
assistant_state = {"status": "idle"}  # "idle", "listening", "thinking", "speaking"

ACTION_PREFIXES = (
    "đã mở", "đã đóng", "đã tắt", "đã bật", "đã đặt",
    "đã chụp", "đã ghi", "đã chuyển", "đã tạm dừng",
    "kết quả là", "tạm biệt", "chào bạn", "xin lỗi"
)

def set_assistant_state(
    status: str,
    text: str = "",
    subtext: str = "",
    query: str = "",
    is_long_text: bool = None,
    long_answer: str = "",
    clear_card: bool = False
):
    """Cập nhật trạng thái hiển thị UI và ghi ra state file để Quickshell hiển thị."""
    with state_lock:
        assistant_state["status"] = status
        assistant_state["text"] = text
        assistant_state["subtext"] = subtext
        assistant_state["updated_at"] = time.time()

        if clear_card:
            assistant_state["is_long_text"] = False
            assistant_state["long_answer"] = ""
            assistant_state["query"] = ""
        else:
            if query:
                assistant_state["query"] = query

            if is_long_text is not None:
                assistant_state["is_long_text"] = is_long_text
                if is_long_text:
                    assistant_state["long_answer"] = long_answer or text
                elif not is_long_text and status != "idle":
                    assistant_state["long_answer"] = ""
            else:
                if status in ("listening", "thinking") and not assistant_state.get("is_long_text", False):
                    assistant_state["is_long_text"] = False
                    assistant_state["long_answer"] = ""
                elif status == "speaking" and not assistant_state.get("is_long_text", False):
                    # Tự động nhận diện văn bản dài (> 90 ký tự và không phải câu lệnh thao tác hệ thống)
                    clean_t = text.strip().lower()
                    is_action = any(clean_t.startswith(p) for p in ACTION_PREFIXES)
                    if (len(text) > 90 or "\n" in text) and not is_action:
                        assistant_state["is_long_text"] = True
                        assistant_state["long_answer"] = text

        try:
            tmp = STATE_FILE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(assistant_state, f, ensure_ascii=False)
            os.replace(tmp, STATE_FILE_PATH)
        except Exception:
            pass

def get_assistant_state() -> dict:
    """Lấy trạng thái UI hiện tại của trợ lý."""
    with state_lock:
        return dict(assistant_state)

def ensure_overlay_running():
    """Khởi động giao diện hiển thị Dynamic Island Overlay qua Quickshell nếu chưa chạy."""
    try:
        res = subprocess.run(["pgrep", "-f", "VoiceOverlay.qml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            if os.path.exists(OVERLAY_QML_PATH):
                subprocess.Popen(["qs", "-p", OVERLAY_QML_PATH, "-d"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _handle_exit_signal(sig, frame):
    set_assistant_state("idle")
    sys.exit(0)

def init_state_handlers():
    """Đăng ký hook khi kết thúc tiến trình."""
    atexit.register(lambda: set_assistant_state("idle"))
    try:
        signal.signal(signal.SIGTERM, _handle_exit_signal)
        signal.signal(signal.SIGINT, _handle_exit_signal)
    except Exception:
        pass
