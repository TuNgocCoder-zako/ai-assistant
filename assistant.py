#!/usr/bin/env python3
"""
Voice AI Assistant (Alexa V2) - Backward-compatible Entry Point & Shim.
Kiến trúc V2 đã được phân tách thành các module chuyên biệt trong package `src/ai_assistant/`.
File này đóng vai trò cầu nối tương thích (Shim / Facade) để mọi lệnh gọi hiện tại
từ systemd service, phím tắt Hyprland và các script trong ~/.local/bin hoạt động trơn tru 100%.
"""

import os
import sys

# Đảm bảo đường dẫn `src/` luôn nằm trong sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Re-export các hằng số và cấu hình
from ai_assistant.config import (
    BASE_DIR,
    OLLAMA_URL,
    DEFAULT_FAST_MODEL,
    DEFAULT_CODER_MODEL,
    DEFAULT_REASONING_MODEL,
    DEFAULT_VOICE,
    DEFAULT_STT_MODEL,
    SAMPLE_RATE,
    CHUNK_SIZE,
    DEFAULT_THRESHOLD,
    DEFAULT_FOLLOWUP_TIMEOUT,
    TTS_ECHO_GUARD_SECONDS,
    STATE_FILE_PATH,
    MEMORY_FILE,
    TIMERS_FILE,
    NOTES_FILE,
    WHISPER_INITIAL_PROMPT,
    APP_ALIASES,
    URL_SHORTCUTS,
    EXIT_PHRASES,
    PROTECTED_CLASSES,
)

# Re-export Speech & Audio
from ai_assistant.speech import (
    play_chime,
    make_chime_wav,
    stop_current_speech,
    trigger_event,
    interrupt_speech_event,
    tts_queue,
    CHIMES,
    speak,
    speak_edge_tts,
    sanitize_text_for_voice,
    send_notification,
)
from ai_assistant.audio import (
    normalize_audio,
    record_audio,
    SOS_FILTER,
    load_wakeword_model,
    load_whisper_model,
)

# Re-export State & IPC
from ai_assistant.core.state import (
    ensure_overlay_running,
    set_assistant_state,
    get_assistant_state,
    assistant_state,
)
from ai_assistant.ipc import (
    get_socket_path,
    start_ipc_server,
    send_ipc_command,
)

# Re-export AI & Models
from ai_assistant.ai import (
    get_installed_ollama_models,
    resolve_model_roles,
    route_task,
    MODEL_ROLES,
    get_system_prompt,
    query_ollama_streaming,
    conversation_history,
)

# Re-export Tools
from ai_assistant.tools import (
    timer_manager,
    TimerAlarmManager,
    set_timer,
    get_vietnamese_time,
    get_vietnamese_date,
    get_battery_info,
    get_system_hardware_info,
    get_weather_info,
    parse_simple_math,
    get_clipboard_content,
    build_app_index,
    clean_target_query,
    match_app,
    find_app_in_text,
    launch_desktop_app,
    close_active_window,
    close_all_open_apps,
    close_specific_app,
    set_system_volume,
    check_port_status,
    kill_port_process,
    check_docker_containers,
    check_java_version,
    get_git_status_summary,
    search_duckduckgo_summary,
    search_and_display_image,
)

# Re-export Core & Runtime
from ai_assistant.core.memory import (
    load_user_memory,
    save_user_memory,
    add_user_fact,
    get_user_facts_prompt,
    add_quick_note,
    read_quick_notes,
)
from ai_assistant.core.nlu import (
    is_exit_phrase,
    clean_user_input,
    fast_path_nlu,
)
from ai_assistant.core.agent import (
    process_interaction,
    run_push_to_talk,
)
from ai_assistant.app import main

if __name__ == "__main__":
    main()
