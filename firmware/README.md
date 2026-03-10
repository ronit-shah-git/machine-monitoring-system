# ESP32 Vibration Sensor Firmware

This firmware runs on an ESP32 connected to an ADXL345 accelerometer.

Features:
- Reads acceleration from ADXL345
- Calculates RMS vibration
- Publishes data to MQTT
- WebSocket live monitor
- Watchdog auto restart
- WiFi auto reconnect

MQTT Topic:
vibration/rms

Hardware:
ESP32 + ADXL345

I2C Pins:
SDA → GPIO21
SCL → GPIO22