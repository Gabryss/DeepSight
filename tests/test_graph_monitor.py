from __future__ import annotations

from deepsight.graph_monitor import GraphMonitor
from deepsight.config import AppConfig


class FakeNode:
    def get_topic_names_and_types(self):
        return [
            ("/tf", ["tf2_msgs/msg/TFMessage"]),
            ("/leo05/livox/lidar", ["sensor_msgs/msg/PointCloud2"]),
        ]

    def get_service_names_and_types(self):
        return [("/leo05/reset", ["std_srvs/srv/Trigger"])]

    def get_node_names_and_namespaces(self):
        return [("lidar", "/leo05"), ("controller", "/")]


def test_graph_monitor_snapshot_uses_rclpy_graph_without_cli():
    monitor = GraphMonitor(AppConfig())
    monitor._node = FakeNode()

    payload = monitor.refresh()

    assert payload["available"] is True
    assert payload["source"] == "rclpy_graph_event"
    assert payload["topics"] == ["/leo05/livox/lidar", "/tf"]
    assert payload["topic_types"] == {
        "/leo05/livox/lidar": ["sensor_msgs/msg/PointCloud2"],
        "/tf": ["tf2_msgs/msg/TFMessage"],
    }
    assert payload["nodes"] == ["/controller", "/leo05/lidar"]
    assert payload["services"] == ["/leo05/reset"]
    assert payload["bandwidth"] == []
