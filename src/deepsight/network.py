from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from deepsight.config import AppConfig, Robot
from deepsight.runner import run_shell_command


def ping_robot(robot: Robot, config: AppConfig) -> dict[str, object]:
    timeout = max(1, int(config.network.ping_timeout_sec))
    result = run_shell_command(f"ping -c 1 -W {timeout} {robot.host}", timeout + 1, None)
    latency = None
    for token in result.stdout.replace("=", " ").replace("/", " ").split():
        try:
            value = float(token)
        except ValueError:
            continue
        if "time=" in result.stdout:
            latency = value
            break
    return {
        "id": robot.id,
        "label": robot.label,
        "host": robot.host,
        "ssh_target": robot.ssh_target,
        "online": result.ok,
        "latency_ms": latency,
        "error": "" if result.ok else result.stderr or result.stdout,
    }


def robot_connectivity(config: AppConfig) -> list[dict[str, object]]:
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(config.robots)))) as pool:
        return list(pool.map(lambda robot: ping_robot(robot, config), config.robots))


def robot_batteries(config: AppConfig) -> list[dict[str, object]]:
    readings = []
    for robot in config.robots:
        if not robot.battery_command:
            readings.append({"id": robot.id, "label": robot.label, "available": False, "value": None, "raw": ""})
            continue
        result = run_shell_command(robot.battery_command, 4, config)
        value = None
        for token in result.stdout.replace("%", " ").split():
            try:
                value = float(token)
                break
            except ValueError:
                continue
        readings.append(
            {
                "id": robot.id,
                "label": robot.label,
                "available": result.ok,
                "value": value,
                "raw": result.stdout or result.stderr,
            }
        )
    return readings
