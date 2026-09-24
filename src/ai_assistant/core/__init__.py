"""
Core package for Voice AI Assistant.
"""

from ai_assistant.core.state import (
    set_assistant_state,
    get_assistant_state,
    ensure_overlay_running,
    init_state_handlers,
    assistant_state,
)
from ai_assistant.core.memory import (
    load_user_memory,
    save_user_memory,
    add_user_fact,
    get_user_facts_prompt,
    add_quick_note,
    read_quick_notes,
)

__all__ = [
    "set_assistant_state",
    "get_assistant_state",
    "ensure_overlay_running",
    "init_state_handlers",
    "assistant_state",
    "load_user_memory",
    "save_user_memory",
    "add_user_fact",
    "get_user_facts_prompt",
    "add_quick_note",
    "read_quick_notes",
]
