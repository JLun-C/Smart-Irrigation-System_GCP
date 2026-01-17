# System Design Document - Smart Irrigation System (IoT)

## 1. System Architecture
The Smart Irrigation System is an IoT application designed to optimize water usage in algaculture. It leverages a fuzzy logic inference system to make intelligent irrigation decisions based on real-time sensor data and weather forecasts.

### High-Level Architecture
```mermaid
graph LR
    subgraph Device Layer
        Note[Simulated/Physical ESP32] --> Logic[Intelligent Component (Fuzzy Logic)]
        Sensors[Sensors: Temp, Hum, Soil] -.-> Note
    end
    
    subgraph "Data & Logic Layer"
        Logic --"Push Data"--> DB[(Supabase Database)]
        OpenWeather[OpenWeatherMap API] --"Forecast Data"--> Logic
    end
    
    subgraph Application Layer
        DB --> Dashboard[Streamlit Dashboard]
        User((User)) --"View"--> Dashboard
    end
```

### Component Description
1.  **IoT Device (ESP32 / Simulator)**:
    -   Collects environmental data (Temperature, Humidity, Soil Moisture, Rain Status).
    -   In **Simulation Mode**, it generates realistic mock data to verify system logic without hardware.
    -   Communicates with the Intelligent Component via Serial (or direct integration in simulation).

2.  **Intelligent Component (Fuzzy Logic Model)**:
    -   **File**: `Intelligent_Components/fuzzy_logic_model.py`
    -   **Role**: Acts as an Edge Gateway. It aggregates local sensor data and fetches forecasted rain probability from OpenWeatherMap.
    -   **Decision Engine**: Uses the `scikit-fuzzy` library to compute an "Irrigation Volume" score (0-100) based on inputs.
    -   **Output**: Controls the pump (OFF/LOW/HIGH) and pushes telemetry to the Cloud Database.

3.  **Cloud Database (Supabase)**:
    -   **Role**: Stores historical sensor data and decision logs.
    -   **Tables**: `sensor_data`, `weather_data`.
    -   **Why Supabase?**: Provides a scalable PostgreSQL database with real-time capabilities and simple REST/Client API, suitable for rapid prototyping (PoC).

4.  **Dashboard (Streamlit)**:
    -   **File**: `Intelligent_Components/dashboard.py`
    -   **Role**: Visualizes real-time status and historical trends.
    -   **Features**: Displays metrics, charts for soil moisture/temperature, and latest weather forecast.

## 2. Design Considerations

### Decisions & Trade-offs
-   **Fuzzy Logic vs. Thresholds**:
    -   *Choice*: Fuzzy Logic.
    -   *Reason*: Agriculture is complex. A simple threshold (e.g., "Water if moisture < 30%") is inefficient. Fuzzy logic handles ambiguity (e.g., "Hot but Dry with High Rain Probability") better.
    -   *Trade-off*: Higher computational cost than simple if-else statements, but justifiable for precision agriculture.

-   **Supabase vs. GCP (Project Requirement)**:
    -   *Choice*: Supabase (for this Proof of Concept).
    -   *Reason*: Faster setup time and lower latency for retrieving real-time updates in a PoC environment.
    -   *Note*: The architecture is modular. The database client in `fuzzy_logic_model.py` and `dashboard.py` can be swapped for GCP Firestore without changing the core business logic.

-   **Local vs. Cloud Intelligence**:
    -   *Choice*: Edge/Local Intelligence (Fuzzy Logic runs on the Gateway).
    -   *Reason*: Ensures the system can make decisions even if the internet connection is intermittent (though weather API requires internet, historical/default values are used as fallback).

## 3. Development Process

### Prerequisites
-   Python 3.9+
-   Supabase Project (URL & Key)
-   OpenWeatherMap API Key

### Setup
1.  **Install Dependencies**:
    ```bash
    pip install -r Intelligent_Components/requirements.txt
    ```
2.  **Configure Environment**:
    -   Create `.env` file with `SUPABASE_URL`, `SUPABASE_KEY`, `OPENWEATHER_API_KEY`, `LAT`, `LON`.

### Running the Application
1.  **Start the Logic/Simulator**:
    ```bash
    python Intelligent_Components/fuzzy_logic_model.py --simulate
    ```
    -   This script will simulate sensor readings, calculate irrigation needs, and push data to the cloud.

2.  **Start the Dashboard**:
    ```bash
    streamlit run Intelligent_Components/dashboard.py
    ```
    -   Open the provided local URL (e.g., `http://localhost:8501`) to view the system.

## 4. Security Considerations for Proof Of Concept

-   **Environment Variables**: All sensitive keys (API Keys, Database Credentials) are stored in a `.env` file and **never committed** to version control (via `.gitignore`).
-   **Database Access**:
    -   The Supabase client uses a public API Key (Safe for client-side if RLS is on, but here used server-side).
    -   *Future Improvement*: Implement Row Level Security (RLS) policies to restrict write access only to authenticated devices.
-   **Input Validation**: The simulator checks for valid JSON ranges to prevent injection of malformed data.
