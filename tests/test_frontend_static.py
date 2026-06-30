from __future__ import annotations

from pathlib import Path


def test_dashboard_contains_primary_feature_surfaces():
    html = (Path(__file__).parents[1] / "src" / "deepsight" / "web" / "index.html").read_text(encoding="utf-8")

    for element_id in (
        "feed-live",
        "feed-cloud",
        "feed-map",
        "feed-camera",
        "feed-costmap",
        "feed-network",
        "feed-post-processing",
        "post-bag-select",
        "post-topic-list",
        "post-play",
        "post-stop",
        "post-progress-fill",
        "console-commands",
    ):
        assert f'id="{element_id}"' in html


def test_server_exposes_core_api_routes():
    from deepsight.server import create_app

    paths = {route.path for route in create_app().routes}

    for path in (
        "/api/health",
        "/api/config",
        "/api/status",
        "/api/bags",
        "/api/post-processing/status",
        "/api/post-processing/play",
        "/api/post-processing/stop",
        "/api/commands/run",
    ):
        assert path in paths
