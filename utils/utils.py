from __future__ import annotations

import functools
import logging
from math import ceil, floor
import signal
import datetime
from typing import Any, Collection, Dict, Generic, Iterable, List, TypeVar, Union

A = TypeVar("A")


# Magic
class EquivalentWrapper(Generic[A], object):
    def __init__(self, o: A):
        self.obj = o

    def __eq__(self, other):
        return isinstance(other, EquivalentWrapper)

    def __hash__(self):
        return 0


# URL resolution
@functools.cache
def _resolve_url_database(uppered: str) -> str:
    """
    Given a URL or list of URLs, return the canonical version used in DATABASE and other internal references. Note that some projects operate at multiple
    URLs. This will choose one URL and collapse all other URLs into it.
    @param url: A url you want canonicalized
    """
    canonical = uppered[:]
    canonical = canonical.replace("HTTPS://WWW.", "")
    canonical = canonical.replace("HTTP://WWW.", "")
    canonical = canonical.replace("HTTPS://", "")
    canonical = canonical.replace("HTTP://", "")
    if canonical.startswith(
        "WWW."
    ):  # This is needed as WWW. may legitimately exist in a url outside of the starting portion
        canonical = canonical.replace("WWW.", "")
    if canonical.endswith("/"):  # Remove trailing slashes
        canonical = canonical[:-1]
    if "WORLDCOMMUNITYGRID.ORG/BOINC" in canonical:
        canonical = "WORLDCOMMUNITYGRID.ORG"
    return canonical


def resolve_url_database(url: str) -> str:
    """
    Given a URL or list of URLs, return the canonical version used in DATABASE and other internal references. Note that some projects operate at multiple
    URLs. This will choose one URL and collapse all other URLs into it.
    @param url: A url you want canonicalized
    """
    uppered = url.upper()
    return _resolve_url_database(uppered)


def resolve_url_list_to_database(url_list: List[str]) -> List[str]:
    """
    @param url_list: A list of URLs
    @return: The URLs in canonical database format
    """
    return_list = []
    for url in url_list:
        return_list.append(resolve_url_database(url))
    return return_list


def in_list(my_str: str, list_: Collection[str]) -> bool:
    search_str = resolve_url_database(my_str)
    for item in list_:
        if search_str in item.upper():
            return True
    return False


def project_name_to_url(
    searchname: str, project_resolver_dict: Dict[str, str]
) -> Union[str, None]:
    uppered = searchname.upper()
    for found_project_name, project_url in project_resolver_dict.items():
        if found_project_name.upper() == uppered:
            return resolve_url_database(project_url)
    return None


def grc_project_name_to_url(
    searchname: str,
    all_projects: Union[Dict[str, str], Dict[str, Dict[str, Any]]],
) -> Union[str, None]:
    """
    Convert a project name into its canonical project URL
    : param : all_projects putput from listprojects rpc command
    """
    uppered = searchname.upper()
    for found_project_name, found_project_dict in all_projects.items():
        if found_project_name.upper() == uppered:
            if isinstance(found_project_dict, str):
                return found_project_dict
            elif isinstance(found_project_dict, dict):
                return found_project_dict["base_url"]
    return None


def project_url_to_name_boinc(url: str, project_names: Dict[str, str]):
    """Attempt to convert specified project URL to the project name.

    This function is the same as project_url_to_name, except it returns names for
    parsing BOINC logs.

    Args:
        url: URL of desired BOINC project.
        project_names: Dictionary of project names with the key as the project URL,
            from the BOINC client database..

    Returns:
        The human-readable project name associated with the specified URL, or
        the converted specified URL if the project is not found.
    """
    canonical_url = resolve_url_database(url)
    for project_url, name in project_names.items():
        if canonical_url in project_url or canonical_url == project_url:
            return name
    return url


@functools.cache
def _project_url_to_name(url: str, project_names: EquivalentWrapper[Dict[str, str]]):
    """Attempt to convert specified project URL to the project name.

    This function is of low importance and must only be used when printing the table.
    Do NOT USE for any other purpose.

    Args:
        url: URL of desired BOINC project.
        project_names: Dictionary of project names with the key as the project URL,
            from the BOINC client database..

    Returns:
        The human-readable project name associated with the specified URL, or
        the converted specified URL if the project is not found.
    """
    canonical_url = resolve_url_database(url)
    found = url
    for project_url, name in project_names.obj.items():
        if canonical_url in project_url.upper() or canonical_url == project_url.upper():
            found = name.lower().replace("@home", "").replace("athome", "")
    return found


def project_url_to_name(url: str, project_names: Dict[str, str]):
    """Attempt to convert specified project URL to the project name.

    This function is of low importance and must only be used when printing the table.
    Do NOT USE for any other purpose.

    Args:
        url: URL of desired BOINC project.
        project_names: Dictionary of project names with the key as the project URL,
            from the BOINC client database..

    Returns:
        The human-readable project name associated with the specified URL, or
        the converted specified URL if the project is not found.
    """
    return _project_url_to_name(url, EquivalentWrapper(project_names))


# String alignment
def left_align(yourstring: str, total_len: int, min_pad: int = 0) -> str:
    """Left-aligns specified string using given length and padding.

    Constructs a string of length total_len with yourstring left-aligned and
    padded with spaces on the right. Padding includes at least min_pad spaces,
    cutting off yourstring if required.

    Example: ("examplestring", 15, 1) will create a string that looks like
    this: 'examplestring  '.

    Returns:
        Left-aligned string of total_len with min_pad padding of spaces on the
        right of the text.

    TODO:
        Confirm that returned string should be shorter than total_len based on
        the value of min_pad, or should the length always be total_len.
        Example ("yourstring",15,1) returns 'yourstring    ' where the length
        is actually 14 instead 15.
    """
    if len(yourstring) >= total_len - min_pad:
        yourstring = yourstring[0 : total_len - (min_pad)]
    space_left = total_len - (len(yourstring) + min_pad)
    right_pad = " " * (space_left + min_pad)
    return yourstring + right_pad


def center_align(yourstring: str, total_len: int, min_pad: int = 0) -> str:
    """Center-aligns specified string using given length and padding.

    Constructs a string of length total_len with yourstring center-aligned and
    padded with spaces on the left and right. Padding includes at least min_pad
    spaces, truncating yourstring if required.

    If the padding can not be equal on both sides, then an additional +1 padding is
    added to the right side.

    Example: ("examplestring", 15, 1) will create a string that looks like
    this: ' examplestring '.

    Returns:
        Center-aligned string of total_len with min_pad padding of spaces on the
        left and right of the text.

    TODO:
        Confirm that returned string should be shorter than total_len based on
        the value of min_pad, or should the length always be total_len.
        Example ("yourstring",15,1) returns '  yourstring  ' where the length
        is actually 14 instead 15.
    """
    total_min_pad = min_pad * 2
    room_for_string = total_len - total_min_pad
    if len(yourstring) >= room_for_string:
        yourstring = yourstring[0:room_for_string]
    space_left = total_len - len(yourstring)
    left_pad = " " * floor(space_left / 2)
    right_pad = " " * ceil(space_left / 2)
    return left_pad + yourstring + right_pad


# Object manipulation
def combine_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given dict1, dict2, add dict2 to dict1, over-writing anything in dict1.
    @param dict1:
    @param dict2:
    @return: NONE
    """
    for k, v in dict2.items():
        dict1[k] = v
    return dict1


def date_to_date(date: str) -> datetime.datetime:
    """
    Convert date from str to datetime
    """
    split = date.split("-")
    return datetime.datetime(int(split[2]), int(split[0]), int(split[1]))


def object_hook(obj: Dict[str, str]) -> Union[datetime.datetime, Dict[str, str]]:
    """
    For de-serializing datetimes from json
    """
    _isoformat = obj.get("_isoformat")
    if _isoformat is not None:
        return datetime.datetime.fromisoformat(_isoformat)
    return obj


def json_default(obj) -> Dict[str, str]:
    """
    For serializing datetimes to json
    """
    if isinstance(obj, datetime.datetime):
        return {"_isoformat": obj.isoformat()}
    raise TypeError("...")


# Logging and printing
def print_and_log(
    msg: str,
    log_level: str,
    log: Union[logging.Logger, None] = None,
) -> None:
    """
    Print a message and add it to the log at LOG_LEVEL. Valid log_levels are DEBUG, INFO, WARNING, ERROR
    """
    if log is None:
        log = logging.getLogger()
    print(msg)
    if log_level == "DEBUG":
        log.debug(msg)
    elif log_level == "INFO":
        log.info(msg)
    elif log_level == "WARNING":
        log.warning(msg)
    elif log_level == "ERROR":
        log.error(msg)
    else:
        log.error("Being asked to log at an unknown level: %s", log_level)
        log.info("Unknown message: %s", msg)


# Lifecycle management
class GracefulInterruptHandler(object):

    def __init__(
        self,
        sig: Union[signal.Signals, Iterable[signal.Signals]] = signal.SIGINT,
        handler=lambda _, __: None,
    ):
        self.sig: List[signal.Signals]
        try:
            self.sig = list(sig)
        except TypeError:
            self.sig = [sig]
        self.handler = handler

    def __enter__(self):
        self.released = False

        self.original_handlers = {sig: signal.getsignal(sig) for sig in self.sig}

        def handler(signum, frame):
            self.handler(signum, frame)

        for sig in self.sig:
            signal.signal(sig, handler)

        return self

    def __exit__(self, type, value, tb):
        self.release()

    def release(self):

        if self.released:
            return False

        for sig, original_handler in self.original_handlers.items():
            signal.signal(sig, original_handler)

        self.released = True

        return True


def project_list_to_project_list(project_list: List[dict]) -> List[str]:
    """
    Convert get_project_list into a list of project URLs so we can perform 'in' comparisons
    """
    return_list = []
    for project in project_list:
        return_list.append(project["master_url"])
    return return_list
