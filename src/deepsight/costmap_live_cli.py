from __future__ import annotations

import json
import struct
import sys
import time


def encode_frame(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return struct.pack(">I", len(body)) + body


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m deepsight.costmap_live_cli TOPIC RATE_HZ", file=sys.stderr)
        return 2

    topic = sys.argv[1]
    rate_hz = max(0.2, min(float(sys.argv[2]), 10.0))
    min_interval = 1.0 / rate_hz
    last_sent = 0.0

    try:
        import rclpy
        from nav_msgs.msg import OccupancyGrid
        from rclpy.executors import ExternalShutdownException
        from rclpy.qos import qos_profile_sensor_data
    except ImportError as exc:
        sys.stdout.buffer.write(encode_frame({"ok": False, "error": f"ROS live costmap bindings unavailable: {exc}"}))
        sys.stdout.buffer.flush()
        return 1

    rclpy.init()
    node = rclpy.create_node("deepsight_costmap_stream")

    def callback(message: OccupancyGrid) -> None:
        nonlocal last_sent
        now = time.monotonic()
        if now - last_sent < min_interval:
            return
        last_sent = now

        stamp = getattr(message.header, "stamp", None)
        timestamp = None
        if stamp is not None:
            timestamp = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        origin = getattr(message.info, "origin", None)
        position = getattr(origin, "position", None)
        orientation = getattr(origin, "orientation", None)
        sys.stdout.buffer.write(
            encode_frame(
                {
                    "ok": True,
                    "topic": topic,
                    "timestamp": timestamp,
                    "width": int(message.info.width),
                    "height": int(message.info.height),
                    "resolution": float(message.info.resolution),
                    "origin": {
                        "x": float(getattr(position, "x", 0.0)),
                        "y": float(getattr(position, "y", 0.0)),
                        "z": float(getattr(position, "z", 0.0)),
                        "qx": float(getattr(orientation, "x", 0.0)),
                        "qy": float(getattr(orientation, "y", 0.0)),
                        "qz": float(getattr(orientation, "z", 0.0)),
                        "qw": float(getattr(orientation, "w", 1.0)),
                    },
                    "data": list(message.data),
                }
            )
        )
        sys.stdout.buffer.flush()

    node.create_subscription(OccupancyGrid, topic, callback, qos_profile_sensor_data)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
