from __future__ import annotations

from deepsight import ros
from deepsight.config import AppConfig
from deepsight.runner import CommandResult


def test_ros_snapshot_does_not_export_tf_frames_during_poll(monkeypatch):
    commands = []

    def fake_command_available(command, config):
        return True

    def fake_run_shell_command(command, timeout_sec, config):
        commands.append(command)
        if command == "ros2 topic list":
            return CommandResult(True, command, 0, "/tf\n/tf_static\n/cloud", "")
        if command == "ros2 node list":
            return CommandResult(True, command, 0, "/node", "")
        if command == "ros2 service list":
            return CommandResult(True, command, 0, "/service", "")
        return CommandResult(True, command, 0, "average: 1.0 KB/s", "")

    monkeypatch.setattr(ros, "command_available", fake_command_available)
    monkeypatch.setattr(ros, "run_shell_command", fake_run_shell_command)

    snapshot = ros.ros_snapshot(AppConfig())

    assert "ros2 run tf2_tools view_frames" not in commands
    assert snapshot["tf_tree"] == "TF topics active: /tf, /tf_static"
