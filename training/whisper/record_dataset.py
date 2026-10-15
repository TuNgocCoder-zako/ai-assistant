"""
Script thu âm tập lệnh mẫu tự động để chuẩn bị dữ liệu Fine-Tune Whisper trên Colab.
Cách dùng: python training/whisper/record_dataset.py
"""

import os
import sys
import wave
import json
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
OUTPUT_DIR = os.path.expanduser("~/Projects/python/voice-ai/training/whisper/dataset")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROMPT_LIST = [
    # Nhạc & Media
    "phát nhạc", "bật nhạc", "tắt nhạc", "dừng nhạc", "tạm dừng nhạc", "nghe tiếp",
    "chuyển bài hát", "đổi bài hát", "bài tiếp theo", "bài trước đó", "lùi bài",
    "bài này tên gì", "ai đang hát",
    # Âm lượng & Màn hình
    "tăng âm lượng", "giảm âm lượng", "cho to lên", "cho nhỏ lại", "tắt tiếng", "bật lại tiếng",
    "tăng độ sáng", "giảm độ sáng", "sáng lên", "tối đi",
    # Ứng dụng & Web
    "mở firefox", "mở trình duyệt", "mở vs code", "mở terminal", "mở spotify",
    "mở youtube", "mở zalo", "mở gmail", "mở github", "mở facebook",
    "đóng cửa sổ", "tắt ứng dụng", "đóng tab",
    # Hệ thống & Tiện ích
    "kiểm tra pin", "pin còn bao nhiêu", "mấy giờ rồi", "hôm nay ngày mấy",
    "kiểm tra tốc độ mạng", "bật wifi", "tắt wifi", "bật bluetooth", "tắt bluetooth",
    "chế độ turbo", "chế độ yên tĩnh", "chế độ cân bằng", "chụp màn hình",
    # Báo thức & Hẹn giờ
    "hẹn giờ 5 phút", "hẹn giờ 10 phút", "hủy hẹn giờ", "báo thức 6 giờ sáng"
]

def record_sample(text: str, idx: int):
    while True:
        print(f"\n────────────────────────────────────────────────────────────")
        print(f"[{idx+1}/{len(PROMPT_LIST)}] 👉 Hãy đọc tự nhiên, to và rõ ràng câu:")
        print(f"   👉 \"{text}\"")
        cmd_in = input("👉 Bấm [Enter] để thu âm ngay (nói trong 2.5s), hoặc [s] để bỏ qua câu này: ").strip().lower()
        if cmd_in == 's':
            print("⏭️ Đã bỏ qua câu này.")
            return None
        
        print("🔴 ĐANG THU ÂM... (Hãy đọc ngay câu trên!)")
        duration = 3.5
        recording = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
        sd.wait()
        print("⏹️ Đã thu xong!")
        
        # Đo cường độ âm thanh thực tế & Tự động chống vỡ tiếng (Clipping Protection)
        peak = abs(recording).max()
        if peak < 800:
            print("⚠️ Cảnh báo: Âm lượng thu được quá nhỏ hoặc micro bị tắt tiếng (mute).")
        elif peak >= 31000:
            print("⚠️ Cảnh báo: Âm lượng quá lớn làm vỡ tiếng (Clipping)! Đang tự động hạ biên độ an toàn để bảo vệ Whisper.")
            recording = (recording.astype(np.float32) / peak * 26000).astype(np.int16)
        elif peak > 15000:
            recording = (recording.astype(np.float32) / peak * 26000).astype(np.int16)
        
        ans = input("   👉 Bấm [Enter] để LƯU, bấm [p] để NGHE LẠI, bấm [r] để THU LẠI câu này: ").strip().lower()
        if ans == 'p':
            print("🔊 Đang phát lại âm thanh vừa thu...")
            sd.play(recording, samplerate=SAMPLE_RATE)
            sd.wait()
            ans2 = input("   👉 Bấm [Enter] để LƯU, hoặc [r] để THU LẠI: ").strip().lower()
            if ans2 == 'r':
                continue
        elif ans == 'r':
            print("🔄 Chuẩn bị thu lại...")
            continue
            
        wav_filename = f"sample_{idx:03d}.wav"
        wav_path = os.path.join(OUTPUT_DIR, wav_filename)
        
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(recording.tobytes())
            
        print(f"✅ Đã lưu mẫu vào: {wav_filename}")
        return {"audio": wav_filename, "sentence": text}

def main():
    metadata = []
    print("=" * 60)
    print("🎙️ TOOL THU ÂM BỘ DỮ LIỆU CÂU LỆNH CHO WHISPER")
    print(f"Tổng cộng có {len(PROMPT_LIST)} câu lệnh cần thu âm.")
    print("Mẹo: Nói đúng giọng điệu hằng ngày của bạn khi gọi máy tính.")
    print("=" * 60)
    
    try:
        for idx, text in enumerate(PROMPT_LIST):
            entry = record_sample(text, idx)
            if entry:
                metadata.append(entry)
    except KeyboardInterrupt:
        print("\n\n⚠️ Đã tạm dừng hoặc ngắt thu âm sớm.")
        
    metadata_path = os.path.join(OUTPUT_DIR, "metadata.jsonl")
    with open(metadata_path, "w", encoding="utf-8") as f:
        for entry in metadata:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
    print(f"\n✅ Đã lưu dữ liệu vào thư mục: {OUTPUT_DIR}")
    print(f"File nhãn: {metadata_path}")
    print("Bạn chỉ cần nén thư mục này thành `dataset.zip` và kéo thả lên Google Colab để train!")

if __name__ == "__main__":
    main()
