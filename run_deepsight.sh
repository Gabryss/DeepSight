#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

CONFIG="${DEEPSIGHT_CONFIG:-configs/mission.example.toml}"
HOST="${DEEPSIGHT_HOST:-127.0.0.1}"
PORT="${DEEPSIGHT_PORT:-8766}"
ROS_LOG_DIR="${ROS_LOG_DIR:-/tmp/deepsight_ros_logs}"

mkdir -p "$ROS_LOG_DIR"
export DEEPSIGHT_CONFIG="$CONFIG"
export ROS_LOG_DIR
export PYTHONUNBUFFERED=1

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
  url:    http://$HOST:$PORT
  logs:   $ROS_LOG_DIR

Stop with Ctrl+C.
EOF

exec "${RUNNER[@]}" --config "$CONFIG" --host "$HOST" --port "$PORT"
