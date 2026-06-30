from __future__ import annotations

from dataclasses import dataclass

from deepsight.bags import bag_inventory
from deepsight.config import AppConfig
from deepsight.runner import command_available, run_shell_command


POINT_CLOUD_TYPES = {"sensor_msgs/msg/PointCloud2"}
CAMERA_TYPES = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
COSTMAP_TYPES = {"nav_msgs/msg/OccupancyGrid"}


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


def visual_topics(config: AppConfig) -> dict[str, object]:
    topics: dict[tuple[str, str, str], VisualTopic] = {}
    for topic in live_visual_topics(config):
        topics[(topic.source, topic.name, topic.type)] = topic
    for topic in _bag_visual_topics(config):
        topics[(topic.source, topic.name, topic.type)] = topic

    values = sorted(topics.values(), key=lambda topic: (topic.source != "live", topic.name, topic.type))
    point_cloud = [topic.payload() for topic in values if topic.type in POINT_CLOUD_TYPES]
    camera = [topic.payload() for topic in values if topic.type in CAMERA_TYPES]
    costmap = [topic.payload() for topic in values if topic.type in COSTMAP_TYPES]

    return {
        "point_cloud": point_cloud,
        "camera": camera,
        "costmap": costmap,
        "available": bool(point_cloud or camera or costmap),
    }
