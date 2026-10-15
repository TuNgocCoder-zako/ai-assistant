# 🎙️ Hướng Dẫn Fine-Tune Whisper Tiếng Việt Cho Voice AI Assistant

Tài liệu này hướng dẫn quy trình chuẩn để thu âm, huấn luyện bổ sung (Fine-Tuning qua LoRA PEFT) trên Google Colab GPU T4, và xuất mô hình về laptop Arch Linux chạy ngoại tuyến 100% với `faster-whisper`.

---

## I. Yêu Cầu Về Dữ Liệu Thu Âm (Data Requirements)

1. **Số lượng mẫu khuyến nghị**:
   - **Tối thiểu**: 200 – 300 mẫu (đảm bảo Whisper không bị Catastrophic Forgetting).
   - **Lý tưởng**: 500 – 1000 mẫu gồm:
     - Câu lệnh điều khiển hệ thống, media, cửa sổ, ứng dụng.
     - Câu hỏi kiến thức, giao tiếp thông thường.
     - Cả giọng đọc nhanh, chậm, nói thì thầm và khi có quạt gió laptop chạy nhẹ.
2. **Công cụ thu âm**:
   Chạy script đã được tối ưu sẵn:
   ```bash
   venv/bin/python training/whisper/record_dataset.py
   ```
   - Thời lượng mỗi mẫu: 3.5 giây (đủ cho các câu lệnh dài, tránh nuốt âm).
   - Script tự động chuẩn hóa tần số 16kHz Mono 16-bit PCM.
   - Dữ liệu được lưu tại `training/whisper/dataset/` kèm nhãn `metadata.jsonl`.
3. **Đóng gói dữ liệu**:
   ```bash
   cd training/whisper/dataset
   zip -r ../dataset.zip ./*
   cd ../..
   ```

---

## II. Huấn Luyện Trên Google Colab (LoRA PEFT)

1. Mở notebook: [FineTune_Whisper_Vietnamese_Colab.ipynb](file:///home/tu/Projects/python/voice-ai/training/whisper/FineTune_Whisper_Vietnamese_Colab.ipynb) trên Google Colab.
2. Chọn Runtime: **GPU T4** (Free tier).
3. Tải file `dataset.zip` lên thanh Files của Colab.
4. Chạy tuần tự các Cells:
   - **Giải nén & Tiền xử lý**: Trích xuất Mel-Spectrogram (80 bins) và mã hóa nhãn tiếng Việt với các token bắt buộc `<|startoftranscript|><|vi|><|transcribe|><|notimestamps|>`.
   - **LoRA Adapter**: Rank `r=16`, `lora_alpha=32`, gắn vào các lớp attention `["q_proj", "v_proj"]`.
   - **Huấn luyện**: 10 – 15 epochs, learning rate `1e-4`, FP16 mixed precision.
   - **Hợp nhất (Merge)**: Gọi `model.merge_and_unload()` để gộp trọng số LoRA vào mô hình gốc.

---

## III. Xuất Mô Hình Về Laptop (CTranslate2 int8_float16)

Sau khi huấn luyện xong trên Colab, cell cuối cùng sẽ tự động chuyển đổi mô hình sang định dạng tối ưu cho CTranslate2:
```bash
ct2-transformers-converter --model ./whisper-small-merged --output_dir ./whisper-small-vietnamese-ct2 --quantization int8_float16 --force
zip -r whisper-small-vietnamese-ct2.zip ./whisper-small-vietnamese-ct2
```

Tải file `whisper-small-vietnamese-ct2.zip` về máy tính của bạn và giải nén:
```bash
unzip whisper-small-vietnamese-ct2.zip -d ~/.local/share/voice-ai/models/
```

Cập nhật cấu hình trong [src/ai_assistant/config.py](file:///home/tu/Projects/python/voice-ai/src/ai_assistant/config.py):
```python
DEFAULT_STT_MODEL = os.path.expanduser("~/.local/share/voice-ai/models/whisper-small-vietnamese-ct2")
```

---

## IV. Phương Án Dự Phòng Không Cần Train Lại (Zero-Cost Optimization)

Mô hình gốc `whisper-small` đã có xác suất tiếng Việt rất mạnh. Để sửa lỗi nghe nhầm mà không cần tốn thời gian thu âm/train lại:
1. Thêm từ bạn hay nói vào `WHISPER_INITIAL_PROMPT` trong [config.py](file:///home/tu/Projects/python/voice-ai/src/ai_assistant/config.py).
2. Thêm dị âm vào `clean_user_input()` trong [nlu.py](file:///home/tu/Projects/python/voice-ai/src/ai_assistant/core/nlu.py).
