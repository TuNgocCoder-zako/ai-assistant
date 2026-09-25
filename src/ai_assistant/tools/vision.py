"""
Vision Module cho Local AI OS Agent (V2.3 — Screen Awareness & Multimodal AI).
Cung cấp khả năng "nhìn" đa phương thức:
1. see_screen: Chụp màn hình Wayland (grim) và phân tích tức thì bằng Vision Model (Ollama).
2. capture_screen: Chụp màn hình lưu thành file trên đĩa cứng (không tốn VRAM LLM).
3. analyze_image: Phân tích file ảnh bất kỳ có sẵn trên máy tính.
4. watch_camera: Chụp ảnh từ webcam (OpenCV / ffmpeg) và phân tích qua Vision Model.
Hỗ trợ: Wayland/Hyprland native, Image Caching (MD5 hash + TTL), Hyprland active window region, Slurp interactive.
"""

import os
import time
import base64
import hashlib
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

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV chưa được cài đặt. Chụp webcam sẽ dùng fallback ffmpeg (pip install opencv-python-headless).")

from ai_assistant.config import (
    OLLAMA_BASE_URL,
    DEFAULT_VISION_MODEL,
    VISION_TIMEOUT,
    VISION_MAX_IMAGE_SIZE,
    VISION_JPEG_QUALITY,
    WEBCAM_DEVICE_INDEX,
    WEBCAM_CAPTURE_WIDTH,
    WEBCAM_CAPTURE_HEIGHT,
    VISION_CACHE_TTL_SEC,
    SCREENSHOTS_DIR,
)
from ai_assistant.tools.registry import tool_registry

# Thư mục tạm cho ảnh chụp vision
VISION_TEMP_PATH = "/tmp/alexa_vision_capture.png"
WEBCAM_TEMP_PATH = "/tmp/alexa_webcam_capture.jpg"

# Bộ nhớ đệm quan sát thị giác (Image Caching): hash(img) + query -> (timestamp, result)
_vision_cache: dict[str, tuple[float, str]] = {}


# ── Hàm nội bộ & Tiện ích ──────────────────────────────────────────────

def _check_grim_available() -> bool:
    """Kiểm tra grim đã cài đặt (Wayland screen capture)."""
    try:
        result = subprocess.run(["which", "grim"], capture_output=True, timeout=3)
        return result.returncode == 0
    except Exception:
        return False


def _check_vision_model_available(model: str = DEFAULT_VISION_MODEL) -> bool:
    """Kiểm tra vision model đã được pull về Ollama chưa."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if r.status_code == 200:
            installed = {m.get("name", "") for m in r.json().get("models", [])}
            return model in installed or any(model.split(":")[0] in m for m in installed)
    except Exception:
        pass
    return False


def _parse_region(region: str) -> Optional[dict]:
    """
    Phân tích chuỗi region thành dict {x, y, width, height}.
    Hỗ trợ:
    - Tọa độ chuẩn: "0,0 960x540", "0 0 960 540", "0,0,960,540"
    - "active" / "current": Cửa sổ đang kích hoạt trên Hyprland (hyprctl activewindow -j)
    - "slurp" / "interactive": Kéo chuột chọn vùng tương tác trên Wayland
    """
    if not region:
        return None
    r = region.strip().lower()

    # 1. Hyprland active window native detection
    if r in ["active", "current", "cửa sổ", "cua so"]:
        try:
            res = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                import json
                data = json.loads(res.stdout)
                at = data.get("at", [0, 0])
                size = data.get("size", [0, 0])
                if size[0] > 0 and size[1] > 0:
                    return {"x": int(at[0]), "y": int(at[1]), "width": int(size[0]), "height": int(size[1])}
        except Exception as e:
            logger.warning(f"Không thể lấy active window từ Hyprland: {e}")

    # 2. Slurp interactive region selection
    if r in ["slurp", "interactive", "chọn vùng", "chon vung"]:
        try:
            res = subprocess.run(["slurp"], capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                r = res.stdout.strip()
        except Exception as e:
            logger.warning(f"Lỗi khi chạy slurp: {e}")

    # 3. Tọa độ số học
    parts = r.replace(",", " ").replace("x", " ").split()
    if len(parts) == 4:
        try:
            return {
                "x": int(parts[0]),
                "y": int(parts[1]),
                "width": int(parts[2]),
                "height": int(parts[3])
            }
        except ValueError:
            pass

    raise ValueError(f"Region không hợp lệ: '{region}'. Định dạng đúng: 'x,y widthxheight' (VD: '0,0 960x540'), 'active', hoặc 'slurp'.")


def _get_cached_analysis(image_hash: str, query: str) -> Optional[str]:
    """Kiểm tra bộ đệm quan sát hình ảnh để tránh gọi Ollama trùng lặp."""
    cache_key = f"{image_hash}:{query.strip().lower()}"
    if cache_key in _vision_cache:
        timestamp, cached_desc = _vision_cache[cache_key]
        if time.time() - timestamp < VISION_CACHE_TTL_SEC:
            logger.info("⚡ [Vision Cache] Tái sử dụng kết quả phân tích trong bộ nhớ đệm (P99 < 1ms)")
            return cached_desc
    return None


def _store_cached_analysis(image_hash: str, query: str, description: str):
    """Lưu kết quả phân tích vào bộ nhớ đệm."""
    cache_key = f"{image_hash}:{query.strip().lower()}"
    _vision_cache[cache_key] = (time.time(), description)


# ── Xử lý Capture Màn hình & Webcam ─────────────────────────────────────

def capture_screen_wayland(region: Optional[dict] = None, output_path: Optional[str] = None) -> tuple[Optional[str], dict]:
    """
    Chụp màn hình Wayland bằng grim → resize Pillow → JPEG compress → base64.

    Args:
        region: {"x": int, "y": int, "width": int, "height": int} hoặc None (toàn màn hình)
        output_path: Đường dẫn lưu ảnh nếu muốn lưu vĩnh viễn (hoặc None để dùng file tạm)

    Returns:
        (base64_string | None, metadata_dict)
    """
    if not _check_grim_available():
        return None, {"error": "grim chưa được cài đặt. Cài bằng: sudo pacman -S grim"}

    target_file = output_path or VISION_TEMP_PATH

    try:
        # Xây dựng lệnh grim
        cmd = ["grim"]
        if region:
            geometry = f"{region['x']},{region['y']} {region['width']}x{region['height']}"
            cmd.extend(["-g", geometry])
        cmd.append(target_file)

        # Thực thi grim (Wayland-native wlr-screencopy)
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode != 0:
            error = result.stderr.decode().strip()
            return None, {"error": f"grim thất bại: {error}"}

        if not os.path.exists(target_file):
            return None, {"error": "grim không tạo được file ảnh"}

        # Đọc và xử lý ảnh
        if PIL_AVAILABLE:
            img = Image.open(target_file)
            original_size = img.size

            # Resize giữ tỷ lệ nếu vượt ngưỡng cấu hình
            w, h = img.size
            max_dim = VISION_MAX_IMAGE_SIZE
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            # Compress → JPEG → base64
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=VISION_JPEG_QUALITY)
            img_bytes = buffer.getvalue()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            img_hash = hashlib.md5(img_bytes).hexdigest()

            metadata = {
                "original_size": f"{original_size[0]}x{original_size[1]}",
                "processed_size": f"{img.size[0]}x{img.size[1]}",
                "file_size_kb": round(len(img_bytes) / 1024, 1),
                "image_hash": img_hash,
                "source": "wayland/grim",
            }
        else:
            with open(target_file, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            img_hash = hashlib.md5(img_bytes).hexdigest()
            metadata = {
                "file_size_kb": round(len(img_bytes) / 1024, 1),
                "image_hash": img_hash,
                "source": "wayland/grim",
                "note": "Ảnh chưa được resize (cài Pillow: pip install Pillow)",
            }

        if output_path:
            metadata["file_path"] = output_path

        return b64, metadata

    except subprocess.TimeoutExpired:
        return None, {"error": "grim timeout (>5s) — có thể Wayland compositor chưa sẵn sàng"}
    except Exception as e:
        logger.error(f"Screen capture failed: {e}")
        return None, {"error": str(e)}
    finally:
        # Dọn file tạm nếu không chỉ định output_path
        if not output_path:
            try:
                if os.path.exists(VISION_TEMP_PATH):
                    os.remove(VISION_TEMP_PATH)
            except OSError:
                pass


def capture_webcam_frame(device_index: int = WEBCAM_DEVICE_INDEX) -> tuple[Optional[str], dict]:
    """
    Chụp một khung hình từ webcam (/dev/videoN) → resize → JPEG compress → base64.
    Ưu tiên OpenCV (cv2), tự động fallback sang ffmpeg nếu thiết bị bận hoặc chưa có cv2.
    """
    # 1. Thử dùng OpenCV
    if CV2_AVAILABLE:
        try:
            cap = cv2.VideoCapture(device_index)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    # Resize về kích thước tiêu chuẩn webcam
                    h, w = frame.shape[:2]
                    target_w, target_h = WEBCAM_CAPTURE_WIDTH, WEBCAM_CAPTURE_HEIGHT
                    resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

                    # Encode JPEG
                    success, enc_buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), VISION_JPEG_QUALITY])
                    if success:
                        img_bytes = enc_buf.tobytes()
                        b64 = base64.b64encode(img_bytes).decode("utf-8")
                        img_hash = hashlib.md5(img_bytes).hexdigest()
                        return b64, {
                            "original_size": f"{w}x{h}",
                            "processed_size": f"{target_w}x{target_h}",
                            "file_size_kb": round(len(img_bytes) / 1024, 1),
                            "image_hash": img_hash,
                            "source": f"webcam/cv2 (/dev/video{device_index})",
                        }
        except Exception as e:
            logger.warning(f"OpenCV capture failed, trying ffmpeg fallback: {e}")

    # 2. Fallback sang ffmpeg (v4l2 native capture)
    video_dev = f"/dev/video{device_index}"
    if not os.path.exists(video_dev):
        return None, {"error": f"Không tìm thấy thiết bị webcam tại {video_dev}. Hãy kiểm tra kết nối camera."}

    try:
        cmd = [
            "ffmpeg", "-y", "-f", "v4l2",
            "-video_size", f"{WEBCAM_CAPTURE_WIDTH}x{WEBCAM_CAPTURE_HEIGHT}",
            "-i", video_dev,
            "-frames:v", "1",
            WEBCAM_TEMP_PATH
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=5)
        if res.returncode == 0 and os.path.exists(WEBCAM_TEMP_PATH):
            with open(WEBCAM_TEMP_PATH, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            img_hash = hashlib.md5(img_bytes).hexdigest()
            return b64, {
                "processed_size": f"{WEBCAM_CAPTURE_WIDTH}x{WEBCAM_CAPTURE_HEIGHT}",
                "file_size_kb": round(len(img_bytes) / 1024, 1),
                "image_hash": img_hash,
                "source": f"webcam/ffmpeg ({video_dev})",
            }
        else:
            return None, {"error": f"ffmpeg không thể chụp từ {video_dev}: {res.stderr.decode()[:150]}"}
    except Exception as e:
        return None, {"error": f"Lỗi chụp webcam: {e}"}
    finally:
        try:
            if os.path.exists(WEBCAM_TEMP_PATH):
                os.remove(WEBCAM_TEMP_PATH)
        except OSError:
            pass


def analyze_with_vision_model(
    image_base64: str,
    query: str,
    model: str = DEFAULT_VISION_MODEL
) -> str:
    """
    Gửi ảnh + câu hỏi đến vision model qua Ollama API.

    Args:
        image_base64: Chuỗi base64 của ảnh (JPEG)
        query: Câu hỏi / yêu cầu phân tích
        model: Tên vision model trong Ollama
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


# ── Đăng ký 4 Tools Vision vào Registry (Hybrid Architecture) ───────────

@tool_registry.register(
    name="see_screen",
    description="Chụp và phân tích màn hình hiện tại bằng AI Vision đa phương thức. Sử dụng khi người dùng hỏi về những gì đang hiển thị trên màn hình, đọc văn bản, tìm lỗi hoặc hiểu trạng thái cửa sổ ứng dụng."
)
def see_screen(query: str, region: str = "") -> dict:
    """Chụp màn hình Wayland (grim) và phân tích bằng vision model qua Ollama.

    Args:
        query: Câu hỏi về nội dung màn hình (VD: 'đang mở gì', 'có lỗi gì', 'đọc nội dung')
        region: Vùng cần xem dạng 'x,y widthxheight' (VD: '0,0 960x540'), 'active' (cửa sổ hiện tại), hoặc 'slurp' (chọn chuột). Để trống = toàn màn hình.
    """
    vision_model = DEFAULT_VISION_MODEL
    if not _check_vision_model_available(vision_model):
        return {
            "success": False,
            "error": f"Vision model '{vision_model}' chưa được cài đặt. "
                     f"Chạy: ollama pull {vision_model}"
        }

    # 1. Parse region nếu có
    parsed_region = None
    if region:
        try:
            parsed_region = _parse_region(region)
        except ValueError as ve:
            return {"success": False, "error": str(ve)}

    # 2. Capture màn hình
    b64, meta = capture_screen_wayland(region=parsed_region)
    if b64 is None:
        return {"success": False, "error": f"Không thể chụp màn hình: {meta.get('error', 'unknown')}"}

    img_hash = meta.get("image_hash", "")

    # 3. Kiểm tra Image Cache
    cached_res = _get_cached_analysis(img_hash, query)
    if cached_res:
        return {
            "success": True,
            "result": cached_res,
            "metadata": {**meta, "cached": True}
        }

    # 4. Enrich query
    enriched_query = (
        f"Bạn đang nhìn vào screenshot màn hình máy tính Arch Linux / Hyprland. "
        f"Kích thước ảnh: {meta.get('processed_size', meta.get('file_size_kb', '?'))}. "
        f"\n\nYêu cầu phân tích: {query}"
        f"\n\nHãy mô tả chính xác, đi thẳng vào trọng tâm. Trả lời bằng tiếng Việt."
    )

    # 5. Phân tích qua Vision Model
    print(f"👁️ [Vision] Đang phân tích màn hình bằng {vision_model}...")
    description = analyze_with_vision_model(b64, enriched_query, model=vision_model)

    # 6. Lưu vào cache
    _store_cached_analysis(img_hash, query, description)

    return {
        "success": True,
        "result": description,
        "metadata": meta
    }


@tool_registry.register(
    name="capture_screen",
    description="Chụp màn hình máy tính và lưu thành file ảnh trên đĩa cứng (không phân tích). Sử dụng khi người dùng muốn lưu ảnh màn hình vào file, hoặc khi quy trình đa bước cần lưu ảnh chụp để tham chiếu sau này."
)
def capture_screen(save_path: str = "", region: str = "") -> dict:
    """Chụp màn hình và lưu file trực tiếp trên đĩa cứng.

    Args:
        save_path: Đường dẫn tệp cần lưu (VD: '/home/user/Pictures/shot.png'). Để trống sẽ tự lưu vào ~/Pictures/Screenshots/
        region: Vùng cần chụp ('x,y widthxheight', 'active', 'slurp'). Để trống = toàn màn hình.
    """
    if not save_path:
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        t_str = time.strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(SCREENSHOTS_DIR, f"screenshot_{t_str}.png")
    else:
        save_path = os.path.expanduser(save_path)
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

    parsed_region = None
    if region:
        try:
            parsed_region = _parse_region(region)
        except ValueError as ve:
            return {"success": False, "error": str(ve)}

    _, meta = capture_screen_wayland(region=parsed_region, output_path=save_path)
    if "error" in meta:
        return {"success": False, "error": meta["error"]}

    print(f"📸 [Vision] Đã lưu ảnh chụp màn hình tại: {save_path}")
    return {
        "success": True,
        "file_path": save_path,
        "metadata": meta
    }


@tool_registry.register(
    name="analyze_image",
    description="Phân tích nội dung của một tệp ảnh đã có sẵn trên đĩa cứng bằng AI Vision. Hỗ trợ đọc chữ trong ảnh, nhận dạng giao diện, phát hiện đối tượng hoặc giải thích sơ đồ, biểu đồ."
)
def analyze_image(image_path: str, query: str = "Mô tả chi tiết nội dung bức ảnh này") -> dict:
    """Đọc tệp ảnh từ đĩa cứng và phân tích bằng Vision Model.

    Args:
        image_path: Đường dẫn tuyệt đối hoặc tương đối tới tệp ảnh trên đĩa (PNG, JPG, JPEG, WEBP).
        query: Câu hỏi hoặc yêu cầu cụ thể về bức ảnh.
    """
    vision_model = DEFAULT_VISION_MODEL
    if not _check_vision_model_available(vision_model):
        return {
            "success": False,
            "error": f"Vision model '{vision_model}' chưa được cài đặt. "
                     f"Chạy: ollama pull {vision_model}"
        }

    real_path = os.path.realpath(os.path.expanduser(image_path))
    if not os.path.exists(real_path):
        return {"success": False, "error": f"Tệp ảnh không tồn tại: '{image_path}'"}

    try:
        if PIL_AVAILABLE:
            img = Image.open(real_path)
            orig_size = img.size
            w, h = orig_size
            max_dim = VISION_MAX_IMAGE_SIZE
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=VISION_JPEG_QUALITY)
            img_bytes = buffer.getvalue()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            meta = {
                "file_path": real_path,
                "original_size": f"{orig_size[0]}x{orig_size[1]}",
                "processed_size": f"{img.size[0]}x{img.size[1]}",
                "file_size_kb": round(len(img_bytes) / 1024, 1),
            }
        else:
            with open(real_path, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            meta = {
                "file_path": real_path,
                "file_size_kb": round(len(img_bytes) / 1024, 1),
            }

        img_hash = hashlib.md5(img_bytes).hexdigest()
        cached = _get_cached_analysis(img_hash, query)
        if cached:
            return {"success": True, "result": cached, "metadata": {**meta, "cached": True}}

        enriched_query = f"Phân tích bức ảnh đính kèm: {query}. Hãy trả lời súc tích bằng tiếng Việt."
        description = analyze_with_vision_model(b64, enriched_query, model=vision_model)
        _store_cached_analysis(img_hash, query, description)

        return {"success": True, "result": description, "metadata": meta}

    except Exception as e:
        return {"success": False, "error": f"Không thể xử lý tệp ảnh '{image_path}': {e}"}


@tool_registry.register(
    name="watch_camera",
    description="Chụp ảnh từ webcam máy tính và phân tích bằng AI Vision. Sử dụng khi người dùng yêu cầu quan sát không gian bên ngoài, nhận diện người hoặc vật trước máy tính."
)
def watch_camera(query: str = "Bạn nhìn thấy gì qua webcam?", device_index: int = WEBCAM_DEVICE_INDEX) -> dict:
    """Chụp khung hình từ webcam và gửi tới Vision Model.

    Args:
        query: Câu hỏi về những gì đang thấy qua camera.
        device_index: Số thứ tự thiết bị webcam (mặc định 0 cho /dev/video0).
    """
    vision_model = DEFAULT_VISION_MODEL
    if not _check_vision_model_available(vision_model):
        return {
            "success": False,
            "error": f"Vision model '{vision_model}' chưa được cài đặt. "
                     f"Chạy: ollama pull {vision_model}"
        }

    b64, meta = capture_webcam_frame(device_index=device_index)
    if b64 is None:
        return {"success": False, "error": f"Không thể chụp từ webcam: {meta.get('error', 'unknown')}"}

    enriched_query = (
        f"Bạn đang nhìn vào hình ảnh chụp từ webcam laptop của người dùng. "
        f"Yêu cầu: {query}. "
        f"Hãy quan sát và mô tả tự nhiên, thân thiện bằng tiếng Việt."
    )

    print(f"📹 [Webcam] Đang phân tích camera bằng {vision_model}...")
    description = analyze_with_vision_model(b64, enriched_query, model=vision_model)

    return {
        "success": True,
        "result": description,
        "metadata": meta
    }
