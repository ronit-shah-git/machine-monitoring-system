import ssl

import paho.mqtt.client as mqtt

from config import (
    MQTT_BROKER,
    MQTT_KEEPALIVE,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_TOPIC,
    MQTT_USERNAME,
)
from state_manager import AppState


class MQTTService:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self.client = mqtt.Client()
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self.client.tls_set(tls_version=ssl.PROTOCOL_TLS)
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT broker.")
            client.subscribe(MQTT_TOPIC)
        else:
            print(f"MQTT connection failed with code {rc}")

    def on_message(self, client, userdata, msg) -> None:
        try:
            new_value = float(msg.payload.decode())
        except Exception:
            new_value = 0.0

        with self.state.lock:
            if new_value != self.state.mqtt_vibration:
                import time
                self.state.last_change_time = time.time()

            self.state.mqtt_vibration = new_value
            self.state.vibration_history.append(new_value)

    def start(self) -> None:
        self.client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
        self.client.loop_start()