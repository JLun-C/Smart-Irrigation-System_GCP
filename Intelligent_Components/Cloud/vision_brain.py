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
env_path = os.path.join(os.path.dirname(__file__), '../.env')
config = dotenv_values(env_path)

url = config.get("SUPABASE_URL")
key = config.get("SUPABASE_SERVICE_KEY") or config.get("SUPABASE_KEY")
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
    try:
        # Case 1: Already bytes
        if isinstance(img_data, bytes):
            return img_data
        
        # Case 2: Hex string from Postgres (\x...)
        if isinstance(img_data, str) and img_data.startswith('\\x'):
            return bytes.fromhex(img_data[2:])
        
        # Case 3: Base64 string (Common in web/IoT uploads)
        if isinstance(img_data, str):
            try:
                return base64.b64decode(img_data)
            except:
                # If not base64, try raw hex
                return bytes.fromhex(img_data)
        
        return None
    except Exception as e:
        print(f"Decoding error: {e}")
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
            # Find oldest image with no result
            response = supabase.table("images").select("*").is_("result", "null").order("created_at", desc=False).limit(1).execute()
            
            if response.data:
                record = response.data[0]
                image_id = record['id']
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Processing Image ID: {image_id}")
                
                img_hex = record['images']
                img_bytes = decode_image(img_hex)
                
                if img_bytes:
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    # CRITICAL: Verify img is NOT None before accessing attributes like .shape
                    if img is not None:
                        h, w = img.shape[:2]
                        if h > 0 and w > 0:
                            img = cv2.resize(img, (224, 224))
                            img_array = img_to_array(img)
                            img_array = np.expand_dims(img_array, axis=0) / 255.0
                            
                            predictions = model.predict(img_array)
                            class_idx = np.argmax(predictions[0])
                            confidence = float(np.max(predictions[0]) * 100)
                            result = CLASSES[class_idx] if class_idx < len(CLASSES) else "Unknown"
                            
                            summary = f"{result} ({confidence:.2f}%)"
                            print(f"Prediction Result: {summary}")
                            
                            # Update DB
                            supabase.table("images").update({"result": result}).eq("id", image_id).execute()
                            
                            # Publish Result to Edge
                            mqtt_client.publish(TOPIC_RESULT, f"ID {image_id}: {summary}")
                        else:
                            print(f"Error: Image ID {image_id} has zero dimensions ({w}x{h}).")
                            supabase.table("images").update({"result": "Error: Empty Dimensions"}).eq("id", image_id).execute()
                            mqtt_client.publish(TOPIC_RESULT, f"ID {image_id}: ERROR (Zero Dim)")
                    else:
                        print(f"Error: OpenCV imdecode returned None for ID {image_id}")
                        supabase.table("images").update({"result": "Error: Decode Fail"}).eq("id", image_id).execute()
                        mqtt_client.publish(TOPIC_RESULT, f"ID {image_id}: ERROR (OpenCV Decode)")
                else:
                    print(f"Failed to extract binary data for image {image_id}.")
                    supabase.table("images").update({"result": "Error: Extraction Fail"}).eq("id", image_id).execute()
                    mqtt_client.publish(TOPIC_RESULT, f"ID {image_id}: ERROR (Binary Fail)")
            
            time.sleep(POLL_INTERVAL)
                
        except Exception as e:
            print(f"Vision Brain Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_images()
