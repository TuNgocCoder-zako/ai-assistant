#!/usr/bin/env python3
"""
Chuẩn bị và chuẩn hóa Dataset cho Piper TTS Fine-tuning.
Chức năng:
1. Quét các file âm thanh (.wav, .mp3, .m4a, .ogg) trong thư mục nguồn.
2. Chuẩn hóa về format bắt buộc của Piper: WAV PCM 16-bit, Mono, 22050 Hz.
3. Cắt tỉa khoảng lặng (trim silence) ở đầu/cuối file.
4. Kiểm tra và định dạng lại metadata.csv chuẩn (id|transcript).
"""
import os
import sys
import csv
import subprocess
from pathlib import Path

def check_ffmpeg():
    res = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    if res.returncode != 0:
        print("❌ Lỗi: Chưa cài đặt ffmpeg. Vui lòng cài: sudo pacman -S ffmpeg")
        sys.exit(1)

def convert_audio_to_piper_spec(src_path: Path, dst_path: Path):
    """
    Chuyển đổi file âm thanh sang:
    - Codec: pcm_s16le (16-bit PCM)
    - Channels: 1 (Mono)
    - Sample rate: 22050 Hz
    - Tự động cắt khoảng lặng đầu/đuôi (silenceremove)
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-af", "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:detection=peak,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:detection=peak,areverse",
        "-ar", "22050",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        str(dst_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0

def process_dataset(raw_dir: str, output_dir: str, metadata_file: str):
    check_ffmpeg()
    raw_path = Path(raw_dir)
    out_path = Path(output_dir)
    out_wavs = out_path / "wavs"
    out_wavs.mkdir(parents=True, exist_ok=True)
    
    meta_path = Path(metadata_file)
    if not meta_path.exists():
        print(f"❌ Không tìm thấy file metadata: {meta_path}")
        return
        
    print(f"📂 Đang xử lý dataset từ: {raw_path}")
    print(f"🎯 Thư mục đích chuẩn hóa: {out_path}")
    
    clean_entries = []
    # Đọc metadata gốc (hỗ trợ phân cách bởi | hoặc ,)
    with open(meta_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="|")
        for line_num, row in enumerate(reader, 1):
            if not row or len(row) < 2:
                continue
            audio_name = row[0].strip()
            text = row[1].strip()
            
            # Tìm file âm thanh gốc
            candidates = [
                raw_path / audio_name,
                raw_path / f"{audio_name}.wav",
                raw_path / f"{audio_name}.mp3",
                raw_path / "wavs" / audio_name,
                raw_path / "wavs" / f"{audio_name}.wav",
            ]
            src_file = next((p for p in candidates if p.exists()), None)
            
            if not src_file:
                print(f"⚠️ Dòng {line_num}: Không tìm thấy file audio cho '{audio_name}', bỏ qua.")
                continue
                
            file_id = f"{line_num:04d}"
            dst_wav = out_wavs / f"{file_id}.wav"
            
            ok = convert_audio_to_piper_spec(src_file, dst_wav)
            if ok:
                clean_entries.append((f"{file_id}.wav", text))
            else:
                print(f"⚠️ Lỗi convert ffmpeg cho: {src_file.name}")
                
    # Ghi metadata.csv chuẩn hóa
    target_meta = out_path / "metadata.csv"
    with open(target_meta, "w", encoding="utf-8") as f:
        for fname, text in clean_entries:
            f.write(f"{fname}|{text}\n")
            
    print(f"✅ Đã chuẩn hóa thành công {len(clean_entries)} câu audio!")
    print(f"📁 Thư mục xuất: {out_path}")
    print(f"   ├── wavs/ ({len(clean_entries)} files)")
    print(f"   └── metadata.csv")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Cách dùng:")
        print("    python prepare_dataset.py <thu_muc_audio_goc> <thu_muc_xuat> <file_metadata.csv>")
        print("\nVí dụ:")
        print("    python prepare_dataset.py ./my_voice_raw ./dataset_ready ./my_voice_raw/metadata.csv")
        sys.exit(0)
    process_dataset(sys.argv[1], sys.argv[2], sys.argv[3])
