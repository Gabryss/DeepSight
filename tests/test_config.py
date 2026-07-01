from __future__ import annotations

from deepsight.config import load_config


def test_load_config_reads_mission_file(tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text(
        """
        [mission]
        name = "Test Mission"
        ros_setup = "/opt/ros/jazzy/setup.bash"

        [server]
        host = "0.0.0.0"
        port = 9000

        [[robots]]
        id = "rover"
        label = "Rover"
        host = "10.0.0.2"

        [[commands]]
        id = "restart"
        label = "Restart"
        command = "ssh rover sudo systemctl restart rover.service"
        """,
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.mission.name == "Test Mission"
    assert config.server.host == "0.0.0.0"
    assert config.server.port == 9000
    assert config.robots[0].id == "rover"
    assert config.command_ids == {"restart"}
