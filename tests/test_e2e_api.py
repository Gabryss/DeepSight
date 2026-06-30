from __future__ import annotations

from deepsight import postprocessing
from deepsight.bags import bag_inventory
from deepsight.config import AppConfig, Mission
from deepsight.postprocessing import BagPlayback, start_bag_playback, stop_bag_playback


class FakeProcess:
    pid = 4321

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


def write_bag(root, name="rosbag2_test"):
    bag_dir = root / name
    bag_dir.mkdir()
    (bag_dir / f"{name}_0.mcap").write_bytes(b"abc")
    (bag_dir / "metadata.yaml").write_text(
        f"""
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
            - {name}_0.mcap
        """,
        encoding="utf-8",
    )
    return bag_dir


def test_post_processing_service_flow_prevents_parallel_bag_playback(monkeypatch, tmp_path):
    bag_dir = write_bag(tmp_path)
    other_bag_dir = write_bag(tmp_path, "rosbag2_other")
    config = AppConfig(mission=Mission(bag_root=str(tmp_path), ros_setup="/opt/ros/jazzy/setup.bash"))
    playback = BagPlayback()
    killed = []
    monkeypatch.setenv("DEEPSIGHT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(postprocessing.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(postprocessing.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    bags = bag_inventory(config)
    assert bags["available"] is True
    assert str(bag_dir) in {bag["path"] for bag in bags["bags"]}

    first = start_bag_playback(playback, config, str(bag_dir), ["/cloud"], 1.0, False)
    assert first["ok"] is True
    assert first["status"]["state"] == "running"

    second = start_bag_playback(playback, config, str(bag_dir), ["/cloud"], 1.0, False)
    assert second["ok"] is False
    assert second["error"] == "selected bag is already playing"

    other = start_bag_playback(playback, config, str(other_bag_dir), ["/cloud"], 1.0, False)
    assert other["ok"] is False
    assert other["error"] == "another bag playback is already running"

    status = playback.status()
    assert status["running"] is True
    assert status["bag_path"] == str(bag_dir)
    assert status["progress_percent"] >= 0.0

    stopped = stop_bag_playback(playback)
    assert stopped["ok"] is True
    assert stopped["status"]["state"] == "stopped"
    assert killed
