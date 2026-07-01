from __future__ import annotations

import re

from deepsight.config import AppConfig
from deepsight.runner import CommandResult, command_available, run_shell_command


def _lines(result: CommandResult) -> list[str]:
    if not result.ok or not result.stdout:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _tf_frames(topic_names: list[str], config: AppConfig) -> list[str]:
    frames: set[str] = set()
    for topic in ("/tf_static", "/tf"):
        if topic not in topic_names:
            continue
        result = run_shell_command(f"timeout 2 ros2 topic echo --once {topic}", 3, config)
        if not result.ok or not result.stdout:
            continue
        for key in ("frame_id", "child_frame_id"):
            for match in re.finditer(rf"{key}:\s*['\"]?([^'\"\n]+)", result.stdout):
                frame = match.group(1).strip()
                if frame:
                    frames.add(frame)
    return sorted(frames)


def ros_snapshot(config: AppConfig) -> dict[str, object]:
    if not command_available("ros2", config):
        return {
            "available": False,
            "topics": [],
            "nodes": [],
            "services": [],
            "tf_tree": "",
            "tf_frames": [],
            "bandwidth": [],
            "error": "ros2 command not found",
        }

    topics = run_shell_command("ros2 topic list", 3, config)
    nodes = run_shell_command("ros2 node list", 3, config)
    services = run_shell_command("ros2 service list", 3, config)

    topic_names = _lines(topics)
    tf_topics = [topic for topic in topic_names if topic in {"/tf", "/tf_static"}]
    tf_frames = _tf_frames(topic_names, config)
    bandwidth = []
    for topic in topic_names[:8]:
        result = run_shell_command(f"timeout 2 ros2 topic bw {topic}", 3, config)
        bandwidth.append(
            {
                "topic": topic,
                "ok": result.ok,
                "sample": result.stdout.splitlines()[-1] if result.stdout else "",
                "error": result.stderr,
            }
        )

    return {
        "available": True,
        "topics": topic_names,
        "nodes": _lines(nodes),
        "services": _lines(services),
        "tf_tree": "TF topics active: " + ", ".join(tf_topics) if tf_topics else "No /tf or /tf_static topics detected",
        "tf_frames": tf_frames,
        "bandwidth": bandwidth,
    }
