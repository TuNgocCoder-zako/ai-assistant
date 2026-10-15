# 🎙️ Hướng Dẫn Thu Âm Dữ Liệu & Huấn Luyện Wake Word Cá Nhân

Thư mục này chứa công cụ và tài liệu giúp bạn thu âm giọng nói cá nhân của chính mình và huấn luyện mô hình chống kích hoạt nhầm (False Positives) trên Google Colab.

---

## 1. Chuẩn Bị Dữ Liệu Bằng Kịch Bản Tự Động

Dự án cung cấp kịch bản [record_samples.py](file:///home/tu/Projects/python/voice-ai/training/wakeword/record_samples.py) giúp bạn thu âm theo chuẩn âm thanh 16kHz Mono:

### Bước 1: Thu âm mẫu giọng bạn gọi "Alexa" (Positive Samples)
Thu âm khoảng 30 - 50 mẫu với các ngữ điệu, âm lượng và khoảng cách khác nhau:
```bash
venv/bin/python training/wakeword/record_samples.py --type positive --count 30
```
- Các file sẽ được lưu tại: `training/wakeword/dataset/positive/`

### Bước 2: Thu âm mẫu âm nhạc và tạp âm (Negative Samples)
Bật nhạc Spotify hoặc YouTube to vừa phải, hoặc gõ phím, rồi chạy lệnh:
```bash
venv/bin/python training/wakeword/record_samples.py --type negative --count 50
```
- Các file sẽ được lưu tại: `training/wakeword/dataset/negative/`

### Bước 3: Nén dữ liệu để tải lên Google Colab
```bash
cd training/wakeword
tar -czvf dataset_wakeword.tar.gz dataset/
```

---

## 2. Huấn Luyện Trên Google Colab

1. Mở trình duyệt truy cập: [https://colab.research.google.com/](https://colab.research.google.com/)
2. Tạo một Notebook mới (Khuyên dùng GPU T4 miễn phí).
3. Tải file `dataset_wakeword.tar.gz` lên Colab và giải nén:
   ```bash
   !tar -xzvf dataset_wakeword.tar.gz
   ```
4. Sao chép và chạy các đoạn mã huấn luyện từ tài liệu chi tiết:
   - Đọc hướng dẫn đầy đủ tại: [docs/WAKEWORD_UPGRADE_GUIDE.md](file:///home/tu/Projects/python/voice-ai/docs/WAKEWORD_UPGRADE_GUIDE.md)
5. Quá trình huấn luyện Verifier sẽ xuất ra file `alexa_verifier.pkl` (kích thước chỉ vài chục KB).

---

## 3. Triển Khai Mô Hình Đã Huấn Luyện Vào Hệ Thống

Khi tải file `alexa_verifier.pkl` về máy:
```bash
mkdir -p /home/tu/Projects/python/voice-ai/models/wakeword/
mv ~/Downloads/alexa_verifier.pkl /home/tu/Projects/python/voice-ai/models/wakeword/
```

Hệ thống `ai_assistant` sẽ **tự động phát hiện** file này khi khởi động và kích hoạt tầng kiểm duyệt Verifier thứ cấp.

Khởi động lại dịch vụ:
```bash
systemctl --user restart alexa.service
```
Kiểm tra log:
```bash
journalctl --user -u alexa.service -n 20 --no-pager
```
Bạn sẽ thấy thông báo:
```text
🎯 [WakeWord] Đã kích hoạt bộ lọc thứ cấp Verifier: alexa_verifier.pkl
```
