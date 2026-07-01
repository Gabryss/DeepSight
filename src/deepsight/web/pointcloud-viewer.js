export class PointCloudViewer {
  constructor(canvas, statsNode, statusNode) {
    this.canvas = canvas;
    this.statsNode = statsNode;
    this.statusNode = statusNode;
    this.gl = canvas.getContext("webgl", { antialias: false, alpha: true, powerPreference: "high-performance" });
    this.pointCount = 0;
    this.budget = 50000;
    this.frameCount = 0;
    this.lastFpsAt = performance.now();
    this.rotation = 0;
    this.program = null;
    this.buffer = null;
    this.locations = {};
    this.animation = null;
    if (this.gl) {
      this.initGl();
    } else {
      this.setStatus("webgl unavailable");
    }
  }

  setStatus(value) {
    this.statusNode.textContent = value;
  }

  setBudget(value) {
    this.budget = Number.parseInt(value, 10) || 50000;
  }

  reset() {
    this.rotation = 0;
  }

  clear(message = "no cloud loaded") {
    this.pointCount = 0;
    if (this.gl && this.buffer) {
      this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffer);
      this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array(), this.gl.DYNAMIC_DRAW);
    }
    this.statsNode.textContent = "0 pts · 0 fps";
    this.setStatus(message);
  }

  initGl() {
    const vertexSource = `
      attribute vec3 position;
      attribute float intensity;
      uniform mat4 transform;
      varying float vIntensity;
      void main() {
        vec4 p = transform * vec4(position, 1.0);
        gl_Position = p;
        gl_PointSize = max(1.0, 3.5 - p.z * 1.3);
        vIntensity = intensity;
      }
    `;
    const fragmentSource = `
      precision mediump float;
      varying float vIntensity;
      void main() {
        float d = distance(gl_PointCoord, vec2(0.5));
        if (d > 0.5) discard;
        gl_FragColor = vec4(vec3(0.55 + vIntensity * 0.45), 0.92);
      }
    `;
    this.program = this.createProgram(vertexSource, fragmentSource);
    this.buffer = this.gl.createBuffer();
    this.locations.position = this.gl.getAttribLocation(this.program, "position");
    this.locations.intensity = this.gl.getAttribLocation(this.program, "intensity");
    this.locations.transform = this.gl.getUniformLocation(this.program, "transform");
    this.gl.enable(this.gl.BLEND);
    this.gl.blendFunc(this.gl.SRC_ALPHA, this.gl.ONE_MINUS_SRC_ALPHA);
    this.clear("select a bag topic and load");
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
    if (!this.gl) {
      return;
    }
    const count = Math.min(points.length, this.budget);
    const data = new Float32Array(count * 4);
    for (let index = 0; index < count; index += 1) {
      const point = points[index];
      data[index * 4] = point[0];
      data[index * 4 + 1] = point[1];
      data[index * 4 + 2] = point[2];
      data[index * 4 + 3] = point[3] ?? 0.65;
    }
    this.pointCount = count;
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffer);
    this.gl.bufferData(this.gl.ARRAY_BUFFER, data, this.gl.DYNAMIC_DRAW);
    this.setStatus(message);
    this.statsNode.textContent = `${this.pointCount.toLocaleString()} pts · loading`;
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
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
  }

  transformMatrix() {
    const aspect = this.canvas.width / Math.max(1, this.canvas.height);
    const c = Math.cos(this.rotation);
    const s = Math.sin(this.rotation);
    const scale = 0.82;
    return new Float32Array([
      scale / aspect * c, 0, scale / aspect * -s, 0,
      0, scale, 0, 0,
      scale * s, 0, scale * c, 0,
      0, 0, 0, 1,
    ]);
  }

  render = () => {
    if (!this.gl) {
      return;
    }
    this.resize();
    this.rotation += 0.0025;
    this.gl.clearColor(0, 0, 0, 0);
    this.gl.clear(this.gl.COLOR_BUFFER_BIT | this.gl.DEPTH_BUFFER_BIT);
    this.gl.useProgram(this.program);
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffer);
    this.gl.enableVertexAttribArray(this.locations.position);
    this.gl.vertexAttribPointer(this.locations.position, 3, this.gl.FLOAT, false, 16, 0);
    this.gl.enableVertexAttribArray(this.locations.intensity);
    this.gl.vertexAttribPointer(this.locations.intensity, 1, this.gl.FLOAT, false, 16, 12);
    this.gl.uniformMatrix4fv(this.locations.transform, false, this.transformMatrix());
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
