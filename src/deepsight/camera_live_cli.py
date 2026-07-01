from __future__ import annotations

import base64
import json
import struct
import sys
import time


def encode_frame(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return struct.pack(">I", len(body)) + body


def _stamp_ns(message: object) -> int | None:
    header = getattr(message, "header", None)
    stamp = getattr(header, "stamp", None)
    if stamp is None:
        return None
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def _compressed_mime(format_text: str) -> str:
    lower = format_text.lower()
    if "png" in lower:
        return "image/png"
    if "webp" in lower:
        return "image/webp"
    return "image/jpeg"


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: python -m deepsight.camera_live_cli TOPIC TYPE RATE_HZ", file=sys.stderr)
        return 2

    topic = sys.argv[1]
    topic_type = sys.argv[2]
    rate_hz = max(0.2, min(float(sys.argv[3]), 30.0))
    min_interval = 1.0 / rate_hz
    last_sent = 0.0

    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.qos import qos_profile_sensor_data
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        sys.stdout.buffer.write(encode_frame({"ok": False, "error": f"ROS live camera bindings unavailable: {exc}"}))
        sys.stdout.buffer.flush()
        return 1

    try:
        message_type = get_message(topic_type)
    except (AttributeError, ModuleNotFoundError, ValueError) as exc:
        sys.stdout.buffer.write(encode_frame({"ok": False, "error": f"unsupported camera topic type {topic_type}: {exc}"}))
        sys.stdout.buffer.flush()
        return 1

    rclpy.init()
    node = rclpy.create_node("deepsight_camera_stream")

    def callback(message: object) -> None:
        nonlocal last_sent
        now = time.monotonic()
        if now - last_sent < min_interval:
            return
        last_sent = now

        if topic_type == "sensor_msgs/msg/CompressedImage":
            format_text = str(getattr(message, "format", "jpeg") or "jpeg")
            payload = {
                "ok": True,
                "topic": topic,
                "topic_type": topic_type,
                "timestamp": _stamp_ns(message),
                "frame_type": "compressed",
                "mime": _compressed_mime(format_text),
                "format": format_text,
                "data": base64.b64encode(bytes(getattr(message, "data", b""))).decode("ascii"),
            }
        else:
            payload = {
                "ok": True,
                "topic": topic,
                "topic_type": topic_type,
                "timestamp": _stamp_ns(message),
                "frame_type": "raw",
                "width": int(getattr(message, "width", 0) or 0),
                "height": int(getattr(message, "height", 0) or 0),
                "encoding": str(getattr(message, "encoding", "") or ""),
                "step": int(getattr(message, "step", 0) or 0),
                "data": base64.b64encode(bytes(getattr(message, "data", b""))).decode("ascii"),
            }
        sys.stdout.buffer.write(encode_frame(payload))
        sys.stdout.buffer.flush()

    node.create_subscription(message_type, topic, callback, qos_profile_sensor_data)
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
