#!/usr/bin/env python3
"""
Test so sánh các giọng đọc Piper TTS cục bộ (Offline) và Edge-TTS (Online).
Chạy:
    venv/bin/python training/tts/test_voices.py
"""
import os
import sys
import time
from pathlib import Path

# Thêm src vào sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from piper import PiperVoice
import subprocess

MODELS = {
    "1. Nữ phổ thông (Piper Offline)": BASE_DIR / "models/piper/vi_VN-giong_nu_pho_thong-medium.onnx",
    "2. Nam thanh niên (Piper Offline)": BASE_DIR / "models/piper/vi_VN-thanh_nien_tu_tin-medium.onnx"
}

SAMPLE_SENTENCES = [
    "Đã mở Zalo cho bạn rồi nhé.",
    "Tôi đã kiểm tra thời tiết hôm nay, trời nắng đẹp và nhiệt độ khoảng 28 độ C.",
    "Chào bạn, tôi là trợ lý ảo Alexa tiếng Việt chạy hoàn toàn trên máy cục bộ.",
    "Đã đóng ứng dụng Facebook theo yêu cầu của bạn."
]

def play_audio_bytes(audio_bytes: bytes, sample_rate: int = 22050):
    proc = subprocess.Popen(
        [
            "mpv", "--no-video", "--really-quiet",
            "--demuxer=rawaudio",
            f"--demuxer-rawaudio-rate={sample_rate}",
            "--demuxer-rawaudio-channels=1",
            "--demuxer-rawaudio-format=s16le",
            "-"
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    proc.stdin.write(audio_bytes)
    proc.stdin.close()
    proc.wait()

def benchmark_piper_model(name: str, model_path: Path, text: str):
    if not model_path.exists():
        print(f"❌ Không tìm thấy model: {model_path}")
        return
    print(f"\n--- Đang thử: {name} ---")
    print(f"📝 Câu: \"{text}\"")
    
    t0 = time.perf_counter()
    voice = PiperVoice.load(str(model_path))
    load_time = (time.perf_counter() - t0) * 1000
    
    t_synth = time.perf_counter()
    raw_audio = b"".join(chunk.audio_int16_bytes for chunk in voice.synthesize(text))
    synth_time = (time.perf_counter() - t_synth) * 1000
    
    # Tính thời lượng audio thực tế
    # 22050 samples/s, 16-bit = 2 bytes/sample -> 44100 bytes/s
    audio_duration_sec = len(raw_audio) / (22050 * 2)
    rtf = (synth_time / 1000) / audio_duration_sec if audio_duration_sec > 0 else 0
    
    print(f"⏱️ Thời gian tạo giọng (Synthesis): {synth_time:.1f}ms")
    print(f"⏱️ Độ dài audio: {audio_duration_sec:.2f}s | RTF: {rtf:.3f} (Nhanh gấp {1/rtf:.1f}x so với thời gian thực)")
    print("🔊 Đang phát qua loa...")
    play_audio_bytes(raw_audio, voice.config.sample_rate)

def main():
    print("=" * 60)
    print("🔊 KIỂM TRA CHẤT LƯỢNG GIỌNG ĐỌC PIPER OFFLINE (VIỆT NAM)")
    print("=" * 60)
    
    sentence = SAMPLE_SENTENCES[0]
    if len(sys.argv) > 1:
        sentence = " ".join(sys.argv[1:])
    
    for name, path in MODELS.items():
        benchmark_piper_model(name, path, sentence)

if __name__ == "__main__":
    main()
