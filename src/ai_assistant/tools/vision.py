"""
Vision Module cho Local AI OS Agent (V2.3 — Screen Awareness).
Cung cấp khả năng "nhìn" cho agent thông qua chụp màn hình Wayland (grim)
và phân tích bằng vision model đa phương thức qua Ollama.
"""

import os
import base64
import logging
import subprocess
import requests
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    from io import BytesIO
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow chưa được cài đặt. Vision sẽ gửi ảnh nguyên bản (pip install Pillow).")

from ai_assistant.config import (
    OLLAMA_BASE_URL,
    DEFAULT_VISION_MODEL,
    VISION_TIMEOUT,
    VISION_MAX_IMAGE_SIZE,
    VISION_JPEG_QUALITY,
)
from ai_assistant.tools.registry import tool_registry

# Thư mục tạm cho ảnh chụp vision (không lưu vĩnh viễn)
VISION_TEMP_PATH = "/tmp/alexa_vision_capture.png"


# ── Hàm nội bộ ──────────────────────────────────────────────────────────

def _check_grim_available() -> bool:
    """Kiểm tra grim đã cài đặt (Wayland screen capture)."""
    try:
        result = subprocess.run(["which", "grim"], capture_output=True, timeout=3)
        return result.returncode == 0
    except Exception:
        return False


def _check_vision_model_available(model: str) -> bool:
    """Kiểm tra vision model đã được pull về Ollama chưa."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if r.status_code == 200:
            installed = {m.get("name", "") for m in r.json().get("models", [])}
            return model in installed or any(model.split(":")[0] in m for m in installed)
    except Exception:
        pass
    return False


def capture_screen_wayland(region: Optional[dict] = None) -> tuple[Optional[str], dict]:
    """
    Chụp màn hình Wayland bằng grim → resize → JPEG compress → base64.

    Args:
        region: {"x": int, "y": int, "width": int, "height": int} hoặc None (toàn màn hình)

    Returns:
        (base64_string | None, metadata_dict)
    """
    if not _check_grim_available():
        return None, {"error": "grim chưa được cài đặt. Cài bằng: pacman -S grim"}

    try:
        # Build grim command
        cmd = ["grim"]
        if region:
            geometry = f"{region['x']},{region['y']} {region['width']}x{region['height']}"
            cmd.extend(["-g", geometry])
        cmd.append(VISION_TEMP_PATH)

        # Thực thi grim (Wayland-native screen capture)
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode != 0:
            error = result.stderr.decode().strip()
            return None, {"error": f"grim thất bại: {error}"}

        if not os.path.exists(VISION_TEMP_PATH):
            return None, {"error": "grim không tạo được file ảnh"}

        # Đọc và xử lý ảnh qua Pillow
        if PIL_AVAILABLE:
            img = Image.open(VISION_TEMP_PATH)
            original_size = img.size

            # Resize giữ tỷ lệ nếu ảnh quá lớn
            w, h = img.size
            max_dim = VISION_MAX_IMAGE_SIZE
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            # Compress → JPEG → base64 (nhẹ hơn PNG ~5-10 lần)
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=VISION_JPEG_QUALITY)
            img_bytes = buffer.getvalue()
            b64 = base64.b64encode(img_bytes).decode("utf-8")

            metadata = {
                "original_size": f"{original_size[0]}x{original_size[1]}",
                "processed_size": f"{img.size[0]}x{img.size[1]}",
                "file_size_kb": round(len(img_bytes) / 1024, 1),
                "source": "wayland/grim",
            }
        else:
            # Fallback: đọc raw PNG → base64 (không resize)
            with open(VISION_TEMP_PATH, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            metadata = {
                "file_size_kb": round(len(img_bytes) / 1024, 1),
                "source": "wayland/grim",
                "note": "Ảnh chưa được resize (cài Pillow để tối ưu: pip install Pillow)",
            }

        return b64, metadata

    except subprocess.TimeoutExpired:
        return None, {"error": "grim timeout (>5s) — có thể Wayland compositor chưa sẵn sàng"}
    except Exception as e:
        logger.error(f"Screen capture failed: {e}")
        return None, {"error": str(e)}
    finally:
        # Dọn file tạm
        try:
            if os.path.exists(VISION_TEMP_PATH):
                os.remove(VISION_TEMP_PATH)
        except OSError:
            pass


def analyze_with_vision_model(image_base64: str,
                               query: str,
                               model: str = DEFAULT_VISION_MODEL) -> str:
    """
    Gửi ảnh + câu hỏi đến vision model qua Ollama API.

    Args:
        image_base64: Ảnh đã encode base64 (JPEG)
        query: Câu hỏi / yêu cầu phân tích
        model: Tên vision model trong Ollama

    Returns:
        Mô tả / phân tích từ vision model (text)
    """
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": query,
                    "images": [image_base64]
                }],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 512,
                }
            },
            timeout=VISION_TIMEOUT
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
    except requests.exceptions.Timeout:
        return "[Vision timeout] Vision model không phản hồi trong thời gian cho phép. Thử model nhẹ hơn (moondream2)."
    except requests.exceptions.ConnectionError:
        return "[Vision error] Không kết nối được Ollama. Kiểm tra Ollama server đã chạy."
    except Exception as e:
        logger.error(f"Vision model call failed: {e}")
        return f"[Vision error] {str(e)}"


# ── Tool đăng ký vào Registry ────────────────────────────────────────────

@tool_registry.register(
    name="see_screen",
    description="Chụp và phân tích màn hình hiện tại bằng AI Vision đa phương thức. Sử dụng khi cần biết nội dung đang hiển thị, đọc chữ trên màn hình, nhận diện ứng dụng đang mở, hoặc hiểu trạng thái giao diện."
)
def see_screen(query: str, region: str = "") -> dict:
    """Chụp màn hình Wayland (grim) và phân tích bằng vision model qua Ollama.

    Args:
        query: Câu hỏi về nội dung màn hình (VD: "đang mở gì", "có lỗi gì", "đọc nội dung")
        region: Vùng cần xem dạng "x,y widthxheight" (VD: "0,0 960x540"). Để trống = toàn bộ màn hình.
    """
    # Kiểm tra vision model
    vision_model = DEFAULT_VISION_MODEL
    if not _check_vision_model_available(vision_model):
        return {
            "success": False,
            "error": f"Vision model '{vision_model}' chưa được cài đặt. "
                     f"Chạy: ollama pull {vision_model}"
        }

    # Parse region nếu có
    parsed_region = None
    if region:
        try:
            parts = region.replace(",", " ").replace("x", " ").split()
            if len(parts) == 4:
                parsed_region = {
                    "x": int(parts[0]), "y": int(parts[1]),
                    "width": int(parts[2]), "height": int(parts[3])
                }
        except (ValueError, IndexError):
            return {
                "success": False,
                "error": f"Region không hợp lệ: '{region}'. Định dạng đúng: 'x,y widthxheight' (VD: '0,0 960x540')"
            }

    # 1. Capture
    b64, meta = capture_screen_wayland(region=parsed_region)
    if b64 is None:
        return {"success": False, "error": f"Không thể chụp màn hình: {meta.get('error', 'unknown')}"}

    # 2. Xây dựng prompt cho vision model
    enriched_query = (
        f"Bạn đang nhìn vào screenshot màn hình máy tính Arch Linux / Hyprland. "
        f"Kích thước ảnh: {meta.get('processed_size', meta.get('file_size_kb', '?'))}. "
        f"\n\nYêu cầu phân tích: {query}"
        f"\n\nHãy mô tả chính xác, đi thẳng vào trọng tâm. Trả lời bằng tiếng Việt."
    )

    # 3. Analyze bằng vision model
    print(f"👁️ [Vision] Đang phân tích màn hình bằng {vision_model}...")
    description = analyze_with_vision_model(b64, enriched_query, model=vision_model)

    # 4. Return observation cho Agent Core
    return {
        "success": True,
        "result": description,
        "metadata": meta
    }
