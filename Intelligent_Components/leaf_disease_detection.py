import os
import cv2
import numpy as np
import psycopg2
from keras.models import load_model
import tensorflow as tf
from tensorflow.keras.utils import load_img, img_to_array
from PIL import Image
from dotenv import load_dotenv
import time

class LeafDiseaseDetector:
    def __init__(self, model_path, db_config):
        self.model = load_model(model_path)
        self.db_config = db_config
        self.classes = ['Healthy', 'Powdery', 'Rust']

    def capture_image(self, image_path):
        cap = cv2.VideoCapture(0)  # Open the default camera
        if not cap.isOpened():
            print("Error: Could not open camera.")
            return False
        ret, frame = cap.read()  # Capture a single frame
        cap.release()  # Release the camera
        if ret:
            cv2.imwrite(image_path, frame)  # Save the captured frame as an image file
            print(f"Picture taken and saved as '{image_path}'.")
            return True
        else:
            print("Error: Could not read frame.")
            return False

    def preprocess_image(self, image_path):
        img = load_img(image_path, target_size=(224, 224))
        img_array = img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)

        # Scale pixels to [0, 1]
        return img_array / 255.0

    def predict(self, img_array):
        predictions = self.model.predict(img_array)
        class_idx = np.argmax(predictions[0])
        confidence = np.max(predictions[0]) * 100

        classes = self.classes
        result = classes[class_idx] if class_idx < len(classes) else "Unknown"
        
        print(f"Prediction: {result} (Confidence: {confidence:.2f}%)")
        return result

    def insert_image_to_db(self, image_path, predicted_class):
        connection = None
        cursor = None
        try:
            connection = psycopg2.connect(**self.db_config)
            cursor = connection.cursor()
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
            insert_query = "INSERT INTO images (images, result) VALUES (%s, %s);"
            cursor.execute(insert_query, (psycopg2.Binary(image_data), predicted_class))
            connection.commit()
            print("Database: Image and result inserted successfully.")
        except Exception as e:
            print(f"Database: Failed to insert image: {e}")
        finally:
            cursor.close()
            connection.close()
            print("Database: Connection closed.")
            
    def run_monitoring_loop(self, image_path, interval_minutes=0.2):
        print(f"Starting continuous monitoring every {interval_minutes} minutes...")
        try:
            while True:
                print("\n--- Starting new monitoring cycle ---")
                if self.capture_image(image_path):
                    test_img_array = self.preprocess_image(image_path)
                    predicted_class = self.predict(test_img_array)
                    print(f'Predicted class: {predicted_class}')
                    self.insert_image_to_db(image_path, predicted_class)

                print(f"Waiting for {interval_minutes} minutes before next capture...")
                time.sleep(interval_minutes * 60)  # Convert minutes to seconds
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        except Exception as e:
            print(f"\nAn error occurred: {e}")

def main():
    load_dotenv()

    # Database configuration
    db_config = {
        'user': "postgres.eeiazmvadvbflsuulcpz",
        'password': "357IIooTT202526^^",
        'host': "aws-1-ap-south-1.pooler.supabase.com",
        'port': "6543",
        'dbname': "postgres"
    }

    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, 'leaf_disease_detection_model.keras')
    image_path = os.path.join(script_dir, 'snapshot.jpg')
    detector = LeafDiseaseDetector(model_path, db_config)

    # For testing purposes, run loop with 1-minute interval
    detector.run_monitoring_loop(image_path, interval_minutes=0.2)

if __name__ == "__main__":
    main()