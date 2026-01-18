import cv2
import time
import threading
import os
import base64
import paho.mqtt.client as mqtt
from dotenv import dotenv_values
from supabase import create_client, Client

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '../.env')
config = dotenv_values(env_path)

# Automation Interval (Manually change this: 20 for development, 21600 for 6h deployment)
AUTO_INTERVAL = 20 

# Supabase Config
url = config.get("SUPABASE_URL")
key = config.get("SUPABASE_SERVICE_KEY") or config.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# MQTT Config
MQTT_BROKER = config.get("MQTT_EDGE_BROKER", "34.59.186.75")
MQTT_PORT = int(config.get("MQTT_PORT", "1883"))
TOPIC_CAPTURE_CMD = "device/camera/command"
TOPIC_RESULT = "device/camera/result"

class VisionGateway:
    def __init__(self):
        print(f"Initializing Vision Gateway (Interval: {AUTO_INTERVAL}s)...")
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.running = True

    def on_connect(self, client, userdata, flags, rc):
        print(f"Connected to MQTT Broker (RC: {rc})")
        client.subscribe(TOPIC_CAPTURE_CMD)
        client.subscribe(TOPIC_RESULT)
        print(f"Subscribed to {TOPIC_CAPTURE_CMD} and {TOPIC_RESULT}")

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            if msg.topic == TOPIC_CAPTURE_CMD:
                if "CAPTURE" in payload.upper():
                    self.capture_and_upload()
            elif msg.topic == TOPIC_RESULT:
                print(f"\n>>> [DIAGNOSIS RESULT] {payload} <<<\n")
        except Exception as e:
            print(f"Error handling message: {e}")

    def capture_and_upload(self):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Capturing Image...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: No Camera Found.")
            return

        ret, frame = cap.read()
        cap.release()

        if ret:
            temp_file = "temp_snap.jpg"
            cv2.imwrite(temp_file, frame)
            
            try:
                with open(temp_file, 'rb') as f:
                    binary_data = f.read()
                
                # Encode to base64 for JSON transport
                ret, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                binary_data = buffer.tobytes()
                encoded_image = base64.b64encode(binary_data).decode("utf-8")

                
                # Insert into Supabase
                record = {
                    "images": encoded_image,
                    "result": None
                }
                supabase.table("images").insert(record).execute()
                print("Image Uploaded to Supabase.")
                self.client.publish("device/camera/status", "UPLOADED")
                
            except Exception as e:
                print(f"Upload Error: {e}")
            finally:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        else:
            print("Failed to capture frame.")

    def auto_capture_loop(self):
        print("Automated Capture Loop Started.")
        while self.running:
            self.capture_and_upload()
            time.sleep(AUTO_INTERVAL)

    def run(self):
        # Start automation in a background thread
        auto_thread = threading.Thread(target=self.auto_capture_loop, daemon=True)
        auto_thread.start()

        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_forever()
        except KeyboardInterrupt:
            self.running = False
            self.client.disconnect()

if __name__ == "__main__":
    gateway = VisionGateway()
    gateway.run()

