# Machine Monitoring System

A production-ready Python backend project for monitoring machine vibration over MQTT, tracking uptime and downtime, serving a Flask dashboard, sending Telegram alerts and commands, exporting Excel reports, and persisting state safely.

---

## Overview

This project monitors machine vibration data received via MQTT and determines whether the machine is:

- Working
- Idle
- Off / sensor unavailable

It tracks uptime and downtime continuously, stores daily state in JSON, writes completed downtime entries to Excel, provides a live dashboard via Flask, and sends Telegram alerts and reports.

---

## Features

- MQTT vibration monitoring
- Machine uptime/downtime detection
- Flask dashboard at `http://localhost:5000`
- Telegram alerts
- Telegram commands:
  - `/status`
  - `/logs`
  - `/download`
  - `/summary`
- Excel downtime logging
- Daily summary messages
- Watchdog stale-data restart
- JSON state persistence
- Downtime reason selection UI
- Daily reset support
- Thread-safe shared state

---

## Architecture

### Main components

- **Flask app**  
  Serves dashboard and JSON APIs.

- **MQTT client**  
  Receives vibration values from the broker.

- **Monitoring service**  
  Calculates machine state, uptime, downtime, MTBF, utilization, summaries, and downtime transitions.

- **Telegram service**  
  Sends machine alerts and handles bot commands.

- **Excel logger**  
  Exports completed downtime records into a daily `.xlsx` file.

- **State manager**  
  Saves and restores runtime state from `data/state.json` and stores summaries in `data/history.json`.

- **Watchdog**  
  Monitors `/data` and exits the process if the value stays stale for too long.
