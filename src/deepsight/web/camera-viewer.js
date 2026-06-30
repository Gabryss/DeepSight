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
    this.lastFrameAt = 0;
    this.animation = requestAnimationFrame(this.render);
  }

  setFpsCap(value) {
    this.fpsCap = Number.parseInt(value, 10) || 10;
  }

  togglePause() {
    this.paused = !this.paused;
    this.statusNode.textContent = this.paused ? "paused" : "preview camera active";
    return this.paused;
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

  render = (now) => {
    this.resize();
    const minInterval = 1000 / this.fpsCap;
    if (!this.paused && now - this.lastFrameAt >= minInterval) {
      this.drawPreview(now / 1000);
      this.frameCount += 1;
      this.lastFrameAt = now;
    } else if (!this.paused) {
      this.dropped += 1;
    }
    if (now - this.lastStatsAt > 1000) {
      this.statsNode.textContent = `${this.frameCount} fps · ${this.dropped} dropped`;
      this.frameCount = 0;
      this.dropped = 0;
      this.lastStatsAt = now;
    }
    this.animation = requestAnimationFrame(this.render);
  };

  drawPreview(seconds) {
    const width = this.canvas.width;
    const height = this.canvas.height;
    const ctx = this.context;
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#050708");
    gradient.addColorStop(0.55, "#151b21");
    gradient.addColorStop(1, "#020303");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    const sweep = (Math.sin(seconds * 0.7) + 1) * 0.5;
    ctx.fillStyle = "rgba(190, 210, 230, 0.10)";
    ctx.beginPath();
    ctx.moveTo(width * (0.15 + sweep * 0.12), height * 0.08);
    ctx.lineTo(width * (0.45 + sweep * 0.1), height * 0.08);
    ctx.lineTo(width * (0.33 + sweep * 0.15), height * 0.92);
    ctx.lineTo(width * (0.08 + sweep * 0.1), height * 0.92);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = Math.max(1, width / 700);
    for (let y = 0; y < height; y += Math.max(14, height / 28)) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    ctx.fillStyle = "rgba(255, 255, 255, 0.75)";
    for (let index = 0; index < 18; index += 1) {
      const x = ((index * 89 + seconds * 18) % 1000) / 1000 * width;
      const y = ((index * 157) % 1000) / 1000 * height;
      ctx.fillRect(x, y, 2, 2);
    }
    this.statusNode.textContent = "preview camera active";
  }
}
