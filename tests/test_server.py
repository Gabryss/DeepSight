from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from deepsight import server
from deepsight.runner import CommandResult


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_mission_snapshot_returns_status(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text(
        """
        [mission]
        name = "API Test"

        [[robots]]
        id = "rover"
        label = "Rover"
        host = "127.0.0.1"

        [[commands]]
        id = "noop"
        label = "No-op"
        command = "true"
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))
    monkeypatch.setattr(server, "robot_connectivity", lambda config: [{"id": "rover", "online": True}])
    monkeypatch.setattr(server, "robot_batteries", lambda config: [])
    monkeypatch.setattr(
        server,
        "ros_snapshot",
        lambda config: {"available": True, "topics": ["/tf", "/leo05/livox/lidar"], "nodes": [], "bandwidth": []},
    )

    app = server.create_app()
    payload = server._mission_snapshot(app.state.config, "dds")

    assert payload["mission"]["name"] == "API Test"
    assert payload["robots"][0]["online"] is True
    assert payload["visible_entities"] == ["leo05"]
    assert payload["commands"][0]["id"] == "noop"


def test_cached_mission_snapshot_reuses_recent_payload(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text("[mission]\nname = \"API Test\"\npoll_interval_sec = 5\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))
    calls = []

    def fake_snapshot(config, mode, ros_payload=None):
        calls.append((mode, ros_payload))
        return {"mode": mode, "ros": ros_payload, "count": len(calls)}

    monkeypatch.setattr(server, "_mission_snapshot", fake_snapshot)
    app = server.create_app()

    first = server._cached_mission_snapshot(app, app.state.config)
    second = server._cached_mission_snapshot(app, app.state.config)

    assert first == second
    assert len(calls) == 1


def test_ros_snapshot_cache_uses_topic_discovery_interval(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text(
        "[mission]\nname = \"API Test\"\ntopic_discovery_interval_sec = 30\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))
    calls = []

    def fake_ros_snapshot(config):
        calls.append(config.mission.name)
        return {"available": True, "topics": [f"/topic_{len(calls)}"], "nodes": [], "bandwidth": []}

    monkeypatch.setattr(server, "ros_snapshot", fake_ros_snapshot)
    app = server.create_app()

    first = server._cached_ros_snapshot(app, app.state.config)
    second = server._cached_ros_snapshot(app, app.state.config)
    refreshed = server._cached_ros_snapshot(app, app.state.config, force=True)

    assert first == second
    assert refreshed["topics"] == ["/topic_2"]
    assert len(calls) == 2


def test_visual_topics_cache_uses_topic_discovery_interval(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text(
        "[mission]\nname = \"API Test\"\ntopic_discovery_interval_sec = 60\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))
    calls = []

    def fake_visual_topics(config):
        calls.append(config.mission.name)
        return {"point_cloud": [{"name": f"/cloud_{len(calls)}"}], "available": True}

    monkeypatch.setattr(server, "visual_topics", fake_visual_topics)
    app = server.create_app()

    first = server._cached_visual_topics(app, app.state.config)
    second = server._cached_visual_topics(app, app.state.config)
    refreshed = server._cached_visual_topics(app, app.state.config, force=True)

    assert first == second
    assert first["next_refresh_sec"] == 60
    assert refreshed["point_cloud"][0]["name"] == "/cloud_2"
    assert len(calls) == 2


def test_invalidate_snapshot_cache_clears_cached_payload(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text("[mission]\nname = \"API Test\"\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))
    app = server.create_app()
    app.state.snapshot_cache = {"cached": True}
    app.state.snapshot_cached_at = 10.0

    server._invalidate_snapshot_cache(app)

    assert app.state.snapshot_cache is None
    assert app.state.snapshot_cached_at == 0.0


@pytest.mark.anyio
async def test_config_endpoint_returns_public_config(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text(
        """
        [mission]
        name = "API Test"

        [[commands]]
        id = "noop"
        label = "No-op"
        command = "true"
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))

    transport = ASGITransport(app=server.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mission"]["name"] == "API Test"
    assert payload["server"]["host"] == "127.0.0.1"
    assert payload["server"]["port"] == 8766
    assert payload["commands"][0]["id"] == "noop"
    assert "command" not in payload["commands"][0]


@pytest.mark.anyio
async def test_command_endpoint_rejects_unknown_id(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text("[mission]\nname = \"API Test\"\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))

    transport = ASGITransport(app=server.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/commands/run", json={"command_id": "missing"})

    assert response.status_code == 404


@pytest.mark.anyio
async def test_ros_domain_endpoint_updates_config_and_restarts_daemon(monkeypatch, tmp_path):
    config_path = tmp_path / "mission.toml"
    config_path.write_text("[mission]\nname = \"API Test\"\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSIGHT_CONFIG", str(config_path))
    calls = []

    async def fake_run_shell_command_async(command, timeout_sec, config):
        calls.append((command, timeout_sec, config.mission.ros_domain_id))
        return CommandResult(True, command, 0, "", "")

    monkeypatch.setattr(server, "run_shell_command_async", fake_run_shell_command_async)

    app = server.create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/ros-domain", json={"domain_id": 23})

    assert response.status_code == 200
    assert response.json()["ros_domain_id"] == 23
    assert app.state.config.mission.ros_domain_id == 23
    assert calls == [
        ("ros2 daemon stop", 8, 23),
        ("ros2 daemon start", 8, 23),
    ]
