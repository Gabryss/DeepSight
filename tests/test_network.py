from __future__ import annotations

from deepsight import network
from deepsight.config import AppConfig, Robot
from deepsight.runner import CommandResult


def test_ping_robot_extracts_latency_from_time_field(monkeypatch):
    def fake_run_shell_command(command, timeout_sec, config):
        return CommandResult(
            ok=True,
            command=command,
            returncode=0,
            stdout="64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=12.7 ms",
            stderr="",
        )

    monkeypatch.setattr(network, "run_shell_command", fake_run_shell_command)

    result = network.ping_robot(Robot(id="robot", label="Robot", host="127.0.0.1"), AppConfig())

    assert result["latency_ms"] == 12.7


def test_ping_robot_handles_less_than_latency(monkeypatch):
    def fake_run_shell_command(command, timeout_sec, config):
        return CommandResult(
            ok=True,
            command=command,
            returncode=0,
            stdout="64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time<1 ms",
            stderr="",
        )

    monkeypatch.setattr(network, "run_shell_command", fake_run_shell_command)

    result = network.ping_robot(Robot(id="robot", label="Robot", host="127.0.0.1"), AppConfig())

    assert result["latency_ms"] == 1.0
