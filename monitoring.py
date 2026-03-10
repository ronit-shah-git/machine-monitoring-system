import time
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from config import (
    ALERT_INTERVAL,
    ALERT_START_DELAY,
    APP_TIMEZONE,
    DAILY_RESET_HOUR,
    DAILY_RESET_MINUTE,
    DAILY_SUMMARY_HOUR,
    DAILY_SUMMARY_MINUTE,
    MONITOR_LOOP_INTERVAL_SECONDS,
    SENSOR_STALE_SECONDS,
    VIBRATION_THRESHOLD,
)
from models import DowntimeEntry
from state_manager import AppState, StateManager


class MonitoringService:
    def __init__(self, state: AppState, state_manager: StateManager) -> None:
        self.state = state
        self.state_manager = state_manager
        self.telegram_service = None

    def set_telegram_service(self, telegram_service: Any) -> None:
        self.telegram_service = telegram_service

    @staticmethod
    def format_duration(seconds: int) -> str:
        seconds = max(0, int(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    @staticmethod
    def format_timestamp(timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def _send_telegram(self, message: str) -> None:
        if self.telegram_service:
            self.telegram_service.send_message(message)

    def compute_currently_on(self, vibration: float, time_since_change: float) -> bool:
        if time_since_change > SENSOR_STALE_SECONDS or vibration == 0.0:
            return False
        if vibration >= VIBRATION_THRESHOLD:
            return True
        if 0.01 <= vibration < VIBRATION_THRESHOLD:
            return False
        return False

    def handle_missed_reset(self) -> None:
        now = datetime.now(APP_TIMEZONE)
        today_reset = now.replace(
            hour=DAILY_RESET_HOUR,
            minute=DAILY_RESET_MINUTE,
            second=0,
            microsecond=0,
        )
        today_str = now.strftime("%Y-%m-%d")

        try:
            if not self.state_manager.state:
                return
        except Exception:
            return

        if now <= today_reset:
            return

        with self.state.lock:
            # Save file contains today's reset date if already handled.
            pass

        try:
            with open(self.state_manager.state.__class__.__module__.replace(".", "/"), "r"):
                pass
        except Exception:
            # no-op; this block only avoids changing existing logic flow in startup
            pass

        try:
            from config import STATE_FILE
            import json

            if not STATE_FILE.exists():
                print("No state file found — creating default state.")
                self.state_manager.save_state()
                return

            with open(STATE_FILE, "r", encoding="utf-8") as file:
                content = file.read().strip()
                if not content:
                    print("Empty state file — creating default state.")
                    self.state_manager.save_state()
                    return
                saved_state = json.loads(content)

            last_reset = saved_state.get("last_reset_date", "")
        except Exception as exc:
            print(f"Failed to read state file: {exc}")
            self.state_manager.save_state()
            return

        if last_reset != today_str and now > today_reset:
            print("Missed 9 AM reset. Performing now.")
            with self.state.lock:
                self.state.total_uptime = 0
                self.state.total_downtime = 0
                self.state.status_uptime_working = 0
                self.state.status_uptime_idle = 0
                self.state.status_downtime_off = 0
                self.state.downtimes.clear()
                self.state.current_downtime = None
            self.state_manager.save_state()

    def check_machine_state(self) -> None:
        messages: list[str] = []

        with self.state.lock:
            now = int(time.time())
            time_since_change = now - self.state.last_change_time

            currently_on = self.compute_currently_on(
                vibration=self.state.mqtt_vibration,
                time_since_change=time_since_change,
            )

            duration = max(now - self.state.last_state_change_time, 0)

            if self.state.mqtt_vibration >= VIBRATION_THRESHOLD:
                self.state.total_uptime += duration
            elif 0.01 <= self.state.mqtt_vibration < VIBRATION_THRESHOLD:
                self.state.total_downtime += duration
            else:
                self.state.total_downtime += duration

            if self.state.mqtt_vibration >= VIBRATION_THRESHOLD:
                self.state.status_uptime_working += duration
            elif 0.01 <= self.state.mqtt_vibration < VIBRATION_THRESHOLD:
                self.state.status_uptime_idle += duration
            elif self.state.mqtt_vibration == 0.0 or time_since_change > SENSOR_STALE_SECONDS:
                self.state.status_downtime_off += duration

            if self.state.machine_was_on and not currently_on:
                if self.state.current_downtime is None:
                    self.state.current_downtime = DowntimeEntry(start=now)
                    self.state.alert_sent_for_current_downtime = False
                    self.state.last_alert_sent = 0

            elif not self.state.machine_was_on and currently_on:
                if self.state.current_downtime:
                    self.state.current_downtime.end = now
                    downtime_duration = self.state.current_downtime.end - self.state.current_downtime.start
                    if downtime_duration >= 120:
                        self.state.current_downtime.is_active = False
                        self.state.downtimes.append(self.state.current_downtime)
                    self.state.current_downtime = None

            elif not self.state.machine_was_on and self.state.current_downtime:
                downtime_duration = now - self.state.current_downtime.start
                if (
                    downtime_duration >= ALERT_START_DELAY
                    and not self.state.alert_sent_for_current_downtime
                ):
                    messages.append(
                        f"Machine has been down from "
                        f"{self.format_timestamp(self.state.current_downtime.start)} to "
                        f"{self.format_timestamp(now)} "
                        f"({self.format_duration(downtime_duration)}) — ongoing"
                    )
                    self.state.alert_sent_for_current_downtime = True
                    self.state.last_alert_sent = now
                elif (
                    self.state.alert_sent_for_current_downtime
                    and now - self.state.last_alert_sent >= ALERT_INTERVAL
                ):
                    messages.append(
                        f"Machine has been down from "
                        f"{self.format_timestamp(self.state.current_downtime.start)} to "
                        f"{self.format_timestamp(now)} "
                        f"({self.format_duration(downtime_duration)}) — ongoing"
                    )
                    self.state.last_alert_sent = now

            self.state.last_state_change_time = now
            self.state.is_machine_on = currently_on
            self.state.machine_was_on = currently_on

        for message in messages:
            self._send_telegram(message)

    def monitoring_loop(self) -> None:
        while True:
            self.check_machine_state()
            time.sleep(MONITOR_LOOP_INTERVAL_SECONDS)

    def reset_daily_metrics_loop(self) -> None:
        last_reset = None

        while True:
            now = datetime.now(APP_TIMEZONE)
            next_reset = now.replace(
                hour=DAILY_RESET_HOUR,
                minute=DAILY_RESET_MINUTE,
                second=0,
                microsecond=0,
            )

            if now >= next_reset:
                next_reset += timedelta(days=1)

            wait_seconds = (next_reset - now).total_seconds()
            time.sleep(wait_seconds)

            now = datetime.now(APP_TIMEZONE)
            today_str = now.strftime("%Y-%m-%d")

            if last_reset != today_str:
                print("Daily reset @ 9 AM IST")
                with self.state.lock:
                    self.state.total_uptime = 0
                    self.state.total_downtime = 0
                    self.state.status_uptime_working = 0
                    self.state.status_uptime_idle = 0
                    self.state.status_downtime_off = 0
                    self.state.downtimes.clear()
                    self.state.current_downtime = None
                last_reset = today_str
                self.state_manager.save_state()

    def compute_summary_data(self) -> dict[str, Any]:
        with self.state.lock:
            now_ts = int(time.time())
            additional = now_ts - self.state.last_state_change_time

            uptime = self.state.total_uptime + (additional if self.state.is_machine_on else 0)
            downtime = self.state.total_downtime + (additional if not self.state.is_machine_on else 0)

            working = self.state.status_uptime_working
            idle = self.state.status_uptime_idle
            off = self.state.status_downtime_off

            if self.state.is_machine_on:
                if 0.01 <= self.state.mqtt_vibration < VIBRATION_THRESHOLD:
                    idle += additional
                elif self.state.mqtt_vibration >= VIBRATION_THRESHOLD:
                    working += additional
            else:
                if (
                    self.state.mqtt_vibration == 0.0
                    or (time.time() - self.state.last_change_time) > SENSOR_STALE_SECONDS
                ):
                    off += additional

            completed_downtimes = [entry for entry in self.state.downtimes if not entry.is_active]
            num_downtimes = len(completed_downtimes)

            avg_duration = (
                sum((entry.end - entry.start) for entry in completed_downtimes) // num_downtimes
                if num_downtimes
                else 0
            )
            longest = max((entry.end - entry.start for entry in completed_downtimes), default=0)
            mtbf = uptime // num_downtimes if num_downtimes else 0
            pending_reasons = sum(
                1 for entry in completed_downtimes if not entry.reason.strip()
            )
            utilization = (uptime * 100 // (uptime + downtime)) if (uptime + downtime) else 0

            reasons = [entry.reason for entry in completed_downtimes if entry.reason.strip()]
            most_common_reason = Counter(reasons).most_common(1)
            most_common_reason_text = most_common_reason[0][0] if most_common_reason else "N/A"

            total_reasons = num_downtimes
            reason_completed = total_reasons - pending_reasons
            reason_completion_rate = (
                reason_completed * 100 // total_reasons if total_reasons else 100
            )

            return {
                "uptime": uptime,
                "downtime": downtime,
                "utilization": utilization,
                "mtbf": mtbf,
                "avg_duration": avg_duration,
                "longest": longest,
                "pending_reasons": pending_reasons,
                "reason_completion_rate": reason_completion_rate,
                "most_common_reason": most_common_reason_text,
                "status_breakdown": {
                    "working": working,
                    "idle": idle,
                    "off": off,
                },
            }

    def get_daily_stats_payload(self) -> dict[str, Any]:
        summary = self.compute_summary_data()
        return {
            "uptime": summary["uptime"],
            "downtime": summary["downtime"],
            "avg_duration": summary["avg_duration"],
            "longest": summary["longest"],
            "mtbf": summary["mtbf"],
            "utilization": summary["utilization"],
            "pending_reasons": summary["pending_reasons"],
        }

    def get_data_payload(self) -> dict[str, Any]:
        with self.state.lock:
            vibration = round(self.state.mqtt_vibration, 2)
            time_since_change = time.time() - self.state.last_change_time

        if time_since_change > SENSOR_STALE_SECONDS:
            status = "Machine is OFF / Sensor is OFF / Restart Code (Downtime)"
        elif 0.01 <= vibration < VIBRATION_THRESHOLD:
            status = "Machine is ON but Idle (Downtime)"
        elif vibration >= VIBRATION_THRESHOLD:
            status = "Machine is ON and Working (Uptime)"
        elif vibration == 0.0:
            status = "Machine is OFF / Sensor is OFF / Restart Code (Downtime)"
        else:
            status = "Unknown"

        return {
            "vibration": vibration,
            "threshold": VIBRATION_THRESHOLD,
            "status": status,
        }

    def get_log_payload(self) -> list[dict[str, Any]]:
        with self.state.lock:
            logs = [
                {
                    "start": entry.start,
                    "end": entry.end if entry.end else None,
                    "active": entry.is_active,
                    "reason": entry.reason,
                }
                for entry in self.state.downtimes
            ]

            if self.state.current_downtime:
                logs.append(
                    {
                        "start": self.state.current_downtime.start,
                        "end": None,
                        "active": True,
                        "reason": self.state.current_downtime.reason,
                    }
                )

        return logs

    def get_history_payload(self) -> list[dict[str, Any]]:
        return self.state_manager.load_history()

    def get_totals_payload(self) -> dict[str, Any]:
        summary = self.compute_summary_data()
        return {
            "uptime": summary["uptime"],
            "downtime": summary["downtime"],
        }

    def get_status_breakdown_payload(self) -> dict[str, Any]:
        summary = self.compute_summary_data()
        return summary["status_breakdown"]

    def update_reason(self, start: int, reason: str) -> tuple[str, int]:
        reason = reason.strip()

        with self.state.lock:
            for entry in self.state.downtimes:
                if entry.start == start:
                    entry.reason = reason
                    self.state_manager.save_state()
                    duration = (entry.end - entry.start) if entry.end else 0
                    message = (
                        f"Reason updated for downtime\n"
                        f"Start: {self.format_timestamp(entry.start)}\n"
                        f"End: {self.format_timestamp(entry.end) if entry.end else 'Ongoing'}\n"
                        f"Duration: {self.format_duration(duration)}\n"
                        f"Reason: {entry.reason}"
                    )
                    self._send_telegram(message)
                    return "Reason updated", 200

            if self.state.current_downtime and self.state.current_downtime.start == start:
                self.state.current_downtime.reason = reason
                self.state_manager.save_state()
                now = int(time.time())
                duration = now - self.state.current_downtime.start
                message = (
                    f"Reason for *ongoing* downtime "
                    f"(started at {self.format_timestamp(self.state.current_downtime.start)}) "
                    f"— Duration: {self.format_duration(duration)} — Reason: {reason}"
                )
                self._send_telegram(message)
                return "Reason updated", 200

        return "Entry not found", 404

    def send_daily_summary_loop(self) -> None:
        while True:
            now = datetime.now(APP_TIMEZONE)
            next_summary = now.replace(
                hour=DAILY_SUMMARY_HOUR,
                minute=DAILY_SUMMARY_MINUTE,
                second=0,
                microsecond=0,
            )

            if now >= next_summary:
                next_summary += timedelta(days=1)

            wait_seconds = (next_summary - now).total_seconds()
            time.sleep(wait_seconds)

            summary = self.compute_summary_data()

            completed_downtimes = []
            with self.state.lock:
                completed_downtimes = [entry for entry in self.state.downtimes if not entry.is_active]

            num_downtimes = len(completed_downtimes)

            history_entry = {
                "date": datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d"),
                "uptime": summary["uptime"],
                "downtime": summary["downtime"],
                "utilization": summary["utilization"],
                "mtbf": summary["mtbf"],
                "avg_duration": summary["avg_duration"],
                "longest": summary["longest"],
                "most_common_reason": summary["most_common_reason"],
                "reason_completion_rate": summary["reason_completion_rate"],
                "pending_reasons": summary["pending_reasons"],
                "working_time": summary["status_breakdown"]["working"],
                "idle_time": summary["status_breakdown"]["idle"],
                "off_time": summary["status_breakdown"]["off"],
                "downtime_count": num_downtimes,
            }
            self.state_manager.append_history_entry(history_entry)

            message = (
                f"*Daily Summary @ 6 PM*\n"
                f"Total Uptime: {self.format_duration(summary['uptime'])}\n"
                f"Total Downtime: {self.format_duration(summary['downtime'])}\n"
                f"Utilization: {summary['utilization']}%\n"
                f"MTBF (Mean Time Between Failures): {self.format_duration(summary['mtbf'])}\n"
                f"Average Downtime: {self.format_duration(summary['avg_duration'])}\n"
                f"Longest Downtime: {self.format_duration(summary['longest'])}\n"
                f"Most Common Reason: {summary['most_common_reason']}\n"
                f"Reason Completion Rate: {summary['reason_completion_rate']}%\n"
                f"Pending Reasons: {summary['pending_reasons']}\n"
                f"\n *Status Breakdown:*\n"
                f"Working: {self.format_duration(summary['status_breakdown']['working'])}\n"
                f"Idle: {self.format_duration(summary['status_breakdown']['idle'])}\n"
                f"Off: {self.format_duration(summary['status_breakdown']['off'])}\n"
            )

            self._send_telegram(message)