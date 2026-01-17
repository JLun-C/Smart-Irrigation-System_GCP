import cv2
import time
import os
import base64
import paho.mqtt.client as mqtt
from dotenv import dotenv_values
from supabase import create_client, Client

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '../.env')
config = dotenv_values(env_path)

# Supabase Config (Like other scripts)
url = config.get("SUPABASE_URL")
key = config.get("SUPABASE_SERVICE_KEY") or config.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# MQTT Config (Connect to VM Broker)
MQTT_BROKER = config.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(config.get("MQTT_PORT", "1883"))
TOPIC_CAPTURE_CMD = "device/camera/command"

class VisionGateway:
    def __init__(self):
        print("Initializing Vision Gateway (MQTT Trigger)...")
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print(f"Connected to MQTT Broker (RC: {rc})")
        client.subscribe(TOPIC_CAPTURE_CMD)
        print(f"Subscribed to {TOPIC_CAPTURE_CMD}")

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            print(f"Received Command: {payload}")
            if "CAPTURE" in payload.upper():
                self.capture_and_upload()
        except Exception as e:
            print(f"Error handling message: {e}")

    def capture_and_upload(self):
        print("Capturing Image...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: No Camera Found.")
            return

        ret, frame = cap.read()
        cap.release()

        if ret:
            cv2.imwrite("temp_snap.jpg", frame)
            
            # Upload to DB using Supabase Client
            try:
                with open("temp_snap.jpg", 'rb') as f:
                    binary_data = f.read()
                
                # Encode to base64 for JSON transport
                encoded_image = base64.b64encode(binary_data).decode('utf-8')
                
                # Insert into Supabase
                record = {
                    "images": encoded_image,
                    "result": None
                }
                supabase.table("images").insert(record).execute()
                print("Image Uploaded to Database via Supabase Client.")
                
                # Optional: Acknowledge via MQTT
                self.client.publish("device/camera/status", "UPLOADED")
                
            except Exception as e:
                print(f"Upload Error: {e}")
            finally:
                if os.path.exists("temp_snap.jpg"):
                    os.remove("temp_snap.jpg")
        else:
            print("Failed to capture frame.")

    def run(self):
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_forever()
        except KeyboardInterrupt:
            self.client.disconnect()

if __name__ == "__main__":
    gateway = VisionGateway()
    gateway.run()

