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
        "cloud-topic-select",
        "cloud-point-budget",
        "cloud-load",
        "cloud-canvas",
        "cloud-stats",
        "camera-topic-select",
        "camera-fps-cap",
        "camera-canvas",
        "camera-stats",
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
        "/api/visual/topics",
        "/api/visual/pointcloud-sample",
        "/api/bags",
        "/api/post-processing/status",
        "/api/post-processing/play",
        "/api/post-processing/stop",
        "/api/commands/run",
    ):
        assert path in paths


def test_dashboard_loads_visual_renderers():
    app_js = (Path(__file__).parents[1] / "src" / "deepsight" / "web" / "app.js").read_text(encoding="utf-8")

    assert 'import { PointCloudViewer } from "./pointcloud-viewer.js";' in app_js
    assert 'import { CameraViewer } from "./camera-viewer.js";' in app_js
    assert "/api/visual/topics" in app_js
    assert "/api/visual/pointcloud-sample" in app_js
