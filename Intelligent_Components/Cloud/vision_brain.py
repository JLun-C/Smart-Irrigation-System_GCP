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

def decode_image(hex_string):
    # Decode PG hex string to bytes
    # The format might be "\x..." or simply hex. 
    # psycopg2.Binary often stores as hex string in text output, but Supabase API might return it differently.
    # We assume standard base64/hex handling here or file text path.
    # For this PoC, we assume the 'images' column contains the HEX string of the binary.
    try:
        if hex_string.startswith('\\x'):
            hex_string = hex_string[2:]
        return bytes.fromhex(hex_string)
    except:
        return None

# Automation Interval (Manually change this: 20 for development, 21600 for 6h deployment)
POLL_INTERVAL = 20 

def process_images():
    print(f"Cloud Vision Service Started (Interval: {POLL_INTERVAL}s)...")
    
    # Setup MQTT Client
    mqtt_client = mqtt.Client()
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"MQTT Connection Error: {e}")

    while True:
        try:
            # Find images with no result or 'Pending'
            response = supabase.table("images").select("*").is_("result", "null").order("created_at", desc=False).limit(1).execute()
            
            if response.data:
                record = response.data[0]
                image_id = record['id']
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Processing Image ID: {image_id}")
                
                img_hex = record['images']
                img_bytes = decode_image(img_hex)
                
                if img_bytes:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                        tf.write(img_bytes)
                        tf_path = tf.name
                    
                    img = cv2.imread(tf_path)
                    
                    if img is not None:
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
                        print(f"Error: Image ID {image_id} could not be read by OpenCV.")
                        supabase.table("images").update({"result": "Error: Invalid Image"}).eq("id", image_id).execute()
                        mqtt_client.publish(TOPIC_RESULT, f"ID {image_id}: ERROR (Invalid Image)")

                    # Cleanup
                    if os.path.exists(tf_path):
                        os.remove(tf_path)
                else:
                    print(f"Failed to decode image {image_id}.")
                    supabase.table("images").update({"result": "Error: Decode Fail"}).eq("id", image_id).execute()
                    mqtt_client.publish(TOPIC_RESULT, f"ID {image_id}: ERROR (Decode Fail)")
            
            # Use configurable interval
            time.sleep(POLL_INTERVAL)
                
        except Exception as e:
            print(f"Vision Brain Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_images()
