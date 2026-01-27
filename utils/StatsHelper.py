from __future__ import annotations

import copy
import os
import functools
import logging
import re
from typing import Collection, Dict, List, Tuple, Union
from utils.utils import EquivalentWrapper, combine_dicts, in_list, resolve_url_database
import datetime
import xmltodict

from utils.utils import print_and_log as _print_and_log

log = logging.getLogger()
print_and_log = functools.partial(_print_and_log, log=log)


def project_url_from_stats_file(statsfilename: str) -> str:
    """Guess a projec url using stats file name.

    Guess a project URL from the name of a stats file.

    Args:
        statsfilename:

    Returns:
        URL for project associated with stats file, or stats file name if URL unknown.
    """
    # Remove extraneous information from name
    statsfilename = statsfilename.replace("job_log_", "")
    statsfilename = statsfilename.replace(".txt", "")
    statsfilename = statsfilename.replace("_", "/")
    return resolve_url_database(statsfilename)


def project_url_from_credit_history_file(filename: str) -> str:
    """Guess a project URL using credit history file name

    Guess a project URL from credit history file name.

    Args:
        filename:

    Returns:
        URL for project associated with stats file, or credit history
        file name if URL unknown.
    """
    filename = filename.replace("statistics_", "")
    filename = filename.replace(".xml", "")
    filename = filename.replace("_", "/")
    return resolve_url_database(filename)


def stat_file_to_list(
    stat_file_abs_path: Union[str, None] = None, content: Union[str, None] = None
) -> List[Dict[str, str]]:
    """Retrieve a list of tasks and related stats from BOINC client log file.

    Turns a BOINC job log into list of dictionaries we can use, each dictionary
    is a task.
    Dictionaries have the following keys:
        STARTTIME,ESTTIME,CPUTIME,ESTIMATEDFLOPS,TASKNAME,WALLTIME,EXITCODE

    Note that ESTIMATEDFLOPS comes from the project and EXITCODE will always be zero.
    All values and keys in dicts are strings.

    BOINC's job log format is:
        [ue]	Estimated runtime	BOINC Client estimate (seconds)
        [ct]	CPU time		Measured CPU runtime at completion (seconds)
        [fe]	Estimated FLOPs count	From project (integer)
        [nm]	Task name		From project
        [et]	Elapsed time 		Wallclock runtime at completion (seconds)

    Args:
        stat_file_abs_path: BOINC client statistics log file with absolute path
        content: Added for testing purposes.

    Returns:
        List dictionaries, each a BOINC task with statistics.

    Raises:
        Exception: An error occurred when attempting to read a BOINC job log file.
        Exception: An error occurred when attempting to parse a BOINC job log file.
    """
    stats_list = []
    try:
        if not content:
            assert stat_file_abs_path is not None
            content = open(stat_file_abs_path, mode="r", errors="ignore").read()
        for log_entry in content.splitlines():
            # log.debug('Found logentry '+str(log_entry))
            match = None
            try:
                match = re.search(
                    r"(\d*)( ue )([\d\.]*)( ct )([\d\.]*)( fe )(\d*)( nm )(\S*)( et )([\d\.]*)( es )(\d)",
                    log_entry,
                )
            except Exception as e:
                print_and_log(
                    (
                        "Error reading BOINC job log at " + "<ARGUMENT>"
                        if stat_file_abs_path is None
                        else stat_file_abs_path
                        + " maybe it's corrupt? Line: {} error: {}".format(log_entry, e)
                    ),
                    "ERROR",
                )
            if not match:
                print_and_log(
                    "Encountered log entry in unknown format: " + log_entry, "ERROR"
                )
                continue
            stats = dict()
            stats["STARTTIME"] = match.group(1)
            stats["ESTTIME"] = match.group(3)
            stats["CPUTIME"] = match.group(5)
            stats["ESTIMATEDFLOPS"] = match.group(7)
            stats["TASKNAME"] = match.group(9)
            stats["WALLTIME"] = match.group(11)
            stats["EXITCODE"] = match.group(13)
            stats_list.append(stats)
        return stats_list
    except Exception as e:
        print_and_log(
            (
                "Error reading BOINC job log at " + "<ARGUMENT>"
                if stat_file_abs_path is None
                else stat_file_abs_path + " maybe it's corrupt? " + str(e)
            ),
            "ERROR",
        )
        return []


def credit_history_file_to_list(credithistoryfileabspath: str) -> List[Dict[str, str]]:
    """Retrieve BOINC credit history

    Turns a BOINC credit history file into list of dictionaries we can use.

    Dictionaries have keys below:
        TIME,USERTOTALCREDIT,USERRAC,HOSTTOTALCREDIT,HOSTRAC

    Note that ESTIMATEDFLOPS comes from the project and EXITCODE will always be zero.

    Args:
        credithistoryfileabspath: Filename with absolute path.

    Returns:
        List of dicionaries with the following keys:
            TIME,USERTOTALCREDIT,USERRAC,HOSTTOTALCREDIT,HOSTRAC

    Raises:
        Exception: An error occurred attempting to read and parse the credit history file.
    """
    statslist = []
    try:
        with open(
            credithistoryfileabspath, mode="r", encoding="ASCII", errors="ignore"
        ) as f:
            parsed = xmltodict.parse(f.read())
            for logentry in parsed.get("project_statistics", {}).get(
                "daily_statistics", []
            ):
                stats = {}
                if not isinstance(logentry, dict):
                    continue
                stats["TIME"] = logentry["day"]
                stats["USERTOTALCREDIT"] = logentry["user_total_credit"]
                stats["USERRAC"] = logentry["user_expavg_credit"]
                stats["HOSTTOTALCREDIT"] = logentry["host_total_credit"]
                stats["HOSTRAC"] = logentry["host_expavg_credit"]
                statslist.append(stats)
    except Exception as e:
        log.error("Error reading statsfile {} {}".format(credithistoryfileabspath, e))
    return statslist


def parse_stats_file(
    stat_list: List[Dict[str, str]],
) -> Dict[str, Dict[str, Union[str, float, int]]]:
    """

    @param stat_list: output from stat_file_to_list
    @return:
    """
    try:
        wu_history = {}
        for wu in stat_list:
            date = str(
                datetime.datetime.fromtimestamp(float(wu["STARTTIME"])).strftime(
                    "%m-%d-%Y"
                )
            )
            if date not in wu_history:
                wu_history[date] = {
                    "TOTALWUS": 0,
                    "total_wall_time": 0,
                    "total_cpu_time": 0,
                }
            wu_history[date]["TOTALWUS"] += 1
            wu_history[date]["total_wall_time"] += float(wu["WALLTIME"])
            wu_history[date]["total_cpu_time"] += float(wu["CPUTIME"])
    except Exception as e:
        log.error("Error in parse_stats_file: {}".format(e))
        return {}
    else:
        return wu_history


def calculate_credit_averages(
    my_stats: dict, rolling_weight_window: int = 60
) -> Dict[str, Dict[str, float]]:
    return_stats = {}
    for project_url, parent_dict in my_stats.items():
        return_stats[project_url] = {}
        total_wus = 0
        total_credit = 0
        total_cpu_time = 0
        total_wall_time = 0
        x_day_wall_time = 0
        for date, credit_history in parent_dict["CREDIT_HISTORY"].items():
            total_credit += credit_history["CREDITAWARDED"]
        for date, wu_history in parent_dict["WU_HISTORY"].items():
            total_wus += wu_history["TOTALWUS"]
            total_wall_time += wu_history["total_wall_time"]
            split_date = date.split("-")
            datetimed_date = datetime.datetime(
                year=int(split_date[2]),
                month=int(split_date[0]),
                day=int(split_date[1]),
            )
            time_ago = datetime.datetime.now() - datetimed_date
            days_ago = time_ago.days
            if days_ago <= rolling_weight_window:
                x_day_wall_time += wu_history["total_wall_time"]
            total_cpu_time += wu_history["total_cpu_time"]
        if total_wus == 0:
            avg_wall_time = 0
            avg_cpu_time = 0
            avg_credit_per_task = 0
            credits_per_hour = 0
        else:
            total_cpu_time = total_cpu_time / 60 / 60  # convert to hours
            total_wall_time = total_wall_time / 60 / 60  # convert to hours
            x_day_wall_time = x_day_wall_time / 60 / 60  # convert to hours
            avg_wall_time = total_wall_time / total_wus
            avg_cpu_time = total_cpu_time / total_wus
            avg_credit_per_task = total_credit / total_wus
            credits_per_hour = total_credit / (total_wall_time)
        return_stats[project_url]["TOTALCREDIT"] = total_credit
        return_stats[project_url]["AVGWALLTIME"] = avg_wall_time
        return_stats[project_url]["AVGCPUTIME"] = avg_cpu_time
        return_stats[project_url]["AVGCREDITPERTASK"] = avg_credit_per_task
        return_stats[project_url]["TOTALTASKS"] = total_wus
        return_stats[project_url]["TOTALWALLTIME"] = total_wall_time
        return_stats[project_url]["TOTALCPUTIME"] = total_cpu_time
        return_stats[project_url]["AVGCREDITPERHOUR"] = credits_per_hour
        return_stats[project_url]["XDAYWALLTIME"] = x_day_wall_time
        log.debug(
            "For project {} this host has crunched {} WUs for {} total credit with an average of {} credits per WU. {} hours were spent on these WUs for {} credit/hr".format(
                project_url.lower(),
                total_wus,
                round(total_credit, 2),
                round(avg_credit_per_task, 2),
                round((total_wall_time), 2),
                round(credits_per_hour, 2),
            )
        )
    return return_stats


def config_files_to_stats(
    config_dir_abs_path: str,
    rolling_weight_window: int = 60,
) -> Dict[str, Dict[str, Union[int, float, Dict[str, Union[float, str]]]]]:
    """Extract BOINC statistics from all available log and stats files.

    Identifies all job log and statistics files in the specified directory. Extracts
    all stats from found files and constructs dictionaries of them.

    Args:
        config_dir_abs_path: Absolute path to BOINC data directory.

    Returns:
        Dictionary of statistics in format COMBINED_STATS_EXAMPLE in main.py, or
        an empty dictionary if unable to retrieve a list of statistics files.

    Raises:
        Exception: An error occurred retrieving list of statistics files.
        Exception: An error occurred parsing credit history files.
    """
    stats_files: List[str] = []
    credit_history_files: List[str] = []
    return_stats = {}
    template_dict = {"CREDIT_HISTORY": {}, "WU_HISTORY": {}, "COMPILED_STATS": {}}

    # Find files to search through, add them to lists
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

        # Add info from credit history files
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
    # Find averages
    found_averages = calculate_credit_averages(
        return_stats, rolling_weight_window=rolling_weight_window
    )
    for url, stats_dict in found_averages.items():
        combine_dicts(return_stats[url]["COMPILED_STATS"], stats_dict)
    return return_stats


def add_mag_to_combined_stats(
    combined_stats: dict,
    mag_ratios: Union[Dict[str, float], None],
    approved_projects: List[str],
    preferred_projects: List[str],
) -> Tuple[dict, List[str]]:
    """Adds magnitude ratios to combined statistics

    Args:
        combined_stats: COMBINED_STATS from main.py.
        mag_ratios: Magnitude ratios returned from get_project_mag_ratios.
            A dictionary with project URL as key and magnitude ratio as value
        approved_projects:
        preferred_projects:

    Returns: A tuple consisting of:
        COMBINED_STATS with magnitude ratios added to it,
        list of projects which are being crunched but not on approved projects list.
    """
    unapproved_list = []
    if not mag_ratios:
        log.error(
            "In add_mag_to_combined_ratios but mag_ratios is empty. Setting all mag ratios to zero."
        )
        mag_ratios = {}
    for project_url, project_stats in combined_stats.items():
        found_mag_ratio = mag_ratios.get(project_url, 0)
        if not found_mag_ratio:
            if project_url not in approved_projects:
                if project_url not in preferred_projects:
                    unapproved_list.append(project_url)
            project_stats["COMPILED_STATS"]["AVGMAGPERHOUR"] = 0
            project_stats["COMPILED_STATS"]["MAGPERCREDIT"] = 0
            continue
        avg_credit_per_hour = 0
        if "AVGCREDITPERHOUR" in project_stats["COMPILED_STATS"]:
            avg_credit_per_hour = project_stats["COMPILED_STATS"]["AVGCREDITPERHOUR"]
        project_stats["COMPILED_STATS"]["AVGMAGPERHOUR"] = (
            avg_credit_per_hour * found_mag_ratio
        )
        project_stats["COMPILED_STATS"]["MAGPERCREDIT"] = found_mag_ratio
    return combined_stats, unapproved_list


def is_project_eligible(
    project_url: str, project_stats: dict, ignored_projects: Collection[str]
) -> bool:
    """
    Returns True if project is eligible based on completed tasks, ignored_projects. Returns True on error.
    """
    # Ignore projects and projects w less than 10 completed tasks are ineligible
    if project_url in ignored_projects:
        return False
    try:
        if int(project_stats["COMPILED_STATS"]["TOTALTASKS"]) >= 10:
            return True
    except Exception as e:
        log.error(
            "Error in is_project_eligible for project {} {}".format(project_url, e)
        )
        return True
    return False


def get_first_non_ignored_project(
    project_list: List[str], ignored_projects: List[str]
) -> Union[str, None]:
    return_value = None
    for project in project_list:
        if project not in ignored_projects:
            return project
    log.error("Error: No projects found in get_first_non_ignored_project")
    return return_value


def get_most_mag_efficient_projects(
    combinedstats: dict,
    ignored_projects: List[str],
    percentdiff: int = 10,
    quiet: bool = False,
) -> List[str]:
    """Determines most magnitude efficient project(s).

    Given combinedstats, determines most mag efficient project(s). This is the #1
    most efficient project and any other projects which are within percentdiff of
    that number.

    Args:
        combinedstats: combinedstats dict
        percentdiff: Maximum percent diff

    Returns:
        List of project URLs, or empty list if none are found.
    """
    return_list = []
    highest_project = get_first_non_ignored_project(
        list(combinedstats.keys()), ignored_projects
    )
    if not highest_project:
        log.error("No highest project found in get_most_mag_efficient_project")
        return []
    # find the highest project
    for project_url, project_stats in combinedstats.items():
        if project_url in ignored_projects:
            continue
        current_mag_per_hour = project_stats["COMPILED_STATS"]["AVGMAGPERHOUR"]
        highest_mag_per_hour = combinedstats[highest_project]["COMPILED_STATS"][
            "AVGMAGPERHOUR"
        ]
        if current_mag_per_hour > highest_mag_per_hour and is_project_eligible(
            project_url, project_stats, ignored_projects
        ):
            highest_project = project_url
    if combinedstats[highest_project]["COMPILED_STATS"]["TOTALTASKS"] >= 10:
        if not quiet:
            print(
                "\n\nHighest mag/hr project --with at least 10 completed WUs-- is {} w/ {}/hr of credit.".format(
                    highest_project.lower(),
                    combinedstats[highest_project]["COMPILED_STATS"]["AVGMAGPERHOUR"],
                )
            )
        log.info(
            "Highest mag/hr project //with at least 10 completed WUs// is {} w/ {}/hr of credit.".format(
                highest_project,
                combinedstats[highest_project]["COMPILED_STATS"]["AVGMAGPERHOUR"],
            )
        )
    return_list.append(highest_project)

    # then compare other projects to it to see if any are within percentdiff of it
    highest_avg_mag = combinedstats[highest_project]["COMPILED_STATS"]["AVGMAGPERHOUR"]
    minimum_for_inclusion = highest_avg_mag - (highest_avg_mag * (percentdiff / 100))
    for project_url, project_stats in combinedstats.items():
        current_avg_mag = project_stats["COMPILED_STATS"]["AVGMAGPERHOUR"]
        if project_url == highest_project:
            continue
        if project_url in ignored_projects:
            continue
        if (
            minimum_for_inclusion <= current_avg_mag
            and is_project_eligible(project_url, project_stats, ignored_projects)
            and current_avg_mag != 0
        ):
            if not quiet:
                print(
                    "Also including this project because it's within {}% variance of highest mag/hr project: {}, mag/hr {}".format(
                        percentdiff, project_url.lower(), current_avg_mag
                    )
                )
            log.info(
                "Also including this project because it's within {}% variance of highest mag/hr project: {}, mag/hr {}".format(
                    percentdiff, project_url.lower(), current_avg_mag
                )
            )
            return_list.append(project_url)

    # If there is no highest project, return empty list
    if len(return_list) == 1:
        if combinedstats[highest_project]["COMPILED_STATS"]["TOTALTASKS"] < 10:
            return_list.clear()
    return return_list


@functools.cache
def _resolve_url_boinc_rpc(
    original_uppered: str,
    known_attached_projects: EquivalentWrapper[Collection[str]],
    known_attached_projects_dev: EquivalentWrapper[Collection[str]],
    dev_mode: bool = False,
) -> str | None:
    """
    Given a URL, return the version BOINC is attached to for RPC purposes. Variables aside from dev_mode default to globals if
    not passed in.
    @param url: A url you want canonicalized
    @param known_attached_projects: Projects BOINC is attached to
    @param known_boinc_projects: Projects BOINC knows about via default install xml file (or rpc get_all_projects which returns the same)
    """

    # Do full lookup if that doesn't work
    uppered = original_uppered.replace("HTTPS://WWW.", "")
    uppered = uppered.replace("HTTP://WWW.", "")
    uppered = uppered.replace("HTTPS://", "")
    uppered = uppered.replace("HTTP://", "")
    if uppered.startswith("WWW."):
        uppered = uppered.replace("WWW.", "")
    if dev_mode:
        for known_attached_project in known_attached_projects_dev.obj:
            if uppered in known_attached_project.upper():
                return known_attached_project
    else:
        for known_attached_project in known_attached_projects.obj:
            if uppered in known_attached_project.upper():
                return known_attached_project
        log.debug(
            "{} not in in known attached projects in resolve_url_boinc_rpc".format(
                uppered
            )
        )

    return None


def resolve_url_boinc_rpc(
    url: str,
    known_attached_projects: Collection[str],
    known_attached_projects_dev: Collection[str],
    known_boinc_projects: Collection[str],
    dev_mode: bool = False,
) -> str:
    """
    Given a URL, return the version BOINC is attached to for RPC purposes. Variables aside from dev_mode default to globals if
    not passed in.
    @param url: A url you want canonicalized
    @param known_attached_projects: Projects BOINC is attached to
    @param known_boinc_projects: Projects BOINC knows about via default install xml file (or rpc get_all_projects which returns the same)
    """
    original_uppered = url.upper()
    if "FOLDINGATHOME" in original_uppered:
        return url
    # if not known_attached_projects:
    #     known_attached_projects = ATTACHED_PROJECT_SET
    # if not known_attached_projects_dev:
    #     known_attached_projects_dev = ATTACHED_PROJECT_SET_DEV
    # if not known_boinc_projects:
    #     known_boinc_projects = ALL_PROJECT_URLS

    known_attached_project = _resolve_url_boinc_rpc(
        original_uppered,
        EquivalentWrapper(known_attached_projects),
        EquivalentWrapper(known_attached_projects_dev),
        dev_mode=dev_mode,
    )
    if known_attached_project is not None:
        return known_attached_project

    uppered = original_uppered.replace("HTTPS://WWW.", "")
    uppered = uppered.replace("HTTP://WWW.", "")
    uppered = uppered.replace("HTTPS://", "")
    uppered = uppered.replace("HTTP://", "")
    if uppered.startswith("WWW."):
        uppered = uppered.replace("WWW.", "")

    for known_boinc_project in known_boinc_projects:
        if uppered in known_boinc_project.upper():
            return known_boinc_project
    log.warning("Unable to resolve URL to BOINC url: {}".format(url))
    return url


def get_highest_priority_project(
    combined_stats: dict,
    project_weights: Dict[str, int],
    attached_projects: Union[Collection[str], None] = None,
    quiet: bool = False,
) -> Tuple[List[str], Dict[str, float]]:
    """
    Given STATS, return list of projects sorted by priority. Note that "benchmark" projects are compared to TOTAL time
    while others are compared to windowed time specific by user
    """
    if not attached_projects:
        attached_projects = []
    priority_dict = {}
    # Calculate total time from stats
    total_xday_time = 0
    total_time = 0
    for found_key, projectstats in combined_stats.items():
        total_xday_time += projectstats["COMPILED_STATS"]["XDAYWALLTIME"]
        total_time += projectstats["COMPILED_STATS"]["TOTALWALLTIME"]
    # print('Calculating project weights: total time is {}'.format(total_xday_time))
    log.debug(
        "Calculating project weights: total windowed time is {}".format(total_xday_time)
    )
    for project, weight in project_weights.items():
        if not in_list(project, attached_projects):
            log.debug("skipping project bc not attached {}".format(project))
            continue
        combined_stats_extract = combined_stats.get(project)
        if not combined_stats_extract:
            if not quiet:
                print(
                    "Warning: {} not found in stats, assuming not attached. You can safely ignore this warning w/ a new BOINC install which has not received credit on this project yet ".format(
                        project
                    )
                )
            log.warning(
                "Warning: {} not found in stats, assuming not attached You can safely ignore this warning w/ a new BOINC install which has not received credit on this project yet ".format(
                    project
                )
            )
            existing_time = 0
        else:
            if (
                weight == 1
            ):  # Benchmarking projects should be over ALL time not just recent time
                existing_time = combined_stats_extract["COMPILED_STATS"][
                    "TOTALWALLTIME"
                ]
            else:
                existing_time = combined_stats_extract["COMPILED_STATS"]["XDAYWALLTIME"]
        if weight == 1:
            target_time = existing_time - (total_time * (weight / 1000))
        else:
            target_time = existing_time - (total_xday_time * (weight / 1000))
        priority_dict[project] = round(target_time / 60 / 60, 2)
        log.debug(
            "Project is {} weight is {} existing time is {} so time delta is {}(s) or {}(h)".format(
                project,
                weight,
                existing_time,
                target_time,
                round(target_time / 60 / 60, 4),
            )
        )
    if len(priority_dict) > 0:
        return sorted(priority_dict, key=priority_dict.get), priority_dict
    else:
        print_and_log(
            "Unable to find a highest priority project, maybe all have been checked recently? Sleeping for 10 min",
            "ERROR",
        )
        return [], {}


def get_avg_mag_hr(combined_stats: dict) -> float:
    """
    Get average mag/hr over all projects to date
    """
    found_mag = []
    found_time = []
    for project_url, stats in combined_stats.items():
        total_hours = stats["COMPILED_STATS"]["TOTALWALLTIME"]
        total_mag = (
            stats["COMPILED_STATS"]["TOTALWALLTIME"]
            * stats["COMPILED_STATS"]["AVGMAGPERHOUR"]
        )
        found_mag.append(total_mag)
        found_time.append(total_hours)
    found_sum = sum(found_time)
    found_mag = sum(found_mag)
    if found_sum == 0 or found_mag == 0:
        return 0
    average = found_mag / found_sum
    return average
