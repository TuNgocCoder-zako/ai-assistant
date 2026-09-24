"""
Quản lý trạng thái trợ lý và giao tiếp với Quickshell Dynamic Island Overlay.
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

def set_assistant_state(status: str, text: str = "", subtext: str = ""):
    """Cập nhật trạng thái trợ lý và ghi ra state file để Quickshell hiển thị."""
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
    """Lấy trạng thái hiện tại của trợ lý."""
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
