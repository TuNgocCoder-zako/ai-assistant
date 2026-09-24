"""
Unix Domain Socket IPC Client gửi lệnh tới Daemon đang chạy nền.
"""

import os
import socket
from ai_assistant.ipc.server import get_socket_path

def send_ipc_command(cmd: str) -> tuple[bool, str]:
    """Gửi lệnh IPC tới trợ lý đang chạy nền từ tiến trình bên ngoài."""
    sock_path = get_socket_path()
    if not os.path.exists(sock_path):
        return False, "Trợ lý ảo Alexa chưa chạy nền."
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(sock_path)
        s.sendall(f"{cmd}\n".encode("utf-8"))
        resp = s.recv(1024).decode("utf-8", errors="ignore").strip()
        s.close()
        return True, resp
    except Exception as e:
        return False, str(e)
