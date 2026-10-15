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
_is_server_instance = False
_atexit_registered = False

def get_socket_path() -> str:
    """Xác định đường dẫn Unix Domain Socket an toàn."""
    xdg_runtime = os.getenv("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.exists(xdg_runtime):
        return os.path.join(xdg_runtime, "alexa_voice.sock")
    return f"/tmp/alexa_voice_{os.getuid()}.sock"

def cleanup_ipc_socket(force: bool = False):
    """Dọn dẹp socket file khi tắt ứng dụng hoặc khi khởi động server daemon."""
    global _server_sock, _server_running, _is_server_instance
    if not (_is_server_instance or force):
        return
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
    _is_server_instance = False

def start_ipc_server():
    """Chạy Unix Domain Socket Server trong luồng ngầm với phân quyền bảo mật 0o600."""
    global _server_sock, _server_running, _is_server_instance, _atexit_registered
    sock_path = get_socket_path()

    cleanup_ipc_socket(force=True)

    # Dọn dẹp socket mồ côi nếu tiến trình trước đó bị dừng đột ngột (SIGKILL)
    if os.path.exists(sock_path):
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(0.3)
            probe.connect(sock_path)
            probe.close()
            print("⚠️ Socket đang được sử dụng bởi một tiến trình khác.")
            return
        except (ConnectionRefusedError, socket.timeout, OSError):
            try:
                os.unlink(sock_path)
            except Exception:
                pass
        finally:
            try:
                probe.close()
            except Exception:
                pass

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(sock_path)
        # BẢO MẬT: Giới hạn quyền chỉ cho riêng user sở hữu (0o600)
        os.chmod(sock_path, 0o600)
        server.listen(5)
        server.settimeout(1.0)
        _server_sock = server
        _server_running = True
        _is_server_instance = True
        if not _atexit_registered:
            atexit.register(cleanup_ipc_socket)
            _atexit_registered = True
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
                    raw_text = raw_data.decode("utf-8", errors="ignore").strip()
                    cmd = raw_text.lower()
                    if cmd in ["trigger", "wake", "listen", "hotkey"]:
                        trigger_event.set()
                        conn.sendall(b"OK:triggered\n")
                    elif cmd in ["relisten", "skip", "next"]:
                        stop_current_speech()  # Dừng ngay LLM suy nghĩ và dừng đọc loa
                        trigger_event.set()    # Mở Micro bắt đầu lượt nghe mới ngay
                        from ai_assistant.core.ui_state import set_assistant_state
                        set_assistant_state("listening", "Đang lắng nghe... (Hãy nói vào micro)")
                        conn.sendall(b"OK:relistening\n")
                    elif cmd in ["stop", "cancel", "mute", "quiet"]:
                        stop_current_speech()
                        conn.sendall(b"OK:stopped\n")
                    elif cmd == "status":
                        st = json.dumps(get_assistant_state())
                        conn.sendall(f"{st}\n".encode())
                    elif cmd == "ping":
                        conn.sendall(b"pong\n")
                    elif cmd in ["screenshot", "capture_screen"]:
                        from ai_assistant.tools.vision import capture_screen
                        res = capture_screen()
                        conn.sendall(json.dumps(res).encode() + b"\n")
                    elif raw_text.lower().startswith("query:") or raw_text.lower().startswith("deep_query:"):
                        is_deep = raw_text.lower().startswith("deep_query:")
                        prefix_len = 11 if is_deep else 6
                        query_content = raw_text[prefix_len:].strip()
                        stop_current_speech()
                        conn.sendall(b"OK:processing\n")
                        from ai_assistant.core.agent import execute_text_command
                        threading.Thread(
                            target=execute_text_command,
                            kwargs={"user_text": query_content, "force_agent": is_deep},
                            daemon=True
                        ).start()
                    else:
                        conn.sendall(b"ERR:unknown_command\n")
                except Exception as ex:
                    print(f"⚠️ Lỗi xử lý lệnh IPC '{cmd}': {ex}", flush=True)
                    try:
                        conn.sendall(f"ERR:{ex}\n".encode())
                    except Exception:
                        pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception as e:
                print(f"⚠️ Ngoại lệ vòng lặp IPC server: {e}", flush=True)
                continue

    t = threading.Thread(target=_server_loop, daemon=True)
    t.start()
