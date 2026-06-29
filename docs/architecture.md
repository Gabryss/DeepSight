# DeepSight Architecture

## Repository Structure

```text
DeepSight/
  configs/
    mission.example.toml     # Field mission inventory and allowlisted commands
  docs/
    architecture.md          # Design and extension notes
    mission-tools.md         # Required mission tool checklist
  src/deepsight/
    cli.py                   # `deepsight` command entrypoint
    config.py                # TOML config models
    network.py               # Robot ping and battery probes
    ros.py                   # ROS graph and bandwidth probes
    runner.py                # Bounded command execution helpers
    server.py                # FastAPI app and WebSocket
    tools.py                 # Required tool catalog
    web/                     # Static dashboard
  tests/                     # Backend smoke tests
```

## Runtime Model

The dashboard is a local FastAPI server that serves a static browser UI. The backend does not import ROS client libraries. Instead, it executes bounded, allowlisted shell commands and ROS 2 CLI probes. This keeps the web server independent from ROS Python ABI issues and makes it usable from a normal field laptop shell.

Configured commands are intentionally identified by `command_id`. The API does not accept arbitrary command text from the browser.

## Dependencies

Python package dependencies:

- FastAPI: HTTP API and WebSocket server.
- Uvicorn: local ASGI server.
- Pydantic and pydantic-settings: config validation.
- Pytest and httpx: development tests.

System and robot dependencies:

- ROS 2 Jazzy or newer field deployment.
- A configured DDS implementation, usually Cyclone DDS or Fast DDS.
- Optional Zenoh bridge for routed underground networks.
- `ping`, `ssh`, and ROS 2 CLI available on the base station.
- Visualization stack such as Foxglove bridge and RViz2 for rich streams.

## Extension Points

- Add robots in `configs/mission.example.toml` or a mission-specific TOML file.
- Add allowlisted remote actions under `[[commands]]`.
- Set `background = true` for long-running launch or bag commands.
- Add battery commands per robot with `battery_command`.
- Set `[mission].bag_root` to a ROS bag directory to populate the dashboard bag inventory.
- Extend `src/deepsight/ros.py` for actions, lifecycle nodes, parameters, or costmap summaries.
- Add authenticated reverse proxying before exposing the dashboard beyond localhost.
