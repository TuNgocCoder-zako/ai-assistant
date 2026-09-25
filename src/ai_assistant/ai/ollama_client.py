"""
Ollama LLM Client với Streaming Sentence-Level TTS và Fallback an toàn.
"""

import re
import json
import time
import asyncio
import threading
import subprocess
import requests
import edge_tts

from ai_assistant.config import OLLAMA_URL, DEFAULT_VOICE
from ai_assistant.core.state import set_assistant_state
from ai_assistant.speech import player
from ai_assistant.speech.tts import sanitize_text_for_voice, speak
from ai_assistant.tools.apps import match_app, find_app_in_text, launch_desktop_app, close_all_open_apps, close_active_window, close_specific_app
from ai_assistant.tools.web import search_duckduckgo_summary
from ai_assistant.ai.model_router import route_task
from ai_assistant.ai.prompts import get_system_prompt

conversation_history = []

def clear_conversation_history():
    global conversation_history
    conversation_history = []

def get_conversation_history() -> list:
    return list(conversation_history)

def query_ollama_streaming(prompt: str, app_index: dict, voice: str = DEFAULT_VOICE) -> str:
    """
    Truy vấn Ollama LLM với Ultra-Fast Streaming TTS:
    - Bắt đầu phát âm thanh ngay từ mệnh đề đầu tiên (thời gian phản hồi < 0.4 giây).
    - Cập nhật hiển thị văn bản theo thời gian thực (Real-time Token-to-Overlay).
    - Phát âm thanh liên tục qua MPV audio pipeline không khoảng ngắt.
    - An toàn phụ trợ: Tự động gọi hàm đóng/mở ứng dụng thật nếu câu phức lọt vào LLM.
    """
    global conversation_history

    system_msg = {"role": "system", "content": get_system_prompt()}
    if not conversation_history:
        conversation_history.append(system_msg)
    else:
        conversation_history[0] = system_msg

    prompt_lower = prompt.lower()

    # An toàn phụ trợ 1: Mở ứng dụng nếu câu lọt xuống LLM
    if re.search(r"\b(mở|bật|chạy|khởi động)\b", prompt_lower):
        app_match = re.search(r"\b(?:mở|bật|chạy|khởi động)\s+(?:ứng dụng\s+|phần mềm\s+|app\s+)?(.+)", prompt_lower)
        app_to_open = None
        if app_match:
            app_to_open = match_app(app_match.group(1).strip(), app_index)
        if not app_to_open:
            app_to_open = find_app_in_text(prompt_lower, app_index)
        if app_to_open:
            launch_desktop_app(app_to_open)

    # An toàn phụ trợ 2: Đóng ứng dụng / Cửa sổ nếu câu lọt xuống LLM
    close_match = re.search(r"\b(?:đóng|tắt|thoát|kill)\s+(?:hết\s+|tất cả\s+)?(?:ứng dụng\s+|phần mềm\s+|app\s+)?(.+)", prompt_lower)
    if close_match and not any(k in prompt_lower for k in ["hẹn giờ", "báo thức", "đếm ngược", "nhạc", "wifi", "bluetooth", "âm thanh"]):
        target = close_match.group(1).strip()
        if any(w in target for w in ["tất cả", "hết", "các ứng dụng", "mọi ứng dụng"]):
            close_all_open_apps()
        elif any(w in target for w in ["cửa sổ", "này", "tab"]):
            close_active_window()
        else:
            close_specific_app(target, app_index)

    # Tra cứu thông tin internet nếu câu hỏi cần dữ liệu thực tế / thời sự
    search_context = ""
    needs_search = any(k in prompt_lower for k in [
        "ai là", "ở đâu", "khi nào", "tại sao", "năm nào", "giá", "dân số",
        "tin tức", "mới nhất", "hôm nay", "thời tiết ngày mai", "tra cứu"
    ])
    if needs_search and len(prompt) > 6:
        snippet = search_duckduckgo_summary(prompt, max_results=2)
        if snippet:
            search_context = f"[Thông tin thực tế tra cứu từ internet: {snippet}]\n\n"

    final_user_prompt = f"{search_context}{prompt}" if search_context else prompt
    conversation_history.append({"role": "user", "content": final_user_prompt})
    if len(conversation_history) > 11:
        conversation_history = [conversation_history[0]] + conversation_history[-10:]

    target_model, role_name, model_opts = route_task(prompt)
    print(f"\n🎯 [Smart Router] Điều hướng: '{target_model}' | Nhóm việc: {role_name}")
    set_assistant_state("thinking", text=f"Đang suy luận ({target_model})...")

    payload = {
        "model": target_model,
        "messages": conversation_history,
        "stream": True,
        "keep_alive": "10m",
        "options": model_opts
    }

    # Khởi tạo hàng đợi âm thanh
    while not player.tts_queue.empty():
        try:
            player.tts_queue.get_nowait()
            player.tts_queue.task_done()
        except Exception:
            break

    player_proc = None
    try:
        player_proc = subprocess.Popen(
            ["mpv", "--no-video", "--really-quiet", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        with player._tts_proc_lock:
            player.current_tts_proc = player_proc
    except Exception:
        player_proc = None

    def tts_worker():
        nonlocal player_proc
        async def feed_phrase(clean_text: str):
            try:
                communicate = edge_tts.Communicate(clean_text, voice)
                async for chunk in communicate.stream():
                    if player.interrupt_speech_event.is_set():
                        break
                    if chunk["type"] == "audio" and player_proc and player_proc.stdin:
                        try:
                            player_proc.stdin.write(chunk["data"])
                        except Exception:
                            break
            except Exception:
                pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            item = player.tts_queue.get()
            if item is None:
                player.tts_queue.task_done()
                break
            if not player.interrupt_speech_event.is_set():
                if player_proc and player_proc.poll() is None:
                    loop.run_until_complete(feed_phrase(item))
                else:
                    loop.run_until_complete(feed_phrase(item))
            player.tts_queue.task_done()

        if player_proc and player_proc.stdin and not player_proc.stdin.closed:
            try:
                player_proc.stdin.close()
            except Exception:
                pass
        if player_proc:
            player.reap_process(player_proc, timeout=1.0)
        loop.close()

    worker_thread = threading.Thread(target=tts_worker, daemon=True)
    worker_thread.start()

    full_reply = ""
    current_sentence_buffer = ""
    first_chunk_sent = False
    last_ui_update = 0

    try:
        resp = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60)
        if resp.status_code == 200:
            for line in resp.iter_lines():
                if player.interrupt_speech_event.is_set():
                    break
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                msg = data.get("message", {})
                content_chunk = msg.get("content", "")
                if content_chunk:
                    full_reply += content_chunk
                    current_sentence_buffer += content_chunk

                    now_ts = time.time()
                    if now_ts - last_ui_update > 0.08:
                        clean_disp = re.sub(r'[\*\#\_\[\]]', '', full_reply).strip()
                        set_assistant_state("speaking", text=clean_disp)
                        last_ui_update = now_ts

                    if not first_chunk_sent:
                        clause_match = re.search(r'([,;:\.\?\!\n]+)\s+', current_sentence_buffer)
                        words = current_sentence_buffer.split()
                        if (clause_match and len(words) >= 3) or len(words) >= 6:
                            split_pos = clause_match.end() if clause_match else current_sentence_buffer.rfind(" ") + 1
                            if split_pos > 0:
                                clause = current_sentence_buffer[:split_pos].strip()
                                current_sentence_buffer = current_sentence_buffer[split_pos:]
                                clean_s = sanitize_text_for_voice(clause)
                                if clean_s and not player.interrupt_speech_event.is_set():
                                    player.tts_queue.put(clean_s)
                                    first_chunk_sent = True
                    else:
                        match = re.search(r'([.?!;\n]+)\s+', current_sentence_buffer)
                        if not match and len(current_sentence_buffer.split()) >= 10:
                            match = re.search(r'([,;:\n]+)\s+', current_sentence_buffer)
                        if match:
                            end_pos = match.end()
                            sentence = current_sentence_buffer[:end_pos].strip()
                            current_sentence_buffer = current_sentence_buffer[end_pos:]
                            clean_s = sanitize_text_for_voice(sentence)
                            if clean_s and not player.interrupt_speech_event.is_set():
                                player.tts_queue.put(clean_s)

            if not player.interrupt_speech_event.is_set() and current_sentence_buffer.strip():
                clean_s = sanitize_text_for_voice(current_sentence_buffer.strip())
                if clean_s:
                    player.tts_queue.put(clean_s)

            final_text = sanitize_text_for_voice(full_reply)
            set_assistant_state("speaking", text=final_text)

            player.tts_queue.put(None)
            worker_thread.join(timeout=20)
            player.set_last_tts_end_time(time.time())
            with player._tts_proc_lock:
                player.current_tts_proc = None

            conversation_history[-1] = {"role": "user", "content": prompt}
            conversation_history.append({"role": "assistant", "content": final_text})
            set_assistant_state("idle")
            return final_text
        else:
            err_msg = f"Xin lỗi, lỗi kết nối mô hình ({resp.status_code})."
            speak(err_msg, voice=voice)
            player.tts_queue.put(None)
            worker_thread.join(timeout=5)
            player.set_last_tts_end_time(time.time())
            with player._tts_proc_lock:
                player.current_tts_proc = None
            if player_proc:
                player.reap_process(player_proc, timeout=0.5)
            set_assistant_state("idle")
            return err_msg
    except Exception as e:
        player.tts_queue.put(None)
        err_msg = f"Không thể kết nối đến Ollama: {e}"
        speak("Hiện tại tôi chưa kết nối được với mô hình xử lý ngôn ngữ.", voice=voice)
        player.set_last_tts_end_time(time.time())
        with player._tts_proc_lock:
            player.current_tts_proc = None
        if player_proc:
            player.reap_process(player_proc, timeout=0.5)
        set_assistant_state("idle")
        return err_msg
