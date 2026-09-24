"""
Unix Domain Socket IPC Server Daemon cho Voice AI Assistant.
"""

import os
import json
import socket
import threading
from ai_assistant.core.state import get_assistant_state
from ai_assistant.speech.player import trigger_event, stop_current_speech

def get_socket_path() -> str:
    """Xác định đường dẫn Unix Domain Socket an toàn."""
    xdg_runtime = os.getenv("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.exists(xdg_runtime):
        return os.path.join(xdg_runtime, "alexa_voice.sock")
    return f"/tmp/alexa_voice_{os.getuid()}.sock"

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
