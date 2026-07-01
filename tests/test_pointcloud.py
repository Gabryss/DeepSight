from __future__ import annotations

import struct
from dataclasses import dataclass

from deepsight.pointcloud import pointcloud2_to_points
from deepsight.config import AppConfig, Mission
from deepsight.pointcloud import ros_python_module_command


@dataclass
class Field:
    name: str
    offset: int
    datatype: int


@dataclass
class Message:
    width: int
    height: int
    point_step: int
    row_step: int
    fields: list[Field]
    data: bytes
    is_bigendian: bool = False


def test_pointcloud2_to_points_decodes_and_downsamples():
    data = b"".join(
        struct.pack("<ffff", float(index), float(index + 1), float(index + 2), 128.0)
        for index in range(4)
    )
    message = Message(
        width=4,
        height=1,
        point_step=16,
        row_step=64,
        fields=[
            Field("x", 0, 7),
            Field("y", 4, 7),
            Field("z", 8, 7),
            Field("intensity", 12, 7),
        ],
        data=data,
    )

    points = pointcloud2_to_points(message, max_points=2)

    assert points == [[0.0, 1.0, 2.0, 0.502], [2.0, 3.0, 4.0, 0.502]]


def test_pointcloud2_to_points_rejects_missing_xyz():
    message = Message(width=1, height=1, point_step=4, row_step=4, fields=[Field("x", 0, 7)], data=b"\x00" * 4)

    assert pointcloud2_to_points(message, max_points=100) == []


def test_ros_python_module_command_sources_ros_and_preserves_pythonpath():
    config = AppConfig(mission=Mission(ros_setup="/opt/ros/jazzy/setup.bash"))

    command = ros_python_module_command(config, "deepsight.pointcloud_live_cli", ["/cloud", "1000", "5"])

    assert command.startswith("source /opt/ros/jazzy/setup.bash && ")
    assert "PYTHONPATH=" in command
    assert ":$PYTHONPATH" in command
    assert "deepsight.pointcloud_live_cli /cloud 1000 5" in command
