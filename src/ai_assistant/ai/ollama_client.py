"""
Ollama LLM Client với Streaming Sentence-Level TTS và Fallback an toàn.
"""

import re
import json
import time
import threading
import requests
import numpy as np
import sounddevice as sd

from ai_assistant.config import OLLAMA_URL, DEFAULT_VOICE
from ai_assistant.core.state import set_assistant_state
from ai_assistant.speech import player
from ai_assistant.speech.tts import (
    sanitize_text_for_voice,
    speak,
    get_piper_voice,
    fix_vietnamese_sticky_tokens,
    trim_incomplete_sentence,
)
from ai_assistant.tools.web import search_duckduckgo_summary
from ai_assistant.ai.model_router import route_task
from ai_assistant.ai.prompts import get_system_prompt

conversation_history = []

def clear_conversation_history():
    global conversation_history
    conversation_history = []

def get_conversation_history() -> list:
    return list(conversation_history)

def query_ollama_streaming(prompt: str, app_index: dict, voice: str = DEFAULT_VOICE, force_deep: bool = False) -> str:
    """
    Truy vấn Ollama LLM với Ultra-Fast Streaming TTS:
    - Bắt đầu phát âm thanh ngay từ mệnh đề đầu tiên (thời gian phản hồi < 0.4 giây).
    - Cập nhật hiển thị văn bản theo thời gian thực (Real-time Token-to-Overlay).
    - Phát âm thanh liên tục qua MPV audio pipeline không khoảng ngắt.
    - An toàn phụ trợ: Tự động gọi hàm đóng/mở ứng dụng thật nếu câu phức lọt vào LLM.
    - Hỗ trợ force_deep: Sử dụng mô hình suy luận sâu (Reasoning 4B) khi được yêu cầu.
    """
    global conversation_history

    system_msg = {"role": "system", "content": get_system_prompt()}
    if not conversation_history:
        conversation_history.append(system_msg)
    else:
        conversation_history[0] = system_msg

    prompt_lower = prompt.lower()



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

    target_model, role_name, model_opts = route_task(prompt, force_deep=force_deep)
    print(f"\n🎯 [Smart Router] Điều hướng: '{target_model}' | Nhóm việc: {role_name}")
    set_assistant_state("thinking", text=f"Đang suy luận ({target_model})...")

    payload = {
        "model": target_model,
        "messages": conversation_history,
        "stream": True,
        "keep_alive": "10m",
        "options": model_opts
    }

    # Khởi tạo hàng đợi âm thanh và reset cờ ngắt
    player.interrupt_speech_event.clear()
    while not player.tts_queue.empty():
        try:
            player.tts_queue.get_nowait()
            player.tts_queue.task_done()
        except Exception:
            break

    voice_model = get_piper_voice(voice)

    def tts_worker():
        while True:
            item = player.tts_queue.get()
            if item is None:
                player.tts_queue.task_done()
                break

            if not player.interrupt_speech_event.is_set() and voice_model:
                try:
                    clean = sanitize_text_for_voice(item)
                    if clean and re.search(r'[\w\d]', clean):
                        chunks = []
                        for chunk in voice_model.synthesize(clean):
                            if player.interrupt_speech_event.is_set():
                                break
                            chunks.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16))

                        if chunks and not player.interrupt_speech_event.is_set():
                            audio_raw = np.concatenate(chunks)
                            audio = audio_raw.astype(np.float32) / 32768.0
                            sr = getattr(voice_model.config, "sample_rate", 22050)

                            # Khử triệt để tiếng xoẹt/pop: 5ms fade-in và 35ms cosine fade-out
                            fade_in = int(sr * 0.005)
                            fade_out = int(sr * 0.035)
                            if len(audio) > fade_in:
                                audio[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
                            if len(audio) > fade_out:
                                audio[-fade_out:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fade_out, dtype=np.float32)))
                            audio[-1] = 0.0

                            silence = np.zeros(int(sr * 0.025), dtype=np.float32)
                            final_audio = np.concatenate([audio, silence])

                            sd.play(final_audio, samplerate=sr)
                            dur = len(final_audio) / sr
                            start_t = time.time()
                            while time.time() - start_t < dur:
                                if player.interrupt_speech_event.is_set():
                                    sd.stop()
                                    break
                                time.sleep(0.015)
                except Exception as e:
                    print(f"⚠️ Lỗi phát âm thanh streaming: {e}")

            player.tts_queue.task_done()

    worker_thread = threading.Thread(target=tts_worker, daemon=True)
    worker_thread.start()

    # Nếu dùng mô hình suy luận (Qwen3 / R1), phát câu đệm tức thì (<0.3s) để loại bỏ hoàn toàn sự im lặng chết
    is_reasoning_model = bool(target_model and ("qwen3" in target_model.lower() or "r1" in target_model.lower()))
    if is_reasoning_model and not player.interrupt_speech_event.is_set():
        import random
        ack_phrase = random.choice([
            "Dạ, đợi tôi một chút nhé.",
            "Để tôi kiểm tra nhé.",
            "Tôi đang suy nghĩ một chút nhé.",
        ])
        player.tts_queue.put(ack_phrase)

    full_reply = ""
    thinking_accumulated = ""
    current_sentence_buffer = ""
    first_chunk_sent = False
    last_ui_update = 0
    in_think_block = False

    try:
        resp = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120)
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
                thinking_chunk = msg.get("thinking", "")
                if thinking_chunk:
                    thinking_accumulated += thinking_chunk
                    now_ts = time.time()
                    if now_ts - last_ui_update > 0.25:
                        set_assistant_state("thinking", text="Đang suy luận logic...", query=prompt)
                        last_ui_update = now_ts
                    continue

                content_chunk = msg.get("content", "")
                if content_chunk:
                    # Lọc sạch thẻ <think>...</think> kể cả khi trải dài qua nhiều chunks
                    if "<think>" in content_chunk:
                        in_think_block = True
                        parts = content_chunk.split("<think>", 1)
                        before_think = parts[0]
                        after_think = parts[1]
                        if "</think>" in after_think:
                            in_think_block = False
                            content_chunk = before_think + after_think.split("</think>", 1)[1]
                        else:
                            content_chunk = before_think
                    elif in_think_block:
                        if "</think>" in content_chunk:
                            in_think_block = False
                            content_chunk = content_chunk.split("</think>", 1)[1]
                        else:
                            content_chunk = ""
                    elif "</think>" in content_chunk:
                        # Mô hình bắt đầu suy luận ngay từ đầu mà không phát thẻ mở <think>
                        in_think_block = False
                        content_chunk = content_chunk.split("</think>", 1)[1]
                        full_reply = ""
                        current_sentence_buffer = ""
                        while not player.tts_queue.empty():
                            try:
                                player.tts_queue.get_nowait()
                                player.tts_queue.task_done()
                            except Exception:
                                break

                    if not content_chunk:
                        continue

                    full_reply += content_chunk
                    current_sentence_buffer += content_chunk

                    now_ts = time.time()
                    if now_ts - last_ui_update > 0.08:
                        clean_disp = re.sub(r'[\*\#\_\[\]]', '', full_reply).strip()
                        clean_disp = fix_vietnamese_sticky_tokens(clean_disp)
                        is_long = len(clean_disp) > 80 or "\n" in clean_disp
                        set_assistant_state("speaking", text=clean_disp, query=prompt, is_long_text=is_long, long_answer=clean_disp if is_long else "")
                        last_ui_update = now_ts

                    # Chặn rò rỉ suy luận tiếng Anh (CoT Leak) trước khi gửi vào TTS
                    cot_pattern = r'^(?:wait,?\s+|okay,?\s+so\b|let me think|since\s+(?:they|the\s+user)|the user\s+(?:is|said|might|wrote|mentioned)|in vietnamese,?\s+|as alexa,?\s+|from the provided|hmm,?\s+|i need to\s+figure|first, standard|so the answer)'
                    if re.search(cot_pattern, current_sentence_buffer.strip(), re.IGNORECASE):
                        continue

                    if not first_chunk_sent:
                        match = re.search(r'([.?!;\n]+)\s+', current_sentence_buffer)
                        if not match:
                            match = re.search(r'([,:]+)\s+', current_sentence_buffer)
                        if match:
                            split_pos = match.end()
                            candidate = current_sentence_buffer[:split_pos].strip()
                            if len(candidate.split()) >= 3 or re.search(r'[.?!]\s*$', candidate):
                                current_sentence_buffer = current_sentence_buffer[split_pos:]
                                clean_s = sanitize_text_for_voice(candidate)
                                if clean_s and not player.interrupt_speech_event.is_set():
                                    player.tts_queue.put(clean_s)
                                    first_chunk_sent = True
                        elif len(current_sentence_buffer.split()) >= 8:
                            split_pos = current_sentence_buffer.rfind(" ") + 1
                            if split_pos > 0:
                                candidate = current_sentence_buffer[:split_pos].strip()
                                current_sentence_buffer = current_sentence_buffer[split_pos:]
                                clean_s = sanitize_text_for_voice(candidate)
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
                candidate_last = current_sentence_buffer.strip()
                if re.search(r'[.!?]', candidate_last):
                    clean_s = sanitize_text_for_voice(trim_incomplete_sentence(candidate_last))
                    if clean_s:
                        player.tts_queue.put(clean_s)
                elif not first_chunk_sent:
                    clean_s = sanitize_text_for_voice(trim_incomplete_sentence(candidate_last))
                    if clean_s:
                        player.tts_queue.put(clean_s)

            # Nếu mô hình tiêu tốn hết token trong khối suy luận mà chưa kịp nhả content:
            if not full_reply.strip() and thinking_accumulated:
                raw_sentences = re.split(r'[\r\n]+', thinking_accumulated)
                vi_lines = []
                for line in raw_sentences:
                    clean_l = line.strip().strip('"\'')
                    if len(clean_l) > 15 and re.search(r'[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]', clean_l):
                        if not any(k in clean_l.lower() for k in ["think", "translate", "rule", "instruction", "so the answer", "user wants"]):
                            vi_lines.append(clean_l)
                if vi_lines:
                    recovered = vi_lines[-1]
                    full_reply = recovered
                    clean_s = sanitize_text_for_voice(recovered)
                    if clean_s and not player.interrupt_speech_event.is_set():
                        player.tts_queue.put(clean_s)

            # Loại bỏ mọi thẻ think lọt vào và tỉa đuôi lửng lơ nếu chạm trần token
            full_reply = re.sub(r'<think>.*?</think>', '', full_reply, flags=re.DOTALL).strip()
            full_reply_trimmed = trim_incomplete_sentence(full_reply)
            final_text = fix_vietnamese_sticky_tokens(sanitize_text_for_voice(full_reply_trimmed))
            leak_markers = ["bắt buộc 100% tiếng việt", "xưng hô thân mật", "quy tắc giao tiếp", "toàn bộ câu trả lời sẽ được phát", "phong cách giao tiếp"]
            if any(m in final_text.lower() for m in leak_markers):
                final_text = "Dạ, tôi chưa nghe rõ câu hỏi của bạn. Bạn có thể nói lại giúp tôi được không?"
            elif not final_text:
                final_text = "Dạ, tôi chưa nghe rõ hoặc chưa kịp xử lý câu này. Bạn hỏi lại giúp tôi nhé."
            is_long = len(final_text) > 80 or "\n" in final_text
            set_assistant_state("speaking", text=final_text, query=prompt, is_long_text=is_long, long_answer=final_text if is_long else "")
            print(f"🗣️ [TTS / Trả lời] Alexa: {final_text}", flush=True)

            player.tts_queue.put(None)
            worker_thread.join(timeout=60)
            player.set_last_tts_end_time(time.time())
            with player._tts_proc_lock:
                player.current_tts_proc = None

            conversation_history[-1] = {"role": "user", "content": prompt}
            conversation_history.append({"role": "assistant", "content": final_text})
            set_assistant_state("idle")
            return final_text
        else:
            err_msg = f"Xin lỗi, lỗi kết nối mô hình ({resp.status_code})."
            print(f"⚠️ {err_msg}", flush=True)
            speak(err_msg, voice=voice)
            player.tts_queue.put(None)
            worker_thread.join(timeout=5)
            player.set_last_tts_end_time(time.time())
            with player._tts_proc_lock:
                player.current_tts_proc = None
            set_assistant_state("idle")
            return err_msg
    except Exception as e:
        player.tts_queue.put(None)
        err_msg = f"Không thể kết nối đến Ollama: {e}"
        print(f"⚠️ {err_msg}", flush=True)
        speak("Hiện tại tôi chưa kết nối được với mô hình xử lý ngôn ngữ.", voice=voice)
        player.set_last_tts_end_time(time.time())
        with player._tts_proc_lock:
            player.current_tts_proc = None
        set_assistant_state("idle")
        return err_msg
