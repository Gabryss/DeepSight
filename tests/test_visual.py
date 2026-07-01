from __future__ import annotations

from deepsight import visual
from deepsight.config import AppConfig, Mission
from deepsight.runner import CommandResult


def test_parse_ros_topic_types_classifies_visual_topics():
    payload = visual._parse_ros_topic_types(
        """
        /cloud [sensor_msgs/msg/PointCloud2]
        /front/image_raw [sensor_msgs/msg/Image]
        /front/image/compressed [sensor_msgs/msg/CompressedImage]
        /scan [sensor_msgs/msg/LaserScan]
        """
    )

    assert [topic.name for topic in payload] == ["/cloud", "/front/image_raw", "/front/image/compressed", "/scan"]
    assert payload[0].type == "sensor_msgs/msg/PointCloud2"


def test_visual_topics_merges_live_and_bag_topics(monkeypatch, tmp_path):
    bag_dir = tmp_path / "bag"
    bag_dir.mkdir()
    (bag_dir / "bag_0.mcap").write_bytes(b"abc")
    (bag_dir / "metadata.yaml").write_text(
        """
        rosbag2_bagfile_information:
          storage_identifier: mcap
          duration:
            nanoseconds: 1000000000
          message_count: 4
          topics_with_message_count:
            - topic_metadata:
                name: /leo05/bag_cloud
                type: sensor_msgs/msg/PointCloud2
              message_count: 1
            - topic_metadata:
                name: /leo05/bag_camera
                type: sensor_msgs/msg/CompressedImage
              message_count: 1
            - topic_metadata:
                name: /leo05/camera_info
                type: sensor_msgs/msg/CameraInfo
              message_count: 1
          relative_file_paths:
            - bag_0.mcap
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(visual, "command_available", lambda command, config: True)
    monkeypatch.setattr(
        visual,
        "run_shell_command",
        lambda command, timeout, config: CommandResult(
            True,
            command,
            0,
            "/base/live_cloud [sensor_msgs/msg/PointCloud2]\n/base/live_camera [sensor_msgs/msg/Image]\n/base/map [nav_msgs/msg/OccupancyGrid]",
            "",
        ),
    )

    payload = visual.visual_topics(AppConfig(mission=Mission(bag_root=str(tmp_path))))

    assert {topic["name"] for topic in payload["point_cloud"]} == {"/base/live_cloud", "/leo05/bag_cloud"}
    assert {topic["name"] for topic in payload["camera"]} == {"/base/live_camera", "/leo05/bag_camera"}
    assert payload["camera_info"][0]["name"] == "/leo05/camera_info"
    assert payload["costmap"][0]["name"] == "/base/map"
    assert payload["entities"] == ["base", "leo05"]
    assert payload["available"] is True


def test_visible_entities_ignore_global_ros_topics():
    topics = [
        "/tf",
        "/tf_static",
        "/tf_statics",
        "/rosout",
        "/rousout",
        "/parameter_events",
        "/clock",
        "/leo05/livox/lidar",
        "/leo05/battery_state",
        "/base_station/status",
    ]

    assert visual.visible_entities_from_topics(topics) == ["base_station", "leo05"]
    assert visual.entity_from_topic("/tf_static") == ""
