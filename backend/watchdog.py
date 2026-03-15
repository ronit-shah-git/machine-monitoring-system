import json
import os
import time
import urllib.request

from config import WATCHDOG_INTERVAL, WATCHDOG_STALE_TIMEOUT, WATCHDOG_URL


class WatchdogService:
    def __init__(self) -> None:
        self.last_value = None
        self.last_change_time = time.time()

    def restart_if_stale_loop(self) -> None:
        while True:
            try:
                with urllib.request.urlopen(WATCHDOG_URL, timeout=15) as response:
                    data = json.loads(response.read().decode())

                if "vibration" in data:
                    vibration = data["vibration"]
                    if vibration != self.last_value:
                        self.last_value = vibration
                        self.last_change_time = time.time()
                    elif time.time() - self.last_change_time > WATCHDOG_STALE_TIMEOUT:
                        print("Data stale for >2 minutes — restarting Flask process.")
                        os._exit(1)
                else:
                    print("Missing 'vibration' in watchdog data")
            except Exception as exc:
                print(f"Watchdog fetch error: {exc}")

            time.sleep(WATCHDOG_INTERVAL)