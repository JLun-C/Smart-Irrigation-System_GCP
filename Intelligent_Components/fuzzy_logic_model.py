import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import requests
import os
import json
from datetime import datetime, time
from dotenv import load_dotenv
import sys
import serial
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client, Client

class WeatherDecisionTester:
    def __init__(self):
        load_dotenv()
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        self.supabase: Client = create_client(supabase_url, supabase_key)

        # Stateful Fallbacks
        self.last_valid_temp = None
        self.last_valid_hum = None

        self.recover_last_readings()

        print("Initializing Fuzzy Logic System for Weather-Based Irrigation Decision...", flush=True)
        # 1. Setup Fuzzy Variables
        self.soil_moisture = ctrl.Antecedent(np.arange(0, 101, 1), 'soil_moisture')
        self.temp = ctrl.Antecedent(np.arange(0, 51, 1), 'temperature')
        self.hum = ctrl.Antecedent(np.arange(0, 101, 1), 'humidity')
        self.is_raining = ctrl.Antecedent(np.arange(0, 2, 1), 'is_raining')
        self.rain_prob = ctrl.Antecedent(np.arange(0, 101, 1), 'rain_probability')

        self.irrigation_volume = ctrl.Consequent(np.arange(0, 101, 1), 'irrigation_volume')

        # 2. Membership Functions
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

        # 3. Fuzzy Rules
        rules = [
            ctrl.Rule(self.soil_moisture['wet'] | self.is_raining['yes'], self.irrigation_volume['none']),
            ctrl.Rule(self.soil_moisture['moist'] & self.rain_prob['high'], self.irrigation_volume['none']),
            ctrl.Rule(self.soil_moisture['moist'] & self.rain_prob['low'] & self.temp['hot'] & self.hum['wet'], self.irrigation_volume['none']),
            ctrl.Rule(self.soil_moisture['moist'] & self.rain_prob['low'] & self.temp['hot'] & self.hum['moderate'], self.irrigation_volume['low']),
            ctrl.Rule(self.soil_moisture['moist'] & self.rain_prob['low'] & self.temp['hot'] & self.hum['dry'], self.irrigation_volume['low']),
            ctrl.Rule(self.soil_moisture['moist'] & self.rain_prob['low'] & self.temp['cool'], self.irrigation_volume['low']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['high'], self.irrigation_volume['low']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['low'] & self.temp['hot'] & self.hum['wet'], self.irrigation_volume['low']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['low'] & self.temp['hot'] & self.hum['moderate'], self.irrigation_volume['high']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['low'] & self.temp['hot'] & self.hum['dry'], self.irrigation_volume['high']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['low'] & self.temp['cool'] & self.hum['wet'], self.irrigation_volume['none']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['low'] & self.temp['cool'] & self.hum['moderate'], self.irrigation_volume['low']),
            ctrl.Rule(self.soil_moisture['dry'] & self.rain_prob['low'] & self.temp['cool'] & self.hum['dry'], self.irrigation_volume['low'])
        ]
        self.control_sys = ctrl.ControlSystem(rules)
        self.simulation = ctrl.ControlSystemSimulation(self.control_sys)

    def recover_last_readings(self):
        try:
            response = self.supabase.table("sensor_data") \
                .select("temperature", "humidity") \
                .order("timestamp", desc=True) \
                .limit(1) \
                .execute()

            if response.data and len(response.data) > 0:
                last_record = response.data[0]
                self.last_valid_temp = last_record['temperature']
                self.last_valid_hum = last_record['humidity']
            else:
                print("No previous sensor data found. Using default values.", flush=True)
                # If the sensors failed to read and there is no previous data, use default values (annual average readings in Penang)
                self.last_valid_temp = 28.0
                self.last_valid_hum = 73.0
        except Exception as e:
            print(f"Error recovering last readings: {e}", flush=True)

    def push_to_database(self, sensor_data, weather_data):
        try:
            sensor_response = self.supabase.table("sensor_data").insert(sensor_data).execute()
            weather_response = self.supabase.table("weather_data").insert(weather_data).execute()
            print("Successfully pushed to database.")
        except Exception as e:
            print(f"Database Error: {e}")

    def get_forecast_rain_prob(self):
        load_dotenv()
        api_key = os.getenv("OPENWEATHER_API_KEY")
        lat = os.getenv("LAT")
        lon = os.getenv("LON")

        url = f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"

        try:
            response = requests.get(url)
            data = response.json()

            # Accessing the first 3-hour forecast block
            next_block = data['list'][0]

            # 'pop' is Probability of Precipitation (0.0 to 1.0)
            prob_rain = next_block.get('pop', 0) * 100 
            dt_unix = next_block['dt']

            f_time = datetime.fromtimestamp(dt_unix).strftime('%H%M%S')

            print(f"Location: {data['city']['name']}")
            print(f"Forecast - Rain Prob: {prob_rain}%")

            return prob_rain, f_time

        except Exception as e:
            print(f"Forecast API Error: {e}")
            return 0, "000000"


    def compute_decision(self, sensor_data):
        p_rain, f_time = self.get_forecast_rain_prob()
        current_t = sensor_data['Temperature']
        current_h = sensor_data['Humidity']
        sm = sensor_data['Soil_moisture']
        is_r = sensor_data['Raining']

        # Validate and use last known good readings if necessary
        if current_t is None or np.isnan(current_t):
            t = self.last_valid_temp
        else:
            t = current_t
            self.last_valid_temp = t

        if current_h is None or np.isnan(current_h):
            h = self.last_valid_hum
        else:
            h = current_h
            self.last_valid_hum = h

        print(f"\n--- Decision Cycle: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        print(f"\n--- Real-Time Weather for Penang ---")
        print(f"Local Sensor Data - Temp: {t}°C, Humidity: {h}%, Soil Moisture: {sm}%, Is Raining: {'Yes' if is_r else 'No'}")
        print("API Forecast Data - Next 3h Rain Probability: "f"{p_rain}% at {f_time[:2]}:{f_time[2:4]}:{f_time[4:]}")

        self.simulation.input['temperature'] = t
        self.simulation.input['humidity'] = h
        self.simulation.input['soil_moisture'] = sm
        self.simulation.input['is_raining'] = 1 if is_r else 0
        self.simulation.input['rain_probability'] = p_rain
        self.simulation.compute()

        decision_score = self.simulation.output['irrigation_volume']

        print(f"Final Irrigation Score: {decision_score:.2f}/100")
        if decision_score > 65:
            pump_state = 2
        elif decision_score > 15:
            pump_state = 1
        else:
            pump_state = 0

        sensor_data_record = {
            "timestamp": datetime.now().isoformat(),
            "temperature": round(t, 1),
            "humidity": h,
            "soil_moisture": sm,
            "is_raining": bool(is_r),
            "pump_state": pump_state
        }

        now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))
        forecast_time = now.replace(hour=int(f_time[:2]), minute=int(f_time[2:4]), second=int(f_time[4:]))
        if forecast_time < now:
            forecast_time += timedelta(days=1)

        weather_data_record = {
            "rain_probability": p_rain,
            "forecast_time": forecast_time.isoformat(),
            "created_at": datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).isoformat()
        }

        self.push_to_database(sensor_data_record, weather_data_record)

        return pump_state

if __name__ == "__main__":
    print("Script started...", flush=True)

    SERIAL_PORT = "COM4"
    BAUD_RATE = 115200

    tester = WeatherDecisionTester()

    try: 
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Connected to ESP32 on {SERIAL_PORT}", flush=True)
    except Exception as e:
        print(f"Serial Connection Error: {e}", flush=True)
        sys.exit(1)

    print("Listening for sensor data from ESP32...", flush=True)

    while True:
        try:

            if ser is None or not ser.is_open:
                print(f"Connecting to ESP32 on {SERIAL_PORT}...", end=" ", flush=True)
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
                print("CONNECTED.")
                time.sleep(2)
            
            while ser.is_open:
                line = ser.readline().decode('utf-8').strip()

                if line.startswith('{') and line.endswith('}'):
                    arduino_data = json.loads(line)
                    state = tester.compute_decision(arduino_data)

                    # Send decision back to ESP32
                    ser.write(f"{state}\n".encode('utf-8'))
                    print(f"Sent to ESP32: {state}", flush=True)
                else:
                    continue

        except json.JSONDecodeError:
            print("JSON Decode Error: Invalid JSON format", flush=True)
        except (serial.SerialException, serial.PortNotOpenError) as e:
            print(f"\n⚠️ Serial Port Error: {e}")
            print("ESP32 might have disconnected or reset. Retrying in 5 seconds...")
            if ser:
                ser.close()
            time.sleep(5)
        except KeyboardInterrupt:
            print("Exiting on user request.", flush=True)
            if ser and ser.is_open:
                try:
                    ser.write(b"0\n")  # Safety: Turn off pump
                    ser.close()
                except:
                    pass
            break
        except Exception as e:
            print(f"Error: {e}", flush=True)
            time.sleep(5)
        finally: 
            if 'ser' in locals() and ser.is_open:
                ser.close()
                print("Serial connection closed safely.")
