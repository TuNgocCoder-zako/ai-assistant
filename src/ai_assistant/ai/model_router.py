"""
Định tuyến tác vụ thông minh (Task Specialization) cho Ollama Local LLMs.
"""

import requests
from ai_assistant.config import DEFAULT_FAST_MODEL, DEFAULT_CODER_MODEL, DEFAULT_REASONING_MODEL

def get_installed_ollama_models() -> set[str]:
    """Lấy danh sách các model hiện có sẵn trong Ollama."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=1.5)
        if r.status_code == 200:
            return {m.get("name", "") for m in r.json().get("models", [])}
    except Exception:
        pass
    return set()

def resolve_model_roles() -> dict:
    """Tự động phát hiện và phân bổ model tốt nhất trên máy cho từng công việc."""
    installed = get_installed_ollama_models()

    # 1. Fast & Daily Model (Ưu tiên: qwen2.5:3b -> qwen2.5:1.5b -> alexa-vn)
    fast_m = None
    for cand in ["qwen2.5:3b", "llama3.2:3b", "qwen2.5:1.5b", "alexa-vn:latest"]:
        if cand in installed:
            fast_m = cand
            break
    if not fast_m:
        fast_m = next(iter(installed)) if installed else DEFAULT_FAST_MODEL

    # 2. Coder Model (Ưu tiên: qwen2.5-coder:7b)
    coder_m = None
    for cand in ["qwen2.5-coder:7b", "qwen2.5-coder:latest", "deepseek-coder:6.7b"]:
        if cand in installed:
            coder_m = cand
            break
    if not coder_m:
        coder_m = fast_m

    # 3. Reasoning Model (Ưu tiên: qwen3:8b)
    reason_m = None
    for cand in ["qwen3:8b", "llama3.1:8b", "deepseek-r1:8b"]:
        if cand in installed:
            reason_m = cand
            break
    if not reason_m:
        reason_m = coder_m

    return {
        "fast": fast_m,
        "coder": coder_m,
        "reasoning": reason_m
    }

MODEL_ROLES = resolve_model_roles()

def route_task(prompt: str) -> tuple[str, str, dict]:
    """
    Bộ định tuyến thông minh (Smart Task Router):
    Phân bổ chính xác từng công việc cho mô hình tối ưu nhất.
    Trả về: (model_name, role_name, generation_options)
    """
    p = prompt.lower().strip()

    # 1. Nhóm LẬP TRÌNH & KỸ THUẬT CHUYÊN SÂU -> CODER MODEL (7B)
    coding_keywords = [
        "code", "lập trình", "java", "spring", "docker", "fix lỗi", "báo lỗi", "bug",
        "thuật toán", "cơ sở dữ liệu", "sql", "hibernate", "jpa", "microservice",
        "git", "bash", "hyprland", "cấu hình", "stack trace", "exception", "jvm",
        "viết hàm", "viết class", "refactor", "tối ưu code", "query", "rest api"
    ]
    if any(k in p for k in coding_keywords):
        return MODEL_ROLES["coder"], "Kỹ thuật & Lập trình (Coder 7B)", {
            "temperature": 0.2,
            "top_p": 0.85,
            "repeat_penalty": 1.15,
            "num_predict": 110,
            "num_ctx": 2048,
        }

    # 2. Nhóm SUY LUẬN LOGIC / PHÂN TÍCH ĐA BƯỚC -> REASONING MODEL (8B)
    reasoning_keywords = [
        "suy luận", "tại sao lại", "chứng minh", "phân tích logic", "so sánh chuyên sâu",
        "nguyên nhân sâu xa", "đánh giá ưu nhược điểm"
    ]
    if any(k in p for k in reasoning_keywords) and MODEL_ROLES["reasoning"] != MODEL_ROLES["fast"]:
        return MODEL_ROLES["reasoning"], "Suy luận Logic (Reasoning 8B)", {
            "temperature": 0.5,
            "top_p": 0.9,
            "repeat_penalty": 1.15,
            "num_predict": 100,
            "num_ctx": 2048,
        }

    # 3. MẶC ĐỊNH: MỞ APP TỰ NHIÊN, TRÌNH DUYỆT, TỐC ĐỘ CAO & THƯỜNG NGÀY -> FAST MODEL (3B)
    return MODEL_ROLES["fast"], "Tốc độ cao & Điều khiển hệ thống (Fast 3B)", {
        "temperature": 0.3,
        "top_p": 0.9,
        "repeat_penalty": 1.18,
        "num_predict": 60,
        "num_ctx": 1024,
    }
