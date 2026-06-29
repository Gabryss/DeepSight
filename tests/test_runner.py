from __future__ import annotations

from deepsight.config import AppConfig, Mission
from deepsight import runner
from deepsight.runner import CommandResult, command_available, prepare_command


def test_prepare_command_sources_ros_setup_for_ros_commands():
    config = AppConfig(mission=Mission(ros_setup="/opt/ros/jazzy/setup.bash"))

    command = prepare_command("ros2 topic list", config)

    assert command == "source /opt/ros/jazzy/setup.bash && ros2 topic list"


def test_command_available_uses_configured_ros_environment(monkeypatch):
    config = AppConfig(mission=Mission(ros_setup="/opt/ros/jazzy/setup.bash"))
    calls = []

    def fake_run_shell_command(command, timeout_sec, config_arg):
        calls.append((command, timeout_sec, config_arg))
        return CommandResult(True, command, 0, "/opt/ros/jazzy/bin/ros2", "")

    monkeypatch.setattr(runner, "run_shell_command", fake_run_shell_command)

    assert command_available("ros2", config) is True
    assert calls == [("command -v ros2", 2, config)]
