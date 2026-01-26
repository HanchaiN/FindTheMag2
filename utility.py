# Used for debugging purposes
from main import ROLLING_WEIGHT_WINDOW
import utils.StatsHelper as StatsHelper


def generate_stats():
    answer = input("Enter BOINC data dir")
    combined_stats = StatsHelper.config_files_to_stats(answer, rolling_weight_window=ROLLING_WEIGHT_WINDOW)
    example_ratios = {
        "WORLDCOMMUNITYGRID.ORG": 0.01,
        "SECH.ME/BOINC/AMICABLE": 0.99,
        "ESCATTER11.FULLERTON.EDU/NFS": 0.0,
    }
    approved_projects = list(example_ratios.keys())
    result = StatsHelper.add_mag_to_combined_stats(
        combined_stats, example_ratios, approved_projects, preferred_projects=[]
    )
    print("Answer is {}".format(result))


if __name__ == "__main__":
    answer = ""
    while True:
        print("1. Generate stats")
        answer = input("Enter the option you would like to choose, or Q for quit")
        if answer == "1":
            generate_stats()
        if answer == "Q":
            quit()
