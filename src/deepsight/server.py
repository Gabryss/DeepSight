from __future__ import annotations

import asyncio
import struct
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from deepsight.bags import bag_inventory
from deepsight.config import AppConfig, load_config
from deepsight.network import robot_batteries, robot_connectivity
from deepsight.pointcloud import pointcloud_sample, ros_python_module_command
from deepsight.postprocessing import BagPlayback, start_bag_playback, stop_bag_playback
from deepsight.ros import ros_snapshot
from deepsight.runner import command_available, find_command, run_shell_command_async, start_background_command_async
from deepsight.tools import MISSION_TOOLS, mission_tools_payload
from deepsight.visual import visual_topics


class CommandRequest(BaseModel):
    command_id: str


class MiddlewareRequest(BaseModel):
    mode: str


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


def _mission_snapshot(config: AppConfig, middleware_mode: str, ros_payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "mission": config.mission.model_dump(),
        "middleware_mode": middleware_mode,
        "tools": _tool_status(config),
        "robots": robot_connectivity(config),
        "batteries": robot_batteries(config),
        "ros": ros_payload if ros_payload is not None else ros_snapshot(config),
        "commands": [command.model_dump(exclude={"command"}) for command in config.commands],
    }


def _topic_discovery_ttl(config: AppConfig) -> float:
    return max(5.0, config.mission.topic_discovery_interval_sec)


def _cached_ros_snapshot(app: FastAPI, config: AppConfig, force: bool = False) -> dict[str, object]:
    now = time.monotonic()
    cached_at = getattr(app.state, "ros_cached_at", 0.0)
    cached_payload = getattr(app.state, "ros_cache", None)
    if not force and cached_payload is not None and now - cached_at < _topic_discovery_ttl(config):
        return cached_payload

    payload = ros_snapshot(config)
    app.state.ros_cache = payload
    app.state.ros_cached_at = now
    return payload


def _cached_visual_topics(app: FastAPI, config: AppConfig, force: bool = False) -> dict[str, object]:
    now = time.monotonic()
    cached_at = getattr(app.state, "visual_topics_cached_at", 0.0)
    cached_payload = getattr(app.state, "visual_topics_cache", None)
    if not force and cached_payload is not None and now - cached_at < _topic_discovery_ttl(config):
        return cached_payload

    payload = visual_topics(config)
    payload["next_refresh_sec"] = _topic_discovery_ttl(config)
    app.state.visual_topics_cache = payload
    app.state.visual_topics_cached_at = now
    return payload


def _cached_mission_snapshot(app: FastAPI, config: AppConfig) -> dict[str, object]:
    now = time.monotonic()
    cached_at = getattr(app.state, "snapshot_cached_at", 0.0)
    cached_payload = getattr(app.state, "snapshot_cache", None)
    ttl = max(0.5, config.mission.poll_interval_sec)
    if cached_payload is not None and now - cached_at < ttl:
        return cached_payload

    ros_payload = _cached_ros_snapshot(app, config)
    payload = _mission_snapshot(config, app.state.middleware_mode, ros_payload)
    app.state.snapshot_cache = payload
    app.state.snapshot_cached_at = now
    return payload


def _invalidate_snapshot_cache(app: FastAPI) -> None:
    app.state.snapshot_cache = None
    app.state.snapshot_cached_at = 0.0


def create_app() -> FastAPI:
    config = load_config()
    static_dir = Path(__file__).parent / "web"
    app = FastAPI(title="DeepSight", version="0.1.0")
    app.state.config = config
    app.state.middleware_mode = "dds"
    app.state.snapshot_cache = None
    app.state.snapshot_cached_at = 0.0
    app.state.ros_cache = None
    app.state.ros_cached_at = 0.0
    app.state.visual_topics_cache = None
    app.state.visual_topics_cached_at = 0.0
    app.state.bag_playback = BagPlayback()

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
        return app.state.bag_playback.status()

    @app.post("/api/post-processing/play")
    async def post_processing_play(request: BagPlaybackRequest) -> dict[str, object]:
        return await asyncio.to_thread(
            start_bag_playback,
            app.state.bag_playback,
            config,
            request.bag_path,
            request.topics,
            request.rate,
            request.loop,
        )

    @app.post("/api/post-processing/stop")
    async def post_processing_stop() -> dict[str, object]:
        return await asyncio.to_thread(stop_bag_playback, app.state.bag_playback)

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
