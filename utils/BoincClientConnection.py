from __future__ import annotations
import datetime
import functools
from time import sleep
import xml.etree.ElementTree as ET

import xmltodict
import asyncio
import re
import os
from typing import Any, Dict, List, Tuple, Union
import logging

from libs.pyboinc._parse import parse_generic
from libs.pyboinc.rpc_client import init_rpc_client, RPCClient
from utils.utils import print_and_log as _print_and_log

log = logging.getLogger()
print_and_log = functools.partial(_print_and_log, log=log)


class BoincClientConnection:
    """Access to BOINC client configuration files.

    A simple class for grepping BOINC config files etc. Doesn't do any RPC communication

    Note: Usage of it should be wrapped in try/except clauses as it does not
          do any error handling internally.

    Attributes:
        config_dir:
    """

    def __init__(self, config_dir: Union[str, None] = None):
        """Initializes the instance using the Gridcoin wallet configuration location.

        Args:
            config_dir:
        """
        if config_dir is None:
            self.config_dir = "/var/lib/boinc-client"
        else:
            self.config_dir = config_dir  # Absolute path to the client config dir

    def get_project_list(self) -> List[str]:
        """Retrieve the list of projects supported by the BOINC client

        Constructs a list of all projects known by the BOINC client. This may include
        more projects than those currently attached to the BOINC client. This may also
        not include some projects currently attached, if they are projects not included
        with BOINC by default.

        Returns: List of project URLs.
        """
        project_list_file = os.path.join(self.config_dir, "all_projects_list.xml")
        return_list = []
        with open(project_list_file, mode="r", encoding="ASCII", errors="ignore") as f:
            parsed = xmltodict.parse(f.read())
            for project in parsed["projects"]["project"]:
                return_list.append(project["url"])
        return return_list


async def run_rpc_command(
    rpc_client: RPCClient,
    command: str,
    arg1: Union[str, None] = None,
    arg1_val: Union[str, None] = None,
    arg2: Union[str, None] = None,
    arg2_val: Union[str, None] = None,
) -> Union[str, Dict[Any, Any], List[Any]]:
    """Send command to BOINC client via RPC

    Runs command on BOINC client via RPC
    Example: run_rpc_command(rpc_client,'project_nomorework','http://project.com/project')

    Attempts to communicate with the BOINC client multiple times based on internal
    parameters.

    Args:
        rpc_client: Connection to BOINC client instance.
        command: Command to be executed by the BOINC client.
        arg1: Optional parameter for BOINC command.
        arg1_val: Value for optional parameter.
        arg2: Optional parameter for BOINC command.
        arg2_val: Value for optional parameter.

    Returns:
        Response from BOINC client, or None if unsuccessful.

    Raises:
        Exception: An error occurred attempting to communicated with the BOINC client.
    """
    max_retries = 3
    retry_wait = 5
    current_retries = 0

    while current_retries < max_retries:
        current_retries += 1
        sleep(retry_wait)
        full_command = "{} {} {} {} {}".format(
            command, arg1, arg1_val, arg2, arg2_val
        )  # added for debugging purposes
        log.debug("Running BOINC rpc request " + full_command)
        req = ET.Element(command)
        if arg1 is not None:
            a = ET.SubElement(req, arg1)
            if arg1_val is not None:
                a.text = arg1_val
        if arg2 is not None:
            b = ET.SubElement(req, arg2)
            if arg2_val is not None:
                b.text = arg2_val
        try:
            response = await rpc_client._request(req)
            parsed = parse_generic(response)
            if not str(parsed):
                print_and_log(
                    "Warning: Error w RPC command {}: {}".format(full_command, parsed),
                    "ERROR",
                )
                continue
        except Exception as e:
            log.error("Error w RPC command {} {}".format(full_command, e))
            continue
        else:
            return parsed


async def get_task_list(rpc_client: RPCClient) -> list:
    """List of active, waiting, or paused BOINC tasks.

    Return list of tasks from BOINC client which are not completed/failed. These
    can be active tasks, tasks waiting to be started, or paused tasks.

    Args:
        rpc_client:

    Returns:
        List of BOINC tasks.
    """
    # Known task states
    # 2: Active
    return_value = []
    reply = await run_rpc_command(rpc_client, "get_results")
    if not reply:
        log.error("Error getting boinc task list")
        return return_value
    if isinstance(reply, str):
        log.info("BOINC appears to have no tasks...")
        return return_value
    for task in reply:
        if task["state"] in [2]:
            return_value.append(task)
        else:
            log.warning("Warning: Found unknown task state %s: %s", task["state"], task)
    return return_value


async def is_boinc_crunching(rpc_client: RPCClient) -> bool:
    """Check if BOINC is actively crunching tasks.

    Queries BOINC client as to crunching status. Returns True is BOINC client
    is crunching, false otherwise.

    Args:
        rpc_client:

    Returns:
        True if crunching, or False if not crunching or unsure.

    Raises:
        Exception: An error occured attempting to check the BOINC client crunching status.
    """
    try:
        reply = await run_rpc_command(rpc_client, "get_cc_status")
        task_suspend_reason = int(reply["task_suspend_reason"])
        if task_suspend_reason != 0:
            # These are documented at
            # https://github.com/BOINC/boinc/blob/73a7754e7fd1ae3b7bf337e8dd42a7a0b42cf3d2/android/BOINC/app/src/main/java/edu/berkeley/boinc/utils/BOINCDefs.kt
            log.debug(
                "Determined BOINC client is not crunching task_suspend_reason: {}".format(
                    task_suspend_reason
                )
            )
            return False
        if task_suspend_reason == 0:
            log.debug(
                "Determined BOINC client is crunching task_suspend_reason: {}".format(
                    task_suspend_reason
                )
            )
            return True
        log.warning("Unable to determine if BOINC is crunching or not, assuming not.")
        return False
    except Exception as e:
        print(
            "Error checking if BOINC is crunching. If you continue to see this error, make sure BOINC is running"
        )
        log.error(
            "Error checking if BOINC is crunching (in is_boinc_crunching: {}".format(e)
        )
        return False


async def setup_connection(
    boinc_ip: Union[str, None] = None,
    boinc_password: Union[str, None] = None,
    port: int = 31416,
) -> Union[RPCClient, None]:
    """Create BOINC RPC client connection.

    Sets up a BOINC RPC client connection

    Args:
        boinc_ip:
        boinc_password:
        port:

    Returns:

    """
    rpc_client = None
    if not boinc_ip:
        boinc_ip = "127.0.0.1"
    rpc_client = await init_rpc_client(boinc_ip, boinc_password, port=port)
    return rpc_client


def stuck_xfer(xfer: dict) -> bool:
    """
    Checks if a xfer is stuck. Returns True if so, false if unable to determine or is stuck
    @param xfer: xfer from xfers-happening
    @return:
    """
    try:
        if "status" not in xfer:
            return False
        if "persistent_file_xfer" in xfer:
            if float(xfer["persistent_file_xfer"].get("num_retries", 0)) > 0:
                return True
    except Exception as e:
        log.error("Error in stuck_xfer: {}".format(e))
    return False


def xfers_happening(xfer_list: list) -> bool:
    """Confirms whether or not the BOINC client has any active transfers.

    Checks list of transfers for any that are active.

    Args:
        xfer_list: List of transfers.

    Returns:
        True if any active xfers are happening, False if none are happening, or
        if only stalled xfers exist, or if unable to determine.

    Raises:
        Exception: An error occurred parsing entry in transfer list.
    """
    # Known statuses:
    # 0 = Active
    # 1 = happens with stalled xfers, may happen in other scenarios as well
    if isinstance(xfer_list, str):
        return False
    try:
        for xfer in xfer_list:
            if stuck_xfer(xfer):  # ignore stuck xfers
                continue
            if str(xfer["status"]) == "0":
                return True
            else:
                log.warning("Found xfer with unknown status: " + str(xfer))
        return False
    except Exception as e:
        log.error("Error parsing xfers: {}:{}".format(xfer_list, e))
    return False


async def wait_till_no_xfers(rpc_client: RPCClient) -> None:
    """Wait on BOINC client to finish all pending transfers.

    Wait for BOINC to finish all pending xfers, return None when done

    Args:
        rpc_client: Connection to BOINC client instance.

    Raises:
        Exception: An error occurred attempting to communicate with the BOINC client.
    """
    max_loops = 30
    current_loops = 0
    loop_wait_in_seconds = 30  # Wait this long between loops
    # Every ten seconds we will request the list of file transfers from BOINC until
    # there are none left.
    while current_loops < max_loops:
        current_loops += 1
        # Ask BOINC for a list of file transfers
        allow_response = None
        cleaned_response = ""
        try:
            allow_response = await run_rpc_command(rpc_client, "get_file_transfers")
        except Exception as e:
            log.error(
                "Error w/ wait_till_no_xfers,allow respponse exception {}".format(e)
            )
            await asyncio.sleep(loop_wait_in_seconds)
            continue
        if not allow_response:
            log.error("Error w/ wait_till_no_xfers, no allow_response")
            await asyncio.sleep(loop_wait_in_seconds)
            continue
        if isinstance(allow_response, str):
            cleaned_response = re.sub(r"\s*", "", allow_response)
            if cleaned_response == "":  # There are no transfers, yay!
                return
        if xfers_happening(allow_response):
            log.debug("xfers happening: {}".format(str(allow_response)))
            await asyncio.sleep(loop_wait_in_seconds)
            continue
        else:
            return


async def kill_all_unstarted_tasks(
    rpc_client: RPCClient, started: bool = False, quiet: bool = False
) -> None:
    """
    Attempts to kill unstarted tasks, returns None if encounters problems
    @param rpc_client:
    @param started: kill started tasks as well if True
    @return:
    """
    task_list = None
    project_status_reply = None
    try:
        task_list = await get_task_list(rpc_client)
    except Exception as e:
        log.error("Error getting task list from BOINC: {}".format(e))
    if not isinstance(task_list, list):
        return
    try:
        project_status_reply = await rpc_client.get_project_status()
    except Exception as e:
        log.error("Error getting projectstatusreply: {}".format(e))
        return
    found_projects = []  # DEBUG ADDED TYPE THIS CORRECTLY
    for task in task_list:
        try:
            # elapsed_time=task['active_task']['current_cpu_time'].seconds
            name = task["name"]
            # wu_name=task['wu_name']
            project_url = task["project_url"].master_url
            if "active_task" not in task or started:
                if not quiet:
                    print("Cancelling unstarted task {}".format(task))
                log.debug("Cancelling unstarted task {}".format(task))
                req = ET.Element("abort_result")
                a = ET.SubElement(req, "project_url")
                a.text = project_url
                b = ET.SubElement(req, "name")
                b.text = name
                response = await rpc_client._request(req)
                parsed = parse_generic(response)  # Returns True if successful
                a = "21"
            else:
                # print('Keeping task {}'.format(task))
                log.debug("Keeping task {}".format(task))
        except Exception as e:
            log.error("Error ending task: {}: {}".format(task, e))


async def nnt_all_projects(rpc_client: RPCClient) -> None:
    """
    NNT all projects, return when done or if encountered errors
    @param rpc_client:
    @return:
    """
    try:
        project_status_reply = await rpc_client.get_project_status()
        found_projects = []
        for project in project_status_reply:
            found_projects.append(project.master_url)
        for project in found_projects:
            req = ET.Element("project_nomorework")
            a = ET.SubElement(req, "project_url")
            a.text = project
            response = await rpc_client._request(req)
            parsed = parse_generic(response)  # Returns True if successful
    except Exception as e:
        log.error("Error NNTing all projects: {}".format(e))


async def undo_nnt_all_projects(rpc_client: RPCClient) -> None:
    """
    Undo NNT all projects, return when done or if encountered errors
    @param rpc_client:
    @return:
    """
    try:
        project_status_reply = await rpc_client.get_project_status()
        found_projects = []
        for project in project_status_reply:
            found_projects.append(project.master_url)
        for project in found_projects:
            req = ET.Element("project_allowmorework")
            a = ET.SubElement(req, "project_url")
            a.text = project
            response = await rpc_client._request(req)
            parsed = parse_generic(response)  # Returns True if successful
    except Exception as e:
        log.error("Error Un-NNTing all projects: %s", str(e))


async def get_stats_helper(rpc_client: RPCClient):
    """
    Return stats from BOINC client. Development on this is stalled due to BOINC not returning all stats + projects in testing.
    """
    return_value = []
    reply = await run_rpc_command(rpc_client, "get_statistics")
    if not reply:
        log.error("Error getting boinc stats")
        return return_value
    if isinstance(reply, str):
        log.info("BOINC appears to have no stats... : %s", reply)
        return return_value
    # job_logs = await run_rpc_command(rpc_client, "get_old_results")
    return reply


async def boinc_client_to_stats(
    rpc_client: RPCClient,
    quiet: bool = False,
) -> Union[Dict[str, Dict[str, Union[int, float, Dict[str, Union[float, str]]]]], None]:
    """
    Function to gather stats from the BOINC client. Currently not used due to pyBOINC not supporting some calls
    :param rpc_client: BOINC RPC Client
    :return: Dict of stats, or None if encounters errors
    """
    return None
    import copy
    import datetime
    from utils import combine_dicts, resolve_url_database
    from StatsHelper import (
        project_url_from_stats_file,
        stat_file_to_list,
        project_url_from_credit_history_file,
        calculate_credit_averages,
    )

    stats_result = None
    project_status_reply = None
    try:
        stats_result = await get_stats_helper(rpc_client)
    except Exception as e:
        log.error(
            "Error getting stats from BOINC in boinc_client_to_stats: {}".format(e)
        )
    if not isinstance(stats_result, dict):
        return None
    if "project_statistics" not in stats_result:
        log.error(
            "Error project_statistics not in stats_result: {}".format(stats_result)
        )
        return None
    for project in stats_result:
        try:
            # elapsed_time=task['active_task']['current_cpu_time'].seconds
            name = task["name"]
            # wu_name=task['wu_name']
            project_url = task["project_url"].master_url
            if "active_task" not in task or started:
                if not quiet:
                    print("Cancelling unstarted task {}".format(task))
                log.debug("Cancelling unstarted task {}".format(task))
                req = ET.Element("abort_result")
                a = ET.SubElement(req, "project_url")
                a.text = project_url
                b = ET.SubElement(req, "name")
                b.text = name
                response = await rpc_client._request(req)
                parsed = parse_generic(response)  # returns True if successful
                a = "21"
            else:
                # print('Keeping task {}'.format(task))
                log.debug("Keeping task {}".format(task))
        except Exception as e:
            log.error("Error ending task: {}: {}".format(task, e))
    # OLD FUNCTION
    stats_files: List[str] = []
    credit_history_files: List[str] = []
    return_stats = {}
    template_dict = {"CREDIT_HISTORY": {}, "WU_HISTORY": {}, "COMPILED_STATS": {}}

    # find files to search through, add them to lists
    try:
        for file in os.listdir(config_dir_abs_path):
            if "job_log" in file:
                stats_files.append(os.path.join(config_dir_abs_path, file))
            if file.startswith("statistics_") and file.endswith(".xml"):
                credit_history_files.append(os.path.join(config_dir_abs_path, file))
    except Exception as e:
        log.error("Error listing stats files: {}".format(e))
        return {}
    log.debug("Found stats_files: " + str(stats_files))
    log.debug("Found historical credit info files at: " + str(credit_history_files))

    # Process stats files
    for statsfile in stats_files:
        project_url = project_url_from_stats_file(os.path.basename(statsfile))
        project_url = resolve_url_database(project_url)
        if project_url not in return_stats:
            return_stats[project_url] = copy.deepcopy(template_dict)
        stat_list = stat_file_to_list(statsfile)
        parsed = parse_stats_file(stat_list)
        return_stats[project_url]["WU_HISTORY"] = parsed

    # process credit logs
    for credit_history_file in credit_history_files:
        project_url = project_url_from_credit_history_file(
            os.path.basename(credit_history_file)
        )
        project_url = resolve_url_database(project_url)
        credithistorylist = credit_history_file_to_list(credit_history_file)

        # add info from credit history files
        for index, entry in enumerate(credithistorylist):
            try:
                # print('In credit_history_file for ' + project_url)
                # startdate = str(datetime.datetime.fromtimestamp(float(credithistorylist[0]['TIME'])).strftime('%m-%d-%Y'))
                # lastdate = str( datetime.datetime.fromtimestamp(float(credithistorylist[len(credithistorylist) - 1]['TIME'])).strftime('%m-%d-%Y'))
                if (
                    index == len(credithistorylist) - 1
                ):  # Skip the last entry as it's already calculated at the previous entry
                    continue
                # quick sanity checks
                if project_url not in return_stats:
                    return_stats[project_url] = copy.deepcopy(template_dict)
                if "CREDIT_HISTORY" not in return_stats[project_url]:
                    return_stats[project_url]["CREDIT_HISTORY"] = {}
                if "COMPILED STATS" not in return_stats[project_url]:
                    return_stats[project_url]["COMPILED_STATS"] = {}

                credit_history = return_stats[project_url]["CREDIT_HISTORY"]
                next_entry = credithistorylist[index + 1]
                current_time = float(entry["TIME"])
                delta_credits = float(next_entry["HOSTTOTALCREDIT"]) - float(
                    entry["HOSTTOTALCREDIT"]
                )
                # Add found info to combined average stats
                date = str(
                    datetime.datetime.fromtimestamp(float(current_time)).strftime(
                        "%m-%d-%Y"
                    )
                )
                if date not in credit_history:
                    credit_history[date] = {}
                if "CREDITAWARDED" not in credit_history[date]:
                    credit_history[date]["CREDITAWARDED"] = 0
                credit_history[date]["CREDITAWARDED"] += delta_credits
            except Exception as e:
                log.error("Error parsing credit history files: {}".format(e))
    # find averages
    found_averages = calculate_credit_averages(return_stats)
    for url, stats_dict in found_averages.items():
        combine_dicts(return_stats[url]["COMPILED_STATS"], stats_dict)
    return return_stats


def ignore_message_from_check_log_entries(message):
    ignore_phrases = [
        "WORK FETCH RESUMED BY USER",
        "UPDATE REQUESTED BY USER",
        "SENDING SCHEDULER REQUEST",
        "SCHEDULER REQUEST COMPLETED",
        "PROJECT REQUESTED DELAY",
        "WORK FETCH SUSPENDED BY USER",
        "STARTED DOWNLOAD OF",
        "FINISHED DOWNLOAD OF",
        "STARTING TASK",
        "REQUESTING NEW TASKSLAST REQUEST TOO RECENTMASTER FILE DOWNLOAD SUCCEEDED",
        "NO TASKS SENT",
        "REQUESTING NEW TASKS FOR",
        "NO TASKS ARE AVAILABLE FOR",
        "COMPUTATION FOR TASK",
        "STARTED UPLOAD OF",
        "FINISHED UPLOAD OF",
        "THIS COMPUTER HAS REACHED A LIMIT ON TASKS IN PROGRESS",
        "UPGRADE TO THE LATEST DRIVER TO PROCESS TASKS USING YOUR COMPUTER'S GPU",
        "PROJECT HAS NO TASKS AVAILABLE",
    ]
    uppered_message = str(message).upper()
    for phrase in ignore_phrases:
        if phrase in uppered_message:
            return True
    if (
        "UP TO" in uppered_message
        and "NEEDS" in uppered_message
        and "IS AVAILABLE FOR USE" in uppered_message
        and "BUT ONLY" in uppered_message
    ):
        return True
    if "REPORTING" in uppered_message and "COMPLETED TASKS" in uppered_message:
        return True
    return False


def cache_full(project_name: str, messages) -> bool:
    """
    Returns TRUE if CPU /AND/ GPU cache full, False is either is un-full.
    Systems w/o GPU will be assumed to have a "full cache" for GPU
    """
    cpu_full = False
    gpu_full = False
    uppered_project = project_name.upper()
    for message in messages:
        if uppered_project not in str(message).upper():
            continue
        difference = datetime.datetime.now() - message["time"]
        if difference.seconds > 60 * 5:  # If message is > 5 min old, skip
            continue
        uppered_message_body = message["body"].upper()
        if (
            """NOT REQUESTING TASKS: "NO NEW TASKS" REQUESTED VIA MANAGER"""
            in uppered_message_body
        ):
            continue
        if uppered_project == message["project"].upper():
            if (
                "CPU: JOB CACHE FULL" in uppered_message_body
                or "NOT REQUESTING TASKS: DON'T NEED (JOB CACHE FULL)"
                in uppered_message_body
            ):
                cpu_full = True
                log.debug("CPU cache appears full {}".format(message["body"]))
            if "NOT REQUESTING TASKS: DON'T NEED".upper() in uppered_message_body:
                if "GPU" not in message["body"].upper():
                    gpu_full = True  # If no GPU, GPU cache is always full
                if (
                    "CPU: JOB CACHE FULL" in uppered_message_body
                    or "NOT REQUESTING TASKS: DON'T NEED (JOB CACHE FULL)"
                    in uppered_message_body
                ):
                    cpu_full = True
                    log.debug("CPU cache appears full {}".format(message["body"]))
                else:
                    if "NOT REQUESTING TASKS: DON'T NEED ()" in uppered_message_body:
                        pass
                    else:
                        log.debug(
                            "CPU cache appears not full {}".format(message["body"])
                        )
                if "GPU: JOB CACHE FULL" in uppered_message_body:
                    gpu_full = True
                    log.debug("GPU cache appears full {}".format(message["body"]))
                elif "GPUS NOT USABLE" in uppered_message_body:
                    gpu_full = True
                    log.debug("GPU cache appears full {}".format(message["body"]))
                else:
                    if "NOT REQUESTING TASKS: DON'T NEED ()" in uppered_message_body:
                        pass
                    else:
                        if (
                            not gpu_full
                        ):  # If GPU is not mentioned in log, this would always
                            # happen so using this to stop erroneous messages
                            log.debug(
                                "GPU cache appears not full {}".format(message["body"])
                            )
                continue
            elif ignore_message_from_check_log_entries(message):
                pass
            else:
                log.warning("Found unknown message1: {}".format(message["body"]))
    if cpu_full and gpu_full:
        return True
    return False


async def check_log_entries(rpc_client: RPCClient, project_name: str) -> bool:
    """
    Return True if project cache full, False if otherwise or unable to determine.
    project_name: name of project as it will appear in BOINC logs, NOT URL
    """

    try:
        # Get message count
        req = ET.Element("get_message_count")
        msg_count_response = await rpc_client._request(req)
        message_count = int(parse_generic(msg_count_response))
        req = ET.Element("get_messages")
        a = ET.SubElement(req, "seqno")
        a.text = str(message_count - 50)  # Get ten most recent messages
        messages_response = await rpc_client._request(req)
        messages = parse_generic(messages_response)  # Returns True if successful
        if cache_full(project_name, messages):
            return True
        return False
    except Exception as e:
        log.error("Error in check_log_entries: {}".format(e))
        return False


def backoff_ignore_message(message: Dict[str, Any], ignore_phrases: List[str]) -> bool:
    """
    Returns True if message can be ignored while checking for backoffs. False otherwise
    """
    uppered = str(message["body"]).upper()
    for phrase in ignore_phrases:
        if phrase in uppered:
            return True
    if "GOT" in uppered and "NEW TASKS" in uppered:
        return True
    if "REPORTING" in uppered and "COMPLETED TASKS" in uppered:
        return True
    if "COMPUTATION FOR TASK" in uppered and "FINISHED" in uppered:
        return True
    return False


def project_backoff(project_name: str, messages) -> bool:
    """
    Returns TRUE if project should be backed off. False otherwise or if unable to determine
    """
    # Phrases which indicate project SHOULD be backed off
    # - removed 'project requested delay' from positive phrases because
    #   projects always provide this, even if work was provided!
    positive_phrases = [
        "PROJECT HAS NO TASKS AVAILABLE",
        "SCHEDULER REQUEST FAILED",
        "NO TASKS SENT",
        "LAST REQUEST TOO RECENT",
        "AN NVIDIA GPU IS REQUIRED TO RUN TASKS FOR THIS PROJECT",
    ]
    # Phrases which indicate project SHOULD NOT be backed off
    negative_phrases = [
        "NOT REQUESTING TASKS: DON'T NEED",
        "STARTED DOWNLOAD",
        "FINISHED DOWNLOAD OF",
    ]
    # Phrases which indicate we can skip this log entry
    ignore_phrases = [
        "WORK FETCH RESUMED BY USER",
        "UPDATE REQUESTED BY USER",
        "WORK FETCH SUSPENDED BY USER",
        "STARTING TASK",
        "REQUESTING NEW TASKS",
        "SENDING SCHEDULER REQUEST",
        "SCHEDULER REQUEST COMPLETED",
        "STARTED UPLOAD",
        "FINISHED UPLOAD",
        "MASTER FILE DOWNLOAD SUCCEEDED",
        "FETCHING SCHEDULER LIST",
        "UPGRADE TO THE LATEST DRIVER TO PROCESS TASKS USING YOUR COMPUTER'S GPU",
        "NOT STARTED AND DEADLINE HAS PASSED",
        "PROJECT REQUESTED DELAY OF",
    ]
    uppered_project = project_name.upper()
    for message in messages:
        uppered_body = message["body"].upper()
        uppered_message = str(message).upper()
        if uppered_project not in uppered_message:
            continue
        difference = datetime.datetime.now() - message["time"]
        if difference.seconds > 60 * 5:  # If message is > 5 min old, skip
            continue
        if backoff_ignore_message(message, ignore_phrases):
            continue
        for phrase in positive_phrases:
            if phrase in uppered_body:
                log.debug("Backing off {} bc {} in logs".format(project_name, phrase))
                return True
        for phrase in negative_phrases:
            if phrase in uppered_body:
                return False
        if (
            "NEEDS" in uppered_body
            and "BUT ONLY" in uppered_body
            and "IS AVAILABLE FOR USE" in uppered_body
        ):
            log.debug(
                "Backing off {} bc NEEDS BUT ONLY AVAILABLE FOR USE in logs".format(
                    project_name
                ),
                "DEBUG",
            )
            return True
        log.debug("Found unknown messagex: {}".format(message["body"]))
    log.warning(
        "Unable to determine if project {} should be backed off, assuming no".format(
            project_name
        )
    )
    return False


async def check_log_entries_for_backoff(
    rpc_client: RPCClient, project_name: str
) -> bool:
    """
    Return True if project should be backed off, False otherwise or if errored
    project_name: name of project as it will appear in BOINC logs, NOT URL
    """
    try:
        # Get message count
        req = ET.Element("get_message_count")
        msg_count_response = await rpc_client._request(req)
        message_count = int(parse_generic(msg_count_response))
        req = ET.Element("get_messages")
        a = ET.SubElement(req, "seqno")
        a.text = str(message_count - 50)  # Get ten most recent messages
        messages_response = await rpc_client._request(req)
        messages = parse_generic(messages_response)  # Returns True if successful
        if project_name.upper() == "GPUGRID.NET":
            project_name = (
                "GPUGRID"  # Fix for log entries which show up under different name
            )
        return project_backoff(project_name, messages)
    except Exception as e:
        log.error(
            "Error in check_log_entries_for_backoff: project name {} :{}".format(
                project_name, e
            )
        )
        return False


async def get_all_projects(
    rpc_client: RPCClient,
) -> Dict[str, str]:
    """
    Get ALL projects the BOINC client knows about, even if unattached. This SHOULD crash the program if it doesn't work
    so there is no try/except clause
    """
    req = ET.Element("get_all_projects_list")
    messages_response = await rpc_client._request(req)
    project_status_reply = parse_generic(
        messages_response
    )  # Returns True if successful
    project_names = {}
    for project in project_status_reply:
        project_names[project["url"]] = project["name"]
    project_names["https://gene.disi.unitn.it/test/"] = (
        "TN-Grid"  # Added bc BOINC client does not list this project for some reason
    )
    return project_names


async def get_attached_projects(
    rpc_client: RPCClient,
) -> Union[Tuple[List[str], Dict[str, str]], Tuple[None, None]]:
    try:
        project_status_reply = await rpc_client.get_project_status()
        found_projects = []
        project_names = {}
        for project in project_status_reply:
            found_projects.append(project.master_url)
            if isinstance(
                project.project_name, bool
            ):  # This happens if project is "attached" but unable to communicate
                # with the project due to it being down or some other issue
                project_names[project.master_url] = project.master_url
            else:
                project_names[project.master_url] = project.project_name
        return found_projects, project_names
    except Exception as e:
        log.error("Error in get_attached_projects {}".format(e))
        return None, None


async def verify_boinc_connection(
    rpc_client: RPCClient,
) -> bool:
    """
    Checks if a BOINC client can be connected to and authorized.
    Returns True if it can, False if it can't.
    """
    try:
        authorize_response = await rpc_client.authorize()
        req = ET.Element("get_global_prefs_working")
        response = await rpc_client._request(req)
        if "unauthorized" in str(response):
            return False
        return True
    except Exception as e:
        log.error("Error connecting to BOINC in verify_boinc_connection: {}".format(e))
        return False


async def prefs_check(
    rpc_client: RPCClient,
    global_prefs: Union[dict, None] = None,
    disk_usage: Union[dict, None] = None,
    min_gb: float = 10,
    expected_gb_used: float = 0.5,
    scripted_run: bool = False,
    testing: bool = False,
) -> bool:
    """
    Check that BOINC is configured in the way FTM needs. Currently checks disk usage settings and network settings,
    warns user and quits if they are not correct. Also returns True is tests pass, false otherwise
    : global_prefs : for testing only
    : disk usage : for testing only
    """
    # Authorize BOINC client
    authorize_response = await rpc_client.authorize()
    # Get prefs
    return_val = True
    if not global_prefs:
        req = ET.Element("get_global_prefs_working")
        response = await rpc_client._request(req)
        parsed = parse_generic(response)  # Returns True if successful
        global_prefs = parsed
    if not disk_usage:
        # Get actual disk usage
        req = ET.Element("get_disk_usage")
        response = await rpc_client._request(req)
        usage = parse_generic(response)  # Returns True if successful
        disk_usage = usage
    max_gb = int(float(global_prefs.get("disk_max_used_gb", 0)))
    used_max_gb = int(int(disk_usage["d_allowed"]) / 1024 / 1024 / 1024)
    if (max_gb < min_gb and max_gb != 0) or used_max_gb < (min_gb - expected_gb_used):
        if not testing:
            print_and_log(
                "BOINC is configured to use less than {}GB, this tool will not run with <{}GB allocated in order to prevent requesting base project files from projects too often.".format(
                    min_gb, min_gb
                ),
                "ERROR",
            )
            print_and_log(
                'If you have configured BOINC to be able to use >={}GB and still get this message, it is because you are low on disk space and BOINC is responding to settings such as "don\'t use greater than X% of space" or "leave x% free"'.format(),
                "ERROR",
            )
            if not scripted_run:
                input("Press enter to quit")
            sys.exit(1)
        else:
            return_val = False
    net_start_hour = int(float(global_prefs["net_start_hour"])) + int(
        float(global_prefs["net_end_hour"])
    )
    if net_start_hour != 0:
        if not testing:
            print(
                "You have BOINC configured to only access the network at certain times, this tool requires constant "
                "internet availability."
            )
            log.error(
                "You have BOINC configured to only access the network at certain times, this tool requires constant "
                "internet availability."
            )
            if not scripted_run:
                input("Press enter to quit")
            sys.exit(1)
        else:
            return_val = False
    return return_val
