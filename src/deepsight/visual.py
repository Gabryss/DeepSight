from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from deepsight.bags import bag_inventory
from deepsight.config import AppConfig
from deepsight.runner import command_available, run_shell_command


POINT_CLOUD_TYPES = {"sensor_msgs/msg/PointCloud2"}
CAMERA_TYPES = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
CAMERA_INFO_TYPES = {"sensor_msgs/msg/CameraInfo"}
COSTMAP_TYPES = {"nav_msgs/msg/OccupancyGrid"}
GLOBAL_TOPIC_NAMES = {
    "/battery_state",
    "/clock",
    "/events",
    "/parameter_events",
    "/rosout",
    "/rousout",
    "/tf",
    "/tf_static",
    "/tf_statics",
}


@dataclass(frozen=True)
class VisualTopic:
    name: str
    type: str
    source: str

    def payload(self) -> dict[str, str]:
        return {"name": self.name, "type": self.type, "source": self.source}


def _parse_ros_topic_types(output: str) -> list[VisualTopic]:
    topics = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "[" not in line or not line.endswith("]"):
            continue
        name, type_section = line.rsplit("[", 1)
        topic_type = type_section[:-1].strip()
        topic_name = name.strip()
        if topic_name and topic_type:
            topics.append(VisualTopic(topic_name, topic_type, "live"))
    return topics


def _bag_visual_topics(config: AppConfig) -> list[VisualTopic]:
    payload = bag_inventory(config)
    topics: dict[tuple[str, str], VisualTopic] = {}
    for bag in payload.get("bags", []):
        for topic in bag.get("topics", []):
            name = str(topic.get("name", ""))
            topic_type = str(topic.get("type", ""))
            if name and topic_type:
                topics[(name, topic_type)] = VisualTopic(name, topic_type, "bag")
    return sorted(topics.values(), key=lambda topic: (topic.name, topic.type))


def live_visual_topics(config: AppConfig) -> list[VisualTopic]:
    if not command_available("ros2", config):
        return []

    result = run_shell_command("ros2 topic list -t", 4, config)
    if not result.ok:
        return []
    return _parse_ros_topic_types(result.stdout)


def graph_visual_topics(topic_types: dict[str, object]) -> list[VisualTopic]:
    topics = []
    for name, raw_types in topic_types.items():
        types = raw_types if isinstance(raw_types, list | tuple | set) else [raw_types]
        for topic_type in types:
            if name and topic_type:
                topics.append(VisualTopic(str(name), str(topic_type), "live"))
    return topics


def visual_topics(config: AppConfig, live_topics: list[VisualTopic] | None = None) -> dict[str, object]:
    topics: dict[tuple[str, str, str], VisualTopic] = {}
    for topic in live_topics if live_topics is not None else live_visual_topics(config):
        topics[(topic.source, topic.name, topic.type)] = topic
    for topic in _bag_visual_topics(config):
        topics[(topic.source, topic.name, topic.type)] = topic

    values = sorted(topics.values(), key=lambda topic: (topic.source != "live", topic.name, topic.type))
    point_cloud = [topic.payload() for topic in values if topic.type in POINT_CLOUD_TYPES]
    camera = [topic.payload() for topic in values if topic.type in CAMERA_TYPES]
    camera_info = [topic.payload() for topic in values if topic.type in CAMERA_INFO_TYPES]
    costmap = [topic.payload() for topic in values if topic.type in COSTMAP_TYPES]
    entities = visible_entities_from_topics(topic.name for topic in values)

    return {
        "point_cloud": point_cloud,
        "camera": camera,
        "camera_info": camera_info,
        "costmap": costmap,
        "entities": entities,
        "available": bool(point_cloud or camera or camera_info or costmap),
    }


def entity_from_topic(topic_name: str) -> str:
    if topic_name in GLOBAL_TOPIC_NAMES:
        return ""
    parts = [part for part in topic_name.split("/") if part]
    if not parts or f"/{parts[0]}" in GLOBAL_TOPIC_NAMES:
        return ""
    return parts[0]


def visible_entities_from_topics(topic_names: Iterable[object]) -> list[str]:
    names = topic_names if isinstance(topic_names, list | tuple | set) else list(topic_names)
    return sorted({entity for name in names if (entity := entity_from_topic(str(name)))})
