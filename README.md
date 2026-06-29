# DeepSight

DeepSight is a local web dashboard for underground field robotics experiments. It gives an operator one page for robot connectivity, ROS graph status, TF checks, topic bandwidth, battery probes, DDS/Zenoh mode selection, and allowlisted remote commands.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
deepsight --config configs/mission.example.toml --host 127.0.0.1 --port 8766
```

Open http://127.0.0.1:8766.

DeepSight automatically sources `[mission].ros_setup` for ROS commands, so a plain shell can start the server as long as the configured setup file exists.

## Mission Configuration

Copy `configs/mission.example.toml` for each field test and edit:

- `[[robots]]`: robot IDs, labels, hosts, SSH targets, and optional battery probes.
- `[[commands]]`: allowlisted launch, restart, recording, or recovery commands.
- `background = true`: use this for long-running launch or bag commands.
- `[mission].ros_setup`: ROS 2 setup script to source before ROS CLI probes.
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
- Post-processing tab for selecting a configured ROS bag, filtering topics, and starting/stopping `ros2 bag play`.
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
