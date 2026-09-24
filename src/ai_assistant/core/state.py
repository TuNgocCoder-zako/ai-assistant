"""
Module tương thích ngược cho trạng thái trợ lý.
Đã được tách biệt thành:
- UI State: `ai_assistant.core.ui_state` (Quản lý trạng thái Quickshell Overlay: idle, listening, thinking, speaking)
- Agent State: `ai_assistant.core.agent_state` (Runtime state đầy đủ của Agent: Goal, Plan, Steps, Observations, Trace)
"""

from ai_assistant.core.ui_state import (
    set_assistant_state,
    get_assistant_state,
    ensure_overlay_running,
    init_state_handlers,
    assistant_state,
    state_lock,
)
