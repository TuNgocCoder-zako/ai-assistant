# Hướng Dẫn Huấn Luyện (Fine-tune) Trợ Lý Ảo Alexa Tiếng Việt với Google Colab

Thư mục này chứa đầy đủ tài liệu và công cụ để bạn tự huấn luyện mô hình **Llama 3.2 3B Instruct** học phong cách giao tiếp tiếng Việt tự nhiên, súc tích và thông minh nhất.

---

### 📁 Danh sách tệp trong thư mục:
1. [`dataset.json`](file:///home/tu/voice-ai/training/dataset.json): Tập dữ liệu 450 mẫu hội thoại chuẩn tiếng Việt đời thường, súc tích 1-2 câu.
2. [`generate_dataset.py`](file:///home/tu/voice-ai/training/generate_dataset.py): Script mở rộng hoặc bổ sung thêm dữ liệu hội thoại mới.
3. [`Train_Alexa_Llama3_2_Colab.ipynb`](file:///home/tu/voice-ai/training/Train_Alexa_Llama3_2_Colab.ipynb): Jupyter Notebook hoàn chỉnh để chạy huấn luyện trên Google Colab GPU T4 miễn phí.
4. [`Modelfile.template`](file:///home/tu/voice-ai/training/Modelfile.template): Mẫu cấu hình nạp mô hình sau khi train vào Ollama.

---

### 🚀 Quy trình thực hiện (Chỉ 3 bước):

#### Bước 1: Mở Notebook trên Google Colab
1. Truy cập [Google Colab](https://colab.research.google.com/).
2. Chọn **Upload (Tải lên)** -> Chọn tệp [`Train_Alexa_Llama3_2_Colab.ipynb`](file:///home/tu/voice-ai/training/Train_Alexa_Llama3_2_Colab.ipynb).
3. Đảm bảo môi trường Colab đang bật GPU: **Runtime (Thời lượng)** -> **Change runtime type (Đổi loại thời lượng)** -> Chọn **T4 GPU** -> Bấm **Save**.

#### Bước 2: Chạy huấn luyện
1. Bấm chạy từng ô lệnh từ trên xuống dưới (hoặc bấm `Ctrl + F9` để chạy tất cả).
2. Tại **Bước 3 (Upload dataset)**, Colab sẽ hiện nút chọn tệp: Hãy chọn tệp [`dataset.json`](file:///home/tu/voice-ai/training/dataset.json).
3. Quá trình huấn luyện chỉ mất khoảng **10 đến 15 phút**.
4. Khi chạy đến bước cuối cùng, Colab sẽ tự động xuất tệp `.gguf` (định dạng Q4_K_M ~1.9 GB) và tải về thư mục `Downloads` trên máy của bạn.

#### Bước 3: Nạp mô hình vào Ollama trên Arch Linux
Khi tệp `.gguf` đã tải về máy, chuyển file vào thư mục và chạy lệnh tạo model:

```bash
# Di chuyển file gguf vào thư mục training (ví dụ file tên alexa_vn.gguf)
mv ~/Downloads/*.gguf /home/tu/voice-ai/training/alexa-trained.gguf

# Đăng ký mô hình mới vào Docker Ollama
docker exec -it fb718d88864a ollama create alexa-vn-pro -f /tmp/Modelfile
```

Sau đó trong [`assistant.py`](file:///home/tu/voice-ai/assistant.py), bạn chỉ cần đổi tên mô hình:
```python
OLLAMA_MODEL = "alexa-vn-pro"
```
Mô hình sẽ chạy hoàn toàn trên GPU RTX 3050, phản xạ siêu nhanh và nói chuyện cực kỳ tự nhiên!
