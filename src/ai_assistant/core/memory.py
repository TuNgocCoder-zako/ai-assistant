"""
Quản lý bộ nhớ người dùng (facts/preferences) và ghi chú nhanh.
"""

import os
import json
import datetime
from ai_assistant.config import MEMORY_FILE, NOTES_FILE

def load_user_memory() -> dict:
    """Tải bộ nhớ thông tin cá nhân của người dùng."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"facts": []}

def save_user_memory(memory: dict):
    """Lưu bộ nhớ thông tin cá nhân của người dùng."""
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def add_user_fact(fact: str) -> str:
    """Ghi nhớ một sự kiện hoặc thông tin về người dùng vào bộ nhớ dài hạn."""
    mem = load_user_memory()
    clean_fact = fact.strip().rstrip(".!?")
    if clean_fact and clean_fact not in mem["facts"]:
        mem["facts"].append(clean_fact)
        if len(mem["facts"]) > 15:
            mem["facts"] = mem["facts"][-15:]
        save_user_memory(mem)
    return f"Đã ghi nhớ thông tin: {clean_fact}."

def get_user_facts_prompt() -> str:
    """Trích xuất các thông tin đã nhớ để đưa vào System Prompt."""
    mem = load_user_memory()
    if mem.get("facts"):
        facts_str = "\n".join([f"- {f}" for f in mem["facts"]])
        return f"\nTHÔNG TIN VỀ NGƯỜI DÙNG ĐÃ GHI NHỚ:\n{facts_str}\n"
    return ""

def add_quick_note(content: str) -> str:
    """Lưu ghi chú nhanh của người dùng."""
    try:
        os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now_str}] {content}\n")
        return f"Đã ghi chú lại cho bạn: {content}."
    except Exception:
        return "Không thể lưu ghi chú vào lúc này."

def read_quick_notes() -> str:
    """Đọc các ghi chú gần nhất."""
    if not os.path.exists(NOTES_FILE):
        return "Bạn hiện chưa có ghi chú nào."
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        if not lines:
            return "Danh sách ghi chú của bạn đang trống."
        last_notes = lines[-2:]
        return "Ghi chú gần nhất của bạn là: " + "; ".join(last_notes)
    except Exception:
        return "Không thể đọc danh sách ghi chú."
