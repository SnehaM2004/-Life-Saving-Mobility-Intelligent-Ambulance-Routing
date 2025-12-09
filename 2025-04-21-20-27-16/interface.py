import streamlit as st
import plotly.graph_objs as go
import plotly.express as px
import traci
import threading
import time
import math
import pandas as pd

# --- SUMO + TraCI simulation params ---
sumoCmd = ["sumo-gui", "-c", "osm.sumocfg"]
PROACTIVE_DISTANCE = 100

# Global logs and data
time_log = []
ambulance_speed_log = []
vehicle_alert_count = []
traffic_light_control_log = []
stopped_vehicle_counts = []
simulation_times = []
vehicle_data = {}  # dict: veh_id -> {speed, class, position, stopped, is_ambulance}
log_lock = threading.Lock()

# Distance helper
def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

# Simulation function runs in background thread
def run_simulation():
    traci.start(sumoCmd)
    step = 0
    original_tl_programs = {}

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        vehicles = traci.vehicle.getIDList()
        ambulances = [v for v in vehicles if "ambulance" in v.lower() or traci.vehicle.getVehicleClass(v) == "emergency"]

        total_alerted_this_step = 0
        traffic_lights_controlled = 0

        # Update vehicle_data for all vehicles
        with log_lock:
            vehicle_data.clear()

        for amb_id in ambulances:
            amb_pos = traci.vehicle.getPosition(amb_id)
            amb_edge = traci.vehicle.getRoadID(amb_id)
            amb_speed = traci.vehicle.getSpeed(amb_id)
            traci.vehicle.setColor(amb_id, (255, 0, 0, 255))
            traci.vehicle.setSpeedMode(amb_id, 0)  # ignore traffic light red

            # V2I: Traffic light control
            junctions = traci.trafficlight.getIDList()
            controlled_this_ambulance = 0
            for tl in junctions:
                controlled_lanes = traci.trafficlight.getControlledLanes(tl)
                if any(amb_edge in lane for lane in controlled_lanes):
                    controlled_this_ambulance += 1
                    if tl not in original_tl_programs:
                        original_tl_programs[tl] = traci.trafficlight.getProgram(tl)
                    original_state = traci.trafficlight.getRedYellowGreenState(tl)
                    state = ''
                    for lane in controlled_lanes:
                        if amb_edge in lane:
                            state += 'G'
                        else:
                            state += 'r'
                    if len(state) == len(original_state):
                        traci.trafficlight.setRedYellowGreenState(tl, state)
            traffic_lights_controlled += controlled_this_ambulance

            # V2V: Alert vehicles in same lane ahead
            alerted_vehicles_in_step = 0
            for veh_id in vehicles:
                if veh_id == amb_id or traci.vehicle.getVehicleClass(veh_id) == "emergency":
                    continue
                veh_edge = traci.vehicle.getRoadID(veh_id)
                veh_lane = traci.vehicle.getLaneIndex(veh_id)
                amb_lane_index = traci.vehicle.getLaneIndex(amb_id)
                veh_pos = traci.vehicle.getPosition(veh_id)

                if veh_edge == amb_edge and veh_lane == amb_lane_index:
                    dist = distance(amb_pos, veh_pos)
                    if 0 < dist < PROACTIVE_DISTANCE and veh_pos[0] > amb_pos[0]:
                        alerted_vehicles_in_step += 1

            total_alerted_this_step += alerted_vehicles_in_step

            with log_lock:
                time_log.append(step)
                ambulance_speed_log.append(amb_speed)
                vehicle_alert_count.append(total_alerted_this_step)
                traffic_light_control_log.append(traffic_lights_controlled)

        # Update vehicle_data for all vehicles including ambulances
        with log_lock:
            for veh_id in vehicles:
                speed = traci.vehicle.getSpeed(veh_id)
                vclass = traci.vehicle.getVehicleClass(veh_id)
                pos = traci.vehicle.getPosition(veh_id)
                stopped = speed < 0.1  # stopped threshold
                is_ambulance = ("ambulance" in veh_id.lower() or vclass == "emergency")
                vehicle_data[veh_id] = {
                    "speed": speed,
                    "class": vclass,
                    "position": pos,
                    "stopped": stopped,
                    "is_ambulance": is_ambulance
                }
            stopped_count = sum(1 for v in vehicle_data.values() if v["stopped"] and not v["is_ambulance"])
            stopped_vehicle_counts.append(stopped_count)
            simulation_times.append(step)

        step += 1

    traci.close()

# --- Streamlit UI setup ---
st.set_page_config(page_title="🚑 V2V Ambulance Simulation Dashboard", layout="wide")

# CSS for dark theme & styling
st.markdown("""
    <style>
    body {
        background-color: #0e0e0e;
        color: #00ffd0;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .block-container {
        padding: 1rem 2rem;
        border-radius: 12px;
        background: #181818;
        box-shadow: 0 0 15px #00ffd0aa;
    }
    h1, h2 {
        text-align: center;
        color: #00ffd0;
        margin-bottom: 20px;
    }
    .stButton>button {
        background-color: #00ffd0;
        color: #000;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.6em 1.2em;
        margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🚑 Real-Time V2V Ambulance Simulation Dashboard")

# Button to start simulation
if st.button("▶ Start Simulation"):
    st.info("Starting SUMO simulation... Please wait.")
    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()
    time.sleep(2)  # Give time for simulation to start

# Placeholders for plots and vehicle data table
speed_chart = st.empty()
alert_chart = st.empty()
tl_chart = st.empty()
vehicle_table_placeholder = st.empty()
stop_vehicle_chart_placeholder = st.empty()

# Live plotting loop
for _ in range(1000):  # Run approx 1000 steps (adjust as needed)
    time.sleep(0.5)
    with log_lock:
        if not time_log:
            continue

        # Ambulance Speed vs Time
        fig_speed = go.Figure()
        fig_speed.add_trace(go.Scatter(x=time_log, y=ambulance_speed_log,
                                       mode='lines+markers', line=dict(color='lime'), name='Ambulance Speed (m/s)'))
        fig_speed.update_layout(title='🚑 Ambulance Speed vs Simulation Time',
                                xaxis_title='Simulation Step',
                                yaxis_title='Speed (m/s)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='#181818',
                                font=dict(color='lime'))
        speed_chart.plotly_chart(fig_speed, use_container_width=True)

        # Number of Vehicles Alerted vs Time
        fig_alert = go.Figure()
        fig_alert.add_trace(go.Scatter(x=time_log, y=vehicle_alert_count,
                                      mode='lines+markers', line=dict(color='orange'), name='Vehicles Alerted'))
        fig_alert.update_layout(title='📡 Vehicles Alerted vs Simulation Time',
                                xaxis_title='Simulation Step',
                                yaxis_title='Number of Vehicles Alerted',
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='#181818',
                                font=dict(color='orange'))
        alert_chart.plotly_chart(fig_alert, use_container_width=True)

        # Traffic Lights Controlled vs Time
        fig_tl = go.Figure()
        fig_tl.add_trace(go.Scatter(x=time_log, y=traffic_light_control_log,
                                    mode='lines+markers', line=dict(color='cyan'), name='Traffic Lights Controlled'))
        fig_tl.update_layout(title='🚦 Traffic Lights Controlled vs Simulation Time',
                             xaxis_title='Simulation Step',
                             yaxis_title='Number of Traffic Lights',
                             plot_bgcolor='rgba(0,0,0,0)',
                             paper_bgcolor='#181818',
                             font=dict(color='cyan'))
        tl_chart.plotly_chart(fig_tl, use_container_width=True)

        # -- New: Live Vehicle Table --
        df_vehicles = pd.DataFrame.from_dict(vehicle_data, orient='index')
        if not df_vehicles.empty:
            df_vehicles_display = df_vehicles.copy()
            df_vehicles_display["speed"] = df_vehicles_display["speed"].map(lambda x: f"{x:.2f} m/s")
            df_vehicles_display["position"] = df_vehicles_display["position"].map(lambda p: f"({p[0]:.1f},{p[1]:.1f})")
            df_vehicles_display["stopped"] = df_vehicles_display["stopped"].map({True: "Yes", False: "No"})
            df_vehicles_display["is_ambulance"] = df_vehicles_display["is_ambulance"].map({True: "Yes", False: "No"})
            df_vehicles_display.rename(columns={
                "speed": "Speed",
                "class": "Class",
                "position": "Position",
                "stopped": "Stopped",
                "is_ambulance": "Is Ambulance"
            }, inplace=True)
            vehicle_table_placeholder.dataframe(df_vehicles_display)

        # -- New: Vehicles Stopping vs Ambulance Passing Graph --
        fig_stops = px.line(
            x=simulation_times,
            y=stopped_vehicle_counts,
            labels={'x': 'Simulation Step', 'y': 'Vehicles Stopped'},
            title='🚗 Vehicles Stopping vs Ambulance Passing',
            line_shape="linear",
        )
        fig_stops.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='#181818', font=dict(color='orange'))
        stop_vehicle_chart_placeholder.plotly_chart(fig_stops, use_container_width=True)
