from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from deepsight.config import AppConfig


def _format_seconds(nanoseconds: int | float | None) -> float | None:
    if nanoseconds is None:
        return None
    return round(float(nanoseconds) / 1_000_000_000, 2)


def _bag_size_bytes(path: Path, relative_files: list[str]) -> int:
    total = 0
    for relative_file in relative_files:
        bag_file = path / relative_file
        if bag_file.exists():
            total += bag_file.stat().st_size
    return total


def _topic_summary(info: dict[str, Any]) -> list[dict[str, object]]:
    topics = []
    for entry in info.get("topics_with_message_count") or []:
        metadata = entry.get("topic_metadata") or {}
        topics.append(
            {
                "name": metadata.get("name", "unknown"),
                "type": metadata.get("type", "unknown"),
                "messages": entry.get("message_count", 0),
            }
        )
    return topics


def inspect_bag(path: Path) -> dict[str, object] | None:
    metadata_path = path / "metadata.yaml"
    if not metadata_path.exists():
        return None

    with metadata_path.open("r", encoding="utf-8") as metadata_file:
        metadata = yaml.safe_load(metadata_file) or {}

    info = metadata.get("rosbag2_bagfile_information") or {}
    relative_files = info.get("relative_file_paths") or []
    topics = _topic_summary(info)
    return {
        "name": path.name,
        "path": str(path),
        "storage": info.get("storage_identifier", "unknown"),
        "ros_distro": info.get("ros_distro", "unknown"),
        "duration_sec": _format_seconds((info.get("duration") or {}).get("nanoseconds")),
        "message_count": info.get("message_count", 0),
        "topic_count": len(topics),
        "topics": topics,
        "size_bytes": _bag_size_bytes(path, relative_files),
    }


def bag_inventory(config: AppConfig) -> dict[str, object]:
    if not config.mission.bag_root:
        return {"available": False, "root": None, "bags": [], "error": "bag_root is not configured"}

    root = Path(config.mission.bag_root).expanduser()
    if not root.exists():
        return {"available": False, "root": str(root), "bags": [], "error": "bag_root does not exist"}

    bags = []
    for metadata_path in sorted(root.glob("**/metadata.yaml")):
        bag = inspect_bag(metadata_path.parent)
        if bag:
            bags.append(bag)

    return {"available": True, "root": str(root), "bags": bags, "error": ""}
