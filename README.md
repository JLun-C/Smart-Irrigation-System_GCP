## Description of the project:
- #### The IoT-based Smart Algaculture System will combine sensors such as soil moisture, rain detection, DHT11 and a water pump for automated irrigation. The decision making to irrigate is based on a fuzzy logic model processing the sensor data with additional aid from the forecast data (rain probability), which is retrieved from OpenWeatherMap API, to implement a future insight to the system's capability in water conservation. By analysing the data, the system controls the irrigation volume, either to pump more, less or not pumping water, maximizing the usage of water for irrigation aligned with the plants' daily need. It also integrates a CNN model for leaf disease detection, creating a smart system that offers precise and efficient plant care. 

- #### This project is for CPC357 (IoT Architecture and Smart Applications) only.

# Deployment Guide: Smart Irrigation System on GCP Ubuntu VM

This guide covers how to set up your Google Cloud Platform (GCP) Compute Engine instance (Ubuntu) and deploy the Smart Irrigation System.

## 1. VM Instance Setup (GCP Console)
1.  **Create a new Instance**:
    *   **OS/Image**: Ubuntu 22.04 LTS (x86/64).
    *   **Machine Type**: e2-medium (2 vCPU, 4GB RAM) or larger is recommended for ML tasks.
    *   **Firewall**: Check both **Allow HTTP traffic** and **Allow HTTPS traffic**.
2.  **Set a firewall rule to enable MQTT connection**:
    *   Go to **VPC Network** > **Firewall**.
    *   Create a rule named `allow-mqtt`.
    *   Targets: `All instances in the network`.
    *   Source IPv4 limits: `[YOUR_VM_EXTERNAL_IP]`.
    *   Protocols and ports: `tcp:1883`.
3.  **SSH into VM**: Click the "SSH" button in the VM instances list.

## 2. System Dependencies
Once logged into the VM, update the system and install required libraries:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git
```

## 3. Install and Configure MQTT Broker (Mosquitto)
Set up a private MQTT broker for secure device communication:
```bash
# Install Mosquitto
sudo apt install -y mosquitto mosquitto-clients

# Enable and start the service
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# Verify it's running
sudo systemctl status mosquitto
```

## 3. Clone Repository
Clone this project into your VM:
```bash
git clone https://github.com/JLun-C/Smart-Irrigation-System_GCP.git
cd Smart-Irrigation-System_GCP
```

## 4. Python Environment Setup
Create a virtual environment to keep dependencies isolated:
```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Configuration (.env)
You must manually create the `.env` file on the server because it is (correctly) ignored by git.
```bash
nano assets/.env
```
Paste your configuration (replace with your actual values):
```env
OPENWEATHER_API_KEY=[YOUR_OPENWEATHERMAP_API_KEY]
CITY_NAME=[YOUR_CITY_NAME]
LAT=[YOUR_PLANT_CURRENT_LATITUDE]
LON=[YOUR_PLANT_CURRENT_LONGITUDE]

# Our Supabase URL and anon key for limited public access
SUPABASE_URL=https://eeiazmvadvbflsuulcpz.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlaWF6bXZhZHZiZmxzdXVsY3B6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY5NzY4MzksImV4cCI6MjA4MjU1MjgzOX0.yb4fd2jnawkGBxZH_m_aCo3xzp6vqMCCSiUXe3Sqo1M

# MQTT Broker (use 'localhost' on VM, VM external IP on laptop)
MQTT_BROKER=localhost
MQTT_PORT=1883
```
*Press `Ctrl+O`, `Enter` to save, and `Ctrl+X` to exit.*

## 7. Running the Application (MQTT Cloud Architecture)

**Important: Before running, configure your ESP32 firmware AND make sure you are in a virtual environment (venv)**
Edit `Edge/Watering_IoT.ino` and replace:
```cpp
const char* ssid = "YOUR_WIFI_SSID"; // Your WIFI SSID
const char* password = "YOUR_WIFI_PASSWORD"; // Your WIFI PW
const char* mqtt_server = "YOUR_VM_EXTERNAL_IP"; // Replace with your actual VM IP
```
Then upload the firmware to your ESP32.

### A. On the Cloud VM (The Brain)
Run the services that act as the intelligence center.
```bash
# Terminal 1: Irrigation Brain (Listens to MQTT, makes decisions)
python3 Cloud/irrigation_brain.py

### B. Access to The Dashboard
http://[YOUR_VM_EXTERNAL_IP]:[YOUR_VM_PORT]

### C. On Your Laptop (Vision Edge)
Since the ESP32 now connects directly to WiFi (MQTT), you only need your laptop for the Webcam.

**Configuration:** On your PC, edit `assets/.env` and set:
```env
MQTT_BROKER=<YOUR_VM_EXTERNAL_IP>
MQTT_PORT=1883
```

Then run:
```bash
# Terminal 1: Vision Gateway (Listens for 'CAPTURE' MQTT command)
python Edge/vision_gateway.py
```

### D. The ESP32 (Irrigation Edge)
Just power it on! It will send telemetry to your **private VM broker**, and listen for pump commands from the Cloud Brain.