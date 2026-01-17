# Deployment Guide: Smart Irrigation System on GCP Ubuntu VM

This guide covers how to set up your Google Cloud Platform (GCP) Compute Engine instance (Ubuntu) and deploy the Smart Irrigation System.

## 1. VM Instance Setup (GCP Console)
1.  **Create a new Instance**:
    *   **OS/Image**: Ubuntu 22.04 LTS (x86/64).
    *   **Machine Type**: e2-medium (2 vCPU, 4GB RAM) or larger is recommended for ML tasks.
    *   **Firewall**: Check both **Allow HTTP traffic** and **Allow HTTPS traffic**.
2.  **Open Streamlit Port (8501)**:
    *   Go to **VPC Network** > **Firewall**.
    *   Create a rule named `allow-streamlit`.
    *   Targets: `All instances in the network`.
    *   Source IPv4 limits: `0.0.0.0/0`.
    *   Protocols and ports: `tcp:8501`.
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

**Configure Firewall for MQTT:**
```bash
# Allow MQTT port (1883)
sudo ufw allow 1883/tcp

# If UFW is not enabled, enable it (be careful with SSH!)
sudo ufw allow ssh
sudo ufw enable
```

## 4. Clone Repository
Clone your project (you may need to set up a Personal Access Token if it's private, or just use HTTPS if public):
```bash
git clone <YOUR_REPO_URL>
cd Smart-Irrigation-System_GCP
```

## 5. Python Environment Setup
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
nano Intelligent_Components/.env
```
Paste your configuration (replace with your actual values):
```env
OPENWEATHER_API_KEY=f3726ac...
CITY_NAME=George Town
LAT=5.3544
LON=100.3018

SUPABASE_URL=https://...
SUPABASE_KEY=eyJ... (Your ANON key)
SUPABASE_SERVICE_KEY=eyJ... (Your SERVICE_ROLE key)

# MQTT Broker (use 'localhost' on VM, VM external IP on laptop)
MQTT_BROKER=localhost
MQTT_PORT=1883
```
*Press `Ctrl+O`, `Enter` to save, and `Ctrl+X` to exit.*

## 7. Running the Application (MQTT Cloud Architecture)

**Important: Before running, configure your ESP32 firmware**
Edit `Watering_IoT/Watering_IoT.ino` and replace:
```cpp
const char* mqtt_server = "YOUR_VM_EXTERNAL_IP"; // Replace with your actual VM IP
```
Then upload the firmware to your ESP32.

### A. On the Cloud VM (The Brain)
Run the services that act as the intelligence center.
```bash
# Terminal 1: Irrigation Brain (Listens to MQTT, makes decisions)
python3 Intelligent_Components/Cloud/irrigation_brain.py

# Terminal 2: Vision Brain (Analyses uploaded images)
python3 Intelligent_Components/Cloud/vision_brain.py
```

### B. On the Cloud VM (The Dashboard)
```bash
streamlit run Intelligent_Components/dashboard.py
```

### C. On Your Laptop (Vision Edge)
Since the ESP32 now connects directly to WiFi (MQTT), you only need your laptop for the Webcam.

**Configuration:** On your laptop, edit `Intelligent_Components/.env` and set:
```env
MQTT_BROKER=<YOUR_VM_EXTERNAL_IP>
MQTT_PORT=1883
```

Then run:
```bash
# Terminal 1: Vision Gateway (Listens for 'CAPTURE' MQTT command)
python Intelligent_Components/Edge/vision_gateway.py
```

### D. The ESP32 (Irrigation Edge)
Just power it on! It will connect to WiFi `cslab`, send telemetry to your **private VM broker**, and listen for pump commands from the Cloud Brain.

*(Note: The `irrigation_gateway.py` script is no longer needed)*
