from __future__ import annotations

from deepsight import ros
from deepsight.config import AppConfig
from deepsight.runner import CommandResult


def test_ros_snapshot_reads_tf_frame_names_without_exporting_frame_graph(monkeypatch):
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
        if command == "timeout 2 ros2 topic echo --once /tf_static":
            return CommandResult(
                True,
                command,
                0,
                "transforms:\n- header:\n    frame_id: map\n  child_frame_id: odom\n",
                "",
            )
        if command == "timeout 2 ros2 topic echo --once /tf":
            return CommandResult(
                True,
                command,
                0,
                "transforms:\n- header:\n    frame_id: odom\n  child_frame_id: leo05/base_link\n",
                "",
            )
        return CommandResult(True, command, 0, "average: 1.0 KB/s", "")

    monkeypatch.setattr(ros, "command_available", fake_command_available)
    monkeypatch.setattr(ros, "run_shell_command", fake_run_shell_command)

    snapshot = ros.ros_snapshot(AppConfig())

    assert "ros2 run tf2_tools view_frames" not in commands
    assert snapshot["tf_tree"] == "TF topics active: /tf, /tf_static"
    assert snapshot["tf_frames"] == ["leo05/base_link", "map", "odom"]
