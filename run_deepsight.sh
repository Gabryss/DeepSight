#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

CONFIG="${DEEPSIGHT_CONFIG:-configs/mission.example.toml}"
ROS_LOG_DIR="${ROS_LOG_DIR:-/tmp/deepsight_ros_logs}"

mkdir -p "$ROS_LOG_DIR"
export DEEPSIGHT_CONFIG="$CONFIG"
export ROS_LOG_DIR
export PYTHONUNBUFFERED=1

URL="$(python3 -c '
import os
import tomllib
from pathlib import Path

path = Path(os.environ["DEEPSIGHT_CONFIG"])
payload = tomllib.load(path.open("rb")) if path.exists() else {}
server = payload.get("server", {})
host = os.environ.get("DEEPSIGHT_HOST") or server.get("host", "127.0.0.1")
port = os.environ.get("DEEPSIGHT_PORT") or server.get("port", 8766)
print(f"http://{host}:{port}")
' 2>/dev/null || true)"

if [[ -x "$ROOT_DIR/.venv/bin/deepsight" ]]; then
  RUNNER=("$ROOT_DIR/.venv/bin/deepsight")
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  RUNNER=("$ROOT_DIR/.venv/bin/python" "-m" "deepsight")
else
  export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
  RUNNER=("python3" "-m" "deepsight")
fi

cat <<EOF
DeepSight
  config: $CONFIG
  url:    ${URL:-configured in [server]}
  logs:   $ROS_LOG_DIR

Stop with Ctrl+C.
EOF

exec "${RUNNER[@]}" --config "$CONFIG"
