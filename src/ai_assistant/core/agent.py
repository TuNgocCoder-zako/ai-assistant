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
    set_assistant_state("listening", "Đang lắng nghe... (Hãy nói vào micro)")
    play_chime("wake")
    print(f"\n✨ [Ting-ting! 🔔] Alexa đang lắng nghe...")
    time.sleep(0.08)

    max_turns = 10 if continuous else 1
    turn = 0

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
        turn_silence = 0.65 if turn > 1 else 0.85
        raw_audio, ambient_noise = record_audio(max_duration=8.0, silence_timeout=turn_silence, max_wait_for_speech=wait_time)
        if len(raw_audio) == 0:
            if turn > 1:
                print("\n⏳ Bạn đã hoàn thành yêu cầu. Alexa trở về trạng thái nghỉ.\n")
            else:
                print("\n⚠️ Không phát hiện tiếng người nói. Alexa trở về trạng thái nghỉ.\n")

            play_chime("sleep")
            set_assistant_state("idle")
            if auto_exit:
                sys.exit(0)
            return

        # 2 & 3. Lọc thông cao & Silero VAD
        clean_audio = filter_speech_with_vad(raw_audio)
        if len(clean_audio) == 0:
            if turn > 1:
                print("\n⏳ Bạn đã hoàn thành yêu cầu. Trở về trạng thái nghỉ.\n")
            else:
                print("\n⏳ Không phát hiện tiếng người nói rõ ràng. Trở về trạng thái nghỉ.\n")
            play_chime("sleep")
            set_assistant_state("idle")
            if auto_exit:
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
            if turn > 1:
                print("\n⏳ Bạn đã hoàn thành yêu cầu. Trở về trạng thái nghỉ.\n")
            else:
                print("\n⏳ Không nghe rõ nội dung câu nói. Trở về trạng thái nghỉ.\n")
            play_chime("sleep")
            set_assistant_state("idle")
            if auto_exit:
                sys.exit(0)
            return

        print(f"\n👤 Bạn: {user_text}")
        set_assistant_state("thinking", f'Bạn: "{user_text}"')

        # Kiểm tra nếu người dùng nói từ khóa kết thúc cuộc trò chuyện
        if is_exit_phrase(user_text):
            farewell = random.choice(["Tạm biệt bạn nhé.", "Chào bạn nhé.", "Hẹn gặp lại bạn."])
            print(f"🤖 Alexa: {farewell}\n")
            speak(farewell, voice=voice)
            play_chime("sleep")
            set_assistant_state("idle")
            print("💤 Alexa trở về trạng thái nghỉ lắng nghe...\n")
            if auto_exit:
                sys.exit(0)
            return

        # 6. Thuật toán HIỂU: Kiểm tra Fast-Path NLU trước
        is_fast_handled, fast_reply = fast_path_nlu(user_text, app_index)
        if is_fast_handled:
            if fast_reply:
                print(f"⚡ [Fast-Path NLU - Phản hồi tức thì <5ms]")
                print(f"🤖 Alexa: {fast_reply}\n")
                set_assistant_state("speaking", text=fast_reply)
                speak(fast_reply, voice=voice)
            set_assistant_state("idle")
            play_chime("sleep")
            if auto_exit:
                sys.exit(0)
            return
        else:
            # 7. Chuyển sang Deep-Path LLM (Streaming TTS)
            print("🧠 [Deep-Path LLM - Đang suy luận và đọc theo luồng...]")
            reply = query_ollama_streaming(user_text, app_index, voice=voice)
            print(f"🤖 Alexa: {reply}\n")
            set_assistant_state("idle")

        if not continuous:
            play_chime("sleep")
            set_assistant_state("idle")
            print("\n👋 Đã hoàn thành yêu cầu. Alexa trở về trạng thái nghỉ.\n")
            if auto_exit:
                sys.exit(0)
            return

        time.sleep(0.5)

    play_chime("sleep")
    set_assistant_state("idle")
    if auto_exit:
        print("\n👋 Phiên trò chuyện kết thúc. Trợ lý ảo đã tắt hoàn toàn.\n")
        sys.exit(0)

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
