from __future__ import annotations

import asyncio
import struct
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from deepsight.bags import bag_inventory
from deepsight.config import AppConfig, load_config
from deepsight.graph_monitor import GraphMonitor
from deepsight.network import robot_batteries, robot_connectivity
from deepsight.pointcloud import pointcloud_sample, ros_python_module_command
from deepsight.postprocessing import BagPlayback, start_bag_playback, stop_bag_playback
from deepsight.ros import ros_snapshot
from deepsight.runner import command_available, find_command, run_shell_command_async, start_background_command_async
from deepsight.tools import MISSION_TOOLS, mission_tools_payload
from deepsight.visual import graph_visual_topics, visible_entities_from_topics, visual_topics


class CommandRequest(BaseModel):
    command_id: str


class MiddlewareRequest(BaseModel):
    mode: str


class RosDomainRequest(BaseModel):
    domain_id: int | None = Field(default=None, ge=0, le=232)


class BagPlaybackRequest(BaseModel):
    bag_path: str
    topics: list[str] = Field(default_factory=list)
    rate: float = 1.0
    loop: bool = False


class PointCloudSampleRequest(BaseModel):
    bag_path: str
    topic: str
    max_points: int = Field(default=50_000, ge=100, le=200_000)


async def _forward_length_prefixed_json(websocket: WebSocket, process: asyncio.subprocess.Process, stream_name: str) -> None:
    try:
        if process.stdout is None:
            await websocket.send_json({"ok": False, "error": f"{stream_name} stdout unavailable"})
            return
        while True:
            header = await process.stdout.readexactly(4)
            frame_size = struct.unpack(">I", header)[0]
            if frame_size <= 0 or frame_size > 64_000_000:
                await websocket.send_json({"ok": False, "error": f"invalid {stream_name} frame size: {frame_size}"})
                return
            payload = await process.stdout.readexactly(frame_size)
            await websocket.send_text(payload.decode(errors="replace"))
    except asyncio.IncompleteReadError:
        stderr = ""
        if process.stderr is not None:
            stderr = (await process.stderr.read()).decode(errors="replace").strip()
        try:
            await websocket.send_json({"ok": False, "error": stderr or f"{stream_name} stopped"})
        except RuntimeError:
            return
    except WebSocketDisconnect:
        return
    except ValueError as exc:
        try:
            await websocket.send_json({"ok": False, "error": str(exc)})
        except RuntimeError:
            return
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


def _tool_status(config: AppConfig) -> list[dict[str, object]]:
    status = []
    for category, tools in MISSION_TOOLS.items():
        status.append(
            {
                "category": category,
                "tools": [
                    {
                        "name": tool.name,
                        "command": tool.command,
                        "required": tool.required,
                        "available": command_available(tool.command, config),
                    }
                    for tool in tools
                ],
            }
        )
    return status


def _ros_activity_payload(app: FastAPI) -> dict[str, object]:
    return dict(getattr(app.state, "ros_activity", {"state": "idle", "detail": "ready", "updated_at": time.time()}))


def _set_ros_activity(app: FastAPI, state: str, detail: str) -> None:
    app.state.ros_activity = {"state": state, "detail": detail, "updated_at": time.time()}


def _mission_snapshot(
    config: AppConfig,
    middleware_mode: str,
    ros_payload: dict[str, object] | None = None,
    ros_activity: dict[str, object] | None = None,
) -> dict[str, object]:
    ros_data = ros_payload if ros_payload is not None else ros_snapshot(config)
    visible_entities = visible_entities_from_topics(ros_data.get("topics", []))
    return {
        "mission": config.mission.model_dump(),
        "middleware_mode": middleware_mode,
        "tools": _tool_status(config),
        "robots": robot_connectivity(config),
        "visible_entities": visible_entities,
        "batteries": robot_batteries(config),
        "ros": ros_data,
        "ros_activity": ros_activity or {"state": "idle", "detail": "ready", "updated_at": time.time()},
        "commands": [command.model_dump(exclude={"command"}) for command in config.commands],
    }


def _topic_discovery_ttl(config: AppConfig) -> float:
    return max(5.0, config.mission.topic_discovery_interval_sec)


def _cached_ros_snapshot(app: FastAPI, config: AppConfig, force: bool = False) -> dict[str, object]:
    graph_monitor = getattr(app.state, "graph_monitor", None)
    if graph_monitor is not None and graph_monitor.available:
        if force:
            _set_ros_activity(app, "updating", "refreshing ROS graph event cache")
            payload = graph_monitor.refresh()
        else:
            payload = graph_monitor.snapshot()
        app.state.ros_cache = payload
        app.state.ros_cached_at = time.monotonic()
        _set_ros_activity(app, "idle" if payload.get("available") else "missing", "ROS graph event cache ready" if payload.get("available") else str(payload.get("error") or "ros unavailable"))
        return payload

    now = time.monotonic()
    cached_at = getattr(app.state, "ros_cached_at", 0.0)
    cached_payload = getattr(app.state, "ros_cache", None)
    if not force and cached_payload is not None and now - cached_at < _topic_discovery_ttl(config):
        return cached_payload

    _set_ros_activity(app, "updating", "refreshing ROS graph")
    payload = ros_snapshot(config)
    app.state.ros_cache = payload
    app.state.ros_cached_at = now
    _set_ros_activity(app, "idle" if payload.get("available") else "missing", "ROS graph refreshed" if payload.get("available") else str(payload.get("error") or "ros unavailable"))
    return payload


def _cached_visual_topics(app: FastAPI, config: AppConfig, force: bool = False) -> dict[str, object]:
    now = time.monotonic()
    cached_at = getattr(app.state, "visual_topics_cached_at", 0.0)
    cached_payload = getattr(app.state, "visual_topics_cache", None)
    if not force and cached_payload is not None and now - cached_at < _topic_discovery_ttl(config):
        return cached_payload

    _set_ros_activity(app, "updating", "refreshing visual topics")
    ros_payload = _cached_ros_snapshot(app, config, force=force)
    live_topics = None
    if ros_payload.get("topic_types"):
        live_topics = graph_visual_topics(ros_payload.get("topic_types", {}))  # type: ignore[arg-type]
    payload = visual_topics(config, live_topics=live_topics)
    payload["next_refresh_sec"] = _topic_discovery_ttl(config)
    app.state.visual_topics_cache = payload
    app.state.visual_topics_cached_at = now
    _set_ros_activity(app, "idle", "visual topics refreshed")
    return payload


def _cached_mission_snapshot(app: FastAPI, config: AppConfig) -> dict[str, object]:
    now = time.monotonic()
    cached_at = getattr(app.state, "snapshot_cached_at", 0.0)
    cached_payload = getattr(app.state, "snapshot_cache", None)
    ttl = max(0.5, config.mission.poll_interval_sec)
    if cached_payload is not None and now - cached_at < ttl:
        return cached_payload

    ros_payload = _cached_ros_snapshot(app, config)
    payload = _mission_snapshot(config, app.state.middleware_mode, ros_payload, _ros_activity_payload(app))
    app.state.snapshot_cache = payload
    app.state.snapshot_cached_at = now
    return payload


def _invalidate_snapshot_cache(app: FastAPI) -> None:
    app.state.snapshot_cache = None
    app.state.snapshot_cached_at = 0.0
    app.state.ros_cache = None
    app.state.ros_cached_at = 0.0
    app.state.visual_topics_cache = None
    app.state.visual_topics_cached_at = 0.0


async def _restart_ros_runtime(app: FastAPI, config: AppConfig) -> dict[str, object]:
    playback_status = app.state.bag_playback.status()
    restart_playback = bool(playback_status.get("running") and playback_status.get("bag_path"))
    bag_path = str(playback_status.get("bag_path") or "")
    topics = list(playback_status.get("topics") or [])
    rate = float(playback_status.get("rate") or 1.0)
    loop = bool(playback_status.get("loop"))

    if restart_playback:
        _set_ros_activity(app, "stopping", "stopping bag playback for ROS_DOMAIN_ID change")
        await asyncio.to_thread(stop_bag_playback, app.state.bag_playback)

    _set_ros_activity(app, "daemon_stopped", "stopping ROS daemon")
    graph_monitor = getattr(app.state, "graph_monitor", None)
    if graph_monitor is not None:
        graph_monitor.stop()
    stop_result = await run_shell_command_async("ros2 daemon stop", 8, config)
    _set_ros_activity(app, "starting", "starting ROS daemon")
    start_result = await run_shell_command_async("ros2 daemon start", 8, config)
    if graph_monitor is not None:
        graph_monitor.start()
    _invalidate_snapshot_cache(app)

    replay_result: dict[str, object] | None = None
    if restart_playback:
        _set_ros_activity(app, "starting", "restarting bag playback")
        replay_result = await asyncio.to_thread(start_bag_playback, app.state.bag_playback, config, bag_path, topics, rate, loop)
    _set_ros_activity(app, "idle", "ROS daemon restarted")

    return {
        "daemon_stop": stop_result.ok,
        "daemon_start": start_result.ok,
        "daemon_stdout": "\n".join(part for part in (stop_result.stdout, start_result.stdout) if part),
        "daemon_stderr": "\n".join(part for part in (stop_result.stderr, start_result.stderr) if part),
        "playback_restarted": bool(replay_result and replay_result.get("ok")),
        "playback_error": "" if not replay_result else str(replay_result.get("error") or ""),
    }


def create_app() -> FastAPI:
    config = load_config()
    static_dir = Path(__file__).parent / "web"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.graph_monitor.start()
        try:
            yield
        finally:
            app.state.graph_monitor.stop()

    app = FastAPI(title="DeepSight", version="0.1.0", lifespan=lifespan)
    app.state.config = config
    app.state.middleware_mode = "dds"
    app.state.snapshot_cache = None
    app.state.snapshot_cached_at = 0.0
    app.state.ros_cache = None
    app.state.ros_cached_at = 0.0
    app.state.visual_topics_cache = None
    app.state.visual_topics_cached_at = 0.0
    app.state.bag_playback = BagPlayback()
    app.state.last_playback_running = False
    app.state.ros_activity = {"state": "idle", "detail": "ready", "updated_at": time.time()}
    app.state.graph_monitor = GraphMonitor(config)

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "mission": config.mission.name}

    @app.get("/api/config")
    async def app_config() -> dict[str, object]:
        return {
            "mission": config.mission.model_dump(),
            "server": config.server.model_dump(),
            "robots": [robot.model_dump() for robot in config.robots],
            "commands": [command.model_dump(exclude={"command"}) for command in config.commands],
        }

    @app.get("/api/tools")
    async def required_tools() -> list[dict[str, object]]:
        return mission_tools_payload()

    @app.get("/api/bags")
    async def bags() -> dict[str, object]:
        return await asyncio.to_thread(bag_inventory, config)

    @app.get("/api/visual/topics")
    async def visual_topic_list(refresh: bool = Query(default=False)) -> dict[str, object]:
        return await asyncio.to_thread(_cached_visual_topics, app, config, refresh)

    @app.post("/api/visual/pointcloud-sample")
    async def visual_pointcloud_sample(request: PointCloudSampleRequest) -> dict[str, object]:
        return await asyncio.to_thread(pointcloud_sample, config, request.bag_path, request.topic, request.max_points)

    @app.websocket("/api/visual/pointcloud-live")
    async def visual_pointcloud_live(
        websocket: WebSocket,
        topic: str = Query(...),
        max_points: int = Query(default=50_000, ge=100, le=200_000),
        rate_hz: float = Query(default=5.0, ge=0.2, le=20.0),
    ) -> None:
        await websocket.accept()
        command = ros_python_module_command(config, "deepsight.pointcloud_live_cli", [topic, str(max_points), str(rate_hz)])
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await _forward_length_prefixed_json(websocket, process, "point cloud stream")

    @app.websocket("/api/visual/camera-live")
    async def visual_camera_live(
        websocket: WebSocket,
        topic: str = Query(...),
        topic_type: str = Query(...),
        rate_hz: float = Query(default=10.0, ge=0.2, le=30.0),
    ) -> None:
        await websocket.accept()
        if topic_type not in {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}:
            await websocket.send_json({"ok": False, "error": "selected topic is not sensor_msgs Image or CompressedImage"})
            return
        command = ros_python_module_command(config, "deepsight.camera_live_cli", [topic, topic_type, str(rate_hz)])
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await _forward_length_prefixed_json(websocket, process, "camera stream")

    @app.websocket("/api/visual/costmap-live")
    async def visual_costmap_live(
        websocket: WebSocket,
        topic: str = Query(...),
        rate_hz: float = Query(default=2.0, ge=0.2, le=10.0),
    ) -> None:
        await websocket.accept()
        command = ros_python_module_command(config, "deepsight.costmap_live_cli", [topic, str(rate_hz)])
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await _forward_length_prefixed_json(websocket, process, "costmap stream")

    @app.get("/api/post-processing/status")
    async def post_processing_status() -> dict[str, object]:
        status = app.state.bag_playback.status()
        running = bool(status.get("running"))
        if bool(getattr(app.state, "last_playback_running", False)) and not running:
            _set_ros_activity(app, "updating", "bag playback finished; refreshing ROS graph")
            _invalidate_snapshot_cache(app)
        app.state.last_playback_running = running
        return status

    @app.post("/api/post-processing/play")
    async def post_processing_play(request: BagPlaybackRequest) -> dict[str, object]:
        _set_ros_activity(app, "starting", "starting bag playback")
        result = await asyncio.to_thread(
            start_bag_playback,
            app.state.bag_playback,
            config,
            request.bag_path,
            request.topics,
            request.rate,
            request.loop,
        )
        if result.get("ok"):
            app.state.last_playback_running = True
            _invalidate_snapshot_cache(app)
            _set_ros_activity(app, "updating", "bag playback started; refreshing ROS graph")
        else:
            _set_ros_activity(app, "idle", str(result.get("error") or "bag playback did not start"))
        return result

    @app.post("/api/post-processing/stop")
    async def post_processing_stop() -> dict[str, object]:
        _set_ros_activity(app, "stopping", "stopping bag playback")
        result = await asyncio.to_thread(stop_bag_playback, app.state.bag_playback)
        app.state.last_playback_running = False
        _invalidate_snapshot_cache(app)
        _set_ros_activity(app, "updating", "bag playback stopped; refreshing ROS graph")
        return result

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        return await asyncio.to_thread(_cached_mission_snapshot, app, config)

    @app.post("/api/middleware")
    async def middleware(request: MiddlewareRequest) -> dict[str, object]:
        if request.mode not in {"dds", "zenoh"}:
            raise HTTPException(status_code=400, detail="mode must be 'dds' or 'zenoh'")
        app.state.middleware_mode = request.mode
        _invalidate_snapshot_cache(app)
        return {"mode": request.mode}

    @app.post("/api/ros-domain")
    async def ros_domain(request: RosDomainRequest) -> dict[str, object]:
        _set_ros_activity(app, "starting", "changing ROS_DOMAIN_ID")
        config.mission.ros_domain_id = request.domain_id
        restart = await _restart_ros_runtime(app, config)
        return {
            "ok": True,
            "ros_domain_id": config.mission.ros_domain_id,
            **restart,
        }

    @app.post("/api/commands/run")
    async def run_command(request: CommandRequest) -> dict[str, object]:
        command = find_command(request.command_id, config)
        if not command:
            raise HTTPException(status_code=404, detail="unknown command_id")
        if command.background:
            result = await start_background_command_async(command.command, config)
        else:
            result = await run_shell_command_async(command.command, command.timeout_sec, config)
        return {
            "id": command.id,
            "label": command.label,
            "ok": result.ok,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
        }

    @app.websocket("/api/live")
    async def live(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                payload = await asyncio.to_thread(_cached_mission_snapshot, app, config)
                await websocket.send_json(payload)
                await asyncio.sleep(config.mission.poll_interval_sec)
        except WebSocketDisconnect:
            return

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    app.mount("/", StaticFiles(directory=static_dir), name="static")
    return app
