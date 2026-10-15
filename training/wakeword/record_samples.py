#!/usr/bin/env python3
"""
Công cụ thu âm tập dữ liệu Wake Word cá nhân (Positive / Negative Samples).
Dùng để chuẩn bị dữ liệu huấn luyện hoặc fine-tune trên Google Colab.

Cách sử dụng:
  # 1. Thu âm 30 mẫu bạn nói "Alexa" (Positive)
  python training/wakeword/record_samples.py --type positive --count 30

  # 2. Thu âm 50 mẫu tạp âm / nhạc / tiếng nói thông thường (Negative)
  python training/wakeword/record_samples.py --type negative --count 50
"""

import os
import sys
import time
import wave
import argparse
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
DURATION_SECONDS = 2.0  # Mỗi mẫu dài 2 giây

def main():
    parser = argparse.ArgumentParser(description="Thu âm mẫu dữ liệu Wake Word cá nhân")
    parser.add_argument(
        "--type",
        choices=["positive", "negative"],
        default="positive",
        help="Loại dữ liệu: 'positive' (bạn gọi Alexa) hoặc 'negative' (nhạc / tiếng ồn / nói chuyện khác)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Số lượng mẫu muốn thu âm (mặc định: 20)"
    )
    parser.add_argument(
        "--output-dir",
        default="training/wakeword/dataset",
        help="Thư mục lưu trữ dữ liệu"
    )
    args = parser.parse_args()

    target_dir = os.path.join(args.output_dir, args.type)
    os.makedirs(target_dir, exist_ok=True)

    print("=" * 60)
    print(f"🎙️ BẮT ĐẦU THU ÂM DỮ LIỆU WAKE WORD [{args.type.upper()}]")
    print(f"📁 Thư mục lưu trữ: {target_dir}")
    print(f"📊 Số lượng mẫu:    {args.count}")
    print(f"⏱️ Thời lượng mẫu:  {DURATION_SECONDS} giây / mẫu (16kHz Mono)")
    print("=" * 60)

    if args.type == "positive":
        print("\n💡 HƯỚNG DẪN THU MẪU DƯƠNG (POSITIVE):")
        print("  - Khi thấy đếm ngược kết thúc và chữ '🔴 ĐANG THU ÂM...', hãy nói rõ ràng từ 'Alexa'.")
        print("  - Hãy thay đổi khoảng cách (gần mic, xa mic 1-2m), âm lượng (bình thường, thì thầm, nói to).")
    else:
        print("\n💡 HƯỚNG DẪN THU MẪU ÂM (NEGATIVE):")
        print("  - Bật nhạc Spotify / YouTube, hoặc gõ bàn phím, hoặc nói các câu tiếng Việt KHÔNG CÓ từ Alexa.")
        print("  - Hệ thống sẽ tự động cắt các đoạn 2 giây lưu vào thư mục negative.")

    input("\n👉 Nhấn phím Enter để bắt đầu thu âm mẫu đầu tiên...")

    for i in range(1, args.count + 1):
        filename = f"{args.type}_{int(time.time())}_{i:03d}.wav"
        filepath = os.path.join(target_dir, filename)

        print(f"\n[{i}/{args.count}] Chuẩn bị trong: ", end="", flush=True)
        for c in range(2, 0, -1):
            print(f"{c}... ", end="", flush=True)
            time.sleep(0.7)

        print("🔴 ĐANG THU ÂM... (Nói ngay)", flush=True)
        num_samples = int(SAMPLE_RATE * DURATION_SECONDS)
        recording = sd.rec(num_samples, samplerate=SAMPLE_RATE, channels=1, dtype='int16')
        sd.wait()

        # Ghi file WAV chuẩn 16kHz Mono 16-bit PCM bằng thư viện chuẩn
        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(recording.tobytes())

        rms = np.sqrt(np.mean(recording.astype(np.float32)**2))
        print(f"✅ Đã lưu: {filename} (Năng lượng RMS: {int(rms)})")

        if i < args.count:
            time.sleep(0.5)

    print("\n" + "=" * 60)
    print(f"🎉 HOÀN TẤT THU ÂM {args.count} MẪU [{args.type.upper()}]!")
    print(f"📂 Vị trí file: {target_dir}")
    print("=" * 60)

if __name__ == "__main__":
    main()
