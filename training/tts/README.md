# 🎙️ Hướng Dẫn Tự Huấn Luyện (Fine-Tune) Giọng Đọc Piper TTS Tiếng Việt

Tài liệu này hướng dẫn bạn cách huấn luyện thêm (Fine-tune) giọng đọc tiếng Việt theo sở thích hoặc theo giọng của chính bạn để chạy **ngoại tuyến 100% (Offline)** trên máy tính cá nhân với độ trễ cực thấp (**< 90 mili-giây**).

---

## ⚡ 1. Nghe Thử Các Giọng Offline Đã Tích Hợp Sẵn

Trước khi bắt đầu thu âm và huấn luyện, bạn có thể kiểm tra trực tiếp 2 mô hình VITS tiếng Việt chất lượng cao đã được tải sẵn vào dự án:

```bash
# Chạy câu mặc định
venv/bin/python training/tts/test_voices.py

# Hoặc thử bất kỳ câu nói nào bạn muốn:
venv/bin/python training/tts/test_voices.py "Xin chào, tôi là trợ lý ảo Alexa tiếng Việt."
```

* **Giọng 1:** Nữ phổ thông (`vi_VN-giong_nu_pho_thong-medium.onnx`)
* **Giọng 2:** Nam thanh niên (`vi_VN-thanh_nien_tu_tin-medium.onnx`)

*(Cả 2 giọng này đều phản hồi trong ~80ms và phát âm rõ ràng đầy đủ thanh điệu tiếng Việt).*

---

## 📋 2. Cần Chuẩn Bị Những Gì Để Fine-Tune?

Để mô hình học được âm sắc mới mà không làm mất khả năng phát âm tiếng Việt chuẩn:

1. **Không huấn luyện từ đầu (Train from scratch):**
   - Chúng ta bắt đầu từ Checkpoint gốc **`vi_VN-vais1000-medium`** (đã học sẵn hơn 4,700 epochs từ cộng đồng).
2. **Dữ liệu âm thanh (Dataset):**
   - **Số lượng:** Chỉ cần khoảng **150 - 300 câu ngắn** (tổng thời lượng từ 30 phút đến 1 tiếng).
   - **Chất lượng:** Thu âm trong không gian yên tĩnh, không vang vọng, phát âm tròn vành rõ chữ.
3. **Cấu trúc thư mục Dataset:**
   ```text
   my_dataset/
     ├── wavs/
     │    ├── 0001.wav
     │    ├── 0002.wav
     │    └── ...
     └── metadata.csv
   ```
   *File `metadata.csv` có định dạng:*
   ```csv
   0001.wav|Đã mở Zalo cho bạn rồi nhé.
   0002.wav|Thời tiết hôm nay rất đẹp và mát mẻ.
   ```

---

## 🛠️ 3. Tự Động Chuẩn Hóa Dataset Với Script Có Sẵn

Nếu bạn có các file âm thanh thu từ điện thoại hoặc phần mềm bất kỳ (định dạng mp3, m4a, wav), hãy dùng script chuẩn hóa tự động:

```bash
# Script sẽ tự động:
# - Chuyển về đúng chuẩn Piper: 22050 Hz, 16-bit PCM Mono
# - Tự động cắt bỏ khoảng lặng (silence trimming) ở đầu và cuối file
venv/bin/python training/tts/prepare_dataset.py <thu_muc_audio_goc> ./dataset_ready <metadata_goc.csv>
```

Sau khi chạy xong, nén thư mục `dataset_ready` thành file `dataset.zip`.

---

## 🚀 4. Chạy Huấn Luyện Trên Google Colab (GPU T4 Miễn Phí)

> **Tại sao nên dùng Google Colab thay vì train trực tiếp trên laptop?**
> - Laptop của bạn có GPU RTX 3050 (4GB VRAM) đang phục vụ cho trợ lý ảo (Whisper + Ollama).
> - Google Colab cung cấp GPU T4 (16GB VRAM) hoàn toàn miễn phí, huấn luyện ổn định gấp 3 lần và không làm nóng máy tính cá nhân.

### Các bước thực hiện:
1. Mở [Google Colab](https://colab.research.google.com/).
2. Chọn **Upload Notebook** $\rightarrow$ Chọn tệp [`Fine_Tune_Piper_TTS_Vietnamese.ipynb`](./Fine_Tune_Piper_TTS_Vietnamese.ipynb).
3. Đảm bảo Runtime bật **T4 GPU** (*Runtime -> Change runtime type -> T4 GPU*).
4. Nhấn **Run All** (`Ctrl + F9`).
5. Tại **Bước 3**, tải tệp `dataset.zip` của bạn lên.
6. Quá trình huấn luyện diễn ra trong khoảng **1 - 1.5 giờ** (khoảng 1000 epochs).
7. Khi hoàn tất, Colab sẽ tự động xuất và tải về 2 file:
   - `vi_VN-custom_voice-medium.onnx`
   - `vi_VN-custom_voice-medium.onnx.json`

---

## 📥 5. Kích Hoạt Giọng Mới Vào Alexa

1. Đặt 2 file vừa tải về vào thư mục `models/piper/`:
   ```bash
   mv ~/Downloads/vi_VN-custom_voice-medium.onnx* /home/tu/Projects/python/voice-ai/models/piper/
   ```

2. Mở file [`src/ai_assistant/config.py`](../../src/ai_assistant/config.py) và cấu hình:
   ```python
   # Đổi đường dẫn sang model mới:
   PIPER_MODEL_PATH = "models/piper/vi_VN-custom_voice-medium.onnx"

   # Chọn chế độ phát:
   # "piper": Dùng 100% giọng offline mới tạo (siêu nhanh <90ms)
   # "hybrid": Ưu tiên Edge-TTS, mất mạng tự động chuyển sang Piper
   TTS_ENGINE = "piper"
   ```

3. Khởi động lại dịch vụ Alexa:
   ```bash
   systemctl --user restart alexa.service
   ```
