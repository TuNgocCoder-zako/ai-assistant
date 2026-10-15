"""
Tích hợp mô hình nhận diện từ khóa đánh thức (openWakeWord).
"""

import os
import glob
import pickle
import openwakeword
from openwakeword.model import Model
from ai_assistant.config import WAKE_VAD_THRESHOLD

def load_wakeword_model(wake_mode: str = "alexa", vad_threshold: float = None) -> tuple[Model, str]:
    """Khởi tạo mô hình openWakeWord theo chế độ được chọn với bộ lọc Silero VAD chống kích hoạt nhầm."""
    custom_model_dir = os.path.expanduser("~/Projects/python/voice-ai/models/wakeword")
    custom_models = glob.glob(os.path.join(custom_model_dir, "*.onnx"))

    if custom_models:
        model_paths = custom_models
        wake_word_label = "Mô hình tùy chỉnh (Custom ONNX)"
    elif wake_mode == "alexa":
        model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "alexa" in p]
        wake_word_label = "Alexa"
    elif wake_mode == "jarvis":
        model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p]
        wake_word_label = "Hey Jarvis"
    else:
        model_paths = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p or "alexa" in p]
        wake_word_label = "Alexa hoặc Hey Jarvis"

    effective_vad = WAKE_VAD_THRESHOLD if vad_threshold is None else vad_threshold
    oww_model = Model(wakeword_model_paths=model_paths, vad_threshold=effective_vad)

    # Tự động nạp bộ lọc Verifier nhị phân nếu người dùng đã train trên Colab
    verifier_path = os.path.join(custom_model_dir, "alexa_verifier.pkl")
    if os.path.exists(verifier_path):
        try:
            with open(verifier_path, "rb") as f:
                raw_verifier = pickle.load(f)

            class VerifierAdapter:
                def __init__(self, model):
                    self.model = model
                def predict_proba(self, X):
                    if hasattr(X, "ndim") and X.ndim > 2:
                        X = X.reshape(X.shape[0], -1)
                    return self.model.predict_proba(X)
                def __getattr__(self, name):
                    return getattr(self.model, name)

            verifier = VerifierAdapter(raw_verifier)
            model_key = list(oww_model.models.keys())[0]
            oww_model.custom_verifier_models = {model_key: verifier}
            oww_model.custom_verifier_threshold = 0.40
            print(f"🎯 [WakeWord] Đã kích hoạt bộ lọc thứ cấp Verifier: {os.path.basename(verifier_path)}")
        except Exception as e:
            print(f"⚠️ [WakeWord] Không thể nạp verifier model: {e}")

    return oww_model, wake_word_label
