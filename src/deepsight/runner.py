from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass

from deepsight.config import AppConfig, Command


@dataclass
class CommandResult:
    ok: bool
    command: str
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


def _needs_ros_setup(command: str) -> bool:
    return command.strip().startswith(("ros2", "rviz2", "rqt_", "zenoh-bridge")) or " ros2 " in f" {command} "


def command_available(command: str | None, config: AppConfig | None = None) -> bool | None:
    if not command:
        return None
    executable = shlex.split(command)[0]
    if config and config.mission.ros_setup and _needs_ros_setup(command):
        result = run_shell_command(f"command -v {shlex.quote(executable)}", 2, config)
        return result.ok and bool(result.stdout)
    return shutil.which(executable) is not None


def _ros_shell_prefix(config: AppConfig) -> str:
    parts = []
    if config.mission.ros_setup:
        parts.append(f"source {shlex.quote(config.mission.ros_setup)}")
    if config.mission.ros_domain_id is not None:
        parts.append(f"export ROS_DOMAIN_ID={shlex.quote(str(config.mission.ros_domain_id))}")
    return " && ".join(parts) + (" && " if parts else "")


def command_environment(config: AppConfig | None = None) -> dict[str, str]:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if config and config.mission.ros_domain_id is not None:
        env["ROS_DOMAIN_ID"] = str(config.mission.ros_domain_id)
    return env


def run_shell_command(command: str, timeout_sec: float, config: AppConfig | None = None) -> CommandResult:
    effective_command = prepare_command(command, config)

    try:
        completed = subprocess.run(
            ["bash", "-lc", effective_command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=command_environment(config),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            ok=False,
            command=command,
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
        )

    return CommandResult(
        ok=completed.returncode == 0,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def prepare_command(command: str, config: AppConfig | None = None) -> str:
    effective_command = command
    if config and _needs_ros_setup(command):
        effective_command = f"{_ros_shell_prefix(config)}{command}"
    return effective_command


def start_background_command(command: str, config: AppConfig | None = None) -> CommandResult:
    effective_command = prepare_command(command, config)
    try:
        process = subprocess.Popen(
            ["bash", "-lc", effective_command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=command_environment(config),
            start_new_session=True,
        )
    except OSError as exc:
        return CommandResult(
            ok=False,
            command=command,
            returncode=None,
            stdout="",
            stderr=str(exc),
        )
    return CommandResult(ok=True, command=command, returncode=None, stdout=f"started pid {process.pid}", stderr="")


async def run_shell_command_async(command: str, timeout_sec: float, config: AppConfig | None = None) -> CommandResult:
    return await asyncio.to_thread(run_shell_command, command, timeout_sec, config)


async def start_background_command_async(command: str, config: AppConfig | None = None) -> CommandResult:
    return await asyncio.to_thread(start_background_command, command, config)


def find_command(command_id: str, config: AppConfig) -> Command | None:
    return next((command for command in config.commands if command.id == command_id), None)
