"""
Định tuyến tác vụ cho Ollama Local LLM — Chế độ Qwen3 4B.
"""

import re
import requests
from ai_assistant.config import DEFAULT_FAST_MODEL

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
    """Phân bổ role: qwen3:4b làm mô hình cốt lõi duy nhất cho toàn bộ hệ thống."""
    installed = get_installed_ollama_models()
    primary_m = None
    for cand in ["qwen3:4b", "qwen2.5:3b", "llama3.2:3b", "qwen2.5:1.5b"]:
        if cand in installed:
            primary_m = cand
            break
    if not primary_m:
        primary_m = DEFAULT_FAST_MODEL

    return {
        "fast": primary_m,
        "coder": primary_m,
        "reasoning": primary_m,
        "vision": None,
    }

MODEL_ROLES = resolve_model_roles()

def get_dynamic_num_predict(prompt: str, model_name: str = None) -> int:
    """
    Tự động cấp phát số token tối đa phù hợp ngữ cảnh và loại mô hình:
    - Nếu là mô hình reasoning (như qwen3 có khối <think>): Cần dự phòng thêm token cho reasoning.
      + Khái niệm / giải thích: 1600 tokens.
      + Xã giao / cảm ơn / chào hỏi: 800 tokens.
      + Câu thông thường: 1200 tokens.
    - Nếu là mô hình standard (như qwen2.5:3b không có khối <think>):
      + Khái niệm / giải thích: 260 tokens.
      + Xã giao / cảm ơn / chào hỏi: 80 tokens.
      + Câu thông thường: 140 tokens.
    """
    p_low = prompt.lower().strip()
    is_reasoning = bool(model_name and ("qwen3" in model_name.lower() or "r1" in model_name.lower()))

    # 1. Câu hỏi khái niệm, kiến thức, tại sao, giải thích
    deep_patterns = [
        r'\blà gì\b', r'\blà ai\b', r'\bthế nào\b', r'\bnhư thế nào\b',
        r'\btại sao\b', r'\bvì sao\b', r'\bnguyên nhân\b', r'\bgiải thích\b',
        r'\bkhái niệm\b', r'\bđịnh nghĩa\b', r'\bphân tích\b', r'\bso sánh\b',
        r'\bkể về\b', r'\btóm tắt\b', r'\bnguồn gốc\b', r'\blịch sử\b',
        r'\bý nghĩa\b', r'\bhướng dẫn\b', r'\bcơ chế\b', r'\bnguyên lý\b',
        r'\bưu nhược điểm\b', r'\bkhác nhau\b'
    ]
    if any(re.search(pat, p_low) for pat in deep_patterns):
        return 2048 if is_reasoning else 260

    # 2. Câu xã giao, cảm ơn, chào hỏi ngắn
    casual_patterns = [
        r'^(xin )?chào\b', r'^(hế lô|hello|hi)\b', r'\bcảm ơn\b', r'\bthank\b',
        r'\btạm biệt\b', r'^(bye|goodbye)\b', r'\bbạn khỏe không\b', r'\bbạn tên gì\b',
        r'^(ok|ừ|được rồi|tốt lắm|hay lắm)\b'
    ]
    if any(re.search(pat, p_low) for pat in casual_patterns) and len(p_low.split()) <= 10:
        return 1024 if is_reasoning else 80

    # 3. Câu thông thường
    return 1500 if is_reasoning else 140

def route_task(prompt: str, force_deep: bool = False) -> tuple[str, str, dict]:
    """Định tuyến tác vụ cho mô hình cốt lõi qwen3:4b."""
    target_model = MODEL_ROLES["fast"]
    num_pred = get_dynamic_num_predict(prompt, model_name=target_model)
    is_qwen3 = bool(target_model and ("qwen3" in target_model.lower() or "r1" in target_model.lower()))
    role_label = "Fast 4B (Qwen3)" if is_qwen3 else "Fast 3B"
    return target_model, role_label, {
        "temperature": 0.6 if is_qwen3 else 0.3,
        "top_p": 0.95 if is_qwen3 else 0.9,
        "repeat_penalty": 1.05,
        "num_predict": num_pred,
        "num_ctx": 2048 if is_qwen3 else 1024,
        "num_gpu": 99,
    }
