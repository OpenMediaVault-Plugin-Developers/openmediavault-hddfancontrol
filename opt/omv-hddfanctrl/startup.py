import subprocess
import sys
import re
import time
import timeit
import math
from pathlib import Path
import threading

def log_error(err, *args, **kwargs):
    print("[omv-hddfanctrl] Error: " + err.format(*args, **kwargs))

def log_info(info, *args, **kwargs):
    print("[omv-hddfanctrl] Info: " + info.format(*args, **kwargs))

def check_file(file_path: Path, file_type):
    if not file_path.exists():
        log_error("Expected {} file at {} but not found!", file_type, file_path)
        return False
    return True

def read_file(file_path: Path):
    with open(file_path, "rt") as f:
        return f.read().strip()

def write_file(file_path: Path, content: str):
    with open(file_path, "wt") as f:
        f.write(content)


class Fan(threading.Thread):
    FAN_PATH_REGEX = re.compile("^(?P<path>.+)pwm(?P<index>[0-9]+)+$")

    STABLE_TEST_SPEED_SAMPLES = 5
    STABLE_TEST_DEFAULT_SAMPLE_PERIOD = 2.5
    STABLE_TEST_DEVIATION_PCT = 0.05

    PWM_RANGE_MAX_ERROR = 10
    STOPPED_RPM_THRESHOLD = 10

    def __init__(self, fan_pwm_file_path, cache=None) -> None:
        super().__init__(name=f"{self.__class__.__name__}-{fan_pwm_file_path}")

        self.stop_pwm = 0
        self.start_pwm = 255

        self.max_rpm = 0

        if cache:
            self.stop_pwm = cache["stop_pwm"]
            self.start_pwm = cache["start_pwm"]
            self.max_rpm = cache["max_rpm"]

        self.pwm_file = Path(str(fan_pwm_file_path))
        if not check_file(self.pwm_file, "PWM"):
            return

        path_match = Fan.FAN_PATH_REGEX.match(str(self.pwm_file))
        if not path_match:
            log_error("Fan filepath '{}' doesn't follow the expected file name format", self.pwm_file)
            return

        base_path = Path(path_match["path"])
        fan_index = path_match["index"]
        self.fan_index = fan_index

        self.enable_file = base_path / f"pwm{fan_index}_enable"
        self.rpm_file = base_path / f"fan{fan_index}_input"

        if not check_file(self.enable_file, "PWM enable"):
            return

        if not check_file(self.rpm_file, "current RPM"):
            return

        self.fan_speed_update_period = Fan.STABLE_TEST_DEFAULT_SAMPLE_PERIOD

    def log_fan_info(self, info, *args, **kwargs):
        log_info("[Fan {}] {}".format(self.fan_index, info), *args, **kwargs)

    def detectStartStopPwm(self, round_to=10):
        stop_value_range_l = 0
        stop_value_range_h = 255

        start_value_range_l = 0
        start_value_range_h = 255

        cur_pwm = (stop_value_range_h + stop_value_range_l) // 2
        update_pwm = True

        UP = 1
        DOWN = -1
        direction = DOWN

        self.log_fan_info("Checking the fan works")
        speed_min = self.setPwmAndWaitUntilStable(0)
        self.setPwmAndDetectUpdatePeriod(255)
        speed_max = self.setPwmAndWaitUntilStable(255)

        if self.max_rpm > 0 and abs((speed_max / self.max_rpm) - 1) < 0.025:
            # If the speed matches the cached one, we can assume it's the same fan so we can skip it
            self.log_fan_info("Max RPM matches the one on cache, assuming same fan and using {} as stop and {} as start PWMs", self.stop_pwm, self.start_pwm)
            return (self.stop_pwm, self.start_pwm)

        if speed_max == 0 or abs(speed_max - speed_min) / speed_max < 0.05:
            # The difference between the max and min speed is < 5%, so it might not even work?
            # just quit and use the default values
            self.log_fan_info("It seems the fan might not be there, or not be responding to pwm changes. Returning default min and max pwm.")
            return (0, 255)

        self.max_rpm = speed_max

        rpm_threshold = speed_min + Fan.STOPPED_RPM_THRESHOLD

        self.log_fan_info("Beginning start and stop pwm search")
        while (stop_value_range_h - stop_value_range_l >= Fan.PWM_RANGE_MAX_ERROR
                or start_value_range_h - start_value_range_l >= Fan.PWM_RANGE_MAX_ERROR):
            if update_pwm:
                last_speed = self.setPwmAndWaitUntilStable(cur_pwm)
            if direction == DOWN:
                if last_speed < rpm_threshold:
                    stop_value_range_l = cur_pwm
                    direction = UP
                    update_pwm = False
                    self.log_fan_info("Fan has stopped at {} pwm, changing search direction", cur_pwm)
                    continue
                else:
                    # Continue going down
                    stop_value_range_h = cur_pwm
                    cur_pwm = (stop_value_range_h + stop_value_range_l) // 2
                    update_pwm = True

            elif direction == UP:
                if last_speed > rpm_threshold:
                    start_value_range_h = cur_pwm
                    direction = DOWN
                    update_pwm = False
                    self.log_fan_info("Fan has started at {}, changing search direction", cur_pwm)
                    continue
                else:
                    # Continue going up
                    start_value_range_l = cur_pwm
                    cur_pwm = (start_value_range_l + start_value_range_h) // 2
                    update_pwm = True

        # Rounding to the closest "unit", by default of 10
        return ((stop_value_range_l // round_to) * round_to, ((start_value_range_h + round_to) // round_to) * round_to)


    def setPwm(self, pwm):
        write_file(self.pwm_file, str(pwm))

    def getRpm(self):
        return int(read_file(self.rpm_file))

    def getSettings(self):
        self.prev_settings = {}
        self.prev_settings["enable"] = read_file(self.enable_file)
        self.prev_settings["pwm"] = read_file(self.pwm_file)

    def setSettingsManualPwm(self):
        log_info("Setting fan {} to manual", self.pwm_file)
        self.getSettings()
        write_file(self.enable_file, "1")

    def restoreSettings(self):
        log_info("Restoring fan {} to previous settings: pwm={}, enable={}", self.pwm_file, self.prev_settings["pwm"], self.prev_settings["enable"])
        write_file(self.pwm_file, self.prev_settings["pwm"])
        write_file(self.enable_file, self.prev_settings["enable"])

    def setPwmAndWaitUntilStable(self, pwm):
        self.setPwm(pwm)

        # Collect speed every few ms, exit when variance is low enough
        start_time = timeit.default_timer()
        speeds = []
        # Wait at most 60 seconds...
        while timeit.default_timer() - start_time < 60:
            speeds.append(self.getRpm())
            if len(speeds) >= Fan.STABLE_TEST_SPEED_SAMPLES:
                # Check if monotonally going in the same direction
                diffs = [b - a for a, b in zip(speeds[1:], speeds[:-1])]
                sign = diffs[0]
                # If all the signs match, then multiplying will always be > 0
                # if any of them is 0 or they don't match, then we check variance
                if not all(d * sign > 0 for d in diffs):
                    m = sum(speeds)/len(speeds)
                    sd = math.sqrt(sum(d * d for d in [(s - m) for s in speeds])/len(speeds))
                    # 10 is an offset to the deviation when m is very small (~0)
                    if sd < 10 or ((sd / m) < Fan.STABLE_TEST_DEVIATION_PCT):
                        return m

            if len(speeds) > Fan.STABLE_TEST_SPEED_SAMPLES:
                speeds = speeds[-Fan.STABLE_TEST_SPEED_SAMPLES:]
            time.sleep(self.fan_speed_update_period)

        self.log_fan_info("Waited over 60 seconds waiting for stability... quitting")

        return sum(speeds)/len(speeds)

    def setPwmAndDetectUpdatePeriod(self, pwm):
        self.setPwm(pwm)

        waited_until_change = []
        last_rpm = self.getRpm()
        t_start = timeit.default_timer()
        while len(waited_until_change) < 3:
            rpm = self.getRpm()
            if rpm != last_rpm:
                waited_until_change.append(timeit.default_timer() - t_start)
                last_rpm = rpm
            time.sleep(0.1)

        # We skip the first time since we don't know when we started timing within an update period
        # We also multiply by 1.2 to ensure the period is greater than the actual period
        self.fan_speed_update_period = 1.2 * sum(waited_until_change[1:]) / len(waited_until_change)
        self.log_fan_info("Update period = {}s", self.fan_speed_update_period)

    def toCacheLine(self):
        return "{},{},{},{}\n".format(str(self.pwm_file), int(self.max_rpm), int(self.stop_pwm), int(self.start_pwm))

    def run(self) -> None:
        self.setSettingsManualPwm()
        self.stop_pwm, self.start_pwm = self.detectStartStopPwm()
        self.log_fan_info("Start and stop pwms found were {} and {}", self.stop_pwm, self.start_pwm)
        self.restoreSettings()

conf: dict[str, str] = {}
with open('/etc/omv-hddfanctrl/fanctrl.conf') as fp:
    for line in fp:
        line = line.strip()
        if line == "":
            continue
        if line.startswith('#'):
            continue
        key, val = line.split('=', 1)
        conf[key.strip()] = val.strip()

fan_pwm_files = conf["fan_pwm_file"].split(" ") if len(conf["fan_pwm_file"]) > 0 else []
fan_pwm_starts = []
fan_pwm_stops = []
drive_files = conf['drive_temp_file'].split(" ") if len(conf['drive_temp_file']) > 0 else []

if len(drive_files) == 0:
    log_error("Not starting due to no drives selected")
    exit(1)

if len(fan_pwm_files) == 0:
    log_error("Not starting due to no fans selected")
    exit(1)

cache_file = Path("/var/cache/omv-hddfanctrl/fan-cache")
cache_file.parent.mkdir(parents=True, exist_ok=True)
cache = {}
if cache_file.exists():
    with open(cache_file, "r") as f:
        for line in f:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 4:
                cache[parts[0]] = {"max_rpm": int(parts[1]), "stop_pwm": int(parts[2]), "start_pwm": int(parts[3])}

fans: list[Fan] = []
for fan_file in fan_pwm_files:
    f = Fan(fan_file, cache=cache[fan_file] if fan_file in cache else None)
    fans.append(f)
    f.start()

for ft in fans:
    ft.join()
    fan_pwm_starts.append(str(ft.start_pwm))
    fan_pwm_stops.append(str(ft.stop_pwm))

log_info("Finished fan pwm start and stop detection. Writing to cache.")

# Save the cache
with open(cache_file, "w") as f:
    f.writelines([ft.toCacheLine() for ft in fans])

proc_args = ["/opt/omv-hddfanctrl/venv/bin/hddfancontrol",
            "--drives", *drive_files,
            "--pwm", *fan_pwm_files,
            "--pwm-start-value", *fan_pwm_starts,
            "--pwm-stop-value", *fan_pwm_stops,
            "--min-fan-speed-prct", conf['fan_min_pct'],
            "--min-temp", conf['min_temp'],
            "--max-temp", conf['max_temp'],
            "--interval", conf['temp_update_interval'],
            "--restore-fan-settings"
            ]

if float(conf['spindown_time']) > 0:
    proc_args += ["--spin-down-time", str(int(conf['spindown_time']) * 60)]

dev_mode_file = Path('/etc/openmediavault/developer-mode')
if dev_mode_file.exists() and dev_mode_file.is_file():
    log_info("This would have called {}".format(str(proc_args)))
    exit(0)

complproc = subprocess.run(proc_args)

exit(complproc.returncode)
