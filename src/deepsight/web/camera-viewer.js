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
    window.addEventListener("resize", () => this.resize());
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

  loadFrame(frame) {
    if (this.paused) {
      this.dropped += 1;
      return;
    }
    if (frame.frame_type === "compressed") {
      this.loadCompressedFrame(frame);
      return;
    }
    this.loadRawFrame(frame);
  }

  loadCompressedFrame(frame) {
    const image = new Image();
    image.onload = () => {
      this.drawImage(image, frame);
    };
    image.onerror = () => {
      this.dropped += 1;
      this.statusNode.textContent = "camera decode failed";
    };
    image.src = `data:${frame.mime || "image/jpeg"};base64,${frame.data}`;
  }

  loadRawFrame(frame) {
    const width = Number(frame.width) || 0;
    const height = Number(frame.height) || 0;
    const step = Number(frame.step) || 0;
    const encoding = String(frame.encoding || "").toLowerCase();
    const supported = new Set(["mono8", "8uc1", "rgb8", "bgr8", "rgba8", "bgra8"]);
    if (!width || !height || !step || !frame.data) {
      this.dropped += 1;
      this.statusNode.textContent = "invalid camera frame";
      return;
    }
    if (!supported.has(encoding)) {
      this.dropped += 1;
      this.statusNode.textContent = `unsupported camera encoding: ${encoding || "unknown"}`;
      return;
    }

    const bytes = Uint8Array.from(atob(frame.data), (char) => char.charCodeAt(0));
    const imageData = this.context.createImageData(width, height);
    for (let y = 0; y < height; y += 1) {
      const row = y * step;
      for (let x = 0; x < width; x += 1) {
        const target = (y * width + x) * 4;
        if (encoding === "mono8" || encoding === "8uc1") {
          const value = bytes[row + x] ?? 0;
          imageData.data[target] = value;
          imageData.data[target + 1] = value;
          imageData.data[target + 2] = value;
        } else {
          const source = row + x * (encoding.includes("rgba") || encoding.includes("bgra") ? 4 : 3);
          const rIndex = encoding.startsWith("bgr") || encoding.startsWith("bgra") ? 2 : 0;
          const bIndex = encoding.startsWith("bgr") || encoding.startsWith("bgra") ? 0 : 2;
          imageData.data[target] = bytes[source + rIndex] ?? 0;
          imageData.data[target + 1] = bytes[source + 1] ?? 0;
          imageData.data[target + 2] = bytes[source + bIndex] ?? 0;
        }
        imageData.data[target + 3] = 255;
      }
    }

    const offscreen = document.createElement("canvas");
    offscreen.width = width;
    offscreen.height = height;
    offscreen.getContext("2d").putImageData(imageData, 0, 0);
    this.drawImage(offscreen, frame);
  }

  drawImage(image, frame) {
    this.resize();
    const imageRatio = image.width / image.height;
    const canvasRatio = this.canvas.width / this.canvas.height;
    let width = this.canvas.width;
    let height = this.canvas.height;
    if (imageRatio > canvasRatio) {
      height = width / imageRatio;
    } else {
      width = height * imageRatio;
    }
    const x = (this.canvas.width - width) / 2;
    const y = (this.canvas.height - height) / 2;
    this.context.fillStyle = "#020303";
    this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.context.drawImage(image, x, y, width, height);

    this.frameCount += 1;
    const now = performance.now();
    const elapsed = Math.max(1, now - this.lastStatsAt);
    if (elapsed > 500) {
      const fps = (this.frameCount * 1000) / elapsed;
      this.statsNode.textContent = `${fps.toFixed(1)} fps · ${this.dropped} dropped`;
      this.frameCount = 0;
      this.lastStatsAt = now;
    }
    this.statusNode.textContent = `${frame.topic} · ${image.width}x${image.height}`;
  }

}
