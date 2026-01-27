from __future__ import annotations

import functools
import logging
import math
import os
import re
import subprocess

from utils.utils import print_and_log as _print_and_log

log = logging.getLogger()
print_and_log = functools.partial(_print_and_log, log=log)


def set_temp_control(
    override_path: str,
    boinccmd_executable: str,
    cpu_time_percent: float = 100,
) -> bool:
    """
    Do initial setup of and start dev boinc client. Returns RPC password. Returns 'ERROR' if unable to start BOINC
    """
    cpu_time_percent = max(1.0, min(100.0, cpu_time_percent))
    # Update settings to match user settings from main BOINC install
    if os.path.exists(override_path):
        # Read in the file
        with open(override_path, "r") as f:
            filedata = f.read()
        # Replace the target string
        if "<cpu_usage_limit>" in filedata:
            filedata = re.sub(
                "<cpu_usage_limit>[^<]*</cpu_usage_limit>",
                "<cpu_usage_limit>{:.02f}</cpu_usage_limit>".format(cpu_time_percent),
                filedata,
            )
        else:
            filedata = filedata.replace(
                "<global_preferences>",
                "<global_preferences><cpu_usage_limit>{:.02f}</cpu_usage_limit>".format(
                    cpu_time_percent
                ),
            )
        log.debug(
            "Updated BOINC override prefs to: cpu_usage_limit=%.02f", cpu_time_percent
        )

        # Write the file out again
        with open(override_path, "w") as f:
            f.write(filedata)
    else:
        with open(override_path, "w") as f:
            f.write(
                "<global_preferences><cpu_usage_limit>{:.02f}</cpu_usage_limit></global_preferences>".format(
                    cpu_time_percent
                )
            )
        log.debug(
            "Created BOINC override prefs with cpu_usage_limit=%.02f", cpu_time_percent
        )
    boinc_arguments = [
        boinccmd_executable,
        "--read_global_prefs_override",
    ]
    try:
        boinc_result = subprocess.Popen(
            boinc_arguments, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
        )
    except Exception as e:
        print_and_log("Error reloading BOINC preferences: {}".format(e), "ERROR")
        return False
    log.debug("Reloaded BOINC preferences with CPU limit %.02f", cpu_time_percent)
    return True


class PIDController:
    def __init__(self, init_ctrl: float = 0.0, target_opt: float = 70.0):
        # Parameters
        self.target_opt = target_opt
        self.clamped_low = 0.0
        self.clamped_high = 1.0
        self.clamp_soft = math.log(1 / 0.001 - 1)
        self.clamp_hard = self.clamp_soft * 1.25

        # Runtime variables
        self.reset_counter = 0
        self.last_timestamp = None

        self.error_0 = None
        self.error_1 = None
        self.delta_time = None
        self.ctrl = init_ctrl

        # PID parameters
        self.k_proportional = 0.0
        self.t_integral = 0.0
        self.t_derivative = 0.0

        # TODO: Automatically tune these parameters
        self.k_ultimate = None
        self.stable_period = None

    def reset(self, counter: int = 0):
        self.reset_counter += 1
        if self.reset_counter < counter:
            return

        self.last_timestamp = None
        self.error_0 = None
        self.error_1 = None
        self.delta_time = None

    def export_state(self):
        return {
            "ctrl": self.ctrl,
            "clamped_ctrl": self.clamped_ctrl,
            # "k_ultimate": self.k_ultimate,
            # "stable_period": self.stable_period,
        }

    def import_state(self, state: dict):
        self.ctrl = state.get("ctrl", self.ctrl)
        if "clamped_ctrl" in state:
            self.clamped_ctrl = state["clamped_ctrl"]

        self.k_ultimate = state.get("k_ultimate", self.k_ultimate)
        self.stable_period = state.get("stable_period", self.stable_period)
        self.set_params_from_state()

        self.k_proportional = state.get("k_proportional", self.k_proportional)
        self.t_integral = state.get("t_integral", self.t_integral)
        self.t_derivative = state.get("t_derivative", self.t_derivative)

    def set_params_from_state(self):
        assert self.stable_period is not None
        assert self.k_ultimate is not None
        if self.k_ultimate is not None:
            self.k_proportional = 0.6 * self.k_ultimate
        if self.stable_period is not None:
            self.t_integral = 0.5 * self.stable_period
            self.t_derivative = 0.125 * self.stable_period
        else:
            self.k_proportional = 0.5 * self.k_ultimate

    @property
    def clamped_ctrl(self) -> float:
        ctrl = self.ctrl
        log.debug(f"Raw control signal before clamping: {ctrl}; sigmoid applied")
        if ctrl < -self.clamp_soft:
            return self.clamped_low
        if ctrl > +self.clamp_soft:
            return self.clamped_high
        raw = 1.0 / (1.0 + math.exp(-ctrl))
        return self.clamped_low + (self.clamped_high - self.clamped_low) * raw

    @clamped_ctrl.setter
    def clamped_ctrl(self, value: float):
        if (value - self.clamped_low) * (self.clamped_high - self.clamped_low) <= 0:
            self.ctrl = -self.clamp_soft
        elif (self.clamped_high - value) * (self.clamped_high - self.clamped_low) <= 0:
            self.ctrl = self.clamp_soft
        else:
            raw = (value - self.clamped_low) / (self.clamped_high - self.clamped_low)
            self.ctrl = -math.log((1.0 / raw) - 1.0)

    def timestamp_update(self, opt_value: float, timestamp: float):
        if self.last_timestamp is None:
            self.last_timestamp = timestamp
            return
        delta_time = timestamp - self.last_timestamp
        self.last_timestamp = timestamp
        self.delta_update(opt_value, delta_time)

    def delta_update(self, opt_value: float, delta_time: float):
        error = self.target_opt - opt_value
        self.ctrl += self.update_pid(
            error, delta_time, clamped=abs(self.ctrl) > self.clamp_soft
        )
        self.ctrl = max(-self.clamp_hard, min(self.clamp_hard, self.ctrl))

    def update_pid(
        self, error: float, delta_time: float, clamped: bool = False
    ) -> float:
        k_p = self.k_proportional
        k_i = k_p / self.t_integral if self.t_integral != 0 else 0.0
        k_d = k_p * self.t_derivative
        dt_mid = delta_time
        dt_ratio = 1.0
        if self.error_0 is None:
            k_d = 0.0
            k_p = 0.0
        if self.delta_time is None or self.error_1 is None:
            k_d = 0.0
        else:
            dt_mid = (delta_time + self.delta_time) / 2.0
            dt_ratio = delta_time / self.delta_time
        if clamped:
            k_i = 0.0
        delta = 0
        delta += (k_p + k_i * delta_time + k_d / dt_mid) * error
        if self.error_0 is not None:
            delta += (-k_p - k_d * (1 + dt_ratio) / dt_mid) * self.error_0
        if self.error_1 is not None:
            delta += (k_d * dt_ratio / dt_mid) * self.error_1
        self.error_1 = self.error_0
        self.error_0 = error
        self.delta_time = delta_time if delta_time > 0 else None
        log.debug(f"Updated control signal: delta={delta}; k=({k_p},{k_i},{k_d})")
        return delta
