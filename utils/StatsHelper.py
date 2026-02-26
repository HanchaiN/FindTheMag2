from __future__ import annotations

import copy
import datetime
import functools
import logging
import math
import os
import re
from typing import (
    Any,
    Collection,
    Container,
    Dict,
    Iterable,
    List,
    Literal,
    Tuple,
    TypedDict,
    Union,
)

import xmltodict

from utils.utils import EquivalentWrapper, combine_dicts, in_list
from utils.utils import print_and_log as _print_and_log
from utils.utils import resolve_url_database

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


@functools.cache
def _resolve_url_boinc_rpc(
    original_uppered: str,
    known_attached_projects: EquivalentWrapper[Collection[str]],
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
    for known_attached_project in known_attached_projects.obj:
        if uppered in known_attached_project.upper():
            return known_attached_project
    log.debug(
        "{} not in in known attached projects in resolve_url_boinc_rpc".format(uppered)
    )

    return None


def resolve_url_boinc_rpc(
    url: str,
    known_attached_projects: Collection[str],
    known_boinc_projects: Collection[str],
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


# === Util classes ===

type TimeMode = Literal["WALL", "CPU", "MAX", "MIN"]


class TimeFloat(TypedDict):
    WALL: float
    CPU: float


def read_timefloat(
    timefloat: TimeFloat,
    time_mode: TimeMode = "WALL",
) -> float:
    if time_mode in timefloat.keys():
        return timefloat.get(time_mode)

    wall_time = read_timefloat(timefloat, "WALL")
    cpu_time = read_timefloat(timefloat, "CPU")
    if wall_time is None or cpu_time is None:
        return wall_time or cpu_time or 0.0

    if time_mode == "MIN":
        return min(wall_time, cpu_time)
    if time_mode == "MAX":
        return max(wall_time, cpu_time)

    log.error("Invalid time_mode: %s" % time_mode)
    return wall_time


# === Config Files to Stats ===
class StatFileEntry(TypedDict):
    STARTTIME: str
    ESTTIME: str
    CPUTIME: str
    ESTIMATEDFLOPS: str
    TASKNAME: str
    WALLTIME: str
    EXITCODE: str


def stat_file_to_list(stat_file_abs_path: str) -> list[StatFileEntry]:
    """Retrieve a list of tasks and related stats from BOINC client log file.

    Turns a BOINC job log into list of dictionaries we can use, each dictionary
    is a task.
    Dictionaries have the following keys:
        STARTTIME,ESTTIME,CPUTIME,ESTIMATEDFLOPS,TASKNAME,WALLTIME,CPUTIME,EXITCODE

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

    Returns:
        List dictionaries, each a BOINC task with statistics.

    Raises:
        Exception: An error occurred when attempting to read a BOINC job log file.
        Exception: An error occurred when attempting to parse a BOINC job log file.
    """
    stats_list: list[StatFileEntry] = []
    try:
        with open(stat_file_abs_path, mode="r", errors="ignore", encoding="utf-8") as f:
            while log_entry := f.readline():
                # log.debug('Found logentry %' % (log_entry))
                match = None
                try:
                    match = re.search(
                        r"(\d*)( ue )([\d\.]*)( ct )([\d\.]*)( fe )(\d*)( nm )(\S*)( et )([\d\.]*)( es )(\d)",
                        log_entry,
                    )
                except Exception as e:
                    print_and_log(
                        "ERROR",
                        (
                            "Error reading BOINC job log at %s maybe it's corrupt? Line: %s error: %s"
                            % (stat_file_abs_path, log_entry, e)
                        ),
                    )
                if not match:
                    print_and_log(
                        "ERROR",
                        "Encountered log entry in unknown format: %s" % log_entry,
                    )
                    continue
                stats = StatFileEntry(
                    STARTTIME=match.group(1),
                    ESTTIME=match.group(3),
                    CPUTIME=match.group(5),
                    ESTIMATEDFLOPS=match.group(7),
                    TASKNAME=match.group(9),
                    WALLTIME=match.group(11),
                    EXITCODE=match.group(13),
                )
                stats_list.append(stats)
    except Exception as e:
        print_and_log(
            "ERROR",
            (
                "Error reading BOINC job log at %s maybe it's corrupt?: %s"
                % (stat_file_abs_path, e)
            ),
        )
        return []
    return stats_list


class WUHistoryEntry(TypedDict):
    TOTALWUS: int
    total_wall_time: float
    total_cpu_time: float


def parse_stats_file(
    stat_list: list[StatFileEntry],
) -> Dict[str, WUHistoryEntry]:
    """

    @param stat_list: output from stat_file_to_list
    @return:
    """
    wu_history: dict[str, WUHistoryEntry] = {}
    for wu in stat_list:
        try:
            date = str(
                datetime.datetime.fromtimestamp(float(wu["STARTTIME"])).strftime(
                    "%m-%d-%Y"
                )
            )
            if date not in wu_history:
                wu_history[date] = WUHistoryEntry(
                    TOTALWUS=0,
                    total_wall_time=0,
                    total_cpu_time=0,
                )
            wu_history[date]["TOTALWUS"] += 1
            wu_history[date]["total_wall_time"] += float(wu["WALLTIME"])
            wu_history[date]["total_cpu_time"] += float(wu["CPUTIME"])
        except Exception as e:
            log.error("Error in parse_stats_file: %s" % e)
    return wu_history


class CreditHistoryFileEntry(TypedDict):
    TIME: str
    USERTOTALCREDIT: str
    USERRAC: str
    HOSTTOTALCREDIT: str
    HOSTRAC: str


def credit_history_file_to_list(
    credithistoryfileabspath: str,
) -> list[CreditHistoryFileEntry]:
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
    statslist: list[CreditHistoryFileEntry] = []
    try:
        with open(
            credithistoryfileabspath, mode="r", encoding="ASCII", errors="ignore"
        ) as f:
            parsed = xmltodict.parse(f.read())
            for logentry in parsed.get("project_statistics", {}).get(
                "daily_statistics", []
            ):
                if not isinstance(logentry, dict):
                    continue
                stats = CreditHistoryFileEntry(
                    TIME=logentry["day"],
                    USERTOTALCREDIT=logentry["user_total_credit"],
                    USERRAC=logentry["user_expavg_credit"],
                    HOSTTOTALCREDIT=logentry["host_total_credit"],
                    HOSTRAC=logentry["host_expavg_credit"],
                )
                statslist.append(stats)
    except Exception as e:
        log.error("Error reading statsfile %s: %s" % (credithistoryfileabspath, e))
    return statslist


class CreditHistoryEntry(TypedDict):
    CREDITAWARDED: float


def parse_credit_history_file(credithistorylist: list[CreditHistoryFileEntry]):
    # Add info from credit history files
    credit_history: dict[str, CreditHistoryEntry] = {}
    for entry, next_entry in zip(credithistorylist, credithistorylist[1:]):
        try:
            delta_credits = float(next_entry["HOSTTOTALCREDIT"]) - float(
                entry["HOSTTOTALCREDIT"]
            )
            # Add found info to combined average stats
            date = str(
                datetime.datetime.fromtimestamp(float(entry["TIME"])).strftime(
                    "%m-%d-%Y"
                )
            )
            if date not in credit_history:
                credit_history[date] = CreditHistoryEntry(CREDITAWARDED=delta_credits)
            credit_history[date]["CREDITAWARDED"] += delta_credits
        except Exception as e:
            log.error("Error parsing credit history files: %s" % (e))
    return credit_history


class BaseCompiledStatsEntry(TypedDict):
    TOTALTASKS: int
    TOTALCREDIT: float
    AVGCREDITPERTASK: float

    TOTALTIME: TimeFloat
    XDAYTIME: TimeFloat
    AVGTIME: TimeFloat
    AVGCREDITPERHOUR: TimeFloat


def calculate_credit_averages(
    project_url: str,
    wu_history_dict: dict[str, WUHistoryEntry],
    credit_history_dict: dict[str, CreditHistoryEntry],
    rolling_weight_window: int = 60,
) -> BaseCompiledStatsEntry:
    total_wus = 0
    total_credit = 0
    total_wall_time = 0
    total_cpu_time = 0
    x_day_cpu_time = 0
    x_day_wall_time = 0
    for date, credit_history in credit_history_dict.items():
        total_credit += credit_history["CREDITAWARDED"]
    for date, wu_history in wu_history_dict.items():
        total_wus += wu_history["TOTALWUS"]
        total_wall_time += wu_history["total_wall_time"]
        total_cpu_time += wu_history["total_cpu_time"]
        split_date = date.split("-")
        datetimed_date = datetime.datetime(
            year=int(split_date[2]),
            month=int(split_date[0]),
            day=int(split_date[1]),
        )
        time_ago = datetime.datetime.now() - datetimed_date
        days_ago = time_ago.days
        if days_ago <= rolling_weight_window:
            x_day_cpu_time += wu_history["total_cpu_time"]
            x_day_wall_time += wu_history["total_wall_time"]
    if total_wus == 0:
        avg_wall_time = 0
        avg_cpu_time = 0
        avg_credit_per_task = 0
        credits_per_wall_hour = 0
        credits_per_cpu_hour = 0
    else:
        total_wall_time = total_wall_time / 60 / 60  # convert to hours
        total_cpu_time = total_cpu_time / 60 / 60  # convert to hours
        x_day_wall_time = x_day_wall_time / 60 / 60  # convert to hours
        x_day_cpu_time = x_day_cpu_time / 60 / 60  # convert to hours
        avg_wall_time = total_wall_time / total_wus
        avg_cpu_time = total_cpu_time / total_wus
        avg_credit_per_task = total_credit / total_wus
        credits_per_wall_hour = total_credit / total_wall_time
        credits_per_cpu_hour = total_credit / total_cpu_time
    log.debug(
        "For project %s this host has crunched %d WUs for %.2f total credit with an average of %.2f credits per WU. %.2f hours were spent on these WUs for %.2f credit/hr"
        % (
            project_url.lower(),
            total_wus,
            total_credit,
            avg_credit_per_task,
            total_wall_time,
            credits_per_wall_hour,
        )
    )
    return BaseCompiledStatsEntry(
        TOTALTASKS=total_wus,
        TOTALCREDIT=total_credit,
        AVGCREDITPERTASK=avg_credit_per_task,
        TOTALTIME=TimeFloat(
            WALL=total_wall_time,
            CPU=total_cpu_time,
        ),
        XDAYTIME=TimeFloat(
            WALL=x_day_wall_time,
            CPU=x_day_cpu_time,
        ),
        AVGTIME=TimeFloat(
            WALL=avg_wall_time,
            CPU=avg_cpu_time,
        ),
        AVGCREDITPERHOUR=TimeFloat(
            WALL=credits_per_wall_hour,
            CPU=credits_per_cpu_hour,
        ),
    )


class CompiledStats(TypedDict):
    TOTALTASKS: int
    TOTALCREDIT: float
    AVGCREDITPERTASK: float
    TOTALTIME: TimeFloat
    XDAYTIME: TimeFloat
    AVGTIME: TimeFloat
    AVGCREDITPERHOUR: TimeFloat

    MAGPERCREDIT: float
    AVGMAGPERHOUR: TimeFloat


def add_mag_to_combined_stats(
    compiled_stats: BaseCompiledStatsEntry,
    found_mag_ratio: float,
) -> CompiledStats:
    """Adds magnitude ratios to combined statistics

    Args:
        compiled_stats: COMPILED_STATS.
        found_mag_ratio: Magnitude ratio returned from get_project_mag_ratios.

    Returns: COMBINED_STATS with magnitude ratios added to it.
    """
    compiled_stats = CompiledStats(
        **compiled_stats, MAGPERCREDIT=0, AVGMAGPERHOUR=TimeFloat(WALL=0, CPU=0)
    )
    if not found_mag_ratio:
        return compiled_stats

    compiled_stats["MAGPERCREDIT"] = found_mag_ratio  # mag / rac = mag day / cred
    for time_key, avgcph in compiled_stats["AVGCREDITPERHOUR"].items():
        compiled_stats["AVGMAGPERHOUR"][time_key] = found_mag_ratio * avgcph
    return compiled_stats


class CombinedStatEntry(TypedDict):
    WU_HISTORY: dict[str, WUHistoryEntry]
    CREDIT_HISTORY: dict[str, CreditHistoryEntry]
    COMPILED_STATS: CompiledStats


type CombinedStats = dict[str, CombinedStatEntry]


def config_files_to_stats(
    config_dir_abs_path: str,
    rolling_weight_window: int = 60,
    mag_ratios: dict[str, float] | None = None,
) -> CombinedStats:
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
    stats_files: list[str] = []
    credit_history_files: list[str] = []
    return_stats: CombinedStats = {}

    # Find files to search through, add them to lists
    try:
        for file in os.listdir(config_dir_abs_path):
            if "job_log" in file:
                stats_files.append(os.path.join(config_dir_abs_path, file))
            if file.startswith("statistics_") and file.endswith(".xml"):
                credit_history_files.append(os.path.join(config_dir_abs_path, file))
    except Exception as e:
        log.error("Error listing stats files: %s" % (e))
        return {}
    log.debug("Found stats_files: %s" % (stats_files))
    log.debug("Found historical credit info files at: %s" % (credit_history_files))

    # Process stats files
    for statsfile in stats_files:
        project_url = project_url_from_stats_file(os.path.basename(statsfile))
        project_url = resolve_url_database(project_url)
        return_stats.setdefault(
            project_url,
            CombinedStatEntry(CREDIT_HISTORY={}, WU_HISTORY={}, COMPILED_STATS={}),
        )["WU_HISTORY"] = parse_stats_file(stat_file_to_list(statsfile))

    # process credit logs
    for credit_history_file in credit_history_files:
        project_url = project_url_from_credit_history_file(
            os.path.basename(credit_history_file)
        )
        project_url = resolve_url_database(project_url)
        return_stats.setdefault(
            project_url,
            CombinedStatEntry(CREDIT_HISTORY={}, WU_HISTORY={}, COMPILED_STATS={}),
        )["CREDIT_HISTORY"] = parse_credit_history_file(
            credit_history_file_to_list(credit_history_file)
        )

    if not mag_ratios:
        log.error("mag_ratios is empty. Setting all mag ratios to zero.")
        mag_ratios = {}
    # Find averages
    for project_url, stat_entry in return_stats.items():
        found_averages = calculate_credit_averages(
            project_url,
            stat_entry["WU_HISTORY"],
            stat_entry["CREDIT_HISTORY"],
            rolling_weight_window=rolling_weight_window,
        )
        compiled_stats = add_mag_to_combined_stats(
            found_averages, mag_ratios.get(project_url, 0)
        )
        stat_entry["COMPILED_STATS"] = compiled_stats

    return return_stats


# === Project status ===


def get_unapproved_list(
    project_urls: Iterable[str],
    mag_ratios: dict[str, float] | None,
    approved_projects: Container[str],
    preferred_projects: Container[str],
) -> list[str]:
    """Adds magnitude ratios to combined statistics

    Args:
        combined_stats: COMBINED_STATS from main.py.
        mag_ratios: Magnitude ratios returned from get_project_mag_ratios.
            A dictionary with project URL as key and magnitude ratio as value
        approved_projects:
        preferred_projects:

    Returns: list of projects which are being crunched but not on approved projects list.
    """
    unapproved_list = []
    if not mag_ratios:
        log.error(
            "In add_mag_to_combined_ratios but mag_ratios is empty. Setting all mag ratios to zero."
        )
        mag_ratios = {}
    for project_url in project_urls:
        found_mag_ratio = mag_ratios.get(project_url, 0)
        if not found_mag_ratio:
            if project_url not in approved_projects:
                if project_url not in preferred_projects:
                    unapproved_list.append(project_url)
    return unapproved_list


def is_project_eligible(
    project_url: str,
    project_stats: CombinedStatEntry,
    ignored_projects: Collection[str],
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


def get_most_mag_efficient_projects(
    combinedstats: CombinedStats,
    ignored_projects: Collection[str],
    percentdiff: int = 10,
    quiet: bool = False,
    time_mode: TimeMode = "WALL",
) -> list[str]:
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
    return_list: list[str] = []
    highest_project = None
    highest_mag_per_hour = -math.inf
    # find the highest project
    for project_url, project_stats in combinedstats.items():
        if project_url in ignored_projects:
            continue
        current_mag_per_hour = read_timefloat(
            project_stats["COMPILED_STATS"]["AVGMAGPERHOUR"], time_mode=time_mode
        )
        if current_mag_per_hour > highest_mag_per_hour and is_project_eligible(
            project_url, project_stats, ignored_projects
        ):
            highest_project = project_url
            highest_mag_per_hour = current_mag_per_hour
    if not highest_project:
        log.error("No highest project found in get_most_mag_efficient_project")
        return []
    if combinedstats[highest_project]["COMPILED_STATS"]["TOTALTASKS"] >= 10:
        print_and_log(
            "INFO",
            "Highest mag/hr project //with at least 10 completed WUs// is %s w/ %f/hr of credit."
            % (
                highest_project.lower(),
                read_timefloat(
                    combinedstats[highest_project]["COMPILED_STATS"]["AVGMAGPERHOUR"],
                    time_mode=time_mode,
                ),
            ),
            quiet=quiet,
        )
    return_list.append(highest_project)

    # then compare other projects to it to see if any are within percentdiff of it
    highest_avg_mag = read_timefloat(
        combinedstats[highest_project]["COMPILED_STATS"]["AVGMAGPERHOUR"],
        time_mode=time_mode,
    )
    minimum_for_inclusion = highest_avg_mag - (highest_avg_mag * (percentdiff / 100))
    for project_url, project_stats in combinedstats.items():
        current_avg_mag = read_timefloat(
            project_stats["COMPILED_STATS"]["AVGMAGPERHOUR"], time_mode=time_mode
        )
        if project_url == highest_project:
            continue
        if project_url in ignored_projects:
            continue
        if (
            minimum_for_inclusion <= current_avg_mag
            and is_project_eligible(project_url, project_stats, ignored_projects)
            and current_avg_mag != 0
        ):
            print_and_log(
                "INFO",
                "Also including this project because it's within %f%% variance of highest mag/hr project: %s, mag/hr %f",
                percentdiff,
                project_url.lower(),
                current_avg_mag,
                quiet=quiet,
            )
            return_list.append(project_url)

    # If there is no highest project, return empty list
    if len(return_list) == 1:
        if combinedstats[highest_project]["COMPILED_STATS"]["TOTALTASKS"] < 10:
            return_list.clear()
    return return_list


def get_highest_priority_project(
    combined_stats: CombinedStats,
    project_weights: dict[str, int],
    attached_projects: Collection[str] | None = None,
    quiet: bool = False,
    time_mode: TimeMode = "WALL",
) -> tuple[list[str], dict[str, float]]:
    """
    Given STATS, return list of projects sorted by priority. Note that "benchmark" projects are compared to TOTAL time
    while others are compared to windowed time specific by user
    """
    if not attached_projects:
        attached_projects = []
    priority_dict: dict[str, float] = {}
    # Calculate total time from stats
    total_xday_time = 0
    total_time = 0
    for _, projectstats in combined_stats.items():
        total_xday_time += read_timefloat(
            projectstats["COMPILED_STATS"]["XDAYTIME"],
            time_mode=time_mode,
        )
        total_time += read_timefloat(
            projectstats["COMPILED_STATS"]["TOTALTIME"], time_mode=time_mode
        )
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
            print_and_log(
                "WARNING",
                "Warning: %s not found in stats, assuming not attached. You can safely ignore this warning w/ a new BOINC install which has not received credit on this project yet ",
                project,
                quiet=quiet,
            )
            existing_time = 0
        else:
            if (
                weight == 1
            ):  # Benchmarking projects should be over ALL time not just recent time
                existing_time = read_timefloat(
                    combined_stats_extract["COMPILED_STATS"]["TOTALTIME"],
                    time_mode=time_mode,
                )
            else:
                existing_time = read_timefloat(
                    combined_stats_extract["COMPILED_STATS"]["XDAYTIME"],
                    time_mode=time_mode,
                )
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
        return (
            sorted(priority_dict.keys(), key=lambda x: priority_dict.get(x, 0)),
            priority_dict,
        )
    else:
        print_and_log(
            "ERROR",
            "Unable to find a highest priority project, maybe all have been checked recently? Sleeping for 10 min",
        )
        return [], {}


def get_avg_mag_hr(
    combined_stats: CombinedStats, time_mode: TimeMode = "WALL"
) -> float:
    """
    Get average mag/hr over all projects to date
    """
    acc_time = 0.0
    acc_mag = 0.0
    for _, stats in combined_stats.items():
        total_hours = read_timefloat(
            stats["COMPILED_STATS"]["TOTALTIME"], time_mode=time_mode
        )
        total_mag = total_hours * read_timefloat(
            stats["COMPILED_STATS"]["AVGMAGPERHOUR"], time_mode=time_mode
        )
        acc_time += total_hours
        acc_mag += total_mag
    if acc_time == 0 or acc_mag == 0:
        return 0.0
    average = acc_mag / acc_time
    return average
