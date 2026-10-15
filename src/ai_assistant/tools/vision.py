"""
Vision Module cho Local AI OS Agent (Chế độ 3B — chỉ giữ capture_screen).
Cung cấp khả năng chụp màn hình Wayland lưu thành file trên đĩa cứng (không tốn VRAM LLM).
"""

import os
import time
import base64
import hashlib
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    from io import BytesIO
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow chưa được cài đặt. Ảnh sẽ lưu nguyên bản (pip install Pillow).")

from ai_assistant.config import (
    VISION_MAX_IMAGE_SIZE,
    VISION_JPEG_QUALITY,
    SCREENSHOTS_DIR,
)
from ai_assistant.tools.registry import tool_registry

# Thư mục tạm cho ảnh chụp
VISION_TEMP_PATH = "/tmp/alexa_vision_capture.png"


def _check_grim_available() -> bool:
    """Kiểm tra grim đã cài đặt (Wayland screen capture)."""
    try:
        result = subprocess.run(["which", "grim"], capture_output=True, timeout=3)
        return result.returncode == 0
    except Exception:
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
