import logging
import os
import platform
import re
import subprocess
import time
import xml.dom.minidom
from dataclasses import dataclass
from pathlib import Path

import psutil
import requests


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
JAVA_8_BIN = PROJECT_ROOT / "Java_8" / "bin"
LOG_DIR = PROJECT_ROOT / "PyLiSuM_Log"

LOGGER_NAME = "LISA+"
OMTC_XML_NAMESPACE = "http://www.schlothauer.de/omtc/services"
PUT_MESSAGE_RESPONSE_RE = re.compile(
    r"^([0-9]+):(\{.+\})(\{.+\})(\{.+\})(\{.*\})(\{.*\})(\{.*\})$",
    flags=re.DOTALL,
)
LISA_CONTROLLER_ID_RE = re.compile(r"z(\d+)_fg(\d+)")

MESSAGE_TEMPLATES = {
    "get_task_list": (
        f'<GetTaskListRequest xmlns="{OMTC_XML_NAMESPACE}">'
        "<Detail>false</Detail>"
        "<StgKennung><ZNr>%d</ZNr><FNr>%d</FNr></StgKennung>"
        "</GetTaskListRequest>"
    ),
    "set_data_dir": (
        f'<SetDataDirRequest xmlns="{OMTC_XML_NAMESPACE}">'
        "<Value>%s</Value>"
        "</SetDataDirRequest>"
    ),
    "remove_task": (
        f'<RemoveTaskRequest xmlns="{OMTC_XML_NAMESPACE}">'
        "<ID>%s</ID>"
        "</RemoveTaskRequest>"
    ),
    "set_task": (
        f'<SetTaskRequest xmlns="{OMTC_XML_NAMESPACE}">'
        "<ID>%d</ID>"
        "<StgKennung><ZNr>%d</ZNr><FNr>%d</FNr></StgKennung>"
        "<Callback><URL>%s</URL></Callback>"
        "<Cycle><IntervallSec>%d</IntervallSec></Cycle>"
        "%s"
        "</SetTaskRequest>"
    ),
    "get_task": (
        f'<GetTaskRequest xmlns="{OMTC_XML_NAMESPACE}">'
        "<ID>%d</ID>"
        "<StgKennung><ZNr>%d</ZNr><FNr>%d</FNr></StgKennung>"
        "</GetTaskRequest>"
    ),
    "task_element": "<TaskElement><MessageType>%s</MessageType></TaskElement>",
    "get_object_list": (
        f'<ObjectListRequest xmlns="{OMTC_XML_NAMESPACE}">'
        "<StgKennung><ZNr>%d</ZNr><FNr>%d</FNr></StgKennung>"
        "</ObjectListRequest>"
    ),
    "message": f'<Message xmlns="{OMTC_XML_NAMESPACE}"><Msg>%s</Msg></Message>',
}

SERVICE_ENDPOINTS = {
    "get_task_list": "/services/PDService/getTaskList",
    "set_data_dir": "/services/DDService/setDataDir",
    "remove_task": "/services/PDService/removeTask",
    "set_task": "/services/PDService/setTask",
    "get_task": "/services/PDService/getTask",
    "get_object_list": "/services/PDService/getObjectList",
    "message": "/services/PDCallback/putMessage",
}

LISA_TO_SUMO_SIGNAL_STATE = {
    0: "r",  # OCIT-Farbbild Dunkel
    3: "r",  # OCIT-Farbbild Rot
    8: "o",  # OCIT-Farbbild Gelb-Blinken
    12: "y",  # OCIT-Farbbild Gelb
    15: "u",  # OCIT-Farbbild Rot/Gelb
    48: "g",  # OCIT-Farbbild Gruen
    -1: "g",
}

LISA_MESSAGE_TYPES = [
    "MeldungType",
    "WunschVektorType",
    "DetFlType",
    "OevTelegrammType",
    "APWertZustType",
    "IstvektorProjType",
]

# Backward-compatible module constants for older internal imports.
Messages = {
    "MSG_GetTaskListRequest": MESSAGE_TEMPLATES["get_task_list"],
    "MSG_SetDataDirRequest": MESSAGE_TEMPLATES["set_data_dir"],
    "MSG_RemoveTaskRequest": MESSAGE_TEMPLATES["remove_task"],
    "MSG_SetTaskRequest": MESSAGE_TEMPLATES["set_task"],
    "MSG_GetTaskRequest": MESSAGE_TEMPLATES["get_task"],
    "MSG_TaskElement": MESSAGE_TEMPLATES["task_element"],
    "MSG_GetObjectListRequest": MESSAGE_TEMPLATES["get_object_list"],
    "MSG_Message": MESSAGE_TEMPLATES["message"],
}

MessageToService = {
    "MSG_GetTaskListRequest": SERVICE_ENDPOINTS["get_task_list"],
    "MSG_SetDataDirRequest": SERVICE_ENDPOINTS["set_data_dir"],
    "MSG_RemoveTaskRequest": SERVICE_ENDPOINTS["remove_task"],
    "MSG_SetTaskRequest": SERVICE_ENDPOINTS["set_task"],
    "MSG_GetTaskRequest": SERVICE_ENDPOINTS["get_task"],
    "MSG_GetObjectListRequest": SERVICE_ENDPOINTS["get_object_list"],
    "MSG_Message": SERVICE_ENDPOINTS["message"],
}

LisaToSumoSignals = LISA_TO_SUMO_SIGNAL_STATE
PutMessageResponsePattern = PUT_MESSAGE_RESPONSE_RE


def configure_logger():
    """Configure the PyLiSuM file logger once."""
    logger_instance = logging.getLogger(LOGGER_NAME)
    if logger_instance.hasHandlers():
        return logger_instance

    logger_instance.setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"pylisum_{time.strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s  %(name)s  %(levelname)s: %(message)s"))
    logger_instance.addHandler(file_handler)
    return logger_instance


logger = configure_logger()


@dataclass
class ControllerUnit:
    z_nr: int
    f_nr: int
    sumo_tl_id: str
    taskID: int = -1
    lisa_sumo_mapping: dict | None = None
    lisa_sgr_seq: list | None = None
    sgr_link_indices_dict: dict | None = None
    control_options: dict | None = None
    conditional_signal_groups: dict | None = None
    callback_cycle_interval_sec: int = 60


class LisaInterfaceManager:
    def __init__(self, host, server_path, lisum_data_dir, lisa_config):
        self.host = host
        self.oml_fg_server = server_path
        self.lisum_data_dir = lisum_data_dir
        self.lisa_config = {str(controlled_node): config for controlled_node, config in lisa_config.items()}
        self.controlled_nodes = self._get_configured_controller_ids()
        self.ports = self._get_controller_ports()
        self.session = requests.Session()

        self.message_templates = MESSAGE_TEMPLATES
        self.service_endpoints = SERVICE_ENDPOINTS
        self.put_message_response_re = PUT_MESSAGE_RESPONSE_RE
        self.message_types = LISA_MESSAGE_TYPES
        self.lisa_to_sumo_signal_state = LISA_TO_SUMO_SIGNAL_STATE

        self.controller_unit_dict = {}
        self.server_process = None

    def start_oml_server(self, invisible=False):
        java_exec, java_version_output = self._select_java_executable(invisible)
        jar_path = str(self.oml_fg_server)
        java_args = self._build_oml_server_command(java_exec, jar_path)

        logger.info("Ensuring OML Server port is free...")
        self._stop_existing_oml_server_processes(jar_path)

        try:
            logger.info("Starting OML Server with command: %s", " ".join(java_args))
            if platform.system() == "Linux":
                self.server_process = subprocess.Popen(java_args, preexec_fn=os.setpgrp)
            else:
                self.server_process = subprocess.Popen(
                    java_args,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )

            logger.info("Waiting 5 seconds for OML Server to initialize...")
            time.sleep(5)
        except Exception as exc:
            logger.error("Failed to start OML Server: %s", exc)
            raise SystemExit(-1) from exc

    def initialize_controllers(self):
        for controlled_node in self.controlled_nodes:
            self._initialize_controller(controlled_node)

    def request_signal_states(self, controlled_node, msg_type, detector_state, pt_telegram, sim_time):
        node_id = str(controlled_node)
        controller_unit = self.controller_unit_dict[node_id]
        put_message_body = self._build_put_message_request(
            controller_unit=controller_unit,
            sim_time=sim_time,
            msg_type=msg_type,
            detector_state=detector_state,
            pt_telegram=pt_telegram,
            ap_val=f"{sim_time}",
        )
        put_message_response = self._post_xml_service(
            node_id,
            self.service_endpoints["message"],
            put_message_body,
        )
        logger.info(
            "<PutMessage> node=%s sim_time=%s msg_type=%s detector_state=%s pt_telegram=%s request=%s",
            node_id,
            sim_time,
            msg_type,
            detector_state,
            pt_telegram,
            put_message_body,
        )
        logger.info(
            "<PutMessageResponse> node=%s sim_time=%s response=%s",
            node_id,
            sim_time,
            put_message_response,
        )

        parsed_response = self._parse_put_message_response(put_message_response, controller_unit)
        sumo_signals_str, signal_states_string, phases_string, output_string, ap_string = parsed_response
        logger.info(
            "<SignalStates> node=%s sim_time=%s lisa_signal_states=%s sumo_signal_state=%s phases=%s output=%s ap=%s",
            node_id,
            sim_time,
            signal_states_string,
            sumo_signals_str,
            phases_string,
            output_string,
            ap_string,
        )
        return parsed_response

    def _select_java_executable(self, invisible):
        java_version_output = ""
        java_exec = None

        try:
            version_result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            java_version_output = (version_result.stderr or version_result.stdout or "").strip()
            version_match = re.search(r'version "(?P<version>[^"]+)"', java_version_output)
            if version_result.returncode == 0 and version_match:
                installed_version = version_match.group("version")
                if installed_version.startswith("1.8.") or installed_version.startswith("8."):
                    java_exec = "javaw" if invisible and platform.system() == "Windows" else "java"
                    logger.info("Using system Java 8 environment: %s", installed_version)
                else:
                    logger.warning("System Java is not version 8: %s", installed_version)
            elif java_version_output:
                logger.warning("Unable to detect a usable system Java version: %s", java_version_output)
        except Exception as exc:
            logger.warning("Failed to probe system Java version: %s", exc)

        if java_exec is not None:
            return java_exec, java_version_output

        java8_path = self._get_bundled_java_executable(invisible)
        if not java8_path.exists():
            logger.error("FATAL: Java 8 not found at %s", java8_path)
            logger.error("Please ensure you have downloaded and extracted JRE 8 to the Java_8 folder.")
            if java_version_output:
                logger.error("Detected system Java output: %s", java_version_output)
            return "java", java_version_output

        logger.info("Using bundled Java 8 environment: %s", java8_path)
        return str(java8_path), java_version_output

    @staticmethod
    def _get_bundled_java_executable(invisible):
        if platform.system() == "Windows":
            java_exec_name = "javaw.exe" if invisible else "java.exe"
            return JAVA_8_BIN / java_exec_name
        return JAVA_8_BIN / "java"

    @staticmethod
    def _build_oml_server_command(java_exec, jar_path):
        if platform.system() == "Linux":
            java_args = ["nohup", java_exec]
        else:
            java_args = [java_exec]
        java_args.extend(["-jar", "-Xmx1024m", "-Xms512m", jar_path])
        return java_args

    @staticmethod
    def _stop_existing_oml_server_processes(jar_path):
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                cmd_line = proc.info["cmdline"] or []
                if any(jar_path in arg for arg in cmd_line):
                    logger.info("Killing existing server process: PID %s", proc.pid)
                    proc.kill()
                    time.sleep(1)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def _initialize_controller(self, controlled_node):
        """Initialize the LISA controller context, task and signal mapping."""
        node_config = self._get_controller_config(controlled_node)
        controller_unit = self._create_controller_context(controlled_node, node_config)
        self._load_signal_mapping(controller_unit, node_config)
        self._load_control_options(controller_unit, node_config)

        self._set_lisa_data_directory(controlled_node)
        self._remove_existing_lisa_tasks(controlled_node, controller_unit)
        controller_unit.taskID = self._register_lisa_callback_task(controlled_node, controller_unit)
        self._fetch_lisa_object_list(controlled_node, controller_unit)

    def _set_lisa_data_directory(self, controlled_node):
        data_dir_body = self.message_templates["set_data_dir"] % self.lisum_data_dir
        data_dir_response = self._post_xml_service(
            controlled_node,
            self.service_endpoints["set_data_dir"],
            data_dir_body,
        )
        logger.info("<SetDataDir> Response received: %s", data_dir_response)

    def _create_controller_context(self, controlled_node, node_config):
        node_id = str(controlled_node)
        lisa_id = node_config["id"]["lisa_id"]
        match = LISA_CONTROLLER_ID_RE.match(lisa_id)
        if not match:
            message = f"lisa_id '{lisa_id}' does not match expected pattern 'z<Nr>_fg<Nr>'"
            logger.error(message)
            raise ValueError(message)

        controller_unit = ControllerUnit(
            z_nr=int(match.group(1)),
            f_nr=int(match.group(2)),
            sumo_tl_id=node_id,
        )
        self.controller_unit_dict[node_id] = controller_unit
        logger.info("Controller Unit: z%s_fg%s", controller_unit.z_nr, controller_unit.f_nr)
        return controller_unit

    def _remove_existing_lisa_tasks(self, controlled_node, controller_unit):
        task_list_body = self.message_templates["get_task_list"] % (controller_unit.z_nr, controller_unit.f_nr)
        task_list_response = self._post_xml_service(
            controlled_node,
            self.service_endpoints["get_task_list"],
            task_list_body,
        )
        logger.info("<GetTaskList> Response received: %s", task_list_response)

        dom_tree = xml.dom.minidom.parseString(task_list_response)
        for task_id_node in dom_tree.getElementsByTagName("ns2:ID"):
            task_id = task_id_node.childNodes[0].nodeValue
            remove_task_body = self.message_templates["remove_task"] % task_id
            self._post_xml_service(
                controlled_node,
                self.service_endpoints["remove_task"],
                remove_task_body,
            )
            logger.info("<RemoveTask> Response received for task %s", task_id)

    def _register_lisa_callback_task(self, controlled_node, controller_unit):
        task_elements = "".join(self.message_templates["task_element"] % mt for mt in self.message_types)
        set_task_body = self.message_templates["set_task"] % (
            0,
            controller_unit.z_nr,
            controller_unit.f_nr,
            f"{self.host}:{self.ports[str(controlled_node)]}",
            controller_unit.callback_cycle_interval_sec,
            task_elements,
        )
        set_task_response = self._post_xml_service(
            controlled_node,
            self.service_endpoints["set_task"],
            set_task_body,
        )
        logger.info("<SetTasks> Response received: %s", set_task_response)

        dom_tree = xml.dom.minidom.parseString(set_task_response)
        task_nodes = dom_tree.getElementsByTagName("ns2:ID")
        if not task_nodes:
            logger.error("No TaskID received in SetTasks response")
            raise ValueError("Failed to obtain TaskID from LISA Controller")
        return int(task_nodes[0].firstChild.nodeValue)

    def _fetch_lisa_object_list(self, controlled_node, controller_unit):
        get_object_list_body = self.message_templates["get_object_list"] % (
            controller_unit.z_nr,
            controller_unit.f_nr,
        )
        get_object_list_response = self._post_xml_service(
            controlled_node,
            self.service_endpoints["get_object_list"],
            get_object_list_body,
        )
        logger.info("<Get Object List> Response received: %s", get_object_list_response)

    def _load_signal_mapping(self, controller_unit, node_config):
        signal_config = self._get_signal_config_section(node_config)
        controller_unit.lisa_sumo_mapping = signal_config["lisa_sumo_mapping"]
        controller_unit.lisa_sgr_seq = signal_config["lisa_sgr_seq"]
        controller_unit.conditional_signal_groups = signal_config.get("conditional_signal_groups", {})
        self._build_signal_group_link_index_map(controller_unit)

    def _load_control_options(self, controller_unit, node_config):
        control_options = node_config.get("control_options")
        if control_options is None:
            raise KeyError("Missing 'control_options' section in junction configuration.")
        controller_unit.control_options = dict(control_options)
        controller_unit.callback_cycle_interval_sec = int(node_config.get("callback_cycle_interval_sec", 60))

    def _get_configured_controller_ids(self):
        """Return all configured junction IDs from lisa_config."""
        return [str(controlled_node) for controlled_node in self.lisa_config.keys()]

    def _get_controller_ports(self):
        """Return a mapping of controlled node ID to local simulation port."""
        return {
            str(controlled_node): node_config["port"]
            for controlled_node, node_config in self.lisa_config.items()
        }

    def _get_controller_config(self, controlled_node):
        node_id = str(controlled_node)
        try:
            return self.lisa_config[node_id]
        except KeyError as exc:
            message = f"Configuration for controlled node '{node_id}' was not found."
            logger.error(message)
            raise KeyError(message) from exc

    def _build_put_message_request(self, controller_unit, sim_time, msg_type, detector_state, pt_telegram, ap_val):
        """
        Build the LISA putMessage request body.

        The control vector is based on the standard LISA parameter types:
        MeldungType, WunschVektorType, DetFlType, OevTelegrammType,
        APWertZustType and IstvektorProjType.
        """
        control_options = controller_unit.control_options
        if control_options is None:
            raise RuntimeError("Controller control options have not been initialized.")
        control_vector = [
            control_options["controlMode"], 0, 0, 0, 1,
            control_options["sp"], 1, control_options["va"],
            control_options["iv"], control_options["oev"],
            control_options["coordinated"],
        ]
        wunsch_vektor_str = "{" + ";".join(map(str, control_vector)) + "}"
        message = (
            f"{controller_unit.taskID} {sim_time} 1 0:{sim_time}"
            f'{{"{msg_type}"}}'
            f"{wunsch_vektor_str}"
            f"{{{detector_state}}}"
            f"{{{pt_telegram}}}"
            f"{{{ap_val}}}"
            f"{{}}"
        )
        return self.message_templates["message"] % message

    def _parse_put_message_response(self, put_message_response, controller_unit):
        try:
            dom_tree = xml.dom.minidom.parseString(put_message_response)
            internal_cmd = dom_tree.documentElement.firstChild.nodeValue
            response_match = self.put_message_response_re.search(internal_cmd)
            if not response_match:
                raise ValueError(f"Unexpected putMessage response format: {internal_cmd!r}")

            _, _, _, signal_states_string, output_string, phases_string, ap_string = response_match.group(
                1, 2, 3, 4, 5, 6, 7
            )
            signal_states_string = signal_states_string[1:-1]
            sumo_signals_str = self._convert_lisa_signal_states_to_sumo(signal_states_string, controller_unit)
            phases_string = phases_string[1:-1]
            output_string = output_string[1:-1]
            ap_string = ap_string[1:-1]
            return sumo_signals_str, signal_states_string, phases_string, output_string, ap_string
        except Exception as exc:
            message = "Failed to parse LISA putMessage response"
            logger.exception("%s: %s", message, exc)
            raise ValueError(message) from exc

    @staticmethod
    def _build_signal_group_link_index_map(controller_unit):
        sgr_link_indices = {}
        for signal_group, links in controller_unit.lisa_sumo_mapping.items():
            signal_group_name = signal_group.strip()
            sgr_link_indices[signal_group_name] = [int(link.strip()) for link in str(links).split(",")]
            logger.info(
                "Link Indices for Sgr %s are: %s",
                signal_group_name,
                sgr_link_indices[signal_group_name],
            )
        controller_unit.sgr_link_indices_dict = sgr_link_indices

    @staticmethod
    def _get_signal_config_section(node_config):
        signal_config = node_config.get("signal")
        if signal_config is None:
            signal_config = node_config.get("signals")
        if signal_config is None:
            raise KeyError("Missing 'signal' or 'signals' section in junction configuration.")
        return signal_config

    def _convert_lisa_signal_states_to_sumo(self, signal_states_string, controller_unit):
        lisa_signal_states = [int(signal_state) for signal_state in signal_states_string.split("/")]
        sumo_signal_states = []
        for state in lisa_signal_states:
            try:
                sumo_signal_states.append(self.lisa_to_sumo_signal_state[state])
            except KeyError as exc:
                known_states = ", ".join(str(key) for key in sorted(self.lisa_to_sumo_signal_state))
                raise ValueError(
                    f"Unknown LISA signal state {state}. Known states are: {known_states}."
                ) from exc
        sgr_link_indices = controller_unit.sgr_link_indices_dict
        lisa_sgr_seq = controller_unit.lisa_sgr_seq

        if len(sumo_signal_states) != len(sgr_link_indices.keys()):
            raise Exception(
                "The lisa_sgr_seq property does not match the signal groups defined in Lisa+ program. "
                "Please configure lisa_sgr_seq correctly in lisa_config.yaml!"
            )

        link_state_by_index = {}
        for index, sumo_signal_state in enumerate(sumo_signal_states):
            signal_group_name = lisa_sgr_seq[index].strip()
            link_indices = sgr_link_indices[signal_group_name]
            if -1 in link_indices:
                continue

            link_state = self._resolve_signal_group_state(
                signal_group_name,
                sumo_signal_state,
                sumo_signal_states,
                lisa_sgr_seq,
                index,
                controller_unit.conditional_signal_groups or {},
            )

            for link_index in link_indices:
                link_state_by_index[link_index] = link_state

        return "".join(state for _, state in sorted(link_state_by_index.items()))

    @staticmethod
    def _resolve_signal_group_state(
        signal_group_name,
        sumo_signal_state,
        sumo_signal_states,
        lisa_sgr_seq,
        index,
        conditional_signal_groups,
    ):
        conditional_config = conditional_signal_groups.get(signal_group_name)
        if conditional_config is None:
            return sumo_signal_state

        reference = conditional_config if isinstance(conditional_config, str) else conditional_config.get("reference", "previous")
        if reference == "previous":
            if index == 0:
                raise ValueError(f"Conditional signal group '{signal_group_name}' cannot reference a previous group.")
            reference_state = sumo_signal_states[index - 1]
        else:
            signal_group_names = [name.strip() for name in lisa_sgr_seq]
            try:
                reference_index = signal_group_names.index(reference)
            except ValueError as exc:
                raise ValueError(
                    f"Conditional signal group '{signal_group_name}' references unknown group '{reference}'."
                ) from exc
            reference_state = sumo_signal_states[reference_index]

        if sumo_signal_state.lower() == "g" and reference_state.lower() == "g":
            return "G"
        return reference_state

    def _post_xml_service(self, controlled_node, endpoint, body, max_retries=10, timeout=5):
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1.")

        node_id = str(controlled_node)
        url = f"http://{self.host}:{self.ports[node_id]}{endpoint}"
        headers = {
            "Accept": "*/*",
            "Content-Type": 'text/xml;charset="utf-8"',
            "Accept-Encoding": "gzip/deflate",
        }

        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.post(url, data=body, headers=headers, timeout=timeout)
                if response.status_code != 200:
                    logger.warning("HTTP %s from %s (Attempt %s/%s)", response.status_code, url, attempt, max_retries)
                    logger.warning("Request body: %s", body)
                    logger.warning("Response body: %s", response.text)
                    response.raise_for_status()

                response_text = response.text
                if "Error 404" in response_text:
                    raise Exception(f"Application Error 404 in response body: {response_text}")

                return response_text
            except Exception as exc:
                logger.warning("Request failed: %s (Attempt %s/%s)", exc, attempt, max_retries)
                if attempt == max_retries:
                    logger.error("Max retries (%s) exceeded for %s", max_retries, endpoint)
                    raise
                time.sleep(1)
