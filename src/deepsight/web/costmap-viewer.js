export class CostmapViewer {
  constructor(canvas, statsNode, statusNode, label = "costmap") {
    this.canvas = canvas;
    this.context = canvas.getContext("2d", { alpha: false });
    this.statsNode = statsNode;
    this.statusNode = statusNode;
    this.label = label;
    this.frameCount = 0;
    this.lastStatsAt = performance.now();
    this.clear(`no ${label} loaded`);
    window.addEventListener("resize", () => this.resize());
  }

  clear(message = `no ${this.label} loaded`) {
    this.resize();
    this.context.fillStyle = "#020303";
    this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.statusNode.textContent = message;
    this.statsNode.textContent = "0 cells";
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

  loadGrid(payload) {
    const width = Number(payload.width) || 0;
    const height = Number(payload.height) || 0;
    const values = payload.data || [];
    if (!width || !height || values.length < width * height) {
      this.clear("invalid OccupancyGrid frame");
      return;
    }

    this.resize();
    const image = this.context.createImageData(width, height);
    for (let y = 0; y < height; y += 1) {
      const sourceY = height - 1 - y;
      for (let x = 0; x < width; x += 1) {
        const source = sourceY * width + x;
        const target = (y * width + x) * 4;
        const value = values[source];
        if (value < 0) {
          image.data[target] = 48;
          image.data[target + 1] = 52;
          image.data[target + 2] = 52;
        } else {
          const occupied = Math.max(0, Math.min(100, value)) / 100;
          image.data[target] = Math.round(28 + occupied * 210);
          image.data[target + 1] = Math.round(34 + occupied * 32);
          image.data[target + 2] = Math.round(34 + occupied * 22);
        }
        image.data[target + 3] = 255;
      }
    }

    const offscreen = document.createElement("canvas");
    offscreen.width = width;
    offscreen.height = height;
    offscreen.getContext("2d").putImageData(image, 0, 0);

    const canvasRatio = this.canvas.width / this.canvas.height;
    const gridRatio = width / height;
    let drawWidth = this.canvas.width;
    let drawHeight = this.canvas.height;
    if (gridRatio > canvasRatio) {
      drawHeight = drawWidth / gridRatio;
    } else {
      drawWidth = drawHeight * gridRatio;
    }
    const x = (this.canvas.width - drawWidth) / 2;
    const y = (this.canvas.height - drawHeight) / 2;

    this.context.fillStyle = "#020303";
    this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.context.imageSmoothingEnabled = false;
    this.context.drawImage(offscreen, x, y, drawWidth, drawHeight);

    this.frameCount += 1;
    const now = performance.now();
    const elapsed = Math.max(1, now - this.lastStatsAt);
    if (elapsed > 500) {
      const fps = (this.frameCount * 1000) / elapsed;
      this.statsNode.textContent = `${width}x${height} · ${fps.toFixed(1)} fps · ${payload.resolution ?? "?"} m/cell`;
      this.frameCount = 0;
      this.lastStatsAt = now;
    }
    this.statusNode.textContent = `${payload.topic} · ${width * height} cells`;
  }
}
