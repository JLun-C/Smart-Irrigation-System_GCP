import streamlit as st
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
from datetime import datetime
import time

# Load environment variables
load_dotenv()

# Page Config
st.set_page_config(
    page_title="Smart Agriculture Dashboard",
    page_icon="🌱",
    layout="wide"
)

# Initialize Supabase Connection
@st.cache_resource
def init_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    try:
        if not url or not key:
            st.error("Missing Supabase URL or Key in .env")
            return None
        return create_client(url, key)
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return None

supabase = init_supabase()

# --- SIDEBAR ---
st.sidebar.title("🌱 IoT Control Panel")
st.sidebar.markdown("---")
st.sidebar.subheader("System Status")
if supabase:
    st.sidebar.success("Database Connected")
else:
    st.sidebar.error("Database Disconnected")

auto_refresh = st.sidebar.checkbox("Auto Refresh (10s)", value=True)

# --- HEADER ---
st.title("🌾 Smart Agriculture Monitoring System")
st.markdown("Real-time monitoring of soil moisture, weather conditions, and plant health.")

# --- METRICS ROW ---
col1, col2, col3, col4 = st.columns(4)

def fetch_latest_sensor_data():
    if not supabase: return None
    try:
        response = supabase.table("sensor_data").select("*").order("timestamp", desc=True).limit(1).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        st.error(f"Error fetching sensor data: {e}")
    return None

data = fetch_latest_sensor_data()

if data:
    temp = data.get("temperature", 0)
    hum = data.get("humidity", 0)
    soil = data.get("soil_moisture", 0)
    rain = data.get("is_raining", False)
    pump = data.get("pump_state", 0) # 0=OFF, 1=LOW, 2=HIGH
    
    col1.metric("Temperature", f"{temp}°C")
    col2.metric("Humidity", f"{hum}%")
    col3.metric("Soil Moisture", f"{soil}%")
    col4.metric("Rain Status", "Raining 🌧️" if rain else "Clear ☀️")
    
    st.markdown("---")
    
    # Pump Status
    pump_status = {0: "OFF ⚪", 1: "LOW (Pulse) 🟡", 2: "HIGH (Heavy) 🔵"}
    st.subheader(f"💧 Pump Status: {pump_status.get(pump, 'Unknown')}")

else:
    st.warning("No sensor data available.")

# --- CHARTS ROW ---
st.subheader("📊 Environmental Trends")

def fetch_history_data(limit=50):
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("sensor_data").select("*").order("timestamp", desc=True).limit(limit).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
    except Exception as e:
        st.error(f"Error fetching history: {e}")
    return pd.DataFrame()

df = fetch_history_data()

if not df.empty:
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        fig_temp = px.line(df, x='timestamp', y=['temperature', 'humidity'], title='Temperature & Humidity Over Time')
        st.plotly_chart(fig_temp, use_container_width=True)
        
    with chart_col2:
        fig_soil = px.area(df, x='timestamp', y='soil_moisture', title='Soil Moisture Trends', color_discrete_sequence=['#2ecc71'])
        st.plotly_chart(fig_soil, use_container_width=True)

# --- WEATHER FORECAST ROW ---
st.subheader("🌦️ Weather Forecast (Rain Probability)")

def fetch_weather_forecast():
    if not supabase: return None
    try:
        response = supabase.table("weather_data").select("*").order("created_at", desc=True).limit(1).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        st.error(f"Error fetching weather data: {e}")
    return None

weather_data = fetch_weather_forecast()

if weather_data:
    prob = weather_data.get("rain_probability", 0)
    # Parse forecast time, handle ISO format errors if any
    f_time_str = weather_data.get("forecast_time", "")
    try:
        f_time = datetime.fromisoformat(f_time_str).strftime('%H:%M')
    except:
        f_time = f_time_str

    # Create a gauge chart for rain probability
    fig_gauge = px.bar(
        x=[prob], 
        y=["Rain Prob"], 
        orientation='h', 
        range_x=[0, 100], 
        text=[f"{prob}%"],
        color=[prob],
        color_continuous_scale=['#87CEEB', '#1E90FF', '#00008B']
    )
    fig_gauge.update_layout(title=f"Next Rain Probability (at {f_time})", xaxis_title="Probability (%)", yaxis_title="", showlegend=False, height=200)
    st.plotly_chart(fig_gauge, use_container_width=True)
else:
    st.info("No weather forecast data available.")


# --- IMAGES ROW ---
st.subheader("🍃 Leaf Disease Detection")

def fetch_latest_image():
    if not supabase: return None
    try:
        # Assuming table 'images' with columns: id, created_at, result (text), images (bytea or url)
        # Note: If images are stored as BYTEA (binary) in Postgres, Streamlit might be slow to load them directly.
        # Ideally, images should be in Storage buckets and this table just processes the result.
        # For assignment purposes, we query the latest result.
        response = supabase.table("images").select("result, created_at").order("created_at", desc=True).limit(1).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        st.error(f"Error fetching image result: {e}")
    return None

img_data = fetch_latest_image()

if img_data:
    st.info(f"Latest Analysis: **{img_data.get('result', 'Unknown')}** at {img_data.get('created_at')}")
else:
    st.write("No disease detection logs found.")

# Refresh Logic
if auto_refresh:
    time.sleep(10)
    st.rerun()
