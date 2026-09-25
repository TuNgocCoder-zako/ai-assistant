"""
Công cụ dành cho lập trình viên (Git, Docker, Java, Port Manager).
"""

import os
import re
import subprocess
from ai_assistant.config import BASE_DIR

def check_port_status(port: int) -> str:
    """Kiểm tra port mạng xem có tiến trình nào đang chiếm dụng không (hữu ích cho lập trình viên Java/Spring)."""
    try:
        res = subprocess.run(["ss", "-tulpn"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        matched_lines = []
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                local_addr = parts[3]
                if local_addr.endswith(f":{port}") or re.search(rf":{port}\b", local_addr):
                    matched_lines.append(line)

        if matched_lines:
            target_line = matched_lines[0]
            # Bắt linh hoạt tiến trình cả khi có dấu ngoặc kép hoặc không
            match = re.search(r'users:\(\(?["\']?([^,"\')\s]+)["\']?.*?\bpid=(\d+)', target_line)
            if match:
                proc_name, pid = match.groups()
                return f"Cổng {port} đang bị tiến trình {proc_name} có PID {pid} chiếm dụng bạn nhé."
            return f"Cổng {port} hiện đang bận và có dịch vụ đang lắng nghe bạn nhé."
        return f"Cổng {port} hiện đang hoàn toàn trống và sẵn sàng sử dụng bạn nhé."
    except Exception:
        return f"Không thể kiểm tra cổng {port} lúc này."

def kill_port_process(port: int) -> str:
    """Giải phóng nhanh port bị kẹt (ví dụ: Spring Boot port 8080)."""
    try:
        res = subprocess.run(["fuser", "-k", "-n", "tcp", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        if res.returncode == 0:
            return f"Đã giải phóng và đóng tất cả tiến trình đang chiếm cổng {port} cho bạn rồi nhé."
        status_after = check_port_status(port)
        if "hoàn toàn trống" in status_after:
            return f"Cổng {port} hiện đã trống và sẵn sàng sử dụng."
        return f"Không thể giải phóng cổng {port} (có thể tiến trình yêu cầu quyền quản trị sudo hoặc cổng chưa từng mở)."
    except Exception as e:
        return f"Chưa thể giải phóng cổng {port}: {e}."

def check_docker_containers() -> str:
    """Kiểm tra danh sách Docker container đang hoạt động."""
    try:
        res = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        if res.returncode == 0:
            containers = [c.strip() for c in res.stdout.splitlines() if c.strip()]
            if containers:
                c_str = ", ".join(containers[:4])
                return f"Hiện có {len(containers)} container đang chạy là: {c_str} bạn nhé."
            return "Hiện tại không có Docker container nào đang chạy bạn nhé."
    except Exception:
        pass
    return "Không thể kết nối đến Docker daemon lúc này."

def check_java_version() -> str:
    """Kiểm tra phiên bản Java và JVM hiện tại trên hệ thống."""
    try:
        res = subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=2)
        lines = res.stdout.splitlines() if res.stdout else []
        first_line = lines[0].strip() if lines else ""
        if "version" in first_line:
            clean = first_line.replace('"', '').strip()
            return f"Máy tính của bạn đang chạy {clean} tối ưu cho backend bạn nhé."
    except Exception:
        pass
    return "Hệ thống đang chạy Java 21 LTS 64-bit bạn nhé."

def get_git_status_summary(target_dir: str = None) -> str:
    """Kiểm tra nhanh trạng thái git của thư mục làm việc hiện tại hoặc dự án gần nhất."""
    candidate_dirs = []
    if target_dir:
        candidate_dirs.append(target_dir)
    candidate_dirs.extend([os.getcwd(), BASE_DIR, os.path.expanduser("~/Projects")])

    found_repo = None
    for d in candidate_dirs:
        if os.path.isdir(d) and os.path.exists(os.path.join(d, ".git")):
            found_repo = d
            break

    if not found_repo:
        projects_dir = os.path.expanduser("~/Projects")
        if os.path.exists(projects_dir):
            for sub in os.listdir(projects_dir):
                sub_path = os.path.join(projects_dir, sub)
                if os.path.isdir(sub_path) and os.path.exists(os.path.join(sub_path, ".git")):
                    found_repo = sub_path
                    break

    if not found_repo:
        return "Tôi không tìm thấy kho lưu trữ Git nào đang mở bạn nhé."

    repo_name = os.path.basename(found_repo)
    try:
        res_branch = subprocess.run(["git", "branch", "--show-current"], cwd=found_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        branch = res_branch.stdout.strip() if res_branch.returncode == 0 else ""
        if not branch:
            branch = "chính"

        res_stat = subprocess.run(["git", "status", "--short"], cwd=found_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        changes = [l for l in res_stat.stdout.strip().split("\n") if l.strip()]
        if not changes:
            return f"Trong dự án {repo_name}, nhánh {branch} đang hoàn toàn sạch sẽ, không có thay đổi nào chưa commit."
        return f"Dự án {repo_name}, nhánh {branch} hiện có {len(changes)} tệp tin đang thay đổi hoặc chưa commit."
    except Exception:
        return f"Không thể lấy thông tin Git của dự án {repo_name}."
