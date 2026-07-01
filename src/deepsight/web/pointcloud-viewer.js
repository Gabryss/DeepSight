export class PointCloudViewer {
  constructor(canvas, statsNode, statusNode) {
    this.canvas = canvas;
    this.statsNode = statsNode;
    this.statusNode = statusNode;
    this.gl = canvas.getContext("webgl", { antialias: false, alpha: true, powerPreference: "high-performance" });
    this.context2d = this.gl ? null : canvas.getContext("2d", { alpha: false });
    this.pointCount = 0;
    this.points = [];
    this.budget = 200000;
    this.colorMode = 0;
    this.frameCount = 0;
    this.lastFpsAt = performance.now();
    this.yaw = -0.7;
    this.pitch = -0.9;
    this.distance = 14;
    this.target = [0, 0, 0];
    this.drag = null;
    this.keys = new Set();
    this.program = null;
    this.buffer = null;
    this.locations = {};
    this.bounds = { minZ: -1, maxZ: 1, maxDistance: 1 };
    this.hasFramed = false;
    this.animation = null;
    this.installControls();
    if (this.gl) {
      try {
        this.initGl();
      } catch (error) {
        console.error("point cloud viewer failed to initialize", error);
        this.gl = null;
        this.context2d = canvas.getContext("2d", { alpha: false });
        this.setStatus(`webgl init failed: ${error.message}`);
      }
    } else {
      this.clear("webgl unavailable; using 2D fallback");
    }
  }

  setStatus(value) {
    this.statusNode.textContent = value;
  }

  setBudget(value) {
    this.budget = Number.parseInt(value, 10) || 200000;
  }

  setColorMode(mode) {
    this.colorMode = { distance: 0, height: 1, intensity: 2 }[mode] ?? 0;
    this.drawFallback();
  }

  reset() {
    this.yaw = -0.7;
    this.pitch = -0.9;
    this.distance = 14;
    this.target = [0, 0, 0];
    this.hasFramed = false;
    this.drawFallback();
  }

  clear(message = "no cloud loaded") {
    this.pointCount = 0;
    this.points = [];
    this.hasFramed = false;
    if (this.gl && this.buffer) {
      this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffer);
      this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array(), this.gl.DYNAMIC_DRAW);
    }
    if (this.context2d) {
      this.resizeCanvas();
      this.context2d.fillStyle = "#020303";
      this.context2d.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }
    this.statsNode.textContent = "0 pts · 0 fps";
    this.setStatus(message);
  }

  installControls() {
    this.canvas.tabIndex = 0;
    this.canvas.addEventListener("pointerdown", (event) => {
      this.canvas.focus();
      this.canvas.setPointerCapture(event.pointerId);
      this.drag = { x: event.clientX, y: event.clientY, button: event.button, shift: event.shiftKey };
    });
    this.canvas.addEventListener("pointermove", (event) => {
      if (!this.drag) return;
      const dx = event.clientX - this.drag.x;
      const dy = event.clientY - this.drag.y;
      this.drag.x = event.clientX;
      this.drag.y = event.clientY;
      if (this.drag.button === 1 || this.drag.button === 2 || this.drag.shift) {
        this.pan(-dx * 0.012 * this.distance, dy * 0.012 * this.distance);
      } else {
        this.yaw += dx * 0.006;
        this.pitch = Math.max(-1.52, Math.min(1.52, this.pitch + dy * 0.006));
      }
      this.drawFallback();
    });
    this.canvas.addEventListener("pointerup", () => {
      this.drag = null;
    });
    this.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    this.canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      this.distance = Math.max(0.2, Math.min(250, this.distance * (1 + event.deltaY * 0.001)));
      this.drawFallback();
    }, { passive: false });
    window.addEventListener("keydown", (event) => {
      if (document.activeElement === this.canvas) {
        this.keys.add(event.key.toLowerCase());
      }
    });
    window.addEventListener("keyup", (event) => this.keys.delete(event.key.toLowerCase()));
  }

  pan(dx, dy) {
    const right = [Math.cos(this.yaw), -Math.sin(this.yaw), 0];
    const up = [0, 0, 1];
    this.target[0] += right[0] * dx + up[0] * dy;
    this.target[1] += right[1] * dx + up[1] * dy;
    this.target[2] += right[2] * dx + up[2] * dy;
  }

  updateKeyboard() {
    const step = 0.055 * this.distance;
    const forward = [Math.sin(this.yaw), Math.cos(this.yaw), 0];
    const right = [Math.cos(this.yaw), -Math.sin(this.yaw), 0];
    if (this.keys.has("w") || this.keys.has("arrowup")) this.panVector(forward, step);
    if (this.keys.has("s") || this.keys.has("arrowdown")) this.panVector(forward, -step);
    if (this.keys.has("d") || this.keys.has("arrowright")) this.panVector(right, step);
    if (this.keys.has("a") || this.keys.has("arrowleft")) this.panVector(right, -step);
    if (this.keys.has("q")) this.target[2] -= step;
    if (this.keys.has("e")) this.target[2] += step;
  }

  panVector(vector, amount) {
    this.target[0] += vector[0] * amount;
    this.target[1] += vector[1] * amount;
    this.target[2] += vector[2] * amount;
  }

  initGl() {
    const vertexSource = `
      attribute vec3 position;
      attribute float intensity;
      uniform mat4 viewProjection;
      uniform float minZ;
      uniform float maxZ;
      uniform float maxDistance;
      uniform int colorMode;
      varying float vMetric;
      varying float vIntensity;
      void main() {
        vec4 p = viewProjection * vec4(position, 1.0);
        gl_Position = p;
        gl_PointSize = 2.0;
        float dist = length(position) / max(maxDistance, 0.001);
        float height = (position.z - minZ) / max(maxZ - minZ, 0.001);
        vMetric = colorMode == 1 ? height : (colorMode == 2 ? intensity : dist);
        vIntensity = intensity;
      }
    `;
    const fragmentSource = `
      precision mediump float;
      varying float vMetric;
      varying float vIntensity;
      uniform int colorMode;
      vec3 ramp(float t) {
        t = clamp(t, 0.0, 1.0);
        return mix(vec3(0.10, 0.65, 0.95), vec3(0.95, 0.92, 0.55), smoothstep(0.15, 0.75, t));
      }
      void main() {
        float d = distance(gl_PointCoord, vec2(0.5));
        if (d > 0.5) discard;
        vec3 color = colorMode == 2 ? vec3(0.25 + vIntensity * 0.75) : ramp(vMetric);
        gl_FragColor = vec4(color, 0.94);
      }
    `;
    this.program = this.createProgram(vertexSource, fragmentSource);
    this.buffer = this.gl.createBuffer();
    this.locations.position = this.gl.getAttribLocation(this.program, "position");
    this.locations.intensity = this.gl.getAttribLocation(this.program, "intensity");
    this.locations.viewProjection = this.gl.getUniformLocation(this.program, "viewProjection");
    this.locations.minZ = this.gl.getUniformLocation(this.program, "minZ");
    this.locations.maxZ = this.gl.getUniformLocation(this.program, "maxZ");
    this.locations.maxDistance = this.gl.getUniformLocation(this.program, "maxDistance");
    this.locations.colorMode = this.gl.getUniformLocation(this.program, "colorMode");
    this.gl.enable(this.gl.BLEND);
    this.gl.blendFunc(this.gl.SRC_ALPHA, this.gl.ONE_MINUS_SRC_ALPHA);
    this.clear("select PointCloud2 topic and stream");
    this.start();
  }

  createShader(type, source) {
    const shader = this.gl.createShader(type);
    this.gl.shaderSource(shader, source);
    this.gl.compileShader(shader);
    if (!this.gl.getShaderParameter(shader, this.gl.COMPILE_STATUS)) {
      throw new Error(this.gl.getShaderInfoLog(shader));
    }
    return shader;
  }

  createProgram(vertexSource, fragmentSource) {
    const program = this.gl.createProgram();
    this.gl.attachShader(program, this.createShader(this.gl.VERTEX_SHADER, vertexSource));
    this.gl.attachShader(program, this.createShader(this.gl.FRAGMENT_SHADER, fragmentSource));
    this.gl.linkProgram(program);
    if (!this.gl.getProgramParameter(program, this.gl.LINK_STATUS)) {
      throw new Error(this.gl.getProgramInfoLog(program));
    }
    return program;
  }

  loadPoints(points, message = "cloud loaded") {
    const count = Math.min(points.length, this.budget);
    this.points = points.slice(0, count);
    const data = new Float32Array(count * 4);
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    let maxDistance = 0;
    for (let index = 0; index < count; index += 1) {
      const point = points[index];
      const x = point[0];
      const y = point[1];
      const z = point[2];
      const intensity = point[3] ?? 0.65;
      data[index * 4] = x;
      data[index * 4 + 1] = y;
      data[index * 4 + 2] = z;
      data[index * 4 + 3] = intensity;
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
      maxDistance = Math.max(maxDistance, Math.hypot(x, y, z));
    }
    this.bounds = {
      minX: Number.isFinite(minX) ? minX : -1,
      maxX: Number.isFinite(maxX) ? maxX : 1,
      minY: Number.isFinite(minY) ? minY : -1,
      maxY: Number.isFinite(maxY) ? maxY : 1,
      minZ: Number.isFinite(minZ) ? minZ : -1,
      maxZ: Number.isFinite(maxZ) ? maxZ : 1,
      maxDistance: Math.max(1, maxDistance),
    };
    this.pointCount = count;
    if (!this.hasFramed) {
      this.frameBounds();
      this.hasFramed = true;
    }
    if (this.gl) {
      this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffer);
      this.gl.bufferData(this.gl.ARRAY_BUFFER, data, this.gl.DYNAMIC_DRAW);
    } else {
      this.drawFallback();
    }
    this.setStatus(message);
    this.statsNode.textContent = `${this.pointCount.toLocaleString()} pts · ${this.gl ? "loading" : "2D fallback"}`;
  }

  frameBounds() {
    const spanX = this.bounds.maxX - this.bounds.minX;
    const spanY = this.bounds.maxY - this.bounds.minY;
    const spanZ = this.bounds.maxZ - this.bounds.minZ;
    this.target = [
      (this.bounds.minX + this.bounds.maxX) / 2,
      (this.bounds.minY + this.bounds.maxY) / 2,
      (this.bounds.minZ + this.bounds.maxZ) / 2,
    ];
    this.distance = Math.max(2, Math.hypot(spanX, spanY, spanZ) * 1.8);
  }

  resizeCanvas() {
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

  resize() {
    this.resizeCanvas();
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
  }

  drawFallback() {
    if (!this.context2d) return;
    this.resizeCanvas();
    this.context2d.fillStyle = "#020303";
    this.context2d.fillRect(0, 0, this.canvas.width, this.canvas.height);
    if (!this.points.length) return;

    const spanX = Math.max(0.001, this.bounds.maxX - this.bounds.minX);
    const spanY = Math.max(0.001, this.bounds.maxY - this.bounds.minY);
    const scale = Math.min(this.canvas.width / spanX, this.canvas.height / spanY) * 0.88;
    const centerX = (this.bounds.minX + this.bounds.maxX) / 2;
    const centerY = (this.bounds.minY + this.bounds.maxY) / 2;
    const stride = Math.max(1, Math.ceil(this.points.length / 50000));
    for (let index = 0; index < this.points.length; index += stride) {
      const point = this.points[index];
      const x = this.canvas.width / 2 + (point[0] - centerX) * scale;
      const y = this.canvas.height / 2 - (point[1] - centerY) * scale;
      const color = this.fallbackColor(point);
      this.context2d.fillStyle = color;
      this.context2d.fillRect(x, y, 2, 2);
    }
  }

  fallbackColor(point) {
    const intensity = Math.max(0, Math.min(1, point[3] ?? 0.65));
    if (this.colorMode === 2) {
      const value = Math.round(64 + intensity * 191);
      return `rgb(${value},${value},${value})`;
    }
    const metric = this.colorMode === 1
      ? (point[2] - this.bounds.minZ) / Math.max(0.001, this.bounds.maxZ - this.bounds.minZ)
      : Math.hypot(point[0], point[1], point[2]) / Math.max(0.001, this.bounds.maxDistance);
    const t = Math.max(0, Math.min(1, metric));
    const r = Math.round(26 + t * 216);
    const g = Math.round(166 + t * 68);
    const b = Math.round(242 - t * 99);
    return `rgb(${r},${g},${b})`;
  }

  viewProjectionMatrix() {
    const aspect = this.canvas.width / Math.max(1, this.canvas.height);
    const eye = [
      this.target[0] + this.distance * Math.cos(this.pitch) * Math.sin(this.yaw),
      this.target[1] + this.distance * Math.cos(this.pitch) * Math.cos(this.yaw),
      this.target[2] + this.distance * Math.sin(this.pitch),
    ];
    return multiply(perspective(Math.PI / 4, aspect, 0.02, 2000), lookAt(eye, this.target, [0, 0, 1]));
  }

  render = () => {
    if (!this.gl) return;
    this.resize();
    this.updateKeyboard();
    this.gl.clearColor(0, 0, 0, 0);
    this.gl.clear(this.gl.COLOR_BUFFER_BIT | this.gl.DEPTH_BUFFER_BIT);
    this.gl.useProgram(this.program);
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffer);
    this.gl.enableVertexAttribArray(this.locations.position);
    this.gl.vertexAttribPointer(this.locations.position, 3, this.gl.FLOAT, false, 16, 0);
    this.gl.enableVertexAttribArray(this.locations.intensity);
    this.gl.vertexAttribPointer(this.locations.intensity, 1, this.gl.FLOAT, false, 16, 12);
    this.gl.uniformMatrix4fv(this.locations.viewProjection, false, this.viewProjectionMatrix());
    this.gl.uniform1f(this.locations.minZ, this.bounds.minZ);
    this.gl.uniform1f(this.locations.maxZ, this.bounds.maxZ);
    this.gl.uniform1f(this.locations.maxDistance, this.bounds.maxDistance);
    this.gl.uniform1i(this.locations.colorMode, this.colorMode);
    this.gl.drawArrays(this.gl.POINTS, 0, this.pointCount);
    this.frameCount += 1;
    const now = performance.now();
    if (now - this.lastFpsAt > 1000) {
      this.statsNode.textContent = `${this.pointCount.toLocaleString()} pts · ${this.frameCount} fps`;
      this.frameCount = 0;
      this.lastFpsAt = now;
    }
    this.animation = requestAnimationFrame(this.render);
  };

  start() {
    if (!this.animation) {
      this.animation = requestAnimationFrame(this.render);
    }
  }
}

function perspective(fov, aspect, near, far) {
  const f = 1 / Math.tan(fov / 2);
  const nf = 1 / (near - far);
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0,
  ]);
}

function lookAt(eye, center, up) {
  const z = normalize([eye[0] - center[0], eye[1] - center[1], eye[2] - center[2]]);
  const x = normalize(cross(up, z));
  const y = cross(z, x);
  return new Float32Array([
    x[0], y[0], z[0], 0,
    x[1], y[1], z[1], 0,
    x[2], y[2], z[2], 0,
    -dot(x, eye), -dot(y, eye), -dot(z, eye), 1,
  ]);
}

function multiply(a, b) {
  const out = new Float32Array(16);
  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      out[col * 4 + row] =
        a[0 * 4 + row] * b[col * 4 + 0] +
        a[1 * 4 + row] * b[col * 4 + 1] +
        a[2 * 4 + row] * b[col * 4 + 2] +
        a[3 * 4 + row] * b[col * 4 + 3];
    }
  }
  return out;
}

function normalize(v) {
  const length = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / length, v[1] / length, v[2] / length];
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
