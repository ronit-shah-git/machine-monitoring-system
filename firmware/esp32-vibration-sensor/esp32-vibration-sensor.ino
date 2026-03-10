#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <math.h>
#include <esp_system.h>
#include <esp_task_wdt.h>
#include <ESPAsyncWebServer.h>
#include <AsyncTCP.h>

// === Configuration ===
#define WDT_TIMEOUT 10
const char* ssid = "<your_wifi_ssid>";  // Replace with your WiFi SSID
const char* password = "<your_wifi_password>";  // Replace with your WiFi password

const char* mqtt_server = "<mqtt_server_ip>";  // Replace with your MQTT broker IP
const int mqtt_port = 8883;  // Secure TLS port
const char* mqtt_user = "rpi";
const char* mqtt_pass = "rpi";
const char* mqtt_topic = "vibration/rms";

// === Globals ===
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);
WiFiClientSecure secureClient;
PubSubClient client(secureClient);
AsyncWebServer server(80);
AsyncWebSocket ws("/vibration");

const int SAMPLE_SIZE = 5;
float vibSamples[SAMPLE_SIZE] = {0};
int sampleIndex = 0;
float vibration = 0;

void setup_wifi() {
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" connected!");
}

void ensureWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost. Reconnecting...");
    WiFi.disconnect();
    WiFi.begin(ssid, password);
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
      delay(500);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("WiFi reconnected!");
    } else {
      Serial.println("WiFi reconnect failed. Restarting...");
      ESP.restart();
    }
  }
}
void reconnect() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    String clientId = "ESP32Client-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str(), mqtt_user, mqtt_pass)) {
      Serial.println(" connected!");
    } else {
      Serial.print(" failed, rc=");
      Serial.print(client.state());
      Serial.println(" retrying...");
      delay(1000);
    }
  }
}
void updateVibration() {
  sensors_event_t event;
  accel.getEvent(&event);
  float x = event.acceleration.x;
  float y = event.acceleration.y;
  float z = event.acceleration.z;

  float magnitude = sqrt(x * x + y * y + z * z);
  float vib = fabs(magnitude - 9.81); // Remove gravity

  vibSamples[sampleIndex++] = vib;
  if (sampleIndex >= SAMPLE_SIZE) sampleIndex = 0;

  float sumSq = 0;
  for (int i = 0; i < SAMPLE_SIZE; i++) {
    sumSq += vibSamples[i] * vibSamples[i];
  }
  vibration = sqrt(sumSq / SAMPLE_SIZE);
}
//simply for cross checking if whether there is problem with the mqtt broker or not
// === WebSocket & Web UI ===

void setupWebSocket() {
  ws.onEvent([](AsyncWebSocket *server, AsyncWebSocketClient *client,
                AwsEventType type, void *arg, uint8_t *data, size_t len) {
    if (type == WS_EVT_CONNECT) {
      Serial.printf("WS Client %u connected\n", client->id());
    } else if (type == WS_EVT_DISCONNECT) {
      Serial.printf("WS Client %u disconnected\n", client->id());
    }
  });
  server.addHandler(&ws);
}

void setupWebPage() {
  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/html", R"rawliteral(
      <!DOCTYPE html>
      <html>
      <head>
        <title>ESP32 Vibration Monitor</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body { font-family: Arial; text-align: center; margin-top: 50px; }
          h1 { font-size: 24px; }
          #vib { font-size: 48px; color: green; }
        </style>
      </head>
      <body>
        <h1>Live Vibration RMS</h1>
        <div id="vib">--</div>
        <script>
          const ws = new WebSocket(`ws://${location.hostname}/vibration`);
          ws.onmessage = (event) => {
            document.getElementById("vib").textContent = parseFloat(event.data).toFixed(2);
          };
        </script>
      </body>
      </html>
    )rawliteral");
  });
}
void setup() {
  Serial.begin(115200);
  // Watchdog setup
  esp_task_wdt_config_t wdt_config = {
  .timeout_ms = WDT_TIMEOUT * 1000,
  .idle_core_mask = (1 << portNUM_PROCESSORS) - 1,
  .trigger_panic = true
};
esp_task_wdt_init(&wdt_config);
  esp_task_wdt_add(NULL);
  // Start I2C for ADXL345
  Wire.begin(21, 22);
  if (!accel.begin()) {
    Serial.println("ADXL345 not detected. Restarting...");
    delay(5000);
    ESP.restart();
  }
  Serial.println("ADXL345 detected.");
  setup_wifi();
  // MQTT
  secureClient.setInsecure();  // Skip TLS cert verification
  client.setServer(mqtt_server, mqtt_port);
  // Web Server
  setupWebSocket();
  setupWebPage();
  server.begin();
  Serial.println("HTTP and WebSocket server started.");
  Serial.println();
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}
void loop() {
  esp_task_wdt_reset();  // Keep watchdog happy
  ensureWiFi();
  if (!client.connected()) {
    reconnect();
  }
  client.loop();
  updateVibration();
  char msg[20];
  dtostrf(vibration, 6, 2, msg);
  if (client.publish(mqtt_topic, msg)) {
    Serial.print("MQTT RMS: ");
    Serial.println(msg);
  } else {
    Serial.println("MQTT publish failed.");
  }
  ws.textAll(msg);
  delay(1000);  // 1 second sampling
}


