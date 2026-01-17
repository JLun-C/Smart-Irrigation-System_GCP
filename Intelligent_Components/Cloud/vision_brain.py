import os
import time
import numpy as np
import cv2
import base64
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

def process_images():
    print("Cloud Vision Service Started...")
    while True:
        try:
            # Find images with no result or 'Pending'
            response = supabase.table("images").select("*").is_("result", "null").limit(1).execute()
            
            if response.data:
                record = response.data[0]
                image_id = record['id']
                print(f"Processing Image ID: {image_id}")
                
                # Retrieve Image Content
                # NOTE: In production, use Storage Buckets. Here assuming bytea column.
                img_hex = record['images'] # Supabase returns bytea as hex string
                img_bytes = decode_image(img_hex)
                
                if img_bytes:
                    # Save to temp file for Keras
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                        tf.write(img_bytes)
                        tf_path = tf.name
                    
                    # Predict
                    img = cv2.imread(tf_path)
                    img = cv2.resize(img, (224, 224))
                    img_array = img_to_array(img)
                    img_array = np.expand_dims(img_array, axis=0) / 255.0
                    
                    predictions = model.predict(img_array)
                    class_idx = np.argmax(predictions[0])
                    confidence = float(np.max(predictions[0]) * 100)
                    result = CLASSES[class_idx] if class_idx < len(CLASSES) else "Unknown"
                    
                    print(f"Prediction: {result} ({confidence:.2f}%)")
                    
                    # Update DB
                    supabase.table("images").update({"result": result}).eq("id", image_id).execute()
                    
                    # Cleanup
                    os.remove(tf_path)
                else:
                    print("Failed to decode image.")
                    supabase.table("images").update({"result": "Error"}).eq("id", image_id).execute()
                    
            else:
                time.sleep(2)
                
        except Exception as e:
            print(f"Vision Brain Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_images()
