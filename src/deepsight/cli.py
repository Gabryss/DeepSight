from __future__ import annotations

import argparse
import os

import uvicorn

from deepsight.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the DeepSight local mission dashboard.")
    parser.add_argument("--host", default=None, help="Bind address. Defaults to [server].host.")
    parser.add_argument("--port", type=int, default=None, help="Bind port. Defaults to [server].port.")
    parser.add_argument(
        "--config",
        default="configs/mission.example.toml",
        help="Mission TOML config path.",
    )
    args = parser.parse_args()
    os.environ["DEEPSIGHT_CONFIG"] = args.config
    config = load_config(args.config)
    host = args.host or os.environ.get("DEEPSIGHT_HOST") or config.server.host
    port = args.port or int(os.environ.get("DEEPSIGHT_PORT") or config.server.port)

    uvicorn.run(
        "deepsight.server:create_app",
        host=host,
        port=port,
        factory=True,
        reload=False,
        app_dir="src",
        log_level="info",
    )
