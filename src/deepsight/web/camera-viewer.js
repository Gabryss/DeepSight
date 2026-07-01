export class CameraViewer {
  constructor(canvas, statsNode, statusNode) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d", { alpha: false });
    this.statsNode = statsNode;
    this.statusNode = statusNode;
    this.fpsCap = 10;
    this.paused = false;
    this.frameCount = 0;
    this.dropped = 0;
    this.lastStatsAt = performance.now();
    this.clear("no camera frame loaded");
  }

  setFpsCap(value) {
    this.fpsCap = Number.parseInt(value, 10) || 10;
  }

  togglePause() {
    this.paused = !this.paused;
    this.statusNode.textContent = this.paused ? "paused" : "no camera frame loaded";
    return this.paused;
  }

  clear(message = "no camera frame loaded") {
    this.resize();
    this.context.fillStyle = "#020303";
    this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.statsNode.textContent = "0 fps · 0 dropped";
    this.statusNode.textContent = message;
  }

  resize() {
    const width = Math.max(1, this.canvas.clientWidth);
    const height = Math.max(1, this.canvas.clientHeight);
    const scale = window.devicePixelRatio || 1;
    const nextWidth = Math.floor(width * scale);
    const nextHeight = Math.floor(height * scale);
    if (this.canvas.width !== nextWidth || this.canvas.height !== nextHeight) {
      this.canvas.width = nextWidth;
      this.canvas.height = nextHeight;
    }
  }

}
