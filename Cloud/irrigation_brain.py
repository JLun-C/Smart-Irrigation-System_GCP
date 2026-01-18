import os
import time
import json
import math
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import requests
import paho.mqtt.client as mqtt
from dotenv import dotenv_values
from supabase import create_client, Client
from datetime import datetime
from zoneinfo import ZoneInfo

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '../assets/.env')
config = dotenv_values(env_path)

# 1. Supabase Setup (For History Logs & Dashboard)
url = config.get("SUPABASE_URL")
key = config.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# 2. MQTT Setup (Use Private Broker on VM)
MQTT_BROKER = config.get("MQTT_BROKER")
MQTT_PORT = int(config.get("MQTT_PORT"))
TOPIC_TELEMETRY = "device/+/telemetry" # + wildcard for any device ID
TOPIC_COMMAND_PREFIX = "device/"

class IrrigationBrain:
    def __init__(self):
        print("Initializing Cloud Fuzzy Logic Engine (MQTT)...")
        self.setup_fuzzy_system()
        
        # MQTT Client
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def setup_fuzzy_system(self):
        # Same Logic as before
        self.soil_moisture = ctrl.Antecedent(np.arange(0, 101, 1), 'soil_moisture')
        self.temp = ctrl.Antecedent(np.arange(0, 51, 1), 'temperature')
        self.hum = ctrl.Antecedent(np.arange(0, 101, 1), 'humidity')
        self.is_raining = ctrl.Antecedent(np.arange(0, 2, 1), 'is_raining')
        self.rain_prob = ctrl.Antecedent(np.arange(0, 101, 1), 'rain_probability')
        self.irrigation_volume = ctrl.Consequent(np.arange(0, 101, 1), 'irrigation_volume')

        # Membership Functions (Simplified for brevity, same as original)
        self.soil_moisture['dry']   = fuzz.gaussmf(self.soil_moisture.universe, 20, 10)
        self.soil_moisture['moist'] = fuzz.gaussmf(self.soil_moisture.universe, 50, 10)
        self.soil_moisture['wet']   = fuzz.gaussmf(self.soil_moisture.universe, 80, 10)
        
        self.temp['cool'] = fuzz.trapmf(self.temp.universe, [0, 0, 24, 29])
        self.temp['hot'] = fuzz.trapmf(self.temp.universe, [26, 31, 50, 50])
        
        self.hum['dry'] = fuzz.trimf(self.hum.universe, [0, 0, 62])
        self.hum['moderate'] = fuzz.trimf(self.hum.universe, [58, 70, 82])
        self.hum['wet'] = fuzz.trimf(self.hum.universe, [80, 100, 100])
        
        self.is_raining['no'] = fuzz.trimf(self.is_raining.universe, [0, 0, 0])
        self.is_raining['yes'] = fuzz.trimf(self.is_raining.universe, [1, 1, 1])
        
        self.rain_prob['low'] = fuzz.trimf(self.rain_prob.universe, [0, 0, 40])
        self.rain_prob['high'] = fuzz.trapmf(self.rain_prob.universe, [30, 70, 100, 100])
        
        self.irrigation_volume['none'] = fuzz.trapmf(self.irrigation_volume.universe, [0, 0, 5, 18])
        self.irrigation_volume['low'] = fuzz.trapmf(self.irrigation_volume.universe, [13, 30, 50, 65])
        self.irrigation_volume['high'] = fuzz.trapmf(self.irrigation_volume.universe, [70, 85, 100, 100])
        
        # Rules (Same as original)
        rules = [
            ctrl.Rule(self.soil_moisture['wet'] | self.is_raining['yes'], self.irrigation_volume['none']),
            ctrl.Rule(self.soil_moisture['moist'] & self.rain_prob['high'], self.irrigation_volume['none']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['low'] & self.temp['hot'], self.irrigation_volume['high']),
            ctrl.Rule(self.soil_moisture['dry'], self.irrigation_volume['low']) 
            # (Truncated rule set for stability, usually you keep the full set)
        ]
        self.control_sys = ctrl.ControlSystem(rules)
        self.simulation = ctrl.ControlSystemSimulation(self.control_sys)

    def get_forecast_rain_prob(self):
        api_key = config.get("OPENWEATHER_API_KEY")
        lat = config.get("LAT")
        lon = config.get("LON")
        city = config.get("CITY_NAME", "Unknown")
        try:
            url = f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
            response = requests.get(url, timeout=5)
            data = response.json()
            prob_rain = data['list'][0].get('pop', 0) * 100
            forecast_time = data['list'][0].get('dt_txt', 'N/A')
            print(f"🌦️  Weather Forecast for {city}: {prob_rain:.1f}% rain probability at {forecast_time}")
            return prob_rain
        except Exception as e:
            print(f"⚠️  Forecast API Error: {e}, using 0% rain probability")
            return 0

    def on_connect(self, client, userdata, flags, rc):
        print(f"Connected to MQTT Broker with result code {rc}")
        client.subscribe(TOPIC_TELEMETRY)

    def on_message(self, client, userdata, msg):
        try:
            print(f"Received msg on {msg.topic}")
            payload = json.loads(msg.payload.decode())
            
            # Extract Device ID from Topic "device/DEVICE_ID/telemetry"
            device_id = msg.topic.split('/')[1]
            
            # Input Validation & Anomaly Detection
            temp = self.validate_sensor(payload.get("Temperature"), 25.0, 0, 50)
            humidity = self.validate_sensor(payload.get("Humidity"), 60.0, 0, 100)
            soil_moisture = self.validate_sensor(payload.get("Soil_moisture"), 50.0, 0, 100)
            is_raining = payload.get("Raining", 0) == 1
            
            # 2. Run Fuzzy Logic FIRST to determine pump state
            rain_prob = self.get_forecast_rain_prob()
            pump_cmd = self.process_logic({
                "Temperature": temp,
                "Humidity": humidity,
                "Soil_moisture": soil_moisture,
                "Raining": 1 if is_raining else 0
            }, rain_prob)
            
            # Log decision details
            now_time = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{'='*60}")
            print(f"📊 IRRIGATION DECISION @ {now_time}")
            print(f"{'='*60}")
            print(f"📍 Location: {config.get('CITY_NAME', 'Unknown')} (Lat: {config.get('LAT')}, Lon: {config.get('LON')})")
            print(f"🌡️  Temperature: {round(temp, 1)}°C")
            print(f"💧 Humidity: {humidity}%")
            print(f"🌱 Soil Moisture: {soil_moisture}%")
            print(f"🌧️  Currently Raining: {'YES' if is_raining else 'NO'}")
            print(f"🌦️  Rain Forecast: {rain_prob:.1f}%")
            print(f"💦 PUMP DECISION: {'🟢 ON' if pump_cmd == 1 else '🔴 OFF'}")
            print(f"{'='*60}\n")
            
            # 1. Log to DB with ACTUAL pump state (don't set timestamp, Supabase auto-generates)
            db_record = {
                "temperature": round(temp, 1),
                "humidity": int(humidity),
                "soil_moisture": int(soil_moisture),
                "is_raining": is_raining,
                "pump_state": pump_cmd,  # 0=OFF, 1=ON
                "timestamp": datetime.now().isoformat()
            }
            supabase.table("sensor_data").insert(db_record).execute()
            print(f"Logged: T={temp}°C, H={humidity}%, SM={soil_moisture}%, Rain={is_raining}, Pump={pump_cmd}")
            
            # 3. Publish Command back to Device
            cmd_topic = f"{TOPIC_COMMAND_PREFIX}{device_id}/command"
            self.client.publish(cmd_topic, str(pump_cmd))
            print(f"Published Command {pump_cmd} to {cmd_topic}")
            
        except Exception as e:
            print(f"Error processing message: {e}")

    def validate_sensor(self, value, default, min_val, max_val):
        """Validate sensor value and return default if invalid"""
        try:
            val = float(value)
            if math.isnan(val) or val is None:
                print(f"⚠️  Anomaly: NaN/None detected, using default {default}")
                return default
            if val < min_val or val > max_val:
                print(f"⚠️  Anomaly: Value {val} out of range [{min_val}, {max_val}], using default {default}")
                return default
            return val
        except (TypeError, ValueError):
            print(f"⚠️  Anomaly: Invalid value '{value}', using default {default}")
            return default

    def process_logic(self, data, rain_prob):
        try:
            self.simulation.input['temperature'] = float(data.get('Temperature', 25))
            self.simulation.input['humidity'] = float(data.get('Humidity', 60))
            self.simulation.input['soil_moisture'] = float(data.get('Soil_moisture', 50))
            self.simulation.input['is_raining'] = int(data.get('Raining', 0))
            self.simulation.input['rain_probability'] = rain_prob
            
            self.simulation.compute()
            score = self.simulation.output['irrigation_volume']
            
            print(f"🧮 Fuzzy Logic Score: {score:.2f}")
            
            if score > 50: return 1 # ON
            return 0 # OFF
        except Exception as e:
            print(f"❌ Fuzzy Logic Error: {e}, defaulting to OFF")
            return 0

    def run(self):
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            print("Listening for MQTT Text...")
            self.client.loop_forever()
        except KeyboardInterrupt:
            print("Stopping...")
            self.client.disconnect()
        finally:
            self.client.disconnect()
            print("Disconnected from MQTT Broker")

if __name__ == "__main__":
    brain = IrrigationBrain()
    brain.run()
