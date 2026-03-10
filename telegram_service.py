import json
import os
import time
import urllib.parse
import urllib.request

import requests

from config import (
    LOGS_DIR,
    TELEGRAM_CHAT_ID,
    TELEGRAM_COMMAND_POLL_SECONDS,
    TELEGRAM_TOKEN,
)
from monitoring import MonitoringService


class TelegramService:
    def __init__(self, monitoring_service: MonitoringService) -> None:
        self.monitoring_service = monitoring_service
        self.chat_id = TELEGRAM_CHAT_ID
        self.token = TELEGRAM_TOKEN

    def send_message(self, message: str) -> None:
        base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"

        try:
            with urllib.request.urlopen(url) as response:
                print("Telegram response:", response.status, response.read().decode())
        except Exception as exc:
            print(f"Telegram Error: {exc}")

    def send_document(self, file_path: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        try:
            with open(file_path, "rb") as file:
                files = {"document": file}
                data = {"chat_id": self.chat_id}
                response = requests.post(url, data=data, files=files, timeout=60)
                print("Telegram upload response:", response.status_code, response.text)
        except Exception as exc:
            print(f"❌ Failed to send document: {exc}")

    def telegram_command_listener_loop(self) -> None:
        command_url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        last_update_id = None

        while True:
            try:
                url = f"{command_url}?timeout=30"
                if last_update_id is not None:
                    url += f"&offset={last_update_id + 1}"

                with urllib.request.urlopen(url) as response:
                    updates = json.loads(response.read().decode())

                for update in updates.get("result", []):
                    last_update_id = update["update_id"]
                    message = update.get("message", {})
                    text = str(message.get("text", "")).strip().lower()
                    chat_id = str(message.get("chat", {}).get("id", ""))

                    if chat_id != self.chat_id:
                        continue

                    if text == "/status":
                        data = self.monitoring_service.get_data_payload()
                        reply = (
                            f"📟 *Machine Status*\n"
                            f"📈 Vibration: {data['vibration']} m/s²\n"
                            f"⚙️ Threshold: {data['threshold']}\n"
                            f"🟢 Status: {data['status']}"
                        )
                        self.send_message(reply)

                    elif text == "/logs":
                        logs = self.monitoring_service.get_log_payload()

                        if not logs:
                            self.send_message("📋 No downtime logs found today.")
                            continue

                        messages = ["📋 *All Downtime Logs:*"]
                        now = int(time.time())

                        for entry in logs:
                            start = self.monitoring_service.format_timestamp(entry["start"])
                            if entry["end"]:
                                end = self.monitoring_service.format_timestamp(entry["end"])
                                duration = self.monitoring_service.format_duration(
                                    entry["end"] - entry["start"]
                                )
                                reason = entry["reason"] or "⚠️ No reason"
                                messages.append(
                                    f"🛑 {start} → {end} ({duration})\nReason: {reason}"
                                )
                            else:
                                duration = self.monitoring_service.format_duration(
                                    now - entry["start"]
                                )
                                messages.append(f"⏳ Ongoing since {start} ({duration})")

                        full_message = "\n\n".join(messages)
                        chunks = [
                            full_message[i:i + 4000]
                            for i in range(0, len(full_message), 4000)
                        ]
                        for chunk in chunks:
                            self.send_message(chunk)

                    elif text == "/download":
                        today_str = time.strftime("%Y-%m-%d")
                        file_path = os.path.join(LOGS_DIR, f"downtime_{today_str}.xlsx")

                        if os.path.exists(file_path):
                            self.send_document(file_path)
                        else:
                            self.send_message("📂 Excel log not found for today.")

                    elif text == "/summary":
                        data = self.monitoring_service.compute_summary_data()
                        reply = (
                            f"📊 *Current Summary*\n"
                            f"🕒 Uptime: {self.monitoring_service.format_duration(data['uptime'])}\n"
                            f"⏸️ Downtime: {self.monitoring_service.format_duration(data['downtime'])}\n"
                            f"⚙️ Utilization: {data['utilization']}%\n"
                            f"⏳ MTBF: {self.monitoring_service.format_duration(data['mtbf'])}\n"
                            f"⌛ Avg Downtime: {self.monitoring_service.format_duration(data['avg_duration'])}\n"
                            f"🛑 Longest Downtime: {self.monitoring_service.format_duration(data['longest'])}\n"
                            f"🔍 Most Common Reason: {data['most_common_reason']}\n"
                            f"✅ Reason Completion Rate: {data['reason_completion_rate']}%\n"
                            f"📋 Pending Reasons: {data['pending_reasons']}\n"
                            f"\n📶 *Status Breakdown:*\n"
                            f"🟢 Working: {self.monitoring_service.format_duration(data['status_breakdown']['working'])}\n"
                            f"🟡 Idle: {self.monitoring_service.format_duration(data['status_breakdown']['idle'])}\n"
                            f"🟥/🔴 Off: {self.monitoring_service.format_duration(data['status_breakdown']['off'])}\n"
                        )
                        self.send_message(reply)

            except Exception as exc:
                print(f"Telegram command listener error: {exc}")

            time.sleep(TELEGRAM_COMMAND_POLL_SECONDS)