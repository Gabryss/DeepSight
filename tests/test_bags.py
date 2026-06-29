from __future__ import annotations

from deepsight.bags import bag_inventory
from deepsight.config import AppConfig, Mission


def test_bag_inventory_reads_rosbag_metadata(tmp_path):
    bag_dir = tmp_path / "rosbag2_test"
    bag_dir.mkdir()
    (bag_dir / "rosbag2_test_0.mcap").write_bytes(b"abc")
    (bag_dir / "metadata.yaml").write_text(
        """
        rosbag2_bagfile_information:
          storage_identifier: mcap
          duration:
            nanoseconds: 2500000000
          message_count: 12
          topics_with_message_count:
            - topic_metadata:
                name: /cloud
                type: sensor_msgs/msg/PointCloud2
              message_count: 7
          relative_file_paths:
            - rosbag2_test_0.mcap
          ros_distro: jazzy
        """,
        encoding="utf-8",
    )
    config = AppConfig(mission=Mission(bag_root=str(tmp_path)))

    payload = bag_inventory(config)

    assert payload["available"] is True
    assert payload["bags"][0]["name"] == "rosbag2_test"
    assert payload["bags"][0]["duration_sec"] == 2.5
    assert payload["bags"][0]["message_count"] == 12
    assert payload["bags"][0]["topics"][0]["name"] == "/cloud"
    assert payload["bags"][0]["capabilities"]["available"]["point_cloud"] is True
    assert "camera" in payload["bags"][0]["capabilities"]["missing_for_full_monitoring"]
    assert payload["bags"][0]["size_bytes"] == 3


def test_bag_inventory_reports_missing_root(tmp_path):
    config = AppConfig(mission=Mission(bag_root=str(tmp_path / "missing")))

    payload = bag_inventory(config)

    assert payload["available"] is False
    assert payload["bags"] == []
