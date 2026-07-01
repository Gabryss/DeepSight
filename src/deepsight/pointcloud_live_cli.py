from __future__ import annotations

import json
import struct
import sys
import time

from deepsight.pointcloud import pointcloud2_to_points


def encode_frame(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return struct.pack(">I", len(body)) + body


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: python -m deepsight.pointcloud_live_cli TOPIC MAX_POINTS RATE_HZ", file=sys.stderr)
        return 2

    topic = sys.argv[1]
    max_points = int(sys.argv[2])
    rate_hz = max(0.2, min(float(sys.argv[3]), 20.0))
    min_interval = 1.0 / rate_hz
    last_sent = 0.0

    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import PointCloud2
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": f"ROS live PointCloud2 bindings unavailable: {exc}"}), flush=True)
        return 1

    rclpy.init()
    node = rclpy.create_node("deepsight_pointcloud_stream")

    def callback(message: PointCloud2) -> None:
        nonlocal last_sent
        now = time.monotonic()
        if now - last_sent < min_interval:
            return
        last_sent = now
        points = pointcloud2_to_points(message, max_points)
        stamp = getattr(message.header, "stamp", None)
        timestamp = None
        if stamp is not None:
            timestamp = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        sys.stdout.buffer.write(
            encode_frame(
                {
                    "ok": True,
                    "topic": topic,
                    "timestamp": timestamp,
                    "point_count": len(points),
                    "points": points,
                }
            )
        )
        sys.stdout.buffer.flush()

    node.create_subscription(PointCloud2, topic, callback, qos_profile_sensor_data)
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
