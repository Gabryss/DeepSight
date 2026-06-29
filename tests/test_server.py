from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from deepsight import server


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
    monkeypatch.setattr(server, "ros_snapshot", lambda config: {"available": False, "topics": [], "nodes": [], "bandwidth": []})

    app = server.create_app()
    payload = server._mission_snapshot(app.state.config, "dds")

    assert payload["mission"]["name"] == "API Test"
    assert payload["robots"][0]["online"] is True
    assert payload["commands"][0]["id"] == "noop"


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
