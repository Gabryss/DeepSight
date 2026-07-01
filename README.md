# DeepSight

DeepSight is a local web dashboard for underground field robotics experiments. It gives an operator one page for robot connectivity, ROS graph status, TF checks, topic bandwidth, battery probes, DDS/Zenoh mode selection, and allowlisted remote commands.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./run_deepsight.sh
```

Open http://127.0.0.1:8766.

The bind host and port are configured in `configs/mission.example.toml`:

```toml
[server]
host = "127.0.0.1"
port = 8766
```

Use `DEEPSIGHT_CONFIG=/path/to/mission.toml ./run_deepsight.sh` to launch another mission file. `DEEPSIGHT_HOST` and `DEEPSIGHT_PORT` can still override the TOML values for one-off runs.

DeepSight automatically sources `[mission].ros_setup` for ROS commands, so a plain shell can start the server as long as the configured setup file exists.

## Mission Configuration

Copy `configs/mission.example.toml` for each field test and edit:

- `[[robots]]`: robot IDs, labels, hosts, SSH targets, and optional battery probes.
- `[[commands]]`: allowlisted launch, restart, recording, or recovery commands.
- `background = true`: use this for long-running launch or bag commands.
- `[server].host` and `[server].port`: local web server bind address.
- `[mission].ros_setup`: ROS 2 setup script to source before ROS CLI probes.
- `[mission].ros_domain_id`: default `ROS_DOMAIN_ID` for all ROS CLI probes, bag playback, and visual streams.
- `[mission].poll_interval_sec`: lightweight dashboard refresh rate for robot state and cached status.
- `[mission].topic_discovery_interval_sec`: slower ROS topic discovery cadence for `ros2 topic list` and `ros2 topic list -t`.
- `[mission].bag_root`: local ROS bag root for the dashboard bag inventory.

The example config points at the current trial dataset:

```toml
bag_root = "/home/gabriel/bag_files/mine_nider"
```

The browser can only run configured command IDs. It cannot submit arbitrary shell text.

## Core Features

- Live robot ping checks in the background.
- ROS 2 topic, node, service, TF, and bandwidth snapshots.
- Battery probe hooks per robot.
- DDS/Zenoh mode indicator for mission coordination.
- Allowlisted remote commands for rover restart, launch, bagging, and recovery.
- Point cloud and camera visualization tabs with topic selectors, render budgets, and performance HUDs.
- Live PointCloud2 streaming into the Cloud tab over a ROS-sourced WebSocket bridge.
- PointCloud2 sample loading from configured ROS bags for the Cloud tab.
- Post-processing tab for selecting a configured ROS bag, filtering topics, and starting/stopping `ros2 bag play`.
- Playback state, progress, and log output for the active post-processing bag.
- Required underground mission tool checklist with local availability status.
- WebSocket updates for live monitoring.

## Documentation

- [Architecture](docs/architecture.md)
- [Underground mission tool checklist](docs/mission-tools.md)
- [Mine Nider trial bag analysis](docs/trial-bag-analysis.md)

## Development

```bash
pip install -e ".[dev]"
pytest
```

The backend uses ROS 2 CLI commands rather than ROS Python bindings, so tests and the local UI can run on machines without a sourced ROS environment. ROS-specific panels show missing status until `ros2` and the configured setup file are available.

Tests include service-level end-to-end coverage for bag inventory and post-processing playback, static guards for the primary dashboard feature surfaces, and a headless-browser cloud render check when Chrome is available.

## Visualization Notes

The Cloud tab uses a canvas 3D renderer with a configurable max-points cap and point size. Use Stream to subscribe to a live PointCloud2 topic and update the 3D panel as frames arrive. The panel auto-orbits until the operator clicks, scrolls, or uses keyboard controls. Mouse controls orbit, pan, and zoom the scene; WASD/arrow keys move through the cloud when the canvas is focused. Color modes support distance, height, and intensity. The max-points cap remains as a field safety control for browser load, and defaults to 200k to avoid dropping too much data.

Select a configured bag in Post Processing, choose a PointCloud2 topic in the Cloud tab, then use Load to render an actual sample from the bag. The Camera tab streams selected `sensor_msgs/msg/Image` or `sensor_msgs/msg/CompressedImage` topics and includes a camera metadata topic selector. The Map and Costmap tabs stream selected `nav_msgs/msg/OccupancyGrid` topics into top-down canvas views. Topic selectors are populated from live ROS topic types when `ros2 topic list -t` is available and from configured bag metadata otherwise.

ROS topic discovery is cached separately from the main dashboard poll. Robot ping and battery state can update every few seconds, while topic selectors and ROS graph counts refresh on `[mission].topic_discovery_interval_sec` to avoid putting unnecessary DDS discovery traffic on an underground field network. The dashboard refresh button and the Topics inspector refresh button force one immediate topic discovery pass. Starting, stopping, finishing, or restarting bag playback invalidates the ROS graph cache so newly published topics appear promptly.

Changing the ROS domain from the dashboard updates the runtime `ROS_DOMAIN_ID`, restarts the ROS daemon, clears cached ROS/topic state, and reconnects active visual streams. If post-processing bag playback is active, DeepSight stops and restarts that playback with the same bag, topics, rate, and loop settings.

The left TF panel replaces the old decorative `IDXC 01` label. It shows whether `/tf` and `/tf_static` are active; the footer ROS state shows when DeepSight is refreshing topics, starting playback, stopping playback, or restarting the ROS daemon. The Network tab uses compact state rows and a separate bandwidth trend graph so text remains readable in the field UI.

The next integration step is to move high-rate visual streams from JSON payloads to binary WebSocket packets for lower CPU overhead during long missions.
