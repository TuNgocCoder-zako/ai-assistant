"""
Trình quản lý Hẹn giờ & Báo thức bền bỉ (Timer & Alarm Manager).
"""

import os
import time
import json
import datetime
import threading
from ai_assistant.config import TIMERS_FILE, DEFAULT_VOICE
from ai_assistant.core.state import get_assistant_state
from ai_assistant.speech.player import play_chime

class TimerAlarmManager:
    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice
        self.timers = []
        self.lock = threading.Lock()
        self._load()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def _load(self):
        if os.path.exists(TIMERS_FILE):
            try:
                with open(TIMERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    now = time.time()
                    self.timers = [t for t in data.get("items", []) if t.get("target_time", 0) > now]
            except Exception:
                self.timers = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(TIMERS_FILE), exist_ok=True)
            with open(TIMERS_FILE, "w", encoding="utf-8") as f:
                json.dump({"items": self.timers}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_timer(self, minutes: float, label: str = "") -> str:
        seconds = int(minutes * 60)
        if seconds <= 0:
            return "Thời gian hẹn giờ không hợp lệ."
        target_time = time.time() + seconds
        timer_id = f"timer_{int(target_time)}"
        with self.lock:
            self.timers.append({
                "id": timer_id,
                "type": "timer",
                "target_time": target_time,
                "duration_sec": seconds,
                "label": label.strip()
            })
            self._save()

        play_chime("ack")
        mins_val = int(minutes) if minutes >= 1 else f"{int(seconds)} giây"
        unit = "phút" if minutes >= 1 else ""
        label_text = f" cho {label}" if label else ""
        return f"Đã đặt hẹn giờ {mins_val} {unit}{label_text} cho bạn rồi nhé."

    def add_alarm(self, hour: int, minute: int, label: str = "") -> str:
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return "Giờ báo thức không hợp lệ."
        now = datetime.datetime.now()
        target_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_dt <= now:
            target_dt += datetime.timedelta(days=1)

        target_time = target_dt.timestamp()
        alarm_id = f"alarm_{int(target_time)}"
        with self.lock:
            self.timers.append({
                "id": alarm_id,
                "type": "alarm",
                "target_time": target_time,
                "duration_sec": 0,
                "label": label.strip()
            })
            self._save()

        play_chime("ack")
        time_display = f"{hour} giờ" + (f" {minute} phút" if minute > 0 else "")
        day_text = "ngày mai" if target_dt.date() > now.date() else "hôm nay"
        label_text = f" cho {label}" if label else ""
        return f"Đã đặt báo thức lúc {time_display} {day_text}{label_text} cho bạn nhé."

    def check_timers(self) -> str:
        now = time.time()
        with self.lock:
            active = [t for t in self.timers if t["target_time"] > now]
        if not active:
            return "Hiện tại bạn không có hẹn giờ hay báo thức nào đang chạy."

        parts = []
        for item in active:
            rem = int(item["target_time"] - now)
            rem_m = rem // 60
            rem_s = rem % 60
            if item["type"] == "timer":
                time_str = f"{rem_m} phút {rem_s} giây" if rem_m > 0 else f"{rem_s} giây"
                label_str = f" {item['label']}" if item['label'] else ""
                parts.append(f"Hẹn giờ{label_str} còn {time_str}")
            else:
                target_dt = datetime.datetime.fromtimestamp(item["target_time"])
                parts.append(f"Báo thức lúc {target_dt.hour} giờ {target_dt.minute} phút")

        return "Hiện có: " + ", ".join(parts) + "."

    def cancel_all(self) -> str:
        with self.lock:
            count = len(self.timers)
            self.timers = []
            self._save()
        play_chime("ack")
        if count == 0:
            return "Hiện tại không có hẹn giờ nào để hủy."
        return "Đã hủy toàn bộ hẹn giờ và báo thức cho bạn rồi nhé."

    def _worker(self):
        while not self._stop_event.is_set():
            time.sleep(1.0)
            now = time.time()
            triggered = []
            with self.lock:
                remaining = []
                for t in self.timers:
                    if t["target_time"] <= now:
                        triggered.append(t)
                    else:
                        remaining.append(t)
                if triggered:
                    self.timers = remaining
                    self._save()

            for item in triggered:
                # Chờ nếu trợ lý đang trong phiên hội thoại để tránh xung đột âm thanh
                for _ in range(30):
                    if get_assistant_state().get("status", "idle") == "idle":
                        break
                    time.sleep(0.5)

                for _ in range(3):
                    play_chime("alarm")
                    time.sleep(0.4)

                if item["type"] == "timer":
                    label_str = f" cho {item['label']}" if item['label'] else ""
                    msg = f"Đã hết thời gian hẹn giờ{label_str} rồi bạn nhé!"
                else:
                    label_str = f" {item['label']}" if item['label'] else ""
                    msg = f"Đã đến giờ báo thức{label_str} rồi, chúc bạn một ngày tốt lành!"

                try:
                    from ai_assistant.speech.tts import send_notification, speak
                    send_notification("Alexa Báo Giờ", msg)
                    speak(msg, voice=self.voice)
                except Exception:
                    pass

timer_manager = TimerAlarmManager(voice=DEFAULT_VOICE)

def set_timer(minutes: float) -> str:
    return timer_manager.add_timer(minutes)
