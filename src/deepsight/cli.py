from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the DeepSight local mission dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address.")
    parser.add_argument("--port", type=int, default=8766, help="Bind port.")
    parser.add_argument(
        "--config",
        default="configs/mission.example.toml",
        help="Mission TOML config path.",
    )
    args = parser.parse_args()
    os.environ["DEEPSIGHT_CONFIG"] = args.config

    uvicorn.run(
        "deepsight.server:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=False,
        app_dir="src",
        log_level="info",
    )
