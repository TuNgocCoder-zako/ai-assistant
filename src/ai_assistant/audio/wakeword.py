"""
Tích hợp mô hình nhận diện từ khóa đánh thức (openWakeWord).
"""

import openwakeword
from openwakeword.model import Model

def load_wakeword_model(wake_mode: str = "alexa") -> tuple[Model, str]:
    """Khởi tạo mô hình openWakeWord theo chế độ được chọn."""
    if wake_mode == "alexa":
        model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "alexa" in p]
        wake_word_label = "Alexa"
    elif wake_mode == "jarvis":
        model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p]
        wake_word_label = "Hey Jarvis"
    else:
        model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p or "alexa" in p]
        wake_word_label = "Alexa hoặc Hey Jarvis"

    oww_model = Model(wakeword_model_paths=model_paths)
    return oww_model, wake_word_label
