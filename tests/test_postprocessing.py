from __future__ import annotations

from pathlib import Path

from deepsight.config import AppConfig, Mission
from deepsight.postprocessing import BagPlayback, build_bag_play_command, find_bag, start_bag_playback


def _write_bag(root: Path) -> Path:
    bag_dir = root / "rosbag2_test"
    bag_dir.mkdir()
    (bag_dir / "rosbag2_test_0.mcap").write_bytes(b"abc")
    (bag_dir / "metadata.yaml").write_text(
        """
        rosbag2_bagfile_information:
          storage_identifier: mcap
          duration:
            nanoseconds: 1000000000
          message_count: 2
          topics_with_message_count:
            - topic_metadata:
                name: /cloud
                type: sensor_msgs/msg/PointCloud2
              message_count: 2
          relative_file_paths:
            - rosbag2_test_0.mcap
        """,
        encoding="utf-8",
    )
    return bag_dir


def test_find_bag_only_returns_bags_from_configured_root(tmp_path):
    bag_dir = _write_bag(tmp_path)
    config = AppConfig(mission=Mission(bag_root=str(tmp_path)))

    assert find_bag(config, str(bag_dir))["name"] == "rosbag2_test"
    assert find_bag(config, str(tmp_path / "outside")) is None


def test_build_bag_play_command_quotes_path_and_topics():
    command = build_bag_play_command("/tmp/my bag", ["/cloud", "/tf"], 0.5, True)

    assert command == "ros2 bag play '/tmp/my bag' --rate 0.5 --loop --topics /cloud /tf"


def test_start_bag_playback_rejects_unknown_topic(tmp_path):
    bag_dir = _write_bag(tmp_path)
    config = AppConfig(mission=Mission(bag_root=str(tmp_path)))

    result = start_bag_playback(BagPlayback(), config, str(bag_dir), ["/missing"], 1.0, False)

    assert result["ok"] is False
    assert "unknown topics" in result["error"]
