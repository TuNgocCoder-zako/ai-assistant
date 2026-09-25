"""
Unix Domain Socket IPC Server Daemon cho Voice AI Assistant.
Tích hợp phân quyền an toàn (chmod 0o600) và dọn dẹp tài nguyên tự động.
"""

import os
import json
import socket
import atexit
import threading
from ai_assistant.core.state import get_assistant_state
from ai_assistant.speech.player import trigger_event, stop_current_speech

_server_sock = None
_server_running = False

def get_socket_path() -> str:
    """Xác định đường dẫn Unix Domain Socket an toàn."""
    xdg_runtime = os.getenv("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.exists(xdg_runtime):
        return os.path.join(xdg_runtime, "alexa_voice.sock")
    return f"/tmp/alexa_voice_{os.getuid()}.sock"

def cleanup_ipc_socket():
    """Dọn dẹp socket file khi tắt ứng dụng."""
    global _server_sock, _server_running
    _server_running = False
    sock_path = get_socket_path()
    if _server_sock is not None:
        try:
            _server_sock.close()
        except Exception:
            pass
        _server_sock = None
    if os.path.exists(sock_path):
        try:
            os.remove(sock_path)
        except Exception:
            pass

atexit.register(cleanup_ipc_socket)

def start_ipc_server():
    """Chạy Unix Domain Socket Server trong luồng ngầm với phân quyền bảo mật 0o600."""
    global _server_sock, _server_running
    sock_path = get_socket_path()

    cleanup_ipc_socket()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(sock_path)
        # BẢO MẬT: Giới hạn quyền chỉ cho riêng user sở hữu (0o600)
        os.chmod(sock_path, 0o600)
        server.listen(5)
        server.settimeout(1.0)
        _server_sock = server
        _server_running = True
    except Exception as e:
        print(f"⚠️ Không thể khởi động IPC socket: {e}")
        try:
            server.close()
        except Exception:
            pass
        return

    def _server_loop():
        global _server_running
        while _server_running:
            try:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                conn.settimeout(2.0)
                try:
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
                finally:
                    conn.close()
            except Exception:
                continue

    t = threading.Thread(target=_server_loop, daemon=True)
    t.start()
