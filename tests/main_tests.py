import os
import sys

sys.path.append(os.getcwd() + '/..')

import json

from soups import SOUP_DICTIONARY
from grc_price_utils import parse_grc_price_soup

import main, datetime
from typing import Dict, List


def test_check_sidestake_original():
    empty = {}
    assert not main.check_sidestake(empty, "a", 2)
    not_enabled = {"A": "2"}
    assert not main.check_sidestake(not_enabled, "a", 2)
    explicit_disabled = {"enablesidestaking": "0"}
    assert not main.check_sidestake(explicit_disabled, "a", 2)
    sidestake_1_addr = "S5CSzXD3SkTA9xGGpeBtoNJpyryACBR9RD"
    sidestake_1_amount = "1"
    sidestake_1 = sidestake_1_addr + "," + sidestake_1_amount
    sidestake_2_addr = "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2"
    sidestake_2_amount = "2"
    sidestake_2 = sidestake_2_addr + "," + sidestake_2_amount
    enabled = {
        "enablesidestaking": "1",
        "sidestake": [sidestake_1, sidestake_2],
    }
    assert main.check_sidestake(
        enabled, "S5CSzXD3SkTA9xGGpeBtoNJpyryACBR9RD", 1
    )  # sidestake should exist
    assert not main.check_sidestake(
        enabled, "S5CSzXD3SkTA9xGGpeBtoNJpyryACBR9RD", 2
    )  # sidestake exists but too small
    assert not main.check_sidestake(enabled, "address_that_doesnt_exist", 2)


def test_global_vars():
    """
    Test to verify various important global vars exist and have sane settings
    @return:
    """
    assert isinstance(main.FORCE_DEV_MODE, bool)
    assert not main.FORCE_DEV_MODE
    assert isinstance(main.BOINC_PROJECT_NAMES, dict)
    assert isinstance(main.DATABASE, dict)
    assert "TABLE_SLEEP_REASON" in main.DATABASE
    assert "TABLE_STATUS" in main.DATABASE


def test_combine_dicts():
    dict1 = {"A": "1"}
    dict2 = {"B": "1"}
    # verify dicts being combined
    main.combine_dicts(dict1, dict2)
    assert dict1["B"] == "1"
    assert dict1["A"] == "1"
    # verify dict2 is taking precedent
    dict1 = {"A": "1"}
    dict2 = {"A": "2"}
    main.combine_dicts(dict1, dict2)
    assert dict1["A"] == "2"


def test_resolve_url_boinc_rpc():
    attached_projects = {"https://project1.com", "http://www.project2.com"}
    attached_projects_dev = {
        "https://project1.com",
        "http://www.PROJECT2.com",
        "http://www.devproject.com",
    }
    known_boinc_projects = ["https://project3.com", "http://PROJECT1.com"]
    # test that it returns attached projects first
    result = main.resolve_url_boinc_rpc(
        "project1.com",
        attached_projects,
        attached_projects_dev,
        known_boinc_projects,
        dev_mode=False,
    )
    assert result == "https://project1.com"
    # test that is returns attached dev project before attached regular project, if in dev mode
    result = main.resolve_url_boinc_rpc(
        "project2.com",
        attached_projects,
        attached_projects_dev,
        known_boinc_projects,
        dev_mode=True,
    )
    assert result == "http://www.PROJECT2.com"
    # test that is returns attached regular project before attached dev project, if in regular mode
    result = main.resolve_url_boinc_rpc(
        "project2.com",
        attached_projects,
        attached_projects_dev,
        known_boinc_projects,
        dev_mode=False,
    )
    assert result == "http://www.project2.com"
    # test that it falls back onto known projects if none attached
    result = main.resolve_url_boinc_rpc(
        "project3.com",
        attached_projects,
        attached_projects_dev,
        known_boinc_projects,
        dev_mode=False,
    )
    assert result == "https://project3.com"


def test_resolve_url_database():
    assert (
        main.resolve_url_database("https://www.boinc.com/myproject")
        == "BOINC.COM/MYPROJECT"
    )
    assert (
        main.resolve_url_database("http://www.boinc.com/myproject")
        == "BOINC.COM/MYPROJECT"
    )
    assert main.resolve_url_database("www.boinc.com/myproject") == "BOINC.COM/MYPROJECT"
    assert (
        main.resolve_url_database("https://boinc.com/myproject")
        == "BOINC.COM/MYPROJECT"
    )
    assert (
        main.resolve_url_database("http://boinc.com/myproject") == "BOINC.COM/MYPROJECT"
    )


def test_resolve_url_list_to_database():
    url_list = ["https://www.boinc.com/myproject", "http://boinc.com/myproject"]
    assert main.resolve_url_list_to_database(url_list) == [
        "BOINC.COM/MYPROJECT",
        "BOINC.COM/MYPROJECT",
    ]


def test_temp_check():
    # test it only activates when temp control enabled
    main.ENABLE_TEMP_CONTROL = False
    assert main.temp_check()
    # make sure it turns on and off at correct setpoints
    main.ENABLE_TEMP_CONTROL = True
    main.TEMP_COMMAND = "echo 67"
    main.START_TEMP = 66
    main.STOP_TEMP = 70
    assert main.temp_check()
    main.TEMP_COMMAND = "echo 77"
    assert not main.temp_check()


# Tests that require a network connection to work. Should be run sparingly for this reason
def test_update_fetch():
    actual_version = main.VERSION
    actual_update_check = main.DATABASE.get("LASTUPDATECHECK")
    update_text = """## Format: Version, SecurityBool (1 or 0), Notes
    ## UPDATE FILE FOR FINDTHEMAG DO NOT DELETE THIS LINE
    1.0,0,Original Version
    2.0,0,Main version
    2.1,0,Update is strongly suggested fixes several major bugs in project handling
    2.2,1,FindTheMag critical security update please see Github for more info
    2.3,0,Various usability improvements and crash fixes
    """
    # assert it finds updates incl security updates
    main.DATABASE["LASTUPDATECHECK"] = datetime.datetime(1997, 3, 3)
    update, security, text = main.update_fetch(update_text, 0.1)
    assert update
    assert security
    assert text
    # assert no false positives
    main.DATABASE["LASTUPDATECHECK"] = datetime.datetime(1997, 3, 3)
    update, security, text = main.update_fetch(update_text, 1000)
    assert not update
    assert not security
    assert not text
    # assert correctly identifying security updates
    main.DATABASE["LASTUPDATECHECK"] = datetime.datetime(1997, 3, 3)
    update, security, text = main.update_fetch(update_text, 2.2)
    assert update
    assert not security
    assert text
    # assert not checking too often
    main.DATABASE["LASTUPDATECHECK"] = datetime.datetime.now()
    update, security, text = main.update_fetch(update_text, 0.1)
    assert not update
    assert not security
    assert not text
    # reset original variables
    main.VERSION = actual_version
    if actual_update_check:
        main.DATABASE["LASTUPDATECHECK"] = actual_update_check


def test_parse_grc_price_from_soup():
    for url, soup in SOUP_DICTIONARY.items():
        price, _, _ = parse_grc_price_soup(url, soup)

        assert price

        if url == "https://www.bybit.com/en/coin-price/gridcoin-research/":
            assert price == 0.00384161
        elif url == "https://coinstats.app/coins/gridcoin/":
            assert price == 0.003835
        elif url == "https://marketcapof.com/crypto/gridcoin-research/":
            assert price == 0.00383864


def test_get_approved_project_urls_web():
    original_gs_resolver_dict = main.DATABASE.get("GSRESOLVERDICT")
    original_last_check = main.DATABASE.get("LASTGRIDCOINSTATSPROJECTCHECK")
    # verify it returns cache if recently requested
    main.DATABASE["GSRESOLVERDICT"] = True
    main.DATABASE["LASTGRIDCOINSTATSPROJECTCHECK"] = datetime.datetime.now()
    a = main.get_approved_project_urls_web()
    assert a
    # reset to original values
    if original_gs_resolver_dict:
        main.DATABASE["GSRESOLVERDICT"] = original_gs_resolver_dict
    else:
        del main.DATABASE["GSRESOLVERDICT"]
    if original_last_check:
        main.DATABASE["LASTGRIDCOINSTATSPROJECTCHECK"] = original_last_check
    else:
        del main.DATABASE["LASTGRIDCOINSTATSPROJECTCHECK"]
    # verify we get the expected output
    query_result = """{"Amicable_Numbers":{"version":2,"display_name":"Amicable Numbers","url":"https:\/\/sech.me\/boinc\/Amicable\/@","base_url":"https:\/\/sech.me\/boinc\/Amicable\/","display_url":"https:\/\/sech.me\/boinc\/Amicable\/","stats_url":"https:\/\/sech.me\/boinc\/Amicable\/stats\/","gdpr_controls":false,"time":"2023-07-14 10:58:32 UTC"},"asteroids@home":{"version":2,"display_name":"asteroids@home","url":"https:\/\/asteroidsathome.net\/boinc\/@","base_url":"https:\/\/asteroidsathome.net\/boinc\/","display_url":"https:\/\/asteroidsathome.net\/boinc\/","stats_url":"https:\/\/asteroidsathome.net\/boinc\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:01:32 UTC"},"einstein@home":{"version":2,"display_name":"einstein@home","url":"https:\/\/einstein.phys.uwm.edu\/@","base_url":"https:\/\/einstein.phys.uwm.edu\/","display_url":"https:\/\/einstein.phys.uwm.edu\/","stats_url":"https:\/\/einstein.phys.uwm.edu\/stats\/","gdpr_controls":true,"time":"2023-07-14 11:04:33 UTC"},"folding@home":{"version":2,"display_name":"folding@home","url":"https:\/\/foldingathome.div72.xyz\/@","base_url":"https:\/\/foldingathome.div72.xyz\/","display_url":"https:\/\/foldingathome.div72.xyz\/","stats_url":"https:\/\/foldingathome.div72.xyz\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:07:33 UTC"},"milkyway@home":{"version":2,"display_name":"milkyway@home","url":"https:\/\/milkyway.cs.rpi.edu\/milkyway\/@","base_url":"https:\/\/milkyway.cs.rpi.edu\/milkyway\/","display_url":"https:\/\/milkyway.cs.rpi.edu\/milkyway\/","stats_url":"https:\/\/milkyway.cs.rpi.edu\/milkyway\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:10:33 UTC"},"nfs@home":{"version":2,"display_name":"nfs@home","url":"https:\/\/escatter11.fullerton.edu\/nfs\/@","base_url":"https:\/\/escatter11.fullerton.edu\/nfs\/","display_url":"https:\/\/escatter11.fullerton.edu\/nfs\/","stats_url":"https:\/\/escatter11.fullerton.edu\/nfs\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:13:34 UTC"},"numberfields@home":{"version":2,"display_name":"numberfields@home","url":"https:\/\/numberfields.asu.edu\/NumberFields\/@","base_url":"https:\/\/numberfields.asu.edu\/NumberFields\/","display_url":"https:\/\/numberfields.asu.edu\/NumberFields\/","stats_url":"https:\/\/numberfields.asu.edu\/NumberFields\/stats\/","gdpr_controls":true,"time":"2023-07-14 11:16:34 UTC"},"odlk1":{"version":2,"display_name":"odlk1","url":"https:\/\/boinc.multi-pool.info\/latinsquares\/@","base_url":"https:\/\/boinc.multi-pool.info\/latinsquares\/","display_url":"https:\/\/boinc.multi-pool.info\/latinsquares\/","stats_url":"https:\/\/boinc.multi-pool.info\/latinsquares\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:19:35 UTC"},"rosetta@home":{"version":2,"display_name":"rosetta@home","url":"https:\/\/boinc.bakerlab.org\/rosetta\/@","base_url":"https:\/\/boinc.bakerlab.org\/rosetta\/","display_url":"https:\/\/boinc.bakerlab.org\/rosetta\/","stats_url":"https:\/\/boinc.bakerlab.org\/rosetta\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:22:35 UTC"},"SiDock@home":{"version":2,"display_name":"SiDock@home","url":"https:\/\/www.sidock.si\/sidock\/@","base_url":"https:\/\/www.sidock.si\/sidock\/","display_url":"https:\/\/www.sidock.si\/sidock\/","stats_url":"https:\/\/www.sidock.si\/sidock\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:25:35 UTC"},"SRBase":{"version":2,"display_name":"SRBase","url":"https:\/\/srbase.my-firewall.org\/sr5\/@","base_url":"https:\/\/srbase.my-firewall.org\/sr5\/","display_url":"https:\/\/srbase.my-firewall.org\/sr5\/","stats_url":"https:\/\/srbase.my-firewall.org\/sr5\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:28:36 UTC"},"TN-Grid":{"version":2,"display_name":"TN-Grid","url":"https:\/\/gene.disi.unitn.it\/test\/@","base_url":"https:\/\/gene.disi.unitn.it\/test\/","display_url":"https:\/\/gene.disi.unitn.it\/test\/","stats_url":"https:\/\/gene.disi.unitn.it\/test\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:31:36 UTC"},"universe@home":{"version":2,"display_name":"universe@home","url":"https:\/\/universeathome.pl\/universe\/@","base_url":"https:\/\/universeathome.pl\/universe\/","display_url":"https:\/\/universeathome.pl\/universe\/","stats_url":"https:\/\/universeathome.pl\/universe\/stats\/","gdpr_controls":true,"time":"2023-07-14 11:34:36 UTC"},"World_Community_Grid":{"version":2,"display_name":"World Community Grid","url":"https:\/\/www.worldcommunitygrid.org\/boinc\/@","base_url":"https:\/\/www.worldcommunitygrid.org\/boinc\/","display_url":"https:\/\/www.worldcommunitygrid.org\/","stats_url":"https:\/\/www.worldcommunitygrid.org\/boinc\/stats\/","gdpr_controls":true,"time":"2023-07-14 11:37:37 UTC"},"yoyo@home":{"version":2,"display_name":"yoyo@home","url":"https:\/\/www.rechenkraft.net\/yoyo\/@","base_url":"https:\/\/www.rechenkraft.net\/yoyo\/","display_url":"https:\/\/www.rechenkraft.net\/yoyo\/","stats_url":"https:\/\/www.rechenkraft.net\/yoyo\/stats\/","gdpr_controls":false,"time":"2023-07-14 11:40:37 UTC"}}"""
    answer = main.get_approved_project_urls_web(query_result)
    assert isinstance(answer, dict)
    assert len(answer) > 3
    assert "Amicable_Numbers" in answer
    assert answer.get("Amicable_Numbers") == "SECH.ME/BOINC/AMICABLE"


def test_xfers_happening():
    # test xfer list w stalled xfers
    xfer_list = [{"status": 0, "persistent_file_xfer": {"num_retries": 2}}]
    assert not main.xfers_happening(xfer_list)
    # test empty xfer list
    xfer_list = []
    assert not main.xfers_happening(xfer_list)
    # test xfer list w xfers happening
    xfer_list = [
        {
            "status": 0,
        }
    ]
    assert main.xfers_happening(xfer_list)


def test_get_gridcoin_config_parameters():
    result = main.get_gridcoin_config_parameters(".")
    assert result.get("enablesidestaking") == "1"
    assert isinstance(result.get("sidestake"), list)
    assert "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2,1" in result.get("sidestake", [])
    assert "RzUgcntbFm8PeSJpauk6a44qbtu92dpw3K,1" in result.get("sidestake", [])
    assert result["rpcport"] == "9876"
    assert result["rpcuser"] == "myusername"
    assert result["rpcpassword"] == "mypassword"


def test_check_sidestake():
    # check it notices when sidestaking disabled
    config = {
        "enablesidestaking": "0",
        "sidestake": [
            "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2,1",
            "RzUgcntbFm8PeSJpauk6a44qbtu92dpw3K,1",
        ],
        "rpcport": "9876",
        "rpcallowip": "127.0.0.1",
        "server": "1",
        "rpcuser": "myusername",
        "rpcpassword": "mypassword",
    }
    assert not main.check_sidestake(config, "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2", 1)
    # check it notices if value too low
    config = {
        "enablesidestaking": "1",
        "sidestake": [
            "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2,1",
            "RzUgcntbFm8PeSJpauk6a44qbtu92dpw3K,1",
        ],
        "rpcport": "9876",
        "rpcallowip": "127.0.0.1",
        "server": "1",
        "rpcuser": "myusername",
        "rpcpassword": "mypassword",
    }
    assert not main.check_sidestake(config, "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2", 5)
    # assert it correctly detects sidestake
    config = {
        "enablesidestaking": "1",
        "sidestake": [
            "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2,1",
            "RzUgcntbFm8PeSJpauk6a44qbtu92dpw3K,1",
        ],
        "rpcport": "9876",
        "rpcallowip": "127.0.0.1",
        "server": "1",
        "rpcuser": "myusername",
        "rpcpassword": "mypassword",
    }
    assert main.check_sidestake(config, "bc3NA8e8E3EoTL1qhRmeprbjWcmuoZ26A2", 1)


def test_project_url_from_stats_file():
    assert (
        main.project_url_from_stats_file("job_log_www.worldcommunitygrid.org.txt")
        == "WORLDCOMMUNITYGRID.ORG"
    )
    assert (
        main.project_url_from_stats_file("job_log_escatter11.fullerton.edu_nfs.txt")
        == "ESCATTER11.FULLERTON.EDU/NFS"
    )
    assert (
        main.project_url_from_stats_file("job_log_www.rechenkraft.net_yoyo.txt")
        == "RECHENKRAFT.NET/YOYO"
    )


def test_project_url_from_credit_history_file():
    assert (
        main.project_url_from_credit_history_file(
            "statistics_boinc.multi-pool.info_latinsquares.xml"
        )
        == "BOINC.MULTI-POOL.INFO/LATINSQUARES"
    )
    assert (
        main.project_url_from_credit_history_file(
            "statistics_boinc.bakerlab.org_rosetta.xml"
        )
        == "BOINC.BAKERLAB.ORG/ROSETTA"
    )
    assert (
        main.project_url_from_credit_history_file(
            "statistics_milkyway.cs.rpi.edu_milkyway.xml"
        )
        == "MILKYWAY.CS.RPI.EDU/MILKYWAY"
    )


def test_stat_file_to_list():
    example = """1680334251 ue 4017.278236 ct 3454.260000 fe 200000000000000 nm TASK1 et 3465.445294 es 0
1680334604 ue 4017.278236 ct 3805.396000 fe 200000000000000 nm TASK2 et 3819.634777 es 0
1680336346 ue 2381.072619 ct 2074.329000 fe 70000000000000 nm TASK3 et 2094.352010 es 0
1680337549 ue 3190.839339 ct 2930.237000 fe 70000000000000 nm TASK4 et 2944.508444 es 0"""
    result = main.stat_file_to_list(None, example)
    assert result == [
        {
            "STARTTIME": "1680334251",
            "ESTTIME": "4017.278236",
            "CPUTIME": "3454.260000",
            "ESTIMATEDFLOPS": "200000000000000",
            "TASKNAME": "TASK1",
            "WALLTIME": "3465.445294",
            "EXITCODE": "0",
        },
        {
            "STARTTIME": "1680334604",
            "ESTTIME": "4017.278236",
            "CPUTIME": "3805.396000",
            "ESTIMATEDFLOPS": "200000000000000",
            "TASKNAME": "TASK2",
            "WALLTIME": "3819.634777",
            "EXITCODE": "0",
        },
        {
            "STARTTIME": "1680336346",
            "ESTTIME": "2381.072619",
            "CPUTIME": "2074.329000",
            "ESTIMATEDFLOPS": "70000000000000",
            "TASKNAME": "TASK3",
            "WALLTIME": "2094.352010",
            "EXITCODE": "0",
        },
        {
            "STARTTIME": "1680337549",
            "ESTTIME": "3190.839339",
            "CPUTIME": "2930.237000",
            "ESTIMATEDFLOPS": "70000000000000",
            "TASKNAME": "TASK4",
            "WALLTIME": "2944.508444",
            "EXITCODE": "0",
        },
    ]


def test_calculate_credit_averages():
    my_input = {
        "WORLDCOMMUNITYGRID.ORG": {
            "CREDIT_HISTORY": {"04-07-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "04-09-2023": {
                    "TOTALWUS": 1,
                    "total_wall_time": 9084.946866,
                    "total_cpu_time": 9072.151,
                },
                "04-10-2023": {
                    "TOTALWUS": 3,
                    "total_wall_time": 41053.747675,
                    "total_cpu_time": 41004.234,
                },
            },
            "COMPILED_STATS": {},
        },
        "SECH.ME/BOINC/AMICABLE": {
            "CREDIT_HISTORY": {"03-31-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "01-22-2023": {
                    "TOTALWUS": 3,
                    "total_wall_time": 51544.448429,
                    "total_cpu_time": 102921.05000000002,
                }
            },
            "COMPILED_STATS": {},
        },
        "ESCATTER11.FULLERTON.EDU/NFS": {
            "CREDIT_HISTORY": {"03-31-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "04-01-2023": {
                    "TOTALWUS": 4,
                    "total_wall_time": 12323.940525000002,
                    "total_cpu_time": 12264.222000000002,
                }
            },
            "COMPILED_STATS": {},
        },
        "RECHENKRAFT.NET/YOYO": {
            "CREDIT_HISTORY": {},
            "WU_HISTORY": {
                "10-02-2022": {
                    "TOTALWUS": 1,
                    "total_wall_time": 6818.480898,
                    "total_cpu_time": 19051.76,
                }
            },
            "COMPILED_STATS": {},
        },
        "BOINC.BAKERLAB.ORG/ROSETTA": {
            "CREDIT_HISTORY": {"04-07-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {},
        },
    }
    result = main.calculate_credit_averages(my_input)
    assert result == {
        "WORLDCOMMUNITYGRID.ORG": {
            "TOTALCREDIT": 0.0,
            "AVGWALLTIME": 3.481853787569444,
            "AVGCPUTIME": 3.477526736111111,
            "AVGCREDITPERTASK": 0.0,
            "TOTALTASKS": 4,
            "TOTALWALLTIME": 13.927415150277776,
            "TOTALCPUTIME": 13.910106944444443,
            "AVGCREDITPERHOUR": 0.0,
            "XDAYWALLTIME": 0.0,
        },
        "SECH.ME/BOINC/AMICABLE": {
            "TOTALCREDIT": 0.0,
            "AVGWALLTIME": 4.772634113796296,
            "AVGCPUTIME": 9.529726851851853,
            "AVGCREDITPERTASK": 0.0,
            "TOTALTASKS": 3,
            "TOTALWALLTIME": 14.317902341388889,
            "TOTALCPUTIME": 28.58918055555556,
            "AVGCREDITPERHOUR": 0.0,
            "XDAYWALLTIME": 0.0,
        },
        "ESCATTER11.FULLERTON.EDU/NFS": {
            "TOTALCREDIT": 0.0,
            "AVGWALLTIME": 0.8558292031250001,
            "AVGCPUTIME": 0.8516820833333334,
            "AVGCREDITPERTASK": 0.0,
            "TOTALTASKS": 4,
            "TOTALWALLTIME": 3.4233168125000004,
            "TOTALCPUTIME": 3.4067283333333336,
            "AVGCREDITPERHOUR": 0.0,
            "XDAYWALLTIME": 0.0,
        },
        "RECHENKRAFT.NET/YOYO": {
            "TOTALCREDIT": 0,
            "AVGWALLTIME": 1.8940224716666665,
            "AVGCPUTIME": 5.292155555555555,
            "AVGCREDITPERTASK": 0.0,
            "TOTALTASKS": 1,
            "TOTALWALLTIME": 1.8940224716666665,
            "TOTALCPUTIME": 5.292155555555555,
            "AVGCREDITPERHOUR": 0.0,
            "XDAYWALLTIME": 0.0,
        },
        "BOINC.BAKERLAB.ORG/ROSETTA": {
            "TOTALCREDIT": 0.0,
            "AVGWALLTIME": 0,
            "AVGCPUTIME": 0,
            "AVGCREDITPERTASK": 0,
            "TOTALTASKS": 0,
            "TOTALWALLTIME": 0,
            "TOTALCPUTIME": 0,
            "AVGCREDITPERHOUR": 0,
            "XDAYWALLTIME": 0,
        },
    }


def test_config_files_to_stats():
    assert main.config_files_to_stats("/path/that/doesntexist") == {}
    result = main.config_files_to_stats("boinc_stats")
    expected = {
        "WORLDCOMMUNITYGRID.ORG": {
            "CREDIT_HISTORY": {"04-07-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "04-09-2023": {
                    "TOTALWUS": 1,
                    "total_wall_time": 9084.946866,
                    "total_cpu_time": 9072.151,
                },
                "04-10-2023": {
                    "TOTALWUS": 3,
                    "total_wall_time": 41053.747675,
                    "total_cpu_time": 41004.234,
                },
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 3.481853787569444,
                "AVGCPUTIME": 3.477526736111111,
                "AVGCREDITPERTASK": 0.0,
                "TOTALTASKS": 4,
                "TOTALWALLTIME": 13.927415150277776,
                "TOTALCPUTIME": 13.910106944444443,
                "AVGCREDITPERHOUR": 0.0,
                "XDAYWALLTIME": 0.0,
            },
        },
        "SECH.ME/BOINC/AMICABLE": {
            "CREDIT_HISTORY": {"03-31-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "01-22-2023": {
                    "TOTALWUS": 3,
                    "total_wall_time": 51544.448429,
                    "total_cpu_time": 102921.05000000002,
                }
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 4.772634113796296,
                "AVGCPUTIME": 9.529726851851853,
                "AVGCREDITPERTASK": 0.0,
                "TOTALTASKS": 3,
                "TOTALWALLTIME": 14.317902341388889,
                "TOTALCPUTIME": 28.58918055555556,
                "AVGCREDITPERHOUR": 0.0,
                "XDAYWALLTIME": 0.0,
            },
        },
        "ESCATTER11.FULLERTON.EDU/NFS": {
            "CREDIT_HISTORY": {"03-31-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "04-01-2023": {
                    "TOTALWUS": 4,
                    "total_wall_time": 12323.940525000002,
                    "total_cpu_time": 12264.222000000002,
                }
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0.8558292031250001,
                "AVGCPUTIME": 0.8516820833333334,
                "AVGCREDITPERTASK": 0.0,
                "TOTALTASKS": 4,
                "TOTALWALLTIME": 3.4233168125000004,
                "TOTALCPUTIME": 3.4067283333333336,
                "AVGCREDITPERHOUR": 0.0,
                "XDAYWALLTIME": 0.0,
            },
        },
        "RECHENKRAFT.NET/YOYO": {
            "CREDIT_HISTORY": {},
            "WU_HISTORY": {
                "10-02-2022": {
                    "TOTALWUS": 1,
                    "total_wall_time": 6818.480898,
                    "total_cpu_time": 19051.76,
                }
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 0,
                "AVGWALLTIME": 1.8940224716666665,
                "AVGCPUTIME": 5.292155555555555,
                "AVGCREDITPERTASK": 0.0,
                "TOTALTASKS": 1,
                "TOTALWALLTIME": 1.8940224716666665,
                "TOTALCPUTIME": 5.292155555555555,
                "AVGCREDITPERHOUR": 0.0,
                "XDAYWALLTIME": 0.0,
            },
        },
        "BOINC.BAKERLAB.ORG/ROSETTA": {
            "CREDIT_HISTORY": {"04-07-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
            },
        },
    }
    assert frozenset(result) == frozenset(expected)


def test_add_mag_to_combined_stats():
    expected = {}
    result = {}
    combined_stats = main.config_files_to_stats("boinc_stats_2")
    example_ratios = {
        "WORLDCOMMUNITYGRID.ORG": 0.01,
        "SECH.ME/BOINC/AMICABLE": 0.99,
        "ESCATTER11.FULLERTON.EDU/NFS": 0.0,
    }
    approved_projects = list(example_ratios.keys())
    approved_projects.remove(
        "ESCATTER11.FULLERTON.EDU/NFS"
    )  # test it gives zero mag for unapproved project
    return1, return2 = main.add_mag_to_combined_stats(
        combined_stats, example_ratios, approved_projects, preferred_projects=[]
    )
    expected_return_1 = {
        "WORLDCOMMUNITYGRID.ORG": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 349.815304}},
            "WU_HISTORY": {
                "04-09-2023": {
                    "TOTALWUS": 1,
                    "total_wall_time": 9084.946866,
                    "total_cpu_time": 9072.151,
                },
                "04-10-2023": {
                    "TOTALWUS": 3,
                    "total_wall_time": 41053.747675,
                    "total_cpu_time": 41004.234,
                },
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 349.815304,
                "AVGWALLTIME": 3.481853787569444,
                "AVGCPUTIME": 3.477526736111111,
                "AVGCREDITPERTASK": 87.453826,
                "TOTALTASKS": 4,
                "TOTALWALLTIME": 13.927415150277776,
                "TOTALCPUTIME": 13.910106944444443,
                "AVGCREDITPERHOUR": 25.11702998908761,
                "XDAYWALLTIME": 0.0,
                "AVGMAGPERHOUR": 0.2511702998908761,
                "MAGPERCREDIT": 0.01,
            },
        },
        "SECH.ME/BOINC/AMICABLE": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "01-22-2023": {
                    "TOTALWUS": 3,
                    "total_wall_time": 51544.448429,
                    "total_cpu_time": 102921.05000000002,
                }
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 4.772634113796296,
                "AVGCPUTIME": 9.529726851851853,
                "AVGCREDITPERTASK": 0.0,
                "TOTALTASKS": 3,
                "TOTALWALLTIME": 14.317902341388889,
                "TOTALCPUTIME": 28.58918055555556,
                "AVGCREDITPERHOUR": 0.0,
                "XDAYWALLTIME": 0.0,
                "AVGMAGPERHOUR": 0.0,
                "MAGPERCREDIT": 0.99,
            },
        },
        "ESCATTER11.FULLERTON.EDU/NFS": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "04-01-2023": {
                    "TOTALWUS": 4,
                    "total_wall_time": 12323.940525000002,
                    "total_cpu_time": 12264.222000000002,
                }
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0.8558292031250001,
                "AVGCPUTIME": 0.8516820833333334,
                "AVGCREDITPERTASK": 0.0,
                "TOTALTASKS": 4,
                "TOTALWALLTIME": 3.4233168125000004,
                "TOTALCPUTIME": 3.4067283333333336,
                "AVGCREDITPERHOUR": 0.0,
                "XDAYWALLTIME": 0.0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "RECHENKRAFT.NET/YOYO": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {
                "10-02-2022": {
                    "TOTALWUS": 1,
                    "total_wall_time": 6818.480898,
                    "total_cpu_time": 19051.76,
                }
            },
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 1.8940224716666665,
                "AVGCPUTIME": 5.292155555555555,
                "AVGCREDITPERTASK": 0.0,
                "TOTALTASKS": 1,
                "TOTALWALLTIME": 1.8940224716666665,
                "TOTALCPUTIME": 5.292155555555555,
                "AVGCREDITPERHOUR": 0.0,
                "XDAYWALLTIME": 0.0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "BOINC.MULTI-POOL.INFO/LATINSQUARES": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "BOINC.BAKERLAB.ORG/ROSETTA": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "UNIVERSEATHOME.PL/UNIVERSE": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "MILKYWAY.CS.RPI.EDU/MILKYWAY": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "EINSTEIN.PHYS.UWM.EDU": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "SRBASE.MY-FIREWALL.ORG/SR5": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "GPUGRID.NET": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "GENE.DISI.UNITN.IT/TEST": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
        "SIDOCK.SI/SIDOCK": {
            "CREDIT_HISTORY": {"06-15-2023": {"CREDITAWARDED": 0.0}},
            "WU_HISTORY": {},
            "COMPILED_STATS": {
                "TOTALCREDIT": 0.0,
                "AVGWALLTIME": 0,
                "AVGCPUTIME": 0,
                "AVGCREDITPERTASK": 0,
                "TOTALTASKS": 0,
                "TOTALWALLTIME": 0,
                "TOTALCPUTIME": 0,
                "AVGCREDITPERHOUR": 0,
                "XDAYWALLTIME": 0,
                "AVGMAGPERHOUR": 0,
                "MAGPERCREDIT": 0,
            },
        },
    }
    return2expected = {
        "ESCATTER11.FULLERTON.EDU/NFS",
        "RECHENKRAFT.NET/YOYO",
        "BOINC.MULTI-POOL.INFO/LATINSQUARES",
        "BOINC.BAKERLAB.ORG/ROSETTA",
        "UNIVERSEATHOME.PL/UNIVERSE",
        "MILKYWAY.CS.RPI.EDU/MILKYWAY",
        "EINSTEIN.PHYS.UWM.EDU",
        "SRBASE.MY-FIREWALL.ORG/SR5",
        "GPUGRID.NET",
        "GENE.DISI.UNITN.IT/TEST",
        "SIDOCK.SI/SIDOCK",
    }
    assert frozenset(list(return2)) == frozenset(return2expected)
    assert frozenset(return1) == frozenset(expected_return_1)


def test_get_most_mag_efficient_projects():
    combinedstats = {
        "WORLDCOMMUNITYGRID.ORG": {
            "COMPILED_STATS": {
                "AVGMAGPERHOUR": 1,
                "TOTALTASKS": 20,
            }
        },
        "ESCATTER11.FULLERTON.EDU/NFS": {
            "COMPILED_STATS": {
                "AVGMAGPERHOUR": 0,
                "TOTALTASKS": 10,
            }
        },
        "RECHENKRAFT.NET/YOYO": {
            "COMPILED_STATS": {
                "AVGMAGPERHOUR": 0.91,
                "TOTALTASKS": 20,
            }
        },
        "BOINC.MULTI-POOL.INFO/LATINSQUARES": {
            "COMPILED_STATS": {
                "AVGMAGPERHOUR": 1,
                "TOTALTASKS": 20,
            }
        },
    }
    ignored_projects = ["BOINC.MULTI-POOL.INFO/LATINSQUARES"]
    percentdiff = 10
    quiet: bool = True
    # test that it finds two highest projects w/ percentdiff, and that it's properly ignoring projects
    result = main.get_most_mag_efficient_projects(
        combinedstats, ignored_projects, percentdiff, quiet
    )
    assert result == ["WORLDCOMMUNITYGRID.ORG", "RECHENKRAFT.NET/YOYO"]
    # test that percentdiff is working
    percentdiff = 1
    result = main.get_most_mag_efficient_projects(
        combinedstats, ignored_projects, percentdiff, quiet
    )
    assert result == ["WORLDCOMMUNITYGRID.ORG"]


def test_get_first_non_ignored_project():
    project_list = [
        "WORLDCOMMUNITYGRID.ORG",
        "RECHENKRAFT.NET/YOYO",
        "BOINC.MULTI-POOL.INFO/LATINSQUARES",
    ]
    ignored_projects = ["RECHENKRAFT.NET/YOYO"]
    assert (
        main.get_first_non_ignored_project(project_list, ignored_projects)
        == "WORLDCOMMUNITYGRID.ORG"
    )
    ignored_projects = ["RECHENKRAFT.NET/YOYO", "WORLDCOMMUNITYGRID.ORG"]
    assert (
        main.get_first_non_ignored_project(project_list, ignored_projects)
        == "BOINC.MULTI-POOL.INFO/LATINSQUARES"
    )


def test_get_project_mag_ratios():
    # use section below if you need to update this test
    # gridcoin_conf = main.get_gridcoin_config_parameters(main.GRIDCOIN_DATA_DIR)
    # rpc_user = gridcoin_conf.get('rpcuser')
    # gridcoin_rpc_password = gridcoin_conf.get('rpcpassword')
    # rpc_port = gridcoin_conf.get('rpcport')
    # grc_client = main.GridcoinClientConnection(rpc_user=rpc_user, rpc_port=rpc_port, rpc_password=gridcoin_rpc_password)

    file = open("gridcoin/superblocks_response.txt").read()
    grc_response = json.loads(file)
    expected_answer = {
        "SECH.ME/BOINC/AMICABLE": 8.91264681577104e-05,
        "SRBASE.MY-FIREWALL.ORG/SR5": 8.539680314693781e-05,
        "SIDOCK.SI/SIDOCK": 0.003301081663199078,
        "GENE.DISI.UNITN.IT/TEST": 0.0035177177490411625,
        "WORLDCOMMUNITYGRID.ORG": 0.0009398350573579004,
        "ASTEROIDSATHOME.NET/BOINC": 0.003858841063201462,
        "EINSTEIN.PHYS.UWM.EDU": 4.0056880080044686e-05,
        "FOLDINGATHOME.DIV72.XYZ": 2.354611008478076e-05,
        "MILKYWAY.CS.RPI.EDU/MILKYWAY": 0.00017020525368876164,
        "ESCATTER11.FULLERTON.EDU/NFS": 0.0014315462447158976,
        "NUMBERFIELDS.ASU.EDU/NUMBERFIELDS": 0.0003832862658003348,
        "BOINC.MULTI-POOL.INFO/LATINSQUARES": 0.004925403380069366,
        "BOINC.BAKERLAB.ORG/ROSETTA": 0.010315385227402484,
        "UNIVERSEATHOME.PL/UNIVERSE": 0.00028549726782855914,
        "RECHENKRAFT.NET/YOYO": 0.0018665701101050107,
    }
    grc_projects = {
        "Amicable_Numbers": {
            "version": 2,
            "display_name": "Amicable Numbers",
            "url": "https://sech.me/boinc/Amicable/@",
            "base_url": "https://sech.me/boinc/Amicable/",
            "display_url": "https://sech.me/boinc/Amicable/",
            "stats_url": "https://sech.me/boinc/Amicable/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 10:58:32 UTC",
        },
        "asteroids@home": {
            "version": 2,
            "display_name": "asteroids@home",
            "url": "https://asteroidsathome.net/boinc/@",
            "base_url": "https://asteroidsathome.net/boinc/",
            "display_url": "https://asteroidsathome.net/boinc/",
            "stats_url": "https://asteroidsathome.net/boinc/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:01:32 UTC",
        },
        "einstein@home": {
            "version": 2,
            "display_name": "einstein@home",
            "url": "https://einstein.phys.uwm.edu/@",
            "base_url": "https://einstein.phys.uwm.edu/",
            "display_url": "https://einstein.phys.uwm.edu/",
            "stats_url": "https://einstein.phys.uwm.edu/stats/",
            "gdpr_controls": True,
            "time": "2023-07-14 11:04:33 UTC",
        },
        "folding@home": {
            "version": 2,
            "display_name": "folding@home",
            "url": "https://foldingathome.div72.xyz/@",
            "base_url": "https://foldingathome.div72.xyz/",
            "display_url": "https://foldingathome.div72.xyz/",
            "stats_url": "https://foldingathome.div72.xyz/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:07:33 UTC",
        },
        "milkyway@home": {
            "version": 2,
            "display_name": "milkyway@home",
            "url": "https://milkyway.cs.rpi.edu/milkyway/@",
            "base_url": "https://milkyway.cs.rpi.edu/milkyway/",
            "display_url": "https://milkyway.cs.rpi.edu/milkyway/",
            "stats_url": "https://milkyway.cs.rpi.edu/milkyway/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:10:33 UTC",
        },
        "nfs@home": {
            "version": 2,
            "display_name": "nfs@home",
            "url": "https://escatter11.fullerton.edu/nfs/@",
            "base_url": "https://escatter11.fullerton.edu/nfs/",
            "display_url": "https://escatter11.fullerton.edu/nfs/",
            "stats_url": "https://escatter11.fullerton.edu/nfs/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:13:34 UTC",
        },
        "numberfields@home": {
            "version": 2,
            "display_name": "numberfields@home",
            "url": "https://numberfields.asu.edu/NumberFields/@",
            "base_url": "https://numberfields.asu.edu/NumberFields/",
            "display_url": "https://numberfields.asu.edu/NumberFields/",
            "stats_url": "https://numberfields.asu.edu/NumberFields/stats/",
            "gdpr_controls": True,
            "time": "2023-07-14 11:16:34 UTC",
        },
        "odlk1": {
            "version": 2,
            "display_name": "odlk1",
            "url": "https://boinc.multi-pool.info/latinsquares/@",
            "base_url": "https://boinc.multi-pool.info/latinsquares/",
            "display_url": "https://boinc.multi-pool.info/latinsquares/",
            "stats_url": "https://boinc.multi-pool.info/latinsquares/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:19:35 UTC",
        },
        "rosetta@home": {
            "version": 2,
            "display_name": "rosetta@home",
            "url": "https://boinc.bakerlab.org/rosetta/@",
            "base_url": "https://boinc.bakerlab.org/rosetta/",
            "display_url": "https://boinc.bakerlab.org/rosetta/",
            "stats_url": "https://boinc.bakerlab.org/rosetta/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:22:35 UTC",
        },
        "SiDock@home": {
            "version": 2,
            "display_name": "SiDock@home",
            "url": "https://www.sidock.si/sidock/@",
            "base_url": "https://www.sidock.si/sidock/",
            "display_url": "https://www.sidock.si/sidock/",
            "stats_url": "https://www.sidock.si/sidock/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:25:35 UTC",
        },
        "SRBase": {
            "version": 2,
            "display_name": "SRBase",
            "url": "https://srbase.my-firewall.org/sr5/@",
            "base_url": "https://srbase.my-firewall.org/sr5/",
            "display_url": "https://srbase.my-firewall.org/sr5/",
            "stats_url": "https://srbase.my-firewall.org/sr5/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:28:36 UTC",
        },
        "TN-Grid": {
            "version": 2,
            "display_name": "TN-Grid",
            "url": "https://gene.disi.unitn.it/test/@",
            "base_url": "https://gene.disi.unitn.it/test/",
            "display_url": "https://gene.disi.unitn.it/test/",
            "stats_url": "https://gene.disi.unitn.it/test/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:31:36 UTC",
        },
        "universe@home": {
            "version": 2,
            "display_name": "universe@home",
            "url": "https://universeathome.pl/universe/@",
            "base_url": "https://universeathome.pl/universe/",
            "display_url": "https://universeathome.pl/universe/",
            "stats_url": "https://universeathome.pl/universe/stats/",
            "gdpr_controls": True,
            "time": "2023-07-14 11:34:36 UTC",
        },
        "World_Community_Grid": {
            "version": 2,
            "display_name": "World Community Grid",
            "url": "https://www.worldcommunitygrid.org/boinc/@",
            "base_url": "https://www.worldcommunitygrid.org/boinc/",
            "display_url": "https://www.worldcommunitygrid.org/",
            "stats_url": "https://www.worldcommunitygrid.org/boinc/stats/",
            "gdpr_controls": True,
            "time": "2023-07-14 11:37:37 UTC",
        },
        "yoyo@home": {
            "version": 2,
            "display_name": "yoyo@home",
            "url": "https://www.rechenkraft.net/yoyo/@",
            "base_url": "https://www.rechenkraft.net/yoyo/",
            "display_url": "https://www.rechenkraft.net/yoyo/",
            "stats_url": "https://www.rechenkraft.net/yoyo/stats/",
            "gdpr_controls": False,
            "time": "2023-07-14 11:40:37 UTC",
        },
    }
    answer = main.get_project_mag_ratios(None, 30, grc_response, grc_projects)
    assert answer == expected_answer


def test_left_align():
    my_string = "test"
    total_len = 10
    # test padding of one
    min_pad = 1
    result = main.left_align(my_string, total_len, min_pad)
    assert result == "test      "
    # test padding of zero
    min_pad = 0
    result = main.left_align(my_string, total_len, min_pad)
    assert result == "test      "
    # test padding > total_len
    total_len = 5
    min_pad = 2
    result = main.left_align(my_string, total_len, min_pad)
    assert result == "tes  "


def test_center_align():
    my_string = "test"
    total_len = 10
    # test padding of one
    min_pad = 1
    result = main.center_align(my_string, total_len, min_pad)
    assert result == "   test   "
    # test string+pad>total_len
    total_len = 9
    min_pad = 3
    result = main.center_align(my_string, total_len, min_pad)
    assert result == "   tes   "
    # test padding > total_len
    total_len = 6
    min_pad = 3
    result = main.center_align(my_string, total_len, min_pad)
    assert result == "      "


def test_ignore_message_from_check_log_entries():
    assert main.ignore_message_from_check_log_entries("WORK FETCH SUSPENDED BY USERS")


def make_fake_boinc_log_entry(
    messages: List[str], project: str
) -> List[Dict[str, str]]:
    return_list = []
    for message in messages:
        now = datetime.datetime.now()
        append_message = str(now) + " | " + project + " | " + message
        return_dict = {"time": now, "body": append_message, "project": project}
        return_list.append(return_dict)
    return return_list


def test_cache_full():
    # check it realizes both caches full
    messages = [
        "testproject CPU: JOB CACHE FULL",
        "TESTPROJECT NOT REQUESTING TASKS: DON'T NEED (JOB CACHE FULL)",
        "testproject GPU: JOB CACHE FULL",
        "testproject: GPUS NOT USABLE",
    ]
    test_messages = make_fake_boinc_log_entry(messages, "testproject")
    assert main.cache_full("testproject", test_messages)
    # make sure it's not counting other projects
    messages = [
        "testproject CPU: JOB CACHE FULL",
        "TESTPROJECT NOT REQUESTING TASKS: DON'T NEED (JOB CACHE FULL)",
        "testproject GPU: JOB CACHE FULL",
        "testproject: GPUS NOT USABLE",
    ]
    test_messages = make_fake_boinc_log_entry(messages, "testproject")
    assert not main.cache_full("anotherproject", test_messages)
    # check it realizes cpu is full on system w no gpu
    messages = ["NOT REQUESTING TASKS: DON'T NEED ()", "CPU: JOB CACHE FULL"]
    test_messages = make_fake_boinc_log_entry(messages, "testproject")
    assert main.cache_full("testproject", test_messages)


def test_project_backoff():
    messages = ["PROJECT HAS NO TASKS AVAILABLE", "SCHEDULER REQUEST FAILED"]
    test_messages = make_fake_boinc_log_entry(messages, "testproject")
    assert main.project_backoff("testproject", test_messages)
    messages = ["NOT REQUESTING TASKS: DON'T NEED", "STARTED DOWNLOAD"]
    test_messages = make_fake_boinc_log_entry(messages, "testproject")
    assert not main.project_backoff("testproject", test_messages)


def test_get_project_mag_ratios_from_response():
    file = open("gridcoin/superblocks_response.txt").read()
    response = json.loads(file)["result"]
    project_resolver_dict = {
        "Amicable_Numbers": "SECH.ME/BOINC/AMICABLE",
        "asteroids@home": "ASTEROIDSATHOME.NET/BOINC",
        "einstein@home": "EINSTEIN.PHYS.UWM.EDU",
        "folding@home": "FOLDINGATHOME.DIV72.XYZ",
        "milkyway@home": "MILKYWAY.CS.RPI.EDU/MILKYWAY",
        "nfs@home": "ESCATTER11.FULLERTON.EDU/NFS",
        "numberfields@home": "NUMBERFIELDS.ASU.EDU/NUMBERFIELDS",
        "odlk1": "BOINC.MULTI-POOL.INFO/LATINSQUARES",
        "rosetta@home": "BOINC.BAKERLAB.ORG/ROSETTA",
        "SiDock@home": "SIDOCK.SI/SIDOCK",
        "SRBase": "SRBASE.MY-FIREWALL.ORG/SR5",
        "TN-Grid": "GENE.DISI.UNITN.IT/TEST",
        "universe@home": "UNIVERSEATHOME.PL/UNIVERSE",
        "World_Community_Grid": "WORLDCOMMUNITYGRID.ORG/BOINC",
        "yoyo@home": "RECHENKRAFT.NET/YOYO",
    }
    lookback_period = 30
    result = main.get_project_mag_ratios_from_response(
        response, lookback_period, project_resolver_dict
    )
    assert result == {
        "SECH.ME/BOINC/AMICABLE": 8.91264681577104e-05,
        "SRBASE.MY-FIREWALL.ORG/SR5": 8.539680314693781e-05,
        "SIDOCK.SI/SIDOCK": 0.003301081663199078,
        "GENE.DISI.UNITN.IT/TEST": 0.0035177177490411625,
        "WORLDCOMMUNITYGRID.ORG": 0.0009398350573579004,
        "ASTEROIDSATHOME.NET/BOINC": 0.003858841063201462,
        "EINSTEIN.PHYS.UWM.EDU": 4.0056880080044686e-05,
        "FOLDINGATHOME.DIV72.XYZ": 2.354611008478076e-05,
        "MILKYWAY.CS.RPI.EDU/MILKYWAY": 0.00017020525368876164,
        "ESCATTER11.FULLERTON.EDU/NFS": 0.0014315462447158976,
        "NUMBERFIELDS.ASU.EDU/NUMBERFIELDS": 0.0003832862658003348,
        "BOINC.MULTI-POOL.INFO/LATINSQUARES": 0.004925403380069366,
        "BOINC.BAKERLAB.ORG/ROSETTA": 0.010315385227402484,
        "UNIVERSEATHOME.PL/UNIVERSE": 0.00028549726782855914,
        "RECHENKRAFT.NET/YOYO": 0.0018665701101050107,
    }


def test_profitability_check():
    # profitable if you sell GRC for a 1000 USD
    grc_price = 0.00
    exchange_fee = 0.10
    main.HOST_COST_PER_HOUR = 1
    grc_sell_price = 1000
    min_profit_per_hour = 0
    combined_stats = {"myproject.com": {"COMPILED_STATS": {"AVGMAGPERHOUR": 4}}}
    assert main.profitability_check(
        grc_price,
        exchange_fee,
        grc_sell_price,
        "myproject.com",
        min_profit_per_hour,
        combined_stats,
    )
    # not profitable if grc is worth zero
    grc_sell_price = 0
    assert not main.profitability_check(
        grc_price,
        exchange_fee,
        grc_sell_price,
        "myproject.com",
        min_profit_per_hour,
        combined_stats,
    )
    # not profitable if expenses too high
    main.HOST_COST_PER_HOUR = 10
    grc_sell_price = 1
    assert not main.profitability_check(
        grc_price,
        exchange_fee,
        grc_sell_price,
        "myproject.com",
        min_profit_per_hour,
        combined_stats,
    )


def test_get_avg_mag_hr():
    combined_stats = {
        "myproject.com": {"COMPILED_STATS": {"TOTALWALLTIME": 1, "AVGMAGPERHOUR": 2}},
        "myproject2.com": {"COMPILED_STATS": {"TOTALWALLTIME": 1, "AVGMAGPERHOUR": 2}},
    }
    result = main.get_avg_mag_hr(combined_stats)
    assert result == 2


def test_make_discrepancy_timeout():
    original_dev_mode = main.FORCE_DEV_MODE
    main.FORCE_DEV_MODE = True
    answer = main.make_discrepancy_timeout(-100)
    assert answer == 60
    main.FORCE_DEV_MODE = False
    answer = main.make_discrepancy_timeout(-60)
    assert answer == 0
    answer = main.make_discrepancy_timeout(100)
    assert answer == 100
    main.FORCE_DEV_MODE == original_dev_mode


def test_owed_to_dev():
    original_ftm_total = None
    if main.DATABASE.get("FTMTOTAL"):
        original_ftm_total = main.DATABASE.get("FTMTOTAL")
    original_dev_total = None
    if main.DATABASE.get("DEVTIMETOTAL"):
        original_dev_total = main.DATABASE.get("DEVTIMETOTAL")
    main.DEV_FEE = 0.01
    # negative hours owed
    main.DATABASE["FTMTOTAL"] = 100 * 60
    main.DATABASE["DEVTIMETOTAL"] = 10 * 60
    discrepancy = main.owed_to_dev()
    assert discrepancy == -8.9
    # 9.01 hr owed
    main.DATABASE["FTMTOTAL"] = 1000 * 60
    main.DATABASE["DEVTIMETOTAL"] = 1 * 60
    discrepancy = main.owed_to_dev()
    assert discrepancy == 9.01
    # restore original values
    if original_ftm_total:
        main.DATABASE["FTMTOTAL"] = original_ftm_total
    if original_dev_total:
        main.DATABASE["DEVTOTAL"] = original_dev_total


def test_date_to_date():
    original_date = "06-26-2023"
    converted = main.date_to_date(original_date)
    assert converted.year == 2023
    assert converted.month == 6
    assert converted.day == 26


def test_get_latest_wu_date():
    dates = ["06-26-2023", "06-27-2024", "06-23-2022"]
    latest_date = main.get_latest_wu_date(dates)
    assert latest_date.year == 2024


def test_stuck_xfer():
    example_xfer = {
        "status": "1",
        "persistent_file_xfer": {
            "num_retries": 1,
        },
    }
    assert main.stuck_xfer(example_xfer)
    example_xfer = {
        "status": "0",
        "persistent_file_xfer": {
            "num_retries": 1,
        },
    }
    assert main.stuck_xfer(example_xfer)
    example_xfer = {
        "status": "0",
        "persistent_file_xfer": {
            "num_retries": 0,
        },
    }
    assert not main.stuck_xfer(example_xfer)
    example_xfer = {
        "status": "0",
    }
    assert not main.stuck_xfer(example_xfer)


def test_json_default():
    return_dict = main.json_default(datetime.datetime.now())
    assert isinstance(return_dict, dict)


def test_object_hook():
    return_dict = main.json_default(datetime.datetime.now())
    result = main.object_hook(return_dict)
    assert isinstance(result, datetime.datetime)


def test_should_crunch_for_dev():
    original_dev_mode = main.FORCE_DEV_MODE
    main.DEV_FEE = 0.01
    # should return false is in dev loop
    assert not main.should_crunch_for_dev(True)
    # should return false if user is sidestaking
    main.CHECK_SIDESTAKE_RESULTS = True
    assert not main.should_crunch_for_dev(False)
    # should return True if dev mode forced
    main.CHECK_SIDESTAKE_RESULTS = False
    main.FORCE_DEV_MODE = True
    assert main.should_crunch_for_dev(False)
    # should return True if due to crunch
    main.FORCE_DEV_MODE = False
    main.DATABASE["FTMTOTAL"] = 100000 * 60
    main.DATABASE["DEVTIMETOTAL"] = 1 * 60
    assert main.should_crunch_for_dev(False)
    # should return True if not due to crunch
    main.FORCE_DEV_MODE = False
    main.DATABASE["FTMTOTAL"] = 98 * 60
    main.DATABASE["DEVTIMETOTAL"] = 1 * 60
    assert not main.should_crunch_for_dev(False)
    # return originals
    main.FORCE_DEV_MODE = original_dev_mode
