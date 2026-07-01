from __future__ import annotations

from pathlib import Path

from deepsight.config import AppConfig, Mission
from deepsight import postprocessing
from deepsight.postprocessing import BagPlayback, build_bag_play_command, find_bag, read_log_tail, start_bag_playback, stop_bag_playback


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


class FakeProcess:
    pid = 1234

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


def test_start_bag_playback_tracks_state_and_rejects_duplicate(monkeypatch, tmp_path):
    bag_dir = _write_bag(tmp_path)
    config = AppConfig(mission=Mission(bag_root=str(tmp_path), ros_setup="/opt/ros/jazzy/setup.bash"))
    playback = BagPlayback()

    monkeypatch.setattr(postprocessing.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(postprocessing.time, "monotonic", lambda: 10.0)

    result = start_bag_playback(playback, config, str(bag_dir), ["/cloud"], 2.0, False)

    assert result["ok"] is True
    assert result["status"]["running"] is True
    assert result["status"]["state"] == "running"
    assert result["status"]["progress_percent"] == 0.0

    duplicate = start_bag_playback(playback, config, str(bag_dir), ["/cloud"], 2.0, False)

    assert duplicate["ok"] is False
    assert duplicate["error"] == "selected bag is already playing"


def test_playback_progress_and_log_tail(monkeypatch, tmp_path):
    log_path = tmp_path / "playback.log"
    log_path.write_text("line 1\nline 2\n", encoding="utf-8")
    playback = BagPlayback(
        process=FakeProcess(),
        bag_path="/tmp/bag",
        started_at=10.0,
        duration_sec=20.0,
        rate=2.0,
        log_path=str(log_path),
    )
    monkeypatch.setattr(postprocessing.time, "monotonic", lambda: 15.0)

    status = playback.status()

    assert status["progress_percent"] == 50.0
    assert read_log_tail(str(log_path)) == "line 1\nline 2\n"


def test_stopped_playback_progress_stays_frozen(monkeypatch):
    playback = BagPlayback(
        process=FakeProcess(),
        bag_path="/tmp/bag",
        started_at=10.0,
        duration_sec=100.0,
        rate=1.0,
    )
    monkeypatch.setattr(postprocessing.time, "monotonic", lambda: 30.0)

    stopped = stop_bag_playback(playback)

    assert stopped["status"]["progress_percent"] == 20.0
    monkeypatch.setattr(postprocessing.time, "monotonic", lambda: 80.0)
    assert playback.status()["progress_percent"] == 20.0
