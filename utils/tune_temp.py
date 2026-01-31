from __future__ import annotations

import functools
import logging
import math
import os
import re

from libs.pyboinc.rpc_client import RPCClient
from utils.BoincClientConnection import run_rpc_command
from utils.utils import print_and_log as _print_and_log

log = logging.getLogger()
print_and_log = functools.partial(_print_and_log, log=log)


async def set_temp_control(
    boinc_rpc_client: RPCClient,
    override_path: str,
    cpu_time_frac: float = 1,
    min_delta: float = 0.0,
):
    cpu_time_percent = max(1.0, min(100.0, cpu_time_frac * 100.0))
    cpu_time_percent_str = "{:.02f}".format(cpu_time_percent)
    # Update settings to match user settings from main BOINC install
    if os.path.exists(override_path):
        # Read in the file
        with open(override_path, "r") as f:
            filedata = f.read()
        # Replace the target string
        if "<cpu_usage_limit>" in filedata:
            original = re.search("<cpu_usage_limit>([^<]*)</cpu_usage_limit>", filedata)
            if original:
                original_value = float(original.group(1))
                if (
                    original.group(1) == cpu_time_percent_str
                    or abs(original_value - cpu_time_percent) < min_delta
                ):
                    log.debug(
                        "BOINC override prefs cpu_usage_limit=%.02f within %.02f of desired %.02f, not updating",
                        original_value,
                        min_delta,
                        cpu_time_percent,
                    )
                    return
            filedata = re.sub(
                "<cpu_usage_limit>[^<]*</cpu_usage_limit>",
                "<cpu_usage_limit>{}</cpu_usage_limit>".format(cpu_time_percent_str),
                filedata,
            )
        else:
            filedata = filedata.replace(
                "<global_preferences>",
                "<global_preferences><cpu_usage_limit>{}</cpu_usage_limit>".format(
                    cpu_time_percent_str
                ),
            )
        log.debug(
            "Updated BOINC override prefs to: cpu_usage_limit=%s", cpu_time_percent_str
        )

        # Write the file out again
        with open(override_path, "w") as f:
            f.write(filedata)
    else:
        with open(override_path, "w") as f:
            f.write(
                "<global_preferences><cpu_usage_limit>{}</cpu_usage_limit></global_preferences>".format(
                    cpu_time_percent_str
                )
            )
        log.debug(
            "Created BOINC override prefs with cpu_usage_limit=%s", cpu_time_percent_str
        )
    return await run_rpc_command(boinc_rpc_client, "read_global_prefs_override")


class PertubationController:
    def __init__(self, target_opt: float = 0.0):
        # Parameters
        self.target_opt = target_opt
        self.ctrl_min = 0.0
        self.ctrl_max = 1.0
        self.step_min = 0.01
        self.step_max = 0.25
        self.step_time_deg = 0.5
        self.step_max_abs = 0.5
        self.min_error = 0.5
        self.step_growth = 0.1
        self.hist_size = 5

        self.step = 0.1
        self.ctrl = 0.5

        # Runtime variables
        self.reset_counter = 0
        self.last_timestamp: float | None = None
        self.sign_history: list[int] = []
        self.time_history: list[float] = []
        self.last_sign: int = 0

    def reset(self, counter: int = 0):
        if self.reset_counter < counter:
            self.reset_counter += 1
            return

        self.reset_counter = 0
        self.last_timestamp = None

        # noop

    def export_state(self):
        return {
            "ctrl": self.ctrl,
            "step": self.step,
        }

    def import_state(self, state: dict):
        self.ctrl = state.get("ctrl", self.ctrl)
        self.ctrl = max(self.ctrl_min, min(self.ctrl_max, self.ctrl))
        self.step = state.get("step", self.step)

    def update(self, opt_values: list[float], timestamp: float):
        if len(opt_values) == 0:
            return 0.0
        if self.last_timestamp is None:
            self.last_timestamp = timestamp
            return self.target_opt - sum(opt_values) / len(opt_values)
        opt_values = sorted(opt_values)
        i05 = 0.05 * (len(opt_values) - 1)
        i05_ = math.floor(i05)
        p05 = opt_values[i05_] * (i05 - i05_) + opt_values[i05_ + 1] * (i05_ + 1 - i05)
        i95 = 0.95 * (len(opt_values) - 1)
        i95_ = math.floor(i95)
        p95 = opt_values[i95_] * (i95 - i95_) + opt_values[i95_ + 1] * (i95_ + 1 - i95)
        center = (p95 + p05) / 2.0
        range_ = min((p95 - p05) * 1 / 0.9, opt_values[-1] - opt_values[0])
        delta_time = timestamp - self.last_timestamp
        self.last_timestamp = timestamp
        return self.delta_update(center, range_, delta_time)

    def delta_update(self, center: float, range_: float, delta_time: float):
        self.reset_counter = 0
        error = self.target_opt - center
        min_error = max(range_ / 2.0, self.min_error)
        log.debug(
            "Temp ctl update: mean=%.02f; error=%.02f; min_error=%.02f",
            center,
            error,
            min_error,
        )
        sign = 0
        if error > min_error:
            sign = 1
        if error < -min_error:
            sign = -1
        if sign != 0:
            log.debug("Temp ctl update: sign=%d (error=%.02f)", sign, error)
            self.sign_history.append(sign)
            if len(self.sign_history) > self.hist_size:
                self.sign_history.pop(0)
        self.time_history.append(delta_time)
        if len(self.time_history) > self.hist_size:
            a = self.time_history.pop(0)
            b = self.time_history.pop(0)
            self.time_history.insert(0, (a + b) / 2.0)
        sign = 0
        if sum(self.sign_history) > 0:
            sign = 1
        if sum(self.sign_history) < 0:
            sign = -1
        if sign != 0:
            log.debug("Temp ctl update: sign=%d; step=%.04f", sign, self.step)
            self.ctrl += sign * min(
                self.step_max_abs,
                self.step * delta_time**self.step_time_deg,
            )
        if sign == self.last_sign and sign != 0:
            self.step *= 1.0 + self.step_growth
        elif sign != self.last_sign:
            self.step *= 1.0 - self.step_growth
            self.last_sign = sign
        self.ctrl = max(self.ctrl_min, min(self.ctrl_max, self.ctrl))
        if self.ctrl == self.ctrl_min or self.ctrl == self.ctrl_max:
            self.step = self.step_min
        self.step = max(self.step_min, min(self.step_max, self.step))
        return error
