import traci
import xml.etree.ElementTree as ET
import math

# Launch SUMO simulation with your configuration
sumoCmd = ["sumo", "-c", "osm.sumocfg", "--start", "--quit-on-end"]
traci.start(sumoCmd)

print("🚑 Scanning for edges used by emergency vehicles...")

# Step 1: Identify edges traveled by emergency vehicles (ambulances)
emergency_edges = set()

# Try to catch ambulances directly (if already spawned)
for veh_id in traci.vehicle.getIDList():
    if traci.vehicle.getVehicleClass(veh_id) == "emergency":
        route = traci.vehicle.getRoute(veh_id)
        emergency_edges.update(route)

# If no vehicles found yet (flows not started), simulate for a few steps
if not emergency_edges:
    print("⚠️ No emergency vehicles detected initially. Advancing simulation to detect flows...")
    for _ in range(200):  # Run ~20s of simulation (if step-length=0.1s)
        traci.simulationStep()
        for veh_id in traci.vehicle.getIDList():
            if traci.vehicle.getVehicleClass(veh_id) == "emergency":
                emergency_edges.update(traci.vehicle.getRoute(veh_id))

print(f"📍 Found {len(emergency_edges)} unique ambulance-route edges")

# Step 2: Place RSUs (induction loops) on each ambulance lane
rsu_list = []
for edge_id in emergency_edges:
    lane_id = edge_id + "_0"
    if lane_id in traci.lane.getIDList():
        lane_length = traci.lane.getLength(lane_id)
        pos = max(1, min(lane_length / 2, lane_length - 1))  # place at center-ish
        rsu_list.append((lane_id, pos))

print(f"✅ Placing {len(rsu_list)} RSUs on ambulance lanes")

# Step 3: Write RSUs to osm.add.xml
root = ET.Element("additional")
for i, (lane_id, pos) in enumerate(rsu_list):
    rsu_id = f"rsu_{i}"
    ET.SubElement(root, "inductionLoop",
                  id=rsu_id,
                  lane=lane_id,
                  pos=str(pos),
                  freq="1",
                  file="ev_detection_output.xml")

tree = ET.ElementTree(root)
tree.write("osm.add.xml")

print("✅ RSU XML file created: osm.add.xml")

traci.close()
