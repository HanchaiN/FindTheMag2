from __future__ import annotations
import functools
import logging

from utils.utils import (
    grc_project_name_to_url,
    json_default,
    print_and_log,
    resolve_url_database,
)


import requests
from requests.auth import HTTPBasicAuth


import json
from time import sleep
from typing import Callable, List, Mapping, Union, Dict
import os
from utils.utils import print_and_log as _print_and_log

log = logging.getLogger()
print_and_log = functools.partial(_print_and_log, log=log)


class GridcoinClientConnection:
    """Allows connecting to a Gridcoin wallet and issuing RPC commands.

    A class for connecting to a Gridcoin wallet and issuing RPC commands. Currently
    quite barebones.

    Attributes:
        config_file:
        ip_address:
        rpc_port:
        rpc_user:
        rpc_password:
        retries:
        retry_delay:
    """

    def __init__(
        self,
        config_file: str | None = None,
        ip_address: str = "127.0.0.1",
        rpc_port: str = "9876",
        rpc_user: str | None = None,
        rpc_password: str | None = None,
        retries: int = 3,
        retry_delay: int = 1,
    ):
        """Initializes the instance based on the connection attributes.

        Attributes:
            config_file:
            ip_address:
            rpc_port:
            rpc_user:
            rpc_password:
            retries: int = 3,
            retry_delay: int = 1,
        """
        self.configfile = config_file  # Absolute path to the client config file
        self.ipaddress = ip_address
        self.rpc_port = rpc_port
        self.rpcuser = rpc_user
        self.rpcpassword = rpc_password
        self.retries = retries
        self.retry_delay = retry_delay

    def run_command(
        self, command: str, arguments: Union[List[Union[str, bool]], None] = None
    ) -> Union[dict, None]:
        """Send command to local Gridcoin wallet

        Sends specifified Gridcoin command to the Gridcoin wallet instance and
        retrieves result of the command execution.

        Args:
            command:
            arguments:

        Returns:
            Response from command exectution as a dictionary of json, or None if
            an error was encounted while connecting to the Gridcoin wallet instance.
        """
        if arguments is None:
            arguments = []
        current_retries = 0
        while current_retries < self.retries:
            sleep(self.retry_delay)
            current_retries += 1
            credentials = None
            url = "http://" + self.ipaddress + ":" + self.rpc_port + "/"
            headers = {"content-type": "application/json"}
            payload = {
                "method": command,
                "params": arguments,
                "jsonrpc": "2.0",
                "id": 0,
            }
            jsonpayload = json.dumps(payload, default=json_default)
            if self.rpcuser is not None and self.rpcpassword is not None:
                credentials = HTTPBasicAuth(self.rpcuser, self.rpcpassword)
            try:
                response = requests.post(
                    url, data=jsonpayload, headers=headers, auth=credentials
                )
                return_response = response.json()
            except Exception:
                pass
            else:
                return return_response
        return None

    def get_approved_project_urls(self) -> List[str]:
        """Retrieves list of projects appoved for Gridcoin.

        Retrieves the list of projects from the local Gridcoin wallet that are
        approved for earning Gridcoin.

        Returns:
            A list of UPPERCASED project URLs using gridcoin command listprojects
        """
        return_list = []
        all_projects = self.run_command("listprojects")
        if all_projects is None:
            return return_list
        for projectname, project in all_projects["result"].items():
            return_list.append(project["base_url"].upper())
        return return_list


def wait_till_synced(grc_client: GridcoinClientConnection):
    """
    A function to WAIT until client is fully synced
    :param grc_client:
    :return:
    """
    printed = False
    while True:
        response = grc_client.run_command("getinfo")
        if isinstance(response, dict):
            sync_status = response.get("result", {}).get("in_sync")
            if sync_status == True:
                return
        sleep(1)
        if printed == False:
            print("Gridcoin wallet is not fully synced yet. Waiting for full sync...")
            printed = True


def get_gridcoin_config_parameters(gridcoin_dir: str) -> Dict[str, str]:
    """Retrive Gridcoin wallet configuration.

       Parses Gridcoin configuration .json and .conf file for configuration parameters.
       Preference is given to those in the json file over those in the to the conf file.

       Note that sidestakes become a list as there may be multiple.

    Args:
        gridcoin_dir: Absolute path to a gridcoin config directory.

    Returns:
        A dictionary of all config parameters found,

    Raises:
        Exception: An error occurred while parsing the config file.
    """
    return_dict = {}
    dupes = {}
    if "gridcoinsettings.json" in os.listdir(gridcoin_dir):
        with open(os.path.join(gridcoin_dir, "gridcoinsettings.json")) as json_file:
            config_dict = json.load(json_file)
            if "rpcuser" in config_dict:
                return_dict["rpc_user"] = config_dict["rpcuser"]
            if "rpcpass" in config_dict:
                return_dict["rpc_pass"] = config_dict["rpcpass"]
            if "rpcport" in config_dict:
                return_dict["rpc_port"] = config_dict["rpcport"]
    if "gridcoinresearch.conf" in os.listdir(gridcoin_dir):
        with open(os.path.join(gridcoin_dir, "gridcoinresearch.conf")) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                if line.strip() == "":
                    continue
                try:
                    key = line.split("=")[0]
                    value = line.split("=")[1].replace("\n", "")
                    if "#" in value:
                        value = value.split("#")[0]
                    value = value.strip()
                except Exception as e:
                    log.error(
                        "Warning: Error parsing line from config file, ignoring: {} error was {}".format(
                            line, e
                        )
                    )
                    continue
                if key == "addnode":
                    continue
                if key == "sidestake":
                    if "sidestake" not in return_dict:
                        return_dict["sidestake"] = []
                    return_dict["sidestake"].append(value)
                    continue
                if key in return_dict:
                    if key not in dupes:
                        dupes[key] = set()
                    dupes[key].add(value)
                    continue
                if key not in return_dict:
                    return_dict[key] = value
    for key, value in dupes.items():
        if len(value) > 1:
            print_and_log(
                "Warning: multiple values found for "
                + key
                + " in gridcoin config file at "
                + os.path.join(gridcoin_dir, "gridcoinresearch.conf")
                + " using the first one we found",
                "WARNING",
            )

    return return_dict


def check_sidestake(
    config_params: Mapping[str, Union[str, List[str]]], address: str, minval: float
) -> bool:
    """Confirms whether or not the given address is being adequately sidestaked.

    Checks if a given address is being sidestaked to or not. Returns False if value < minval

    Args:
        config_params: config_params from get_config_parameters
        address: address to check
        minval: minimum value to pass check

    Returns:
        True if given address is sidestaked for more than the given minium.
    """
    if "enablesidestaking" not in config_params:
        return False
    if "sidestake" not in config_params:
        return False
    if config_params["enablesidestaking"] != "1":
        return False
    for sidestake in config_params["sidestake"]:
        found_address = sidestake.split(",")[0]
        found_value = float(sidestake.split(",")[1])
        if found_address == address:
            if found_value >= minval:
                return True
    return False


class ProjectMagRatio:
    PROJECT_MAG_RATIOS_CACHE = {}

    @classmethod
    def get_project_mag_ratios(
        cls,
        grc_client: GridcoinClientConnection,
        lookback_period: int = 30,
        dump_rac_mag_ratios: Union[Callable[[Dict[str, float]], None], None] = None,
        response: Union[dict, None] = None,
        grc_projects: Union[Dict[str, str], None] = None,
    ) -> Union[Dict[str, float], None]:
        """Retrieve magnitude to RAC ratios for each project from Gridcoin client.

        Calculate the ratio of magnitude to RAC for each project the Gridcoin client
        is aware of. Look back the number of specified superblocks for calculating the
        average.

        A cache of the results is maintained and used if the Grindcoin client is unavailable.

        Args:
            grc_client: Connection to Gridcoin client. If testing, set to None.
            lookback_period: Number of superblocks to look back to determine average.
            response: Used for testing purposes.
            grc_projects: Set to None, unless for testing purposes. When testing
                This is the output of the 'listprojects' command run on the Gridcoin client.

        Returns:
            A dictionary with the key as project URL and value as project magnitude ratio
            (mag per unit of RAC).
            A value of None is returned in the event of an exception and no cached data.

        Raises:
            Exception: An error occurred attempting to communicate with the Gridcoin client.
        """
        try:
            if not response:
                command_result = grc_client.run_command(
                    "superblocks", [lookback_period, True]
                )
                response = command_result
            if not response:
                raise ConnectionError("Issues w superblocks command")
            if not grc_projects:
                grc_projects = grc_client.run_command("listprojects")["result"]
            if not grc_projects:
                raise ConnectionError("Issues w listproject command")
            return_dict = cls.get_project_mag_ratios_from_response(
                response["result"], grc_projects, lookback_period
            )
            if dump_rac_mag_ratios is not None:
                dump_rac_mag_ratios(return_dict)
            return return_dict
        except Exception as e:
            if len(cls.PROJECT_MAG_RATIOS_CACHE) > 0:
                print_and_log(
                    "Error communicating with Gridcoin wallet {}, using cached data!".format(
                        e
                    ),
                    "ERROR",
                )
                return cls.PROJECT_MAG_RATIOS_CACHE
            else:
                print_and_log(
                    "Error communicating with Gridcoin wallet! {}".format(e), "ERROR"
                )
                return None

    @classmethod
    def get_project_mag_ratios_from_url(
        cls,
        project_resolver_dict: Dict[str, str],
        lookback_period: int = 30,
        dump_rac_mag_ratios: Union[Callable[[Dict[str, float]], None], None] = None,
        proxies: Union[Dict[str, str], None] = None,
    ) -> Union[Dict[str, float], None]:
        """
        :param lookback_period: number of superblocks to look back to determine average
        :return: Dictionary w/ key as project URL and value as project mag ratio (mag per unit of RAC)
        """
        import requests as req
        import json

        url = "https://www.gridcoinstats.eu/API/simpleQuery.php?q=superblocks"
        try:
            resp = req.get(url, proxies=proxies)
        except Exception as e:
            print("Error retrieving project mag ratios from gridcoinstats.eu")
            if len(cls.PROJECT_MAG_RATIOS_CACHE) > 0:
                print_and_log(
                    "Error communicating with gridcoinstats for magnitude info, using cached data",
                    "ERROR",
                )
                return cls.PROJECT_MAG_RATIOS_CACHE
            else:
                print_and_log(
                    "Error communicating with gridcoinstats for magnitude info, no cached data available",
                    "ERROR",
                )
            return None
        try:
            loaded_json = json.loads(resp.text)
            if not loaded_json:
                raise Exception
            if len(loaded_json) == 0:
                raise Exception
            return_dict = cls.get_project_mag_ratios_from_response(
                loaded_json, project_resolver_dict, lookback_period
            )
            if dump_rac_mag_ratios is not None:
                dump_rac_mag_ratios(return_dict)
            return return_dict
        except Exception as e:
            log.error("E in get_project_mag_ratios_from_url:{}".format(e))
            if len(cls.PROJECT_MAG_RATIOS_CACHE) > 0:
                print_and_log(
                    "Error communicating with gridcoinstats for magnitude info, using cached data",
                    "ERROR",
                )
                return cls.PROJECT_MAG_RATIOS_CACHE
            return None

    @classmethod
    def get_project_mag_ratios_from_response(
        cls,
        response: dict,
        project_resolver_dict: Dict[str, str],
        lookback_period: int = 30,
    ) -> Dict[str, float]:
        loaded_json = response
        projects = {}
        return_dict = {}
        mag_per_project = 0.0
        for i in range(0, lookback_period):
            superblock = loaded_json[i]
            if i == 0:
                total_magnitude = superblock["total_magnitude"]
                total_projects = superblock["total_projects"]
                mag_per_project = total_magnitude / total_projects
            for project_name, project_stats in superblock["contract_contents"][
                "projects"
            ].items():
                if project_name not in projects:
                    if i == 0:
                        projects[project_name] = []
                    else:
                        continue  # Skip projects which are on greylist
                projects[project_name].append(project_stats["rac"])
        for project_name, project_racs in projects.items():
            average_rac = sum(project_racs) / len(project_racs)
            project_url = grc_project_name_to_url(project_name, project_resolver_dict)
            if project_url is None:
                continue
            canonical_url = resolve_url_database(project_url)
            return_dict[canonical_url] = mag_per_project / average_rac
        cls.PROJECT_MAG_RATIOS_CACHE = return_dict
        return return_dict
