import json
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

from config import (
    APP_TIMEZONE,
    HISTORY_FILE,
    SENSOR_STALE_SECONDS,
    STATE_FILE,
    STATE_SAVE_INTERVAL_SECONDS,
    VIBRATION_HISTORY_SIZE,
)
from models import DowntimeEntry


class AppState:
    def __init__(self) -> None:
        self.lock = threading.RLock()

        self.mqtt_vibration = 0.0
        self.vibration_history = deque(maxlen=VIBRATION_HISTORY_SIZE)
        self.last_change_time = time.time()

        self.total_uptime = 0
        self.total_downtime = 0

        self.status_uptime_working = 0
        self.status_uptime_idle = 0
        self.status_downtime_off = 0

        self.last_state_change_time = int(time.time())
        self.is_machine_on = False
        self.machine_was_on = False

        self.last_alert_sent = 0
        self.alert_sent_for_current_downtime = False

        self.downtimes: list[DowntimeEntry] = []
        self.current_downtime: DowntimeEntry | None = None

        self.last_written_count = 0


class StateManager:
    def __init__(self, state: AppState) -> None:
        self.state = state

    def save_state(self) -> None:
        with self.state.lock:
            payload = {
                "total_uptime": self.state.total_uptime,
                "total_downtime": self.state.total_downtime,
                "last_state_change_time": self.state.last_state_change_time,
                "is_machine_on": self.state.is_machine_on,
                "machine_was_on": self.state.machine_was_on,
                "last_reset_date": datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d"),
                "status_uptime_working": self.state.status_uptime_working,
                "status_uptime_idle": self.state.status_uptime_idle,
                "status_downtime_off": self.state.status_downtime_off,
                "downtimes": [entry.to_dict() for entry in self.state.downtimes],
                "current_downtime": (
                    self.state.current_downtime.to_dict()
                    if self.state.current_downtime
                    else {
                        "start": None,
                        "end": None,
                        "is_active": False,
                        "reason": "",
                    }
                ),
            }

        try:
            with open(STATE_FILE, "w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
        except Exception as exc:
            print(f"Failed to save state: {exc}")

    def load_state(self) -> None:
        if not STATE_FILE.exists():
            return

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as file:
                content = file.read().strip()

            if not content:
                raise ValueError("Empty state file")

            data = json.loads(content)
        except Exception as exc:
            print(f"Failed to load state: {exc}")
            return

        with self.state.lock:
            last_reset_date = data.get("last_reset_date", "")
            today = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d")

            if last_reset_date != today:
                print("🔁 Missed daily reset detected during startup. Resetting daily metrics.")
                self.state.total_uptime = 0
                self.state.total_downtime = 0
                self.state.status_uptime_working = 0
                self.state.status_uptime_idle = 0
                self.state.status_downtime_off = 0
                self.state.downtimes = []
                self.state.current_downtime = None
            else:
                self.state.total_uptime = int(data.get("total_uptime", 0))
                self.state.total_downtime = int(data.get("total_downtime", 0))
                self.state.status_uptime_working = int(data.get("status_uptime_working", 0))
                self.state.status_uptime_idle = int(data.get("status_uptime_idle", 0))
                self.state.status_downtime_off = int(data.get("status_downtime_off", 0))

                self.state.downtimes = [
                    DowntimeEntry.from_dict(item)
                    for item in data.get("downtimes", [])
                ]

                current = data.get("current_downtime")
                if current and current.get("start") is not None:
                    self.state.current_downtime = DowntimeEntry.from_dict(current)
                else:
                    self.state.current_downtime = None

            self.state.is_machine_on = bool(data.get("is_machine_on", False))
            self.state.machine_was_on = bool(data.get("machine_was_on", True))
            self.state.last_state_change_time = int(
                data.get("last_state_change_time", int(time.time()))
            )

            now = time.time()
            time_since_change = now - self.state.last_change_time

            if time_since_change > SENSOR_STALE_SECONDS or self.state.mqtt_vibration == 0.0:
                self.state.is_machine_on = False
                self.state.machine_was_on = False

                if self.state.current_downtime is None:
                    print("⚠️ Machine is OFF at startup — starting downtime.")
                    self.state.current_downtime = DowntimeEntry(start=int(now))

        print("✅ State restored from file.")

    def append_history_entry(self, entry: dict[str, Any]) -> None:
        history = []
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                    content = file.read().strip()
                    history = json.loads(content) if content else []
            except Exception:
                history = []

        history.append(entry)

        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as file:
                json.dump(history, file, indent=2)
        except Exception as exc:
            print(f"Failed to write history: {exc}")

    def load_history(self) -> list[dict[str, Any]]:
        if not HISTORY_FILE.exists():
            return []

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                content = file.read().strip()
            return json.loads(content) if content else []
        except Exception as exc:
            print(f"Failed to load history: {exc}")
            return []

    def periodic_saver_loop(self) -> None:
        while True:
            self.save_state()
            time.sleep(STATE_SAVE_INTERVAL_SECONDS)