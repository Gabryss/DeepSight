from __future__ import annotations

from deepsight.config import AppConfig
from deepsight.runner import CommandResult, command_available, run_shell_command


def _lines(result: CommandResult) -> list[str]:
    if not result.ok or not result.stdout:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def ros_snapshot(config: AppConfig) -> dict[str, object]:
    if not command_available("ros2"):
        return {
            "available": False,
            "topics": [],
            "nodes": [],
            "services": [],
            "tf_tree": "",
            "bandwidth": [],
            "error": "ros2 command not found",
        }

    topics = run_shell_command("ros2 topic list", 3, config)
    nodes = run_shell_command("ros2 node list", 3, config)
    services = run_shell_command("ros2 service list", 3, config)
    tf_tree = run_shell_command("ros2 run tf2_tools view_frames --ros-args --log-level fatal", 5, config)

    topic_names = _lines(topics)
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
        "tf_tree": tf_tree.stdout or tf_tree.stderr,
        "bandwidth": bandwidth,
    }
