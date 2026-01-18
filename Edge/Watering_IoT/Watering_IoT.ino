/*
========================================
ESP32 Smart Watering System (Standard MQTT)
========================================
- Reads environmental sensors (DHT11, Soil, Rain)
- Sends telemetry via MQTT (PubSubClient) AND Serial (JSON)
- Controls water pump via MQTT Commands or Serial Input
========================================
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <Arduino_JSON.h>
#include "DHT.h"

// =====================================================
// WIFI & MQTT SETTINGS
// =====================================================
const char* ssid = "cslab"; // Your WIFI SSID
const char* password = "aksesg31"; // Your WIFI PW
const char* mqtt_server = "34.59.186.75"; // Replace with GCP VM IP
const int mqtt_port = 1883;
const char* mqtt_user = ""; 
const char* mqtt_pass = "";

const char* topic_telemetry = "device/ESP32_001/telemetry";
const char* topic_command   = "device/ESP32_001/command";

// =====================================================
// PIN CONFIGURATION
// =====================================================
const int DHTPIN        = 21;
const int MOISTURE_PIN  = 35;
const int RAIN_PIN      = 23;
const int RELAY_PIN     = 32;
const int LED_Pin_R     = 18;
const int LED_Pin_G     = 19;

// =====================================================
// SENSOR OBJECTS
// =====================================================
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

WiFiClient espClient;
PubSubClient client(espClient);

// =====================================================
// GLOBAL VARIABLES
// =====================================================
unsigned long lastMsg = 0;
const unsigned long TELEMETRY_CYCLE = 3600000; // 3600000 for 1 hour (PRODUCTION)
bool pumpState = false;

// Calibration for Soil Moisture
int MinDepth = 4095;   // Fully dry
int MaxDepth = 2170;   // Fully wet

void sendTelemetry() {
  // Read Sensors
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) { t = 0; h = 0;}
  
  int rawMoisture = analogRead(MOISTURE_PIN);
  int soilPercent = map(rawMoisture, MinDepth, MaxDepth, 0, 100);
  soilPercent = constrain(soilPercent, 0, 100);
  
  bool raining = digitalRead(RAIN_PIN) == LOW; // Low = Rain
  
  // Debug: Print all readings to Serial
  Serial.println("----------------------------");
  Serial.print("Temperature: "); Serial.print(t); Serial.println(" °C");
  Serial.print("Humidity: "); Serial.print(h); Serial.println(" %");
  Serial.print("Soil Moisture: "); Serial.print(soilPercent); Serial.println(" %");
  Serial.print("Rain Status: "); Serial.println(raining ? "YES" : "NO");
  Serial.print("Pump Status: "); Serial.println(pumpState ? "ON" : "OFF");
  
  // JSON Construction
  JSONVar payload;
  payload["Temperature"]   = t;
  payload["Humidity"]      = h;
  payload["Soil_moisture"] = soilPercent;
  payload["Raining"]       = raining ? 1 : 0;
  payload["Pump"]          = pumpState ? "ON" : "OFF"; 
  
  // String for Gateway compatibility
  String jsonString = JSON.stringify(payload);
  
  // A. Send to Serial (For Laptop Gateway)
  Serial.println(jsonString);
  
  // B. Send to MQTT (Direct Cloud)
  if(client.connected()){
    client.publish(topic_telemetry, jsonString.c_str());
  }
}

// =====================================================
// SETUP WIFI
// =====================================================
void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if(WiFi.status() == WL_CONNECTED){
    Serial.println("\nWiFi connected");
    Serial.println("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi Failed (Continuing in Offline Mode for Serial Gateway)");
  }
}

// =====================================================
// MQTT CALLBACK
// =====================================================
void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  Serial.println(message);

  // Parse Command (Expect "1" for ON, "0" for OFF)
  if (String(topic) == topic_command) {
    if(message.toInt() == 1){
      pumpState = true;
      Serial.println("☁️ Cloud Command: PUMP ON");
    } else {
      pumpState = false;
      Serial.println("☁️ Cloud Command: PUMP OFF");
    }
    applyPump();
  }
}

void reconnect() {
  // Loop until we're reconnected (Block only short time)
  if (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Create a random client ID
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    
    if (client.connect(clientId.c_str(), mqtt_user, mqtt_pass)) {
      Serial.println("connected");
      client.subscribe(topic_command);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again later");
    }
  }
}

void applyPump() {
  digitalWrite(RELAY_PIN, pumpState ? HIGH : LOW);
  digitalWrite(LED_Pin_G, pumpState ? HIGH : LOW);
  digitalWrite(LED_Pin_R, pumpState ? LOW : HIGH);
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  
  // Init Pins
  pinMode(MOISTURE_PIN, INPUT);
  pinMode(RAIN_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(LED_Pin_R, OUTPUT);
  pinMode(LED_Pin_G, OUTPUT);

  dht.begin();
  
  // Default OFF
  digitalWrite(RELAY_PIN, LOW);

  // Setup Network
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  // Attempt MQTT connection once at startup
  unsigned long startAttempt = millis();
  while (!client.connected() && millis() - startAttempt < 5000) {
    reconnect();
    client.loop();
    delay(100); // small yield, safe
  }
  
  // Immediate first telemetry after boot
  sendTelemetry();
  lastMsg = millis();
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  // 1. MQTT Handling (Non-blocking attempt)
  if (WiFi.status() == WL_CONNECTED) {
    if (!client.connected()) {
      // Only try to reconnect occasionally, don't block loop
      static unsigned long lastReconnect = 0;
      if(millis() - lastReconnect > 5000){
        lastReconnect = millis();
        reconnect();
      }
    } else {
      client.loop();
    }
  }

  // 2. Serial Input (From Laptop Gateway)
  if (Serial.available() > 0) {
    String incoming = Serial.readStringUntil('\n');
    incoming.trim();
    if (incoming.length() > 0) {
      int val = incoming.toInt();
      if(val == 2 || val == 1) { // High or Low
         pumpState = true;
         Serial.println("💻 Gateway Command: PUMP ON");
      } else {
         pumpState = false;
         Serial.println("� Gateway Command: PUMP OFF");
      }
      applyPump();
    }
  }

  // 3. Telemetry Cycle
  unsigned long now = millis();
  if (now - lastMsg > TELEMETRY_CYCLE) {
    lastMsg = now;

    sendTelemetry();
  }
}