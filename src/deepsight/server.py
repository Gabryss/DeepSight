from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deepsight.config import AppConfig, load_config
from deepsight.network import robot_batteries, robot_connectivity
from deepsight.ros import ros_snapshot
from deepsight.runner import command_available, find_command, run_shell_command_async, start_background_command_async
from deepsight.tools import MISSION_TOOLS, mission_tools_payload


class CommandRequest(BaseModel):
    command_id: str


class MiddlewareRequest(BaseModel):
    mode: str


def _tool_status() -> list[dict[str, object]]:
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
                        "available": command_available(tool.command),
                    }
                    for tool in tools
                ],
            }
        )
    return status


def _mission_snapshot(config: AppConfig, middleware_mode: str) -> dict[str, object]:
    return {
        "mission": config.mission.model_dump(),
        "middleware_mode": middleware_mode,
        "tools": _tool_status(),
        "robots": robot_connectivity(config),
        "batteries": robot_batteries(config),
        "ros": ros_snapshot(config),
        "commands": [command.model_dump(exclude={"command"}) for command in config.commands],
    }


def create_app() -> FastAPI:
    config = load_config()
    static_dir = Path(__file__).parent / "web"
    app = FastAPI(title="DeepSight", version="0.1.0")
    app.state.config = config
    app.state.middleware_mode = "dds"

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "mission": config.mission.name}

    @app.get("/api/config")
    async def app_config() -> dict[str, object]:
        return {
            "mission": config.mission.model_dump(),
            "robots": [robot.model_dump() for robot in config.robots],
            "commands": [command.model_dump(exclude={"command"}) for command in config.commands],
        }

    @app.get("/api/tools")
    async def required_tools() -> list[dict[str, object]]:
        return mission_tools_payload()

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        return await asyncio.to_thread(_mission_snapshot, config, app.state.middleware_mode)

    @app.post("/api/middleware")
    async def middleware(request: MiddlewareRequest) -> dict[str, object]:
        if request.mode not in {"dds", "zenoh"}:
            raise HTTPException(status_code=400, detail="mode must be 'dds' or 'zenoh'")
        app.state.middleware_mode = request.mode
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
                payload = await asyncio.to_thread(_mission_snapshot, config, app.state.middleware_mode)
                await websocket.send_json(payload)
                await asyncio.sleep(config.mission.poll_interval_sec)
        except WebSocketDisconnect:
            return

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    app.mount("/", StaticFiles(directory=static_dir), name="static")
    return app
