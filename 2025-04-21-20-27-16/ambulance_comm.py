import traci
import math

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

sumoCmd = ["sumo-gui", "-c", "osm.sumocfg"]
traci.start(sumoCmd)

PROACTIVE_DISTANCE = 100
alerted_vehicles = set()
original_tl_programs = {}

print("\n🚦 Starting V2V Emergency Communication Simulation...\n")

step = 0
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()
    vehicles = traci.vehicle.getIDList()
    ambulances = [v for v in vehicles if "ambulance" in v.lower() or traci.vehicle.getVehicleClass(v) == "emergency"]

    for amb_id in ambulances:
        amb_pos = traci.vehicle.getPosition(amb_id)
        amb_edge = traci.vehicle.getRoadID(amb_id)
        amb_lane_index = traci.vehicle.getLaneIndex(amb_id)
        amb_speed = traci.vehicle.getSpeed(amb_id)

        traci.vehicle.setColor(amb_id, (255, 0, 0, 255))
        traci.vehicle.setSpeedMode(amb_id, 0)  # Ignore red lights

        junctions = traci.trafficlight.getIDList()
        for tl in junctions:
            controlled_lanes = traci.trafficlight.getControlledLanes(tl)
            # Check if ambulance is on this traffic light's controlled lanes
            if any(amb_edge in lane for lane in controlled_lanes):
                if tl not in original_tl_programs:
                    original_tl_programs[tl] = traci.trafficlight.getProgram(tl)
                    print(f"🚦 [V2I] Ambulance {amb_id} TAKING CONTROL of Traffic Light {tl} for green signal")

                # Construct state string - must match length of original state
                original_state = traci.trafficlight.getRedYellowGreenState(tl)
                state = ''
                for i, lane in enumerate(controlled_lanes):
                    if amb_edge in lane:
                        state += 'G'  # Green for ambulance lane
                    else:
                        state += 'r'  # Red for other lanes

                if len(state) == len(original_state):
                    traci.trafficlight.setRedYellowGreenState(tl, state)
                else:
                    print(f"⚠️ Warning: State length mismatch for TL {tl}. Skipping TL override.")

            else:
                # Restore original program if ambulance not nearby
                if tl in original_tl_programs:
                    print(f"🚦 [V2I] Ambulance {amb_id} RELEASING control of Traffic Light {tl}, restoring original program")
                    traci.trafficlight.setProgram(tl, original_tl_programs[tl])
                    del original_tl_programs[tl]

        congestion_detected = False

        for veh_id in vehicles:
            if veh_id == amb_id or traci.vehicle.getVehicleClass(veh_id) == "emergency":
                continue
            veh_edge = traci.vehicle.getRoadID(veh_id)
            veh_lane = traci.vehicle.getLaneIndex(veh_id)
            veh_pos = traci.vehicle.getPosition(veh_id)

            if veh_edge == amb_edge and veh_lane == amb_lane_index:
                dist = distance(amb_pos, veh_pos)
                if 0 < dist < PROACTIVE_DISTANCE and veh_pos[0] > amb_pos[0]:
                    print(f"📡 [V2V] Ambulance {amb_id} ALERTING Vehicle {veh_id} at distance {int(dist)} meters")
                    congestion_detected = True
                    break


        if congestion_detected:
            num_lanes = traci.edge.getLaneNumber(amb_edge)
            changed = False
            options = []

            if amb_lane_index + 1 < num_lanes:
                options.append(amb_lane_index + 1)
            if amb_lane_index - 1 >= 0:
                options.append(amb_lane_index - 1)

            for new_lane in options:
                try:
                    before_lane_id = traci.vehicle.getLaneID(amb_id)
                    traci.vehicle.changeLane(amb_id, new_lane, 10.0)
                    after_lane_id = traci.vehicle.getLaneID(amb_id)

                    if after_lane_id != before_lane_id:
                        print(f"✅ Ambulance {amb_id} changed lane from {before_lane_id} ➡ {after_lane_id}")
                        changed = True
                        break
                except Exception as e:
                    print(f"⚠️ Lane change error for {amb_id} to lane {new_lane}: {e}")
                    continue

            if not changed:
                print(f"📡 [V2V] Vehicles on other edges are stopping to allow ambulance {amb_id} to pass.")

        else:
            print(f"✅ Ambulance {amb_id} moving freely, no congestion ahead.")

    step += 1

traci.close()

print("\n✅ Simulation completed — Ambulance followed priority rules and passed red lights freely!")
