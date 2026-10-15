"""
Vòng lặp điều phối tương tác trung tâm của Voice AI Agent.
"""

import sys
import time
import random
import numpy as np
from faster_whisper import WhisperModel

from ai_assistant.config import DEFAULT_VOICE, DEFAULT_FOLLOWUP_TIMEOUT, TTS_ECHO_GUARD_SECONDS
from ai_assistant.core.state import set_assistant_state
from ai_assistant.speech.player import play_chime, interrupt_speech_event, get_last_tts_end_time
from ai_assistant.speech.tts import speak
from ai_assistant.audio.capture import record_audio, normalize_audio
from ai_assistant.audio.stt import filter_speech_with_vad, transcribe_audio, is_whisper_hallucination
from ai_assistant.core.nlu import clean_user_input, is_exit_phrase, fast_path_nlu
from ai_assistant.ai.ollama_client import query_ollama_streaming
from ai_assistant.tools.system import is_media_playing, media_pause, media_play

def process_interaction(
    stt_model: WhisperModel,
    app_index: dict,
    voice: str = DEFAULT_VOICE,
    continuous: bool = True,
    follow_timeout: float = DEFAULT_FOLLOWUP_TIMEOUT,
    auto_exit: bool = False
):
    """
    Xử lý tương tác thông minh hỗ trợ Thoại liên tục và Cơ chế Chạy nền:
    - Phản hồi tức thì bằng âm thanh Earcon (Ting-ting) thay vì đọc lời chào gây trễ.
    - Trả lời siêu tốc (<5ms) cho các lệnh thường dùng qua Fast-Path NLU (âm lượng, nhạc, wifi, bluetooth, hẹn giờ).
    - Phát câu trả lời dạng Streaming cho các câu hỏi hội thoại phức tạp.
    - Khi người dùng dừng nói (im lặng) -> Phát âm Bloop êm dịu và quay về trạng thái nghe ngầm (hoặc sys.exit nếu bật --once).
    """
    interrupt_speech_event.clear()

    # Tự động tạm dừng phát nhạc (Auto-Pause on Wake Word) để loại bỏ hoàn toàn tiếng nhạc dội vào micro
    was_media_playing = is_media_playing()
    if was_media_playing:
        media_pause()

    set_assistant_state("listening", "Đang lắng nghe... (Hãy nói vào micro)")
    play_chime("wake")
    print(f"\n✨ [Ting-ting! 🔔] Alexa đang lắng nghe...")
    time.sleep(0.30)  # Chờ chuông Ting-ting (230ms) dứt hẳn để không lọt vào 400ms đo ồn nền

    max_turns = 10 if continuous else 1
    turn = 0

    try:
        while turn < max_turns:
            turn += 1
            interrupt_speech_event.clear()
            wait_time = follow_timeout if turn > 1 else 5.0

            # Echo Guard: Chờ loa im hẳn trước khi mở micro thu âm
            time_since_tts = time.time() - get_last_tts_end_time()
            if time_since_tts < TTS_ECHO_GUARD_SECONDS:
                guard_wait = TTS_ECHO_GUARD_SECONDS - time_since_tts
                time.sleep(guard_wait)

            if turn > 1:
                print(f"🎙️ Alexa đang lắng nghe tiếp... (nói tiếp câu khác, hoặc im lặng {follow_timeout}s để nghỉ)")
            else:
                print("🎙️ Đang lắng nghe... (hãy nói vào micro)")

            set_assistant_state("listening", "Đang lắng nghe tiếp... (Nói tiếp hoặc im lặng để đóng)" if turn > 1 else "Đang lắng nghe... (Hãy nói vào micro)")

            # 1. Thu âm với Pre-roll Ring Buffer và Dual-Threshold Schmitt Trigger
            turn_silence = 1.2 if turn > 1 else 1.5
            raw_audio, ambient_noise = record_audio(max_duration=8.0, silence_timeout=turn_silence, max_wait_for_speech=wait_time)
            if len(raw_audio) == 0:
                if interrupt_speech_event.is_set():
                    print("\n🛑 Vòng thu âm đã bị ngắt bởi thao tác khác.")
                    return
                if turn > 1:
                    print("\n⏳ Bạn đã hoàn thành yêu cầu. Alexa trở về trạng thái nghỉ.\n")
                else:
                    print("\n⚠️ Không phát hiện tiếng người nói. Alexa trở về trạng thái nghỉ.\n")

                set_assistant_state("idle")
                if auto_exit:
                    time.sleep(0.25)
                    sys.exit(0)
                return

            # 2 & 3. Lọc thông cao & Silero VAD
            clean_audio = filter_speech_with_vad(raw_audio)
            if len(clean_audio) == 0:
                if turn == 1:
                    retry_msg = "Tôi chưa nghe rõ câu lệnh, bạn nói lại nhé."
                    print(f"\n⚠️ {retry_msg}\n")
                    set_assistant_state("speaking", text=retry_msg)
                    speak(retry_msg, voice=voice)
                    set_assistant_state("listening", "Đang lắng nghe lại... (Hãy nói vào micro)")
                    time.sleep(0.3)
                    continue
                else:
                    print("\n⏳ Bạn đã hoàn thành yêu cầu. Trở về trạng thái nghỉ.\n")
                    set_assistant_state("idle")
                    if auto_exit:
                        time.sleep(0.25)
                        sys.exit(0)
                    return

            # 4. Chuẩn hóa âm lượng tự động (Automatic Gain Control có trần nhiễu)
            normalized_audio = normalize_audio(clean_audio, target_peak=0.90, ambient_noise=ambient_noise)

            # 5. Nhận diện giọng nói siêu tốc bằng Faster-Whisper
            print("⚡ Đang nhận diện giọng nói...")
            set_assistant_state("thinking", "Đang nhận diện giọng nói...")
            raw_user_text = transcribe_audio(stt_model, normalized_audio)
            user_text = clean_user_input(raw_user_text)

            # Khử ảo giác Whisper
            if is_whisper_hallucination(user_text):
                if turn == 1:
                    retry_msg = "Tôi chưa nghe rõ câu lệnh, bạn nói lại nhé."
                    print(f"\n⚠️ {retry_msg}\n")
                    set_assistant_state("speaking", text=retry_msg)
                    speak(retry_msg, voice=voice)
                    set_assistant_state("listening", "Đang lắng nghe lại... (Hãy nói vào micro)")
                    time.sleep(0.3)
                    continue
                else:
                    print("\n⏳ Bạn đã hoàn thành yêu cầu. Trở về trạng thái nghỉ.\n")
                    set_assistant_state("idle")
                    if auto_exit:
                        time.sleep(0.25)
                        sys.exit(0)
                    return

            print(f"\n👤 Bạn: {user_text}")
            set_assistant_state("thinking", f'Bạn: "{user_text}"', query=user_text, clear_card=True)

            # Kiểm tra nếu người dùng nói từ khóa kết thúc cuộc trò chuyện
            if is_exit_phrase(user_text):
                farewell = random.choice(["Tạm biệt bạn nhé.", "Chào bạn nhé.", "Hẹn gặp lại bạn."])
                print(f"🤖 Alexa: {farewell}\n")
                set_assistant_state("speaking", text=farewell, is_long_text=False)
                speak(farewell, voice=voice)
                time.sleep(0.12)
                set_assistant_state("idle")
                print("💤 Alexa trở về trạng thái nghỉ lắng nghe...\n")
                if auto_exit:
                    time.sleep(0.25)
                    sys.exit(0)
                return

            # 6. Thuật toán HIỂU: Kiểm tra Fast-Path NLU trước
            is_fast_handled, fast_reply = fast_path_nlu(user_text, app_index)
            if is_fast_handled:
                if fast_reply:
                    print(f"⚡ [Fast-Path NLU - Phản hồi tức thì <5ms]")
                    print(f"🤖 Alexa: {fast_reply}\n")
                    set_assistant_state("speaking", text=fast_reply, is_long_text=False)
                    speak(fast_reply, voice=voice)
                    time.sleep(0.12)

                # Cập nhật cờ phát nhạc: Nếu người dùng muốn dừng nhạc thì không bật lại; nếu đã chuyển/phát nhạc thì nhạc đang chạy
                if any(k in fast_reply.lower() for k in ["tạm dừng phát nhạc", "dừng phát", "đã tắt"]):
                    was_media_playing = False
                elif any(k in fast_reply.lower() for k in ["tiếp theo", "bài trước", "tiếp tục phát"]):
                    was_media_playing = False

                if not continuous:
                    set_assistant_state("idle", clear_card=True)
                    if auto_exit:
                        time.sleep(0.25)
                        sys.exit(0)
                    return
                time.sleep(0.4)
                continue
            else:
                # 7. Kiểm tra xem có phải tác vụ đa bước cần kích hoạt Agent Core không
                from ai_assistant.core.orchestrator import agent_orchestrator
                if agent_orchestrator.is_complex_request(user_text):
                    print("🧠 [Agent Core Orchestrator - Kích hoạt vòng lặp Plan-Act-Observe-Reflect]")
                    reply = agent_orchestrator.run_agent_loop(user_text, voice=voice)
                    print(f"🤖 Alexa (Agent Core): {reply}\n")
                else:
                    # 8. Đàm thoại thông thường hoặc câu hỏi kiến thức -> Streaming TTS
                    print("💬 [Deep-Path LLM - Đang suy luận và đọc theo luồng...]")
                    reply = query_ollama_streaming(user_text, app_index, voice=voice)
                    print(f"🤖 Alexa: {reply}\n")

                if any(k in reply.lower() for k in ["tạm dừng", "dừng phát nhạc", "ngừng phát"]):
                    was_media_playing = False
                elif any(k in reply.lower() for k in ["chuyển sang bài tiếp theo", "quay lại bài trước", "tiếp tục phát"]):
                    was_media_playing = False

                if not continuous:
                    time.sleep(0.12)
                    set_assistant_state("idle", clear_card=True)
                    print("\n👋 Đã hoàn thành yêu cầu. Alexa trở về trạng thái nghỉ.\n")
                    if auto_exit:
                        time.sleep(0.25)
                        sys.exit(0)
                    return

                time.sleep(0.4)

        set_assistant_state("idle")
        if auto_exit:
            print("\n👋 Phiên trò chuyện kết thúc. Trợ lý ảo đã tắt hoàn toàn.\n")
            time.sleep(0.25)
            sys.exit(0)
    finally:
        if was_media_playing:
            media_play()

def run_push_to_talk(
    stt_model: WhisperModel,
    app_index: dict,
    voice: str = DEFAULT_VOICE,
    continuous: bool = True,
    follow_timeout: float = DEFAULT_FOLLOWUP_TIMEOUT,
    auto_exit: bool = False
):
    """Chế độ bấm phím nói (Push-to-Talk) tiện lợi."""
    print("\n⌨️ Chế độ Push-to-Talk đã kích hoạt.")
    print("👉 Nhấn Enter để bắt đầu nói (hoặc gõ Ctrl+C để thoát).\n")
    while True:
        try:
            input("Nhấn [Enter] để nói...")
            process_interaction(
                stt_model,
                app_index,
                voice=voice,
                continuous=continuous,
                follow_timeout=follow_timeout,
                auto_exit=auto_exit
            )
            if auto_exit:
                break
        except KeyboardInterrupt:
            print("\n👋 Đã dừng trợ lý ảo. Hẹn gặp lại!")
            break


def execute_text_command(
    user_text: str,
    app_index: dict = None,
    voice: str = DEFAULT_VOICE,
    force_agent: bool = False,
    force_deep: bool = False
) -> str:
    """Thực thi câu lệnh văn bản trực tiếp từ giao diện overlay hoặc CLI."""
    interrupt_speech_event.clear()
    user_text = clean_user_input(user_text)
    if not user_text:
        return ""

    is_deep = force_agent or force_deep

    if app_index is None:
        from ai_assistant.tools.apps import build_app_index
        app_index = build_app_index()

    print(f"\n💬 [Text Query] Nhận lệnh văn bản: '{user_text}' (Deep: {is_deep})")
    set_assistant_state("thinking", f'Bạn: "{user_text}"', query=user_text, clear_card=True)

    # 1. Kiểm tra từ khóa kết thúc
    if is_exit_phrase(user_text):
        farewell = random.choice(["Tạm biệt bạn nhé.", "Chào bạn nhé.", "Hẹn gặp lại bạn."])
        set_assistant_state("speaking", text=farewell, is_long_text=False)
        speak(farewell, voice=voice)
        set_assistant_state("idle")
        return farewell

    # 2. Fast-Path NLU: Xử lý tức thì các lệnh điều khiển hệ thống, phát nhạc, tính toán số học nhanh (<5ms)
    is_fast_handled, fast_reply = fast_path_nlu(user_text, app_index)
    if is_fast_handled and fast_reply:
        print(f"⚡ [Fast-Path NLU - Phản hồi tức thì <5ms]: {fast_reply}")
        set_assistant_state("speaking", text=fast_reply, is_long_text=False)
        speak(fast_reply, voice=voice)
        set_assistant_state("idle")
        return fast_reply

    # 3. Kích hoạt Agent Core nếu là tác vụ điều phối hệ điều hành phức tạp / đa bước
    from ai_assistant.core.orchestrator import agent_orchestrator
    if agent_orchestrator.is_complex_request(user_text):
        print(f"🧠 [Agent Core Orchestrator - Kích hoạt vòng lặp điều phối (Deep: {is_deep})]")
        reply = agent_orchestrator.run_agent_loop(user_text, voice=voice, force_deep=is_deep)
        set_assistant_state("idle")
        return reply

    # 4. Truy vấn mô hình cục bộ LLM (Fast hoặc Deep Reasoning tùy cờ is_deep)
    print(f"💬 [Local LLM - Đang suy luận và đọc theo luồng (Deep: {is_deep})...]")
    reply = query_ollama_streaming(user_text, app_index, voice=voice, force_deep=is_deep)
    set_assistant_state("idle")
    return reply

