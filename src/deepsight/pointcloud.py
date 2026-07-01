from __future__ import annotations

import math
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from deepsight.config import AppConfig
from deepsight.postprocessing import find_bag


POINT_CLOUD_TYPE = "sensor_msgs/msg/PointCloud2"
FLOAT32 = 7
FLOAT64 = 8


def _field_map(message: Any) -> dict[str, Any]:
    return {field.name: field for field in getattr(message, "fields", [])}


def _read_float(data: bytes, offset: int, datatype: int, endian: str) -> float | None:
    if datatype == FLOAT32:
        if offset + 4 > len(data):
            return None
        return struct.unpack_from(f"{endian}f", data, offset)[0]
    if datatype == FLOAT64:
        if offset + 8 > len(data):
            return None
        return float(struct.unpack_from(f"{endian}d", data, offset)[0])
    return None


def pointcloud2_to_points(message: Any, max_points: int) -> list[list[float]]:
    fields = _field_map(message)
    if not {"x", "y", "z"}.issubset(fields):
        return []

    width = int(getattr(message, "width", 0) or 0)
    height = int(getattr(message, "height", 0) or 0)
    point_step = int(getattr(message, "point_step", 0) or 0)
    row_step = int(getattr(message, "row_step", 0) or 0)
    data = bytes(getattr(message, "data", b""))
    if width <= 0 or height <= 0 or point_step <= 0 or row_step <= 0 or not data:
        return []

    total = width * height
    limit = max(1, min(max_points, total))
    stride = max(1, math.ceil(total / limit))
    endian = ">" if getattr(message, "is_bigendian", False) else "<"
    intensity_field = fields.get("intensity")
    points: list[list[float]] = []

    for index in range(0, total, stride):
        row = index // width
        column = index % width
        base = row * row_step + column * point_step
        x = _read_float(data, base + fields["x"].offset, fields["x"].datatype, endian)
        y = _read_float(data, base + fields["y"].offset, fields["y"].datatype, endian)
        z = _read_float(data, base + fields["z"].offset, fields["z"].datatype, endian)
        if x is None or y is None or z is None or not all(math.isfinite(value) for value in (x, y, z)):
            continue
        intensity = 0.65
        if intensity_field is not None:
            raw_intensity = _read_float(data, base + intensity_field.offset, intensity_field.datatype, endian)
            if raw_intensity is not None and math.isfinite(raw_intensity):
                intensity = max(0.0, min(1.0, raw_intensity / 255.0 if raw_intensity > 1.0 else raw_intensity))
        points.append([round(x, 4), round(y, 4), round(z, 4), round(intensity, 4)])
        if len(points) >= limit:
            break
    return points


def _topic_type(bag: dict[str, object], topic_name: str) -> str | None:
    for topic in bag.get("topics", []):
        if topic.get("name") == topic_name:
            return str(topic.get("type"))
    return None


def _read_pointcloud_from_bag(bag: dict[str, object], topic: str, max_points: int) -> dict[str, object]:
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        return {"ok": False, "error": f"ROS bag Python bindings unavailable: {exc}", "points": []}

    topic_type = get_message(POINT_CLOUD_TYPE)
    reader = rosbag2_py.SequentialReader()
    storage_id = str(bag.get("storage") or "mcap")
    reader.open(
        rosbag2_py.StorageOptions(uri=str(Path(str(bag["path"])).expanduser()), storage_id=storage_id),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
    )

    while reader.has_next():
        topic_name, serialized, timestamp = reader.read_next()
        if topic_name != topic:
            continue
        message = deserialize_message(serialized, topic_type)
        points = pointcloud2_to_points(message, max(100, min(max_points, 200_000)))
        return {
            "ok": True,
            "error": "",
            "bag_path": str(bag["path"]),
            "topic": topic,
            "timestamp": timestamp,
            "point_count": len(points),
            "points": points,
        }

    return {"ok": False, "error": "no PointCloud2 message found for selected topic", "points": []}


def _subprocess_pointcloud_sample(config: AppConfig, bag_path: str, topic: str, max_points: int) -> dict[str, object]:
    module_root = str(Path(__file__).resolve().parents[1])
    env_prefix = f"PYTHONPATH={shlex_join([module_root])}:$PYTHONPATH"
    command = f"{env_prefix} {shlex_join([sys.executable, '-m', 'deepsight.pointcloud_cli', bag_path, topic, str(max_points)])}"
    if config.mission.ros_setup:
        command = f"source {shlex_join([config.mission.ros_setup])} && {command}"
    result = subprocess.run(["bash", "-lc", command], capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip() or result.stdout.strip() or "point cloud extractor failed", "points": []}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid point cloud extractor output: {exc}", "points": []}


def shlex_join(parts: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(part) for part in parts)


def pointcloud_sample(config: AppConfig, bag_path: str, topic: str, max_points: int) -> dict[str, object]:
    bag = find_bag(config, bag_path)
    if not bag:
        return {"ok": False, "error": "bag path is not under configured bag_root or has no metadata", "points": []}
    if _topic_type(bag, topic) != POINT_CLOUD_TYPE:
        return {"ok": False, "error": "selected topic is not sensor_msgs/msg/PointCloud2", "points": []}

    result = _read_pointcloud_from_bag(bag, topic, max_points)
    if result["ok"] or not config.mission.ros_setup:
        return result
    return _subprocess_pointcloud_sample(config, bag_path, topic, max_points)
