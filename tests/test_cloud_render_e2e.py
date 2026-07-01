from __future__ import annotations

import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path

import pytest


def _png_bright_pixels(path: Path) -> int:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    width = height = color_type = None
    payload = b""
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
            assert bit_depth == 8
            assert color_type in {2, 6}
        elif chunk_type == b"IDAT":
            payload += chunk
        elif chunk_type == b"IEND":
            break

    assert width and height and color_type is not None
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(payload)
    rows: list[bytearray] = []
    cursor = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                predictor = _paeth(left, up, up_left)
                row[index] = (row[index] + predictor) & 0xFF
        rows.append(row)
        previous = row

    bright = 0
    for row in rows:
        for index in range(0, stride, channels):
            if max(row[index], row[index + 1], row[index + 2]) > 95:
                bright += 1
    return bright


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def test_pointcloud_viewer_renders_visible_pixels_in_browser(tmp_path):
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        pytest.skip("headless Chrome is not installed")

    viewer_path = (Path(__file__).parents[1] / "src" / "deepsight" / "web" / "pointcloud-viewer.js").resolve()
    (tmp_path / "pointcloud-viewer.js").write_text(viewer_path.read_text(encoding="utf-8"), encoding="utf-8")
    html_path = tmp_path / "cloud_render.html"
    screenshot_path = tmp_path / "cloud_render.png"
    points = [
        [x * 0.18, y * 0.18, ((x + y) % 9) * 0.05, 1.0]
        for x in range(-26, 27)
        for y in range(-16, 17)
    ]
    html_path.write_text(
        f"""
        <!doctype html>
        <html>
          <body style="margin:0;background:#020303">
            <canvas id="cloud" width="800" height="520" style="width:800px;height:520px"></canvas>
            <span id="stats" hidden></span>
            <span id="status" hidden></span>
            <script type="module">
              import {{ PointCloudViewer }} from "./pointcloud-viewer.js";
              const viewer = new PointCloudViewer(
                document.querySelector("#cloud"),
                document.querySelector("#stats"),
                document.querySelector("#status"),
              );
              viewer.setPointSize(8);
              viewer.loadPoints({points!r}, "test cloud");
              setTimeout(() => document.body.dataset.ready = "true", 600);
            </script>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    except PermissionError:
        pytest.skip("localhost sockets are blocked by the sandbox")

    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/cloud_render.html", timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.05)
        result = subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-crash-reporter",
                "--disable-crashpad",
                "--hide-scrollbars",
                f"--user-data-dir={tmp_path / 'chrome-profile'}",
                "--virtual-time-budget=1200",
                f"--screenshot={screenshot_path}",
                f"http://127.0.0.1:{port}/cloud_render.html",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    finally:
        server.terminate()
        server.wait(timeout=5)

    if result.returncode != 0 and "Operation not permitted" in result.stderr and "crashpad" in result.stderr:
        pytest.skip("headless Chrome crashpad is blocked by the sandbox")
    assert result.returncode == 0, result.stderr or result.stdout
    assert _png_bright_pixels(screenshot_path) > 500
