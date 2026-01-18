import os
import time
import numpy as np
import cv2
import base64
import paho.mqtt.client as mqtt
from dotenv import dotenv_values
from supabase import create_client, Client
from keras.models import load_model
from tensorflow.keras.utils import img_to_array
import tempfile
import base64

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' # Suppresses info/warning logs

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '../assets/.env')
config = dotenv_values(env_path)

url = config.get("SUPABASE_URL")
key = config.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# MQTT Config (Connect to VM Broker)
MQTT_BROKER = config.get("MQTT_EDGE_BROKER", "34.59.186.75")
MQTT_PORT = int(config.get("MQTT_PORT", "1883"))
TOPIC_RESULT = "device/camera/result"

# Load Model
MODEL_PATH = os.path.join(os.path.dirname(__file__), '../leaf_disease_detection_model.keras')
model = load_model(MODEL_PATH)
CLASSES = ['Healthy', 'Powdery', 'Rust']

import base64

def decode_image(img_data):
    """
    Decode BASE64 image string from Supabase into raw bytes
    """
    if not img_data:
        return None

    try:
        # Supabase stores base64 as TEXT
        missing_padding = len(img_data) % 4
        if missing_padding:
            img_data += "=" * (4 - missing_padding)

        return base64.b64decode(img_data)
    except Exception as e:
        print(f"[Decode Error] Base64 decoding failed: {e}")
        return None

# Automation Interval (Manually change this: 20 for development, 21600 for 6h deployment)
POLL_INTERVAL = 20 

def process_images():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cloud Vision Service v2 (Auto-Automation) Started.")
    print(f"Interval: {POLL_INTERVAL}s, Broker: {MQTT_BROKER}")
    
    # Setup MQTT Client
    mqtt_client = mqtt.Client()
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"MQTT Connection Error: {e}")

    while True:
        try:
            # Find newest image
            response = supabase.table("images").select("*").eq("status", "PENDING").order("created_at", desc=True).limit(1).execute()
            
            if response.data:
                record = response.data[0]
                image_id = record['id']
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Processing Image ID: {image_id}")

                supabase.table("images") \
                .update({"status": "PROCESSING"}) \
                .eq("id", image_id) \
                .execute()
                
                img_bytes = decode_image(record['images'])

                if not img_bytes:
                    supabase.table("images") \
                        .update({"result": "ERROR: Invalid Base64", "status": "ERROR"}) \
                        .eq("id", image_id) \
                        .execute()
                    continue

                if len(img_bytes) > 5 * 1024 * 1024:
                    supabase.table("images") \
                        .update({"result": "ERROR: Image too large (>5MB)", "status": "ERROR"}) \
                        .eq("id", image_id) \
                        .execute()
                    continue

                nparr = np.frombuffer(img_bytes, np.uint8)
                if nparr.size == 0:
                    supabase.table("images") \
                        .update({"result": "ERROR: Empty Image Buffer", "status": "ERROR"}) \
                        .eq("id", image_id) \
                        .execute()
                    continue

                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    supabase.table("images") \
                        .update({"result": "ERROR: Decode Fail", "status": "ERROR"}) \
                        .eq("id", image_id) \
                        .execute()
                    continue

                img = cv2.resize(img, (224, 224))
                img_array = img_to_array(img)
                img_array = np.expand_dims(img_array, axis=0) / 255.0

                predictions = model.predict(img_array)
                class_idx = np.argmax(predictions[0])
                confidence = float(np.max(predictions[0]) * 100)
                result = CLASSES[class_idx] if class_idx < len(CLASSES) else "Unknown"

                summary = f"{result} ({confidence:.2f}%)"

                supabase.table("images") \
                    .update({"result": result, "status": "DONE"}) \
                    .eq("id", image_id) \
                    .execute()

                mqtt_client.publish(
                    TOPIC_RESULT,
                    f"ID {image_id}: {summary}"
                )

                print(f"Prediction Result: {summary}")
            
            time.sleep(POLL_INTERVAL)
                
        except Exception as e:
            print(f"Vision Brain Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_images()
