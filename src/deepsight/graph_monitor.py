from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from deepsight.config import AppConfig


def _tf_tree(topics: list[str]) -> str:
    tf_topics = [topic for topic in topics if topic in {"/tf", "/tf_static"}]
    return "TF topics active: " + ", ".join(tf_topics) if tf_topics else "No /tf or /tf_static topics detected"


def _empty_snapshot(available: bool = False, error: str = "") -> dict[str, object]:
    return {
        "available": available,
        "topics": [],
        "topic_types": {},
        "nodes": [],
        "services": [],
        "tf_tree": "",
        "tf_frames": [],
        "bandwidth": [],
        "source": "rclpy_graph_event",
        "updated_at": time.time(),
        "error": error,
    }


@dataclass
class GraphMonitor:
    config: AppConfig
    debounce_sec: float = 1.0
    reconcile_sec: float = 90.0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _snapshot: dict[str, object] = field(default_factory=lambda: _empty_snapshot(False, "not started"), init=False)
    _rclpy: Any = field(default=None, init=False)
    _node: Any = field(default=None, init=False)
    _started: bool = field(default=False, init=False)
    _available: bool = field(default=False, init=False)

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop.clear()
        try:
            import rclpy  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on ROS installation
            self._snapshot = _empty_snapshot(False, f"rclpy unavailable: {exc}")
            self._started = False
            return

        self._rclpy = rclpy
        try:
            if self.config.mission.ros_domain_id is not None:
                os.environ["ROS_DOMAIN_ID"] = str(self.config.mission.ros_domain_id)
            else:
                os.environ.pop("ROS_DOMAIN_ID", None)
            if not rclpy.ok():
                rclpy.init(args=None)
            self._node = rclpy.create_node("deepsight_graph_monitor")
            self._available = True
            self.refresh()
            self._thread = threading.Thread(target=self._run, name="deepsight-graph-monitor", daemon=True)
            self._thread.start()
        except Exception as exc:  # pragma: no cover - depends on ROS runtime
            self._available = False
            self._snapshot = _empty_snapshot(False, f"rclpy graph monitor failed: {exc}")
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._node is not None:
            try:
                self._node.destroy_node()
            except Exception:
                pass
        self._node = None
        self._available = False
        self._started = False
        if self._rclpy is not None:
            try:
                if self._rclpy.ok():
                    self._rclpy.shutdown()
            except Exception:
                pass

    def refresh(self) -> dict[str, object]:
        if self._node is None:
            return self.snapshot()
        try:
            topic_pairs = self._node.get_topic_names_and_types()
            service_pairs = self._node.get_service_names_and_types()
            node_pairs = self._node.get_node_names_and_namespaces()
            topic_types = {name: list(types) for name, types in topic_pairs}
            topics = sorted(topic_types)
            nodes = sorted(
                f"{namespace.rstrip('/')}/{name}".replace("//", "/")
                for name, namespace in node_pairs
            )
            services = sorted(name for name, _types in service_pairs)
            payload = {
                "available": True,
                "topics": topics,
                "topic_types": topic_types,
                "nodes": nodes,
                "services": services,
                "tf_tree": _tf_tree(topics),
                "tf_frames": [],
                "bandwidth": [],
                "source": "rclpy_graph_event",
                "updated_at": time.time(),
                "error": "",
            }
        except Exception as exc:  # pragma: no cover - depends on ROS runtime
            payload = _empty_snapshot(False, f"rclpy graph snapshot failed: {exc}")

        with self._lock:
            self._snapshot = payload
        return payload

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return dict(self._snapshot)

    def _run(self) -> None:
        next_reconcile = time.monotonic() + self.reconcile_sec
        while not self._stop.is_set() and self._node is not None:
            changed = self._wait_for_graph_change(timeout_sec=1.0)
            now = time.monotonic()
            if changed:
                self._stop.wait(self.debounce_sec)
                self.refresh()
                next_reconcile = time.monotonic() + self.reconcile_sec
            elif now >= next_reconcile:
                self.refresh()
                next_reconcile = now + self.reconcile_sec

    def _wait_for_graph_change(self, timeout_sec: float) -> bool:
        if self._node is None:
            return False
        try:
            event = self._node.get_graph_event()
            return bool(self._node.wait_for_graph_change(event, timeout_sec=timeout_sec))
        except TypeError:  # pragma: no cover - older rclpy signatures vary
            try:
                event = self._node.get_graph_event()
                return bool(self._node.wait_for_graph_change(event, timeout_sec))
            except Exception:
                time.sleep(timeout_sec)
                return False
        except Exception:  # pragma: no cover - depends on ROS runtime
            time.sleep(timeout_sec)
            return False
