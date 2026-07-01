from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from deepsight.bags import bag_inventory
from deepsight.config import AppConfig
from deepsight.runner import command_environment, prepare_command


@dataclass
class BagPlayback:
    process: subprocess.Popen | None = None
    bag_path: str | None = None
    topics: list[str] = field(default_factory=list)
    rate: float = 1.0
    loop: bool = False
    started_at: float | None = None
    duration_sec: float | None = None
    log_path: str | None = None

    def status(self) -> dict[str, object]:
        progress = playback_progress(self)
        if self.process is None:
            state = "stopped" if self.bag_path else "idle"
            return {
                "state": state,
                "running": False,
                "bag_path": self.bag_path,
                "topics": self.topics,
                "rate": self.rate,
                "loop": self.loop,
                "progress_percent": progress,
                "duration_sec": self.duration_sec,
                "log_tail": read_log_tail(self.log_path),
            }
        returncode = self.process.poll()
        return {
            "state": "running" if returncode is None else "exited",
            "running": returncode is None,
            "pid": self.process.pid,
            "returncode": returncode,
            "bag_path": self.bag_path,
            "topics": self.topics,
            "rate": self.rate,
            "loop": self.loop,
            "progress_percent": progress,
            "duration_sec": self.duration_sec,
            "log_tail": read_log_tail(self.log_path),
        }


def read_log_tail(log_path: str | None, max_bytes: int = 6000) -> str:
    if not log_path:
        return ""
    path = Path(log_path)
    if not path.exists():
        return ""
    with path.open("rb") as log_file:
        if path.stat().st_size > max_bytes:
            log_file.seek(-max_bytes, os.SEEK_END)
        return log_file.read().decode(errors="replace")


def playback_progress(playback: BagPlayback) -> float:
    if not playback.started_at or not playback.duration_sec:
        return 0.0
    if playback.process and playback.process.poll() is not None and not playback.loop:
        return 100.0
    played = (time.monotonic() - playback.started_at) * playback.rate
    if playback.loop:
        played %= playback.duration_sec
    return round(max(0.0, min(100.0, (played / playback.duration_sec) * 100.0)), 1)


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
        if str(Path(bag_path).expanduser().resolve()) == str(Path(str(playback.bag_path)).expanduser().resolve()):
            error = "selected bag is already playing"
        else:
            error = "another bag playback is already running"
        return {"ok": False, "error": error, "status": playback.status()}

    bag = find_bag(config, bag_path)
    if not bag:
        return {"ok": False, "error": "bag path is not under configured bag_root or has no metadata", "status": playback.status()}

    allowed_topics = {str(topic["name"]) for topic in bag.get("topics", [])}
    invalid_topics = [topic for topic in topics if topic not in allowed_topics]
    if invalid_topics:
        return {"ok": False, "error": f"unknown topics: {', '.join(invalid_topics)}", "status": playback.status()}

    safe_rate = max(0.01, min(rate, 20.0))
    command = prepare_command(build_bag_play_command(str(bag["path"]), topics, safe_rate, loop), config)
    log_dir = Path(os.environ.get("DEEPSIGHT_LOG_DIR", "/tmp/deepsight/postprocessing"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{Path(str(bag['path'])).name}-{int(time.time())}.log"
    log_file = None
    try:
        log_file = log_path.open("ab")
        process = subprocess.Popen(
            ["bash", "-lc", command],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=command_environment(config),
            start_new_session=True,
        )
    except OSError as exc:
        log_file.close()
        return {"ok": False, "error": str(exc), "status": playback.status()}
    finally:
        if log_file:
            log_file.close()
    playback.process = process
    playback.bag_path = str(bag["path"])
    playback.topics = topics
    playback.rate = safe_rate
    playback.loop = loop
    playback.started_at = time.monotonic()
    playback.duration_sec = float(bag["duration_sec"]) if bag.get("duration_sec") else None
    playback.log_path = str(log_path)
    return {"ok": True, "error": "", "status": playback.status()}


def stop_bag_playback(playback: BagPlayback) -> dict[str, object]:
    if not playback.process or playback.process.poll() is not None:
        playback.process = None
        return {"ok": True, "error": "", "status": playback.status()}

    try:
        os.killpg(playback.process.pid, signal.SIGTERM)
    except ProcessLookupError:
        playback.process = None
        return {"ok": True, "error": "", "status": playback.status()}
    try:
        playback.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(playback.process.pid, signal.SIGKILL)
        playback.process.wait(timeout=2)

    playback.process = None
    return {"ok": True, "error": "", "status": playback.status()}
