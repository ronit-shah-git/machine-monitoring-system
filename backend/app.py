import atexit
import signal
import sys
import threading

from flask import Flask, jsonify, render_template, request

from config import FLASK_DEBUG, FLASK_HOST, FLASK_PORT, ensure_directories
from excel_logger import ExcelLogger
from monitoring import MonitoringService
from mqtt_client import MQTTService
from state_manager import AppState, StateManager
from telegram_service import TelegramService
from watchdog import WatchdogService

ensure_directories()

app = Flask(__name__, template_folder="templates")

state = AppState()
state_manager = StateManager(state)
monitoring_service = MonitoringService(state, state_manager)
mqtt_service = MQTTService(state)
excel_logger = ExcelLogger(state)
watchdog_service = WatchdogService()
telegram_service = TelegramService(monitoring_service)
monitoring_service.set_telegram_service(telegram_service)


@app.route("/")
def root():
    return render_template("dashboard.html")


@app.route("/dailyStats")
def daily_stats():
    return jsonify(monitoring_service.get_daily_stats_payload())


@app.route("/data")
def data():
    return jsonify(monitoring_service.get_data_payload())


@app.route("/log")
def log():
    return jsonify(monitoring_service.get_log_payload())


@app.route("/history")
def history():
    return jsonify(monitoring_service.get_history_payload())


@app.route("/totals")
def totals():
    return jsonify(monitoring_service.get_totals_payload())


@app.route("/updateReason")
def update_reason():
    start = int(request.args.get("start", 0))
    reason = request.args.get("reason", "")
    message, status_code = monitoring_service.update_reason(start, reason)
    return message, status_code


@app.route("/statusBreakdown")
def status_breakdown():
    return jsonify(monitoring_service.get_status_breakdown_payload())


@app.route("/summary")
def summary():
    return jsonify(monitoring_service.compute_summary_data())


def graceful_exit(signum=None, frame=None):
    state_manager.save_state()
    print(f"State saved before exit (Signal {signum})")
    sys.exit(0)


def start_background_threads():
    threads = [
        threading.Thread(target=monitoring_service.monitoring_loop, daemon=True),
        threading.Thread(target=monitoring_service.reset_daily_metrics_loop, daemon=True),
        threading.Thread(target=state_manager.periodic_saver_loop, daemon=True),
        threading.Thread(target=excel_logger.write_downtimes_to_excel_daily_loop, daemon=True),
        threading.Thread(target=monitoring_service.send_daily_summary_loop, daemon=True),
        threading.Thread(target=watchdog_service.restart_if_stale_loop, daemon=True),
        threading.Thread(target=telegram_service.telegram_command_listener_loop, daemon=True),
    ]

    for thread in threads:
        thread.start()


atexit.register(state_manager.save_state)
signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)


if __name__ == "__main__":
    state_manager.load_state()
    monitoring_service.handle_missed_reset()

    mqtt_service.start()
    start_background_threads()

    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)