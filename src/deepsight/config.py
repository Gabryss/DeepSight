from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class Mission(BaseModel):
    name: str = "DeepSight Mission"
    operator: str = "operator"
    ros_setup: str | None = None
    ros_domain_id: int | None = None
    poll_interval_sec: float = 2.0
    topic_discovery_interval_sec: float = 30.0
    bag_root: str | None = None


class Network(BaseModel):
    ping_timeout_sec: float = 1.0


class Server(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8766


class Robot(BaseModel):
    id: str
    label: str
    host: str
    ssh_target: str | None = None
    battery_command: str | None = None


class Command(BaseModel):
    id: str
    label: str
    command: str
    target: str | None = None
    timeout_sec: float = 10.0
    background: bool = False


class AppConfig(BaseModel):
    mission: Mission = Field(default_factory=Mission)
    server: Server = Field(default_factory=Server)
    network: Network = Field(default_factory=Network)
    robots: list[Robot] = Field(default_factory=list)
    commands: list[Command] = Field(default_factory=list)

    @property
    def command_ids(self) -> set[str]:
        return {command.id for command in self.commands}


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.environ.get("DEEPSIGHT_CONFIG", "configs/mission.example.toml"))
    if not config_path.exists():
        return AppConfig()
    with config_path.open("rb") as config_file:
        payload = tomllib.load(config_file)
    return AppConfig.model_validate(payload)
