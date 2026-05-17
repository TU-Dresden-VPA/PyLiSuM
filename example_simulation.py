# Import SUMO
from sumolib import checkBinary
import traci
# Import Python Standard Libraries
from collections import deque
import math
import random
from pathlib import Path
# Import Third-Party Libraries
import yaml
from PyLiSuM.middleware import LisaInterfaceManager

SUMO_DIR = Path("SUMO_Files")
SIMULATION_FILE = SUMO_DIR / "103.sumocfg"
OMLSERVER = Path("OMLFGServer") / "OmlFgServer.jar"
LISA_DATA_DIR = Path("LISA_Files") / "z1_fg103"
CONFIG_FILE = Path("intersection_conf.yaml")
JUNCTION_ID = "103"

# BT Button Configuration
BT_COOLDOWN = 1800
BT_PRESSED_RATE_PER_MINUTE = 1.0
PED_BUTTON_PULSE_STEPS = 3

MSG_INIT = 'Init'
MSG_RUN = 'Run'

class SUMOENV:
    def __init__(self):
        # SUMO Configuration
        self.sumoBinary = checkBinary('sumo-gui')
        self.sumoCmd = [self.sumoBinary, '-c', str(SIMULATION_FILE)]

        # LISA init duration
        self.lisa_init_server_steps = 1
        self.lisa_init_run_steps = 20

        self.bt_button_cooldown_seconds = BT_COOLDOWN
        self.bt_button_pressed_rate_per_minute = BT_PRESSED_RATE_PER_MINUTE
        self.ped_button_pulse_steps = PED_BUTTON_PULSE_STEPS

        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            self.lisa_cfg = yaml.safe_load(f)

        # PyLiSuM Initialisation
        self.pylisum = LisaInterfaceManager(
            host="localhost",
            server_path=OMLSERVER,
            lisum_data_dir=LISA_DATA_DIR,
            lisa_config=self.lisa_cfg
        )

        # Start the server BEFORE initialising context, otherwise connection will fail.
        self.pylisum.start_oml_server(invisible=True)
        self.pylisum.initialize_controllers()

        ##########################################################################
        # The code above is the standard PyLiSuM startup template.
        # The SUMO simulation logic begins below and is intended to be
        # defined by the user according to their specific use case.
        #
        # The current implementation is configured for a single junction.
        # Multi-junction simulation is feasible in principle, but it has
        # not been developed yet because corresponding multi-junction
        # LISA+ files are not currently available.
        ##########################################################################

        # Simulation components
        self.current_timesteps = 0
        self._dmp_vehicle_types = {"bus"}
        junction_config = self.lisa_cfg[JUNCTION_ID]
        self.detectors = junction_config["detectors"]
        self.crossing_to_buttons = junction_config["crossing_ped_button_mapping"]
        self.button_to_walkingareas = junction_config["ped_button_walkingarea_mapping"]

        self.telegrams = junction_config["telegrams"]

        self._pt_enter_lanes = junction_config["r09_telegram_an_lanes"]
        self._bus_telegram_busstop = junction_config["r09_telegram_door_busstops"]
        self._pt_exit_lanes = junction_config["r09_telegram_ab_lanes"]
        self._enter_lane_to_group = junction_config["an_lane_signal_mapping"]
        self.additional_phases = junction_config["phase_cannot_configured_in_pylisum"]
        self.phase_count = junction_config["phase_number"]
        self._dmp_detector_ids = list(dict.fromkeys(
            junction_config["digital_meldepunkt_an"]
            + junction_config["digital_meldepunkt_door"]
            + junction_config["digital_meldepunkt_ab"]
        ))

        self._veh_group = {}
        self._sent_events = set()
        self._pending_pt_telegrams = deque()
        self._in_enter_lanes_previous = set()
        self._in_exit_lanes_previous = set()
        self._in_busstop_previous = set()
        self._pt_vehicle_ids = set()
        self._pt_origin = {}

        self._previous_pedestrian_active = {b: False for b in set(self.button_to_walkingareas.keys())}
        self._sk1_stop_seconds = {}
        self._button_last_press_time = {b: -1e9 for b in self.button_to_walkingareas.keys() if b.startswith("BT")}

        # Pulse extension (Hold '1') counters for specific detectors
        self._dmp_hold_counter = {d: 0 for d in junction_config["digital_meldepunkt_ab"]}

        # Optimization: Pre-calculate mappings for _get_det_str
        self.pedestrian_buttons = set(self.button_to_walkingareas.keys())
        self._button_hold_counter = {b: 0 for b in self.pedestrian_buttons}
        self.valid_crossing_events = set(self.crossing_to_buttons.keys())
        self.walkingarea_to_buttons = {}
        for button, walkingarea_config in self.button_to_walkingareas.items():
            walkingarea_list = (
                walkingarea_config
                if isinstance(walkingarea_config, (list, tuple, set))
                else [walkingarea_config]
            )
            for walkingarea in walkingarea_list:
                self.walkingarea_to_buttons.setdefault(walkingarea, []).append(button)

    def _get_dmp_bus_vehicle_ids(self, detector_id):
        """Return bus IDs detected by a DMP lane-area detector."""
        try:
            vehicle_ids = traci.lanearea.getLastStepVehicleIDs(detector_id)
        except traci.TraCIException:
            return []

        return [
            vehicle_id
            for vehicle_id in vehicle_ids
            if traci.vehicle.getTypeID(vehicle_id) in self._dmp_vehicle_types
        ]

    def _get_pt_type(self, vid):
        """Helper to get the type of a PT vehicle."""
        try:
            t = traci.vehicle.getTypeID(vid)
        except traci.TraCIException:
            return None
        if "bus" in t.lower():
            return "Bus"
        if "shuttle" in t.lower():
            return "Shuttle"
        return None

    def _get_det_str(self):
        dt = traci.simulation.getDeltaT()
        dt_seconds = float(dt)
        now_time = traci.simulation.getTime()

        # --- 1. Identify Active Pedestrian Buttons ---
        raw_active_buttons = {b: False for b in self.pedestrian_buttons}

        for walkingarea, buttons_on_side in self.walkingarea_to_buttons.items():
            pedestrian_ids = traci.edge.getLastStepPersonIDs(walkingarea)
            if not pedestrian_ids:
                continue

            for pedestrian_id in pedestrian_ids:
                # Optimized: Early exit checks
                if traci.person.getWaitingTime(pedestrian_id) <= 0:
                    continue

                next_edge = traci.person.getNextEdge(pedestrian_id)
                if next_edge not in self.valid_crossing_events:
                    continue

                allowed = self.crossing_to_buttons[next_edge]
                for button in buttons_on_side:
                    if button in allowed:
                        raw_active_buttons[button] = True

        # --- 2. Calculate Button Pulses (HT & BT) ---
        bt_lambda = self.bt_button_pressed_rate_per_minute / 60.0
        press_step = (1.0 - math.exp(-bt_lambda * dt_seconds)) if bt_lambda > 0 else 0.0

        button_pulse_states = {}

        for button, is_active in raw_active_buttons.items():
            if button.startswith("HT"):
                # HT: Rising edge detection
                button_pulse_states[button] = (is_active and not self._previous_pedestrian_active.get(button, False))
            elif button.startswith("BT"):
                # BT: Random trigger with cooldown
                triggered = False
                if is_active:
                    last_press = self._button_last_press_time.get(button, -1e9)
                    if (now_time - last_press) >= self.bt_button_cooldown_seconds:
                        if random.random() < press_step:
                            triggered = True
                            self._button_last_press_time[button] = now_time
                button_pulse_states[button] = triggered

        self._previous_pedestrian_active = raw_active_buttons

        # --- 3. PT Logic (Mutual Exclusion for DMP22/DMP32) ---
        dmp_bus_ids = {
            detector: self._get_dmp_bus_vehicle_ids(detector)
            for detector in self._dmp_detector_ids
        }

        # Record origin
        for vid in dmp_bus_ids.get("DMP21", []):
            self._pt_origin.setdefault(vid, "DMP21")
        for vid in dmp_bus_ids.get("DMP31", []):
            self._pt_origin.setdefault(vid, "DMP31")

        # Determine overlap assignment
        overlap_vids = set(dmp_bus_ids.get("DMP22", [])) | set(dmp_bus_ids.get("DMP32", []))
        assigned_to_22 = False
        assigned_to_32 = False

        for vid in overlap_vids:
            origin = self._pt_origin.get(vid)
            if origin == "DMP21":
                assigned_to_22 = True
            elif origin == "DMP31":
                assigned_to_32 = True

        # Pre-calculate PT detector values
        dmp_val = {
            detector: 1 if vehicle_ids else -1
            for detector, vehicle_ids in dmp_bus_ids.items()
        }
        if "DMP22" in dmp_val:
            dmp_val["DMP22"] = 1 if assigned_to_22 else -1
        if "DMP32" in dmp_val:
            dmp_val["DMP32"] = 1 if assigned_to_32 else -1

        # --- 4. Build Detector String ---
        parts = []
        for idx, detector in enumerate(self.detectors):
            val = -1

            if detector in button_pulse_states:
                is_pressed = button_pulse_states[detector]
                if is_pressed:
                    self._button_hold_counter[detector] = self.ped_button_pulse_steps

                if self._button_hold_counter.get(detector, 0) > 0:
                    val = 1
                    self._button_hold_counter[detector] -= 1
                else:
                    val = -1

            elif detector in dmp_val:
                raw_val = dmp_val[detector]

                # Apply Signal Extension (Hold '1') for specific detectors
                if detector in self._dmp_hold_counter:
                    if raw_val == 1:
                        # Reset hold timer on valid detection
                        self._dmp_hold_counter[detector] = 4
                        val = 1
                    elif self._dmp_hold_counter[detector] > 0:
                        # Hold the signal high
                        val = 1
                        self._dmp_hold_counter[detector] -= 1
                    else:
                        val = raw_val
                else:
                    val = raw_val

            elif detector == "SK1":
                vids = traci.lanearea.getLastStepVehicleIDs(detector)
                current_shuttle_vids = {vid for vid in vids if traci.vehicle.getTypeID(vid) == "shuttle"}

                # Cleanup departed shuttles
                self._sk1_stop_seconds = {vid: time for vid, time in self._sk1_stop_seconds.items() if vid in current_shuttle_vids}

                any_trigger = False
                for vid in current_shuttle_vids:
                    if traci.vehicle.getSpeed(vid) < 0.1:
                        self._sk1_stop_seconds[vid] = self._sk1_stop_seconds.get(vid, 0.0) + dt_seconds
                        if self._sk1_stop_seconds[vid] >= 180.0:
                            any_trigger = True
                    else:
                        self._sk1_stop_seconds[vid] = 0.0

                val = 1 if any_trigger else -1

            # Standard Detectors
            else:
                n = traci.lanearea.getLastStepVehicleNumber(detector)
                val = n if n > 0 else -1

            parts.append(f"({idx}){val}")

        return "/".join(parts)

    def _collect_an_telegrams(self):
        current_entered_pts = set()

        for vid in list(self._pt_vehicle_ids):
            pt_type = self._get_pt_type(vid)
            if not pt_type:
                self._pt_vehicle_ids.discard(vid)
                continue

            try:
                pt_lane = traci.vehicle.getLaneID(vid)
            except traci.TraCIException:
                self._pt_vehicle_ids.discard(vid)
                continue
            if pt_lane in self._pt_enter_lanes:
                current_entered_pts.add(vid)

        newly_entered = current_entered_pts - self._in_enter_lanes_previous
        self._in_enter_lanes_previous = current_entered_pts
        an_telegrams = []
        for vid in newly_entered:
            if (vid, "AN_REGISTERED") in self._sent_events:
                continue

            pt_type = self._get_pt_type(vid)
            pt_lane = traci.vehicle.getLaneID(vid)
            group = self._enter_lane_to_group.get(pt_lane)

            if not pt_type or not group:
                continue

            key = f"{pt_type}_{group}_AN"
            if key not in self.telegrams:
                continue

            self._veh_group[vid] = group
            self._sent_events.add((vid, "AN_REGISTERED"))
            an_telegrams.append(self.telegrams[key])

        return an_telegrams

    def _collect_event_telegrams(self):
        door_telegrams = []
        ab_telegrams = []
        # ---------- 2) Door: leaving bus stop bs_1, K1 only ----------
        current_busstop_pts = set(traci.busstop.getVehicleIDs(self._bus_telegram_busstop))
        busstop_left = self._in_busstop_previous - current_busstop_pts
        self._in_busstop_previous = current_busstop_pts

        for vid in busstop_left:
            if (vid, "Door") in self._sent_events:
                continue

            pt_type = self._get_pt_type(vid)
            group = self._veh_group.get(vid)

            if pt_type and group == "K1":
                key = f"{pt_type}_K1_Door"
                if key in self.telegrams:
                    door_telegrams.append(self.telegrams[key])
                    self._sent_events.add((vid, "Door"))

        # ---------- 3) AB: exiting the intersection ----------
        current_exit_pts = set()
        for vid in list(self._pt_vehicle_ids):
            pt_type = self._get_pt_type(vid)
            if not pt_type:
                self._pt_vehicle_ids.discard(vid)
                continue

            try:
                pt_lane = traci.vehicle.getLaneID(vid)
            except traci.TraCIException:
                self._pt_vehicle_ids.discard(vid)
                continue
            if pt_lane in self._pt_exit_lanes:
                current_exit_pts.add(vid)

        newly_exited = current_exit_pts - self._in_exit_lanes_previous
        self._in_exit_lanes_previous = current_exit_pts

        for vid in newly_exited:
            if (vid, "AB") in self._sent_events:
                continue

            pt_type = self._get_pt_type(vid)
            group = self._veh_group.get(vid)

            if pt_type and group:
                key = f"{pt_type}_{group}_AB"
                if key in self.telegrams:
                    ab_telegrams.append(self.telegrams[key])
                    self._sent_events.add((vid, "AB"))

        return door_telegrams + ab_telegrams

    def _queue_pt_telegrams(self, event_telegrams, an_telegrams):
        # Door/AB events keep priority over AN while preserving per-group order.
        for telegram in reversed(event_telegrams):
            self._pending_pt_telegrams.appendleft(telegram)
        self._pending_pt_telegrams.extend(an_telegrams)

    def _next_pt_telegram(self):
        return self._pending_pt_telegrams.popleft() if self._pending_pt_telegrams else ""

    def _request_signal_states(self, msg_type, detector_state, pt_telegram, sim_time):
        result = self.pylisum.request_signal_states(
            JUNCTION_ID,
            msg_type,
            detector_state,
            pt_telegram,
            sim_time,
        )
        if result is None:
            raise RuntimeError("No valid response from LISA controller. Check OML server logs.")
        return result

    def _update_pt_vehicle_cache(self):
        for vehicle_id in traci.simulation.getDepartedIDList():
            if self._get_pt_type(vehicle_id):
                self._pt_vehicle_ids.add(vehicle_id)

        self._cleanup_arrived_vehicle_state(set(traci.simulation.getArrivedIDList()))

    def _cleanup_arrived_vehicle_state(self, arrived_vehicle_ids):
        if not arrived_vehicle_ids:
            return

        self._pt_vehicle_ids -= arrived_vehicle_ids
        self._veh_group = {
            vehicle_id: group
            for vehicle_id, group in self._veh_group.items()
            if vehicle_id not in arrived_vehicle_ids
        }
        self._pt_origin = {
            vehicle_id: origin
            for vehicle_id, origin in self._pt_origin.items()
            if vehicle_id not in arrived_vehicle_ids
        }
        self._sk1_stop_seconds = {
            vehicle_id: seconds
            for vehicle_id, seconds in self._sk1_stop_seconds.items()
            if vehicle_id not in arrived_vehicle_ids
        }
        self._sent_events = {
            event
            for event in self._sent_events
            if event[0] not in arrived_vehicle_ids
        }
        self._in_enter_lanes_previous -= arrived_vehicle_ids
        self._in_exit_lanes_previous -= arrived_vehicle_ids
        self._in_busstop_previous -= arrived_vehicle_ids

    def run(self):
        traci.start(self.sumoCmd)

        # Initial
        for _ in range(self.lisa_init_server_steps):
            _, _, _, _, _ = self._request_signal_states(MSG_INIT, "", "", 0)
        for _ in range(self.lisa_init_run_steps):
            _, _, _, _, _ = self._request_signal_states(MSG_RUN, "", "", 0)

        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            self.current_timesteps += 1
            self._update_pt_vehicle_cache()

            det_str = self._get_det_str()
            event_telegrams = self._collect_event_telegrams()
            an_telegrams = self._collect_an_telegrams()
            self._queue_pt_telegrams(event_telegrams, an_telegrams)
            pt_telegram = self._next_pt_telegram()
            sumo_signals_str, _, phases_string, _, _ = self._request_signal_states(
                MSG_RUN,
                det_str,
                pt_telegram,
                self.current_timesteps,
            )

            phases = [int(x) for x in phases_string.split('/')]
            if len(phases) != self.phase_count:
                raise ValueError(
                    f"LISA returned {len(phases)} phases, but {self.phase_count} phases are configured."
                )

            if 1 in phases:
                active_phase_number = phases.index(1) + 1
                if active_phase_number == 2:
                    sumo_signals_str = self.additional_phases["2"]
                elif active_phase_number == 7:
                    sumo_signals_str = self.additional_phases["7"]

            traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, sumo_signals_str)

        traci.close()

if __name__ == "__main__":
    env = SUMOENV()
    env.run()
