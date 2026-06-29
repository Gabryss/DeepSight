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


def command_available(command: str | None) -> bool | None:
    if not command:
        return None
    executable = shlex.split(command)[0]
    return shutil.which(executable) is not None


def _ros_shell_prefix(config: AppConfig) -> str:
    if config.mission.ros_setup:
        return f"source {shlex.quote(config.mission.ros_setup)} && "
    return ""


def run_shell_command(command: str, timeout_sec: float, config: AppConfig | None = None) -> CommandResult:
    effective_command = prepare_command(command, config)

    try:
        completed = subprocess.run(
            ["bash", "-lc", effective_command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
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
    if config and (
        command.strip().startswith(("ros2 ", "rviz2", "rqt_", "zenoh-bridge"))
        or " ros2 " in f" {command} "
    ):
        effective_command = f"{_ros_shell_prefix(config)}{command}"
    return effective_command


def start_background_command(command: str, config: AppConfig | None = None) -> CommandResult:
    effective_command = prepare_command(command, config)
    try:
        process = subprocess.Popen(
            ["bash", "-lc", effective_command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
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
