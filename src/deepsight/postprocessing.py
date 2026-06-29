from __future__ import annotations

import os
import shlex
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from deepsight.bags import bag_inventory
from deepsight.config import AppConfig
from deepsight.runner import prepare_command


@dataclass
class BagPlayback:
    process: subprocess.Popen | None = None
    bag_path: str | None = None
    topics: list[str] = field(default_factory=list)
    rate: float = 1.0
    loop: bool = False

    def status(self) -> dict[str, object]:
        if self.process is None:
            return {"running": False, "bag_path": None, "topics": [], "rate": self.rate, "loop": self.loop}
        return {
            "running": self.process.poll() is None,
            "pid": self.process.pid,
            "returncode": self.process.poll(),
            "bag_path": self.bag_path,
            "topics": self.topics,
            "rate": self.rate,
            "loop": self.loop,
        }


def find_bag(config: AppConfig, bag_path: str) -> dict[str, object] | None:
    requested = str(Path(bag_path).expanduser().resolve())
    for bag in bag_inventory(config).get("bags", []):
        if str(Path(str(bag["path"])).resolve()) == requested:
            return bag
    return None


def build_bag_play_command(bag_path: str, topics: list[str], rate: float, loop: bool) -> str:
    parts = ["ros2", "bag", "play", shlex.quote(bag_path), "--rate", shlex.quote(str(rate))]
    if loop:
        parts.append("--loop")
    if topics:
        parts.append("--topics")
        parts.extend(shlex.quote(topic) for topic in topics)
    return " ".join(parts)


def start_bag_playback(playback: BagPlayback, config: AppConfig, bag_path: str, topics: list[str], rate: float, loop: bool) -> dict[str, object]:
    if playback.process and playback.process.poll() is None:
        return {"ok": False, "error": "bag playback is already running", "status": playback.status()}

    bag = find_bag(config, bag_path)
    if not bag:
        return {"ok": False, "error": "bag path is not under configured bag_root or has no metadata", "status": playback.status()}

    allowed_topics = {str(topic["name"]) for topic in bag.get("topics", [])}
    invalid_topics = [topic for topic in topics if topic not in allowed_topics]
    if invalid_topics:
        return {"ok": False, "error": f"unknown topics: {', '.join(invalid_topics)}", "status": playback.status()}

    safe_rate = max(0.01, min(rate, 20.0))
    command = prepare_command(build_bag_play_command(str(bag["path"]), topics, safe_rate, loop), config)
    try:
        process = subprocess.Popen(
            ["bash", "-lc", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            start_new_session=True,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc), "status": playback.status()}
    playback.process = process
    playback.bag_path = str(bag["path"])
    playback.topics = topics
    playback.rate = safe_rate
    playback.loop = loop
    return {"ok": True, "error": "", "status": playback.status()}


def stop_bag_playback(playback: BagPlayback) -> dict[str, object]:
    if not playback.process or playback.process.poll() is not None:
        playback.process = None
        return {"ok": True, "error": "", "status": playback.status()}

    os.killpg(playback.process.pid, signal.SIGTERM)
    try:
        playback.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(playback.process.pid, signal.SIGKILL)
        playback.process.wait(timeout=2)

    playback.process = None
    return {"ok": True, "error": "", "status": playback.status()}
