from pathlib import Path
from pytz import timezone

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "templates"

STATE_FILE = DATA_DIR / "state.json"
HISTORY_FILE = DATA_DIR / "history.json"

# Flask
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = False

# Monitoring
VIBRATION_THRESHOLD = 0.80
VIBRATION_HISTORY_SIZE = 5
SENSOR_STALE_SECONDS = 5

# Telegram
TELEGRAM_TOKEN = " <YOUR_TELEGRAM_BOT_TOKEN>"
TELEGRAM_CHAT_ID = " <YOUR_TELEGRAM_CHAT_ID>"

# Alert timings
ALERT_INTERVAL = 1800       # 30 minutes
ALERT_START_DELAY = 1800    # 30 minutes

# MQTT
MQTT_BROKER = "<YOUR_MQTT_BROKER_ADDRESS>"
MQTT_PORT = 8883
MQTT_KEEPALIVE = 60
MQTT_USERNAME = "rpi"
MQTT_PASSWORD = "rpi"
MQTT_TOPIC = "vibration/rms"

# Timezone
APP_TIMEZONE = timezone("Asia/Kolkata")

# Schedules
DAILY_RESET_HOUR = 9
DAILY_RESET_MINUTE = 0

DAILY_SUMMARY_HOUR = 17
DAILY_SUMMARY_MINUTE = 30

# Persistence / loops
STATE_SAVE_INTERVAL_SECONDS = 2
EXCEL_WRITE_INTERVAL_SECONDS = 5
EXCEL_IDLE_SLEEP_SECONDS = 10
MONITOR_LOOP_INTERVAL_SECONDS = 1
TELEGRAM_COMMAND_POLL_SECONDS = 5

# Watchdog
WATCHDOG_URL = f"http://localhost:{FLASK_PORT}/data"
WATCHDOG_STALE_TIMEOUT = 120
WATCHDOG_INTERVAL = 15

# Dashboard reason options
DOWNTIME_REASONS = [
    "No Task Assigned",
    "Loading Mould",
    "Unloading Mould",
    "Preparation of Mould",
    "Waiting for Instructions",
    "Changeover for New Batch",
    "Machine Breakdown",
    "Lunch Break",
    "QC Pending",
    "Raw Material Shortage",
    "Tea Break",
    "Power Cut",
    "Maintenance",
    "Shift Change",
    "Technical Issue",
    "Cleaning",
]


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    if not STATE_FILE.exists():
        STATE_FILE.write_text("{}", encoding="utf-8")

    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")