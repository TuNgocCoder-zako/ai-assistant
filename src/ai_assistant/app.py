"""
Điểm khởi chạy chính (CLI & Daemon Runtime) của Voice AI Assistant.
"""

import sys
import time
import argparse
import threading
import requests
import numpy as np
import sounddevice as sd

from ai_assistant.config import (
    DEFAULT_THRESHOLD,
    MUSIC_WAKE_THRESHOLD_BOOST,
    WAKE_PATIENCE_FRAMES,
    DEFAULT_VOICE,
    DEFAULT_FOLLOWUP_TIMEOUT,
    SAMPLE_RATE,
    CHUNK_SIZE,
    OLLAMA_URL,
)
from ai_assistant.ipc.server import start_ipc_server
from ai_assistant.ipc.client import send_ipc_command
from ai_assistant.core.state import ensure_overlay_running, init_state_handlers
from ai_assistant.speech.player import trigger_event
from ai_assistant.speech.tts import send_notification
from ai_assistant.tools.apps import build_app_index
from ai_assistant.tools.system import is_media_playing
from ai_assistant.audio.stt import load_whisper_model
from ai_assistant.audio.wakeword import load_wakeword_model
from ai_assistant.ai.model_router import MODEL_ROLES
from ai_assistant.core.agent import process_interaction, run_push_to_talk

def parse_args():
    parser = argparse.ArgumentParser(description="Voice AI Assistant Alexa (Arch Linux / Hyprland)")
    parser.add_argument(
        "-p", "--push-to-talk",
        action="store_true",
        help="Chạy ở chế độ bấm Enter để nói thay vì lắng nghe Wake Word liên tục"
    )
    parser.add_argument(
        "--trigger",
        action="store_true",
        help="Gửi tín hiệu đánh thức tới trợ lý đang chạy nền (dùng cho phím tắt Hyprland)"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Gửi tín hiệu ngắt lời / dừng phát âm tới trợ lý đang chạy nền"
    )
    parser.add_argument(
        "--relisten",
        action="store_true",
        help="Dừng ngay suy nghĩ/phát âm và kích hoạt micro lắng nghe ngay lượt mới"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Kiểm tra trạng thái của trợ lý đang chạy nền"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Chạy tương tác 1 phiên rồi thoát hoàn toàn (Single-turn CLI mode)"
    )
    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Ngưỡng nhạy của từ khóa đánh thức (mặc định: 0.52; tăng lên 0.55 - 0.60 nếu môi trường quá ồn)"
    )
    parser.add_argument(
        "-w", "--wake-word",
        type=str,
        default="alexa",
        choices=["alexa", "jarvis", "all"],
        help="Từ khóa đánh thức (mặc định: 'alexa'; có thể chọn 'jarvis' hoặc 'all')"
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3-turbo"],
        help="Mô hình Faster-Whisper (mặc định: small - nhận diện tiếng Việt cực chuẩn và mượt)"
    )
    parser.add_argument(
        "-v", "--voice",
        type=str,
        default=DEFAULT_VOICE,
        help="Giọng đọc Piper TTS Offline (mặc định: vi_VN-giong_nu_pho_thong-medium; vi_VN-thanh_nien_tu_tin-medium)"
    )
    parser.add_argument(
        "-c", "--continuous",
        action="store_true",
        default=True,
        help="Bật chế độ thoại liên tục nhiều lượt (mặc định: BẬT)"
    )
    parser.add_argument(
        "--no-continuous",
        dest="continuous",
        action="store_false",
        help="Tắt chế độ thoại liên tục (chỉ trả lời 1 lượt rồi nghỉ)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_FOLLOWUP_TIMEOUT,
        help="Thời gian chờ người dùng nói tiếp trong chế độ thoại liên tục (mặc định: 3.5 giây)"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Giữ trợ lý chạy ngầm lặp lại sau khi trò chuyện thay vì tự động tắt hoàn toàn"
    )
    parser.add_argument(
        "--text",
        type=str,
        default="",
        help="Thực thi câu lệnh văn bản trực tiếp (gửi qua IPC hoặc xử lý ngay)"
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Bật chế độ Suy luận sâu (Agent Core 3B) cho câu lệnh văn bản"
    )
    args, _ = parser.parse_known_args()
    return args

def main():
    args = parse_args()

    # Xử lý các lệnh IPC gửi tới Daemon đang chạy nền
    if args.trigger:
        ok, msg = send_ipc_command("trigger")
        if ok:
            print(f"✅ Đã gửi tín hiệu đánh thức tới trợ lý Alexa: {msg}")
            sys.exit(0)
        else:
            print(f"⚠️ {msg}")
            sys.exit(1)

    if args.stop:
        ok, msg = send_ipc_command("stop")
        if ok:
            print(f"✅ Đã gửi tín hiệu ngắt lời tới trợ lý Alexa: {msg}")
            sys.exit(0)
        else:
            print(f"⚠️ {msg}")
            sys.exit(1)

    if args.relisten:
        ok, msg = send_ipc_command("relisten")
        if ok:
            print(f"✅ Đã gửi tín hiệu dừng và nghe tiếp tới trợ lý Alexa: {msg}")
            sys.exit(0)
        else:
            print(f"⚠️ {msg}")
            sys.exit(1)

    if args.status:
        ok, msg = send_ipc_command("status")
        if ok:
            print(f"Trạng thái Alexa: {msg}")
            sys.exit(0)
        else:
            print(f"⚠️ {msg}")
            sys.exit(1)

    if args.text:
        ipc_cmd = f"deep_query:{args.text}" if args.deep else f"query:{args.text}"
        ok, msg = send_ipc_command(ipc_cmd)
        if ok:
            print(f"✅ Đã gửi lệnh văn bản tới trợ lý Alexa: {msg}")
            sys.exit(0)
        else:
            # Nếu daemon chưa chạy, thực thi trực tiếp câu lệnh
            ensure_overlay_running()
            from ai_assistant.core.agent import execute_text_command
            res = execute_text_command(args.text, voice=args.voice, force_agent=args.deep)
            print(f"🤖 Alexa: {res}")
            sys.exit(0)

    wake_threshold = args.threshold
    selected_model = args.model
    selected_voice = args.voice
    wake_mode = args.wake_word
    continuous_mode = args.continuous
    follow_timeout = args.timeout
    auto_exit_mode = args.once

    print("=" * 65)
    print("        🚀 KHỞI ĐỘNG TRỢ LÝ ẢO VOICE AI THÔNG MINH (ALEXA V2)")
    print("        ✨ Phong cách smartphone: Earcons Ting-ting + Chạy nền Daemon")
    print("        ⚡ Phím tắt IPC + Cắt lời (Barge-in) + Hẹn giờ & Báo thức bền bỉ")
    print("=" * 65)

    # Khởi động IPC Socket Server & Giao diện Dynamic Island Overlay
    start_ipc_server()
    ensure_overlay_running()
    init_state_handlers()

    # 0. Quét danh sách ứng dụng trên hệ thống
    print("⏳ [1/4] Đang lập chỉ mục các ứng dụng trên hệ thống...")
    app_index = build_app_index()
    print(f"✅ Đã lập chỉ mục {len(app_index)} ứng dụng desktop thành công!")

    # 1. Kiểm tra mô hình STT (Ưu tiên GPU CUDA)
    print(f"⏳ [2/4] Nạp mô hình Whisper '{selected_model}'...")
    stt_model, stt_device, stt_compute_type = load_whisper_model(selected_model)
    print(f"✅ Mô hình Whisper '{selected_model}' ({stt_compute_type}) đã sẵn sàng trên {stt_device.upper()}!")

    # 2. Kiểm tra mô hình Wake Word nếu không dùng push-to-talk
    oww_model = None
    wake_word_label = "Alexa"
    if not args.push_to_talk:
        print("⏳ [3/4] Nạp mô hình Wake Word (openWakeWord)...")
        oww_model, wake_word_label = load_wakeword_model(wake_mode)
        print(f"✅ Mô hình Wake Word đã sẵn sàng! (Chỉ lắng nghe: '{wake_word_label}')")
    else:
        print("⏭️ [3/4] Bỏ qua Wake Word (đang bật chế độ Push-to-Talk)")

    # 3. Kiểm tra kết nối Ollama & Nạp trước (Pre-warm) mô hình lên VRAM
    print("⏳ [4/4] Kiểm tra kết nối Ollama LLM...")
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            print(f"✅ Ollama đang hoạt động! Phân bổ mô hình trí tuệ nhân tạo:")
            print(f"   ⚡ Tốc độ & Điều khiển (Mở app/Trình duyệt/Chat): {MODEL_ROLES['fast']}")
            print(f"   💻 Lập trình & Kỹ thuật (Java/Spring/Linux):      {MODEL_ROLES['coder']}")
            print(f"   🧠 Suy luận logic đa bước:                      {MODEL_ROLES['reasoning']}")
            print(f"⏳ Đang nạp sẵn mô hình tốc độ '{MODEL_ROLES['fast']}' vào VRAM GPU...")
            def _prewarm_ollama():
                try:
                    requests.post(
                        OLLAMA_URL,
                        json={
                            "model": MODEL_ROLES["fast"],
                            "messages": [{"role": "user", "content": "hi"}],
                            "stream": False,
                            "keep_alive": "15m",
                            "options": {
                                "num_predict": 1,
                                "num_gpu": 99,
                                "num_ctx": 2048,
                            }
                        },
                        timeout=10
                    )
                except Exception:
                    pass
            threading.Thread(target=_prewarm_ollama, daemon=True).start()
        else:
            print("⚠️ Cảnh báo: Không thể kết nối tới Ollama!")
    except Exception as e:
        print(f"⚠️ Cảnh báo: Ollama chưa bật ({e})")

    print("\n" + "-" * 65)
    print(f"🎙️ NGHE: Pre-roll 300ms + Schmitt Trigger VAD + Earcon Chimes + Whisper {selected_model}")
    print(f"⚡ HIỂU: Hybrid NLU (<5ms Fast-Path: app, nhạc, wifi, bluetooth, hẹn giờ, ghi chú, RAG)")
    print(f"🗣️ TRẢ LỜI: Sentence-Level Streaming Piper TTS Offline ('{selected_voice}') + Hỗ trợ Barge-in cắt lời")
    print(f"🔄 CHẠY NỀN: {'CHẠY 1 LẦN (--once)' if auto_exit_mode else 'DAEMON 24/7 (Luôn túc trực)'}")
    if args.push_to_talk:
        print("💡 Chế độ: Push-to-Talk (Bấm Enter để nói)")
    else:
        print(f"💡 Chế độ: Wake Word ('{wake_word_label}') & IPC Socket Hotkey")
    print("  * Bấm Ctrl+C bất kỳ lúc nào để thoát.")
    print("-" * 65)

    send_notification("Alexa AI", "Trợ lý ảo Alexa đã sẵn sàng phục vụ.")
    time.sleep(0.15)

    if args.push_to_talk:
        run_push_to_talk(stt_model, app_index, voice=selected_voice, continuous=continuous_mode, follow_timeout=follow_timeout, auto_exit=auto_exit_mode)
        return

    print(f"🎧 Đang lắng nghe từ khóa '{wake_word_label}' hoặc phím tắt IPC...\n")

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16') as stream:
            try:
                if stream.read_available > 0:
                    stream.read(stream.read_available)
            except Exception:
                pass
            last_candidate_log = 0.0
            last_media_check = 0.0
            is_music_active = False
            model_keys = list(oww_model.models.keys())
            patience_dict = {k: WAKE_PATIENCE_FRAMES for k in model_keys}

            while True:
                # 1. Kiểm tra tín hiệu IPC Socket
                if trigger_event.is_set():
                    trigger_event.clear()
                    print("\n\n⚡ [IPC Hotkey] Nhận tín hiệu kích hoạt từ phím tắt / IPC!", flush=True)
                    oww_model.reset()
                    try:
                        stream.stop()
                    except Exception:
                        pass
                    try:
                        process_interaction(
                            stt_model,
                            app_index,
                            voice=selected_voice,
                            continuous=continuous_mode,
                            follow_timeout=follow_timeout,
                            auto_exit=auto_exit_mode
                        )
                    finally:
                        try:
                            stream.start()
                        except Exception:
                            pass
                    time.sleep(0.8)
                    try:
                        avail = stream.read_available
                        if avail > 0:
                            stream.read(avail)
                    except Exception:
                        pass
                    oww_model.reset()
                    for _ in range(3):
                        try:
                            dummy_data, _ = stream.read(CHUNK_SIZE)
                            oww_model.predict(dummy_data.flatten())
                        except Exception:
                            break
                    print(f"\n🎧 Đang lắng nghe từ khóa '{wake_word_label}' hoặc phím tắt...\n", flush=True)
                    continue

                # 2. Đọc chunk và nhận diện wake word
                audio_data, _ = stream.read(CHUNK_SIZE)
                audio_chunk = audio_data.flatten()

                now = time.time()
                if now - last_media_check >= 1.0:
                    is_music_active = is_media_playing()
                    last_media_check = now

                effective_threshold = wake_threshold + (MUSIC_WAKE_THRESHOLD_BOOST if is_music_active else 0.0)
                threshold_dict = {k: effective_threshold for k in model_keys}

                prediction = oww_model.predict(
                    audio_chunk,
                    patience=patience_dict,
                    threshold=threshold_dict
                )

                rms = np.sqrt(np.mean(audio_chunk.astype(np.float32)**2))
                raw_max = max((float(oww_model.prediction_buffer[k][-1]) for k in model_keys), default=0.0)

                if sys.stdout.isatty():
                    bars = int(min(rms / 4000, 1.0) * 8)
                    meter = "█" * bars + "░" * (8 - bars)
                    status_note = " 🎵 [AEC On]" if is_music_active else ""
                    print(f"\r🎤 Mic: [{meter}] | Độ khớp: {raw_max:.2f} (Ngưỡng: {effective_threshold:.2f}{status_note})  ", end="", flush=True)
                elif raw_max >= 0.25:
                    if now - last_candidate_log > 0.4:
                        status_note = " (Đang phát nhạc -> AEC lọc loa)" if is_music_active else ""
                        print(f"🎙️ [WakeWord Candidate] Độ khớp tức thời: {raw_max:.2f} / {effective_threshold:.2f} (RMS: {int(rms)}){status_note}", flush=True)
                        last_candidate_log = now

                for model_name, score in prediction.items():
                    if score >= effective_threshold:
                        detected_name = "Alexa" if "alexa" in model_name else "Hey Jarvis"
                        print(f"\n\n✨ Đã phát hiện từ khóa '{detected_name}'! (Độ tin cậy: {score:.2f})", flush=True)
                        oww_model.reset()

                        try:
                            stream.stop()
                        except Exception:
                            pass
                        try:
                            process_interaction(
                                stt_model,
                                app_index,
                                voice=selected_voice,
                                continuous=continuous_mode,
                                follow_timeout=follow_timeout,
                                auto_exit=auto_exit_mode
                            )
                        finally:
                            try:
                                stream.start()
                            except Exception:
                                pass

                        time.sleep(0.8)
                        try:
                            avail = stream.read_available
                            if avail > 0:
                                stream.read(avail)
                        except Exception:
                            pass
                        oww_model.reset()
                        for _ in range(3):
                            try:
                                dummy_data, _ = stream.read(CHUNK_SIZE)
                                oww_model.predict(dummy_data.flatten())
                            except Exception:
                                break
                        print(f"\n🎧 Đang lắng nghe từ khóa '{wake_word_label}' hoặc phím tắt...\n", flush=True)
                        break

    except KeyboardInterrupt:
        print("\n👋 Đã dừng trợ lý ảo. Hẹn gặp lại!")
    except Exception as e:
        print(f"\n❌ Lỗi trong luồng lắng nghe: {e}")

if __name__ == "__main__":
    main()
