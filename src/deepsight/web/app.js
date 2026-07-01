import { CameraViewer } from "./camera-viewer.js";
import { CostmapViewer } from "./costmap-viewer.js";
import { PointCloudViewer } from "./pointcloud-viewer.js";

const state = {
  latest: null,
  bags: [],
  selectedBagPath: null,
  visualTopics: { point_cloud: [], camera: [], costmap: [] },
  cloudSocket: null,
  cameraSocket: null,
  mapSocket: null,
  costmapSocket: null,
  commandTarget: "all",
  topicDiscoveryIntervalMs: 30000,
  topicDiscoveryTimer: null,
};

const $ = (selector) => document.querySelector(selector);

function on(selector, eventName, handler) {
  const element = $(selector);
  if (element) {
    element.addEventListener(eventName, handler);
  }
}

function text(selector, value) {
  const element = $(selector);
  if (element) {
    element.textContent = value;
  }
}

function chip(value) {
  const span = document.createElement("span");
  span.className = "chip";
  span.textContent = value;
  return span;
}

function renderRobots(robots) {
  const root = $("#robots");
  root.replaceChildren();
  for (const robot of robots) {
    const card = document.createElement("div");
    card.className = "robot";
    const latency = robot.latency_ms == null ? "" : `${robot.latency_ms.toFixed(1)} ms`;
    card.innerHTML = `
      <div class="title"><strong>${robot.label}</strong><span class="dot ${robot.online ? "ok" : ""}"></span></div>
      <span class="muted">${robot.host}</span>
      <span>${robot.online ? "online" : "offline"} ${latency}</span>
    `;
    root.append(card);
  }
}

function renderBatteries(batteries) {
  const root = $("#batteries");
  root.replaceChildren();
  for (const battery of batteries) {
    const value = typeof battery.value === "number" ? Math.max(0, Math.min(100, battery.value * (battery.value <= 1 ? 100 : 1))) : null;
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="title"><strong>${battery.label}</strong><span>${value == null ? "n/a" : `${value.toFixed(0)}%`}</span></div>
      <div class="meter ${value != null && value < 25 ? "low" : ""}"><span style="width: ${value ?? 0}%"></span></div>
      <span class="muted">${battery.available ? battery.raw : "not configured"}</span>
    `;
    root.append(row);
  }
}

function renderCommands(commands) {
  const root = $("#commands");
  const targetSelect = $("#command-target-select");
  root.replaceChildren();
  if (!targetSelect.children.length) {
    targetSelect.replaceChildren(new Option("All targets", "all"));
  }
  for (const command of commands) {
    if (state.commandTarget !== "all" && command.target && command.target !== state.commandTarget) {
      continue;
    }
    const row = document.createElement("div");
    row.className = "command";
    row.innerHTML = `<strong>${command.label}</strong><span>${command.target || "base"}</span><button type="button" title="Run command">▶</button>`;
    row.querySelector("button").addEventListener("click", () => runCommand(command.id, row.querySelector("button")));
    root.append(row);
  }
  if (!root.children.length) {
    const empty = document.createElement("div");
    empty.className = "row";
    empty.textContent = "No commands for selected target.";
    root.append(empty);
  }
}

function renderRos(ros) {
  text("#ros-state", ros.available ? "Ready" : "Missing");
  text("#topic-count", String(ros.topics?.length ?? 0));
  const nodes = $("#nodes");
  const topics = $("#topics");
  nodes.replaceChildren(...(ros.nodes ?? []).map(chip));
  topics.replaceChildren(...(ros.topics ?? []).map(chip));
  text("#tf-tree", ros.tf_tree || ros.error || "No TF data");

  const bandwidth = $("#bandwidth");
  bandwidth.replaceChildren();
  for (const sample of ros.bandwidth ?? []) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="title"><strong>${sample.topic}</strong><span class="dot ${sample.ok ? "ok" : ""}"></span></div>
      <span class="muted">${sample.sample || sample.error || "no sample"}</span>
    `;
    bandwidth.append(row);
  }
}

function graphRow(label, percent, value, bad = false) {
  const row = document.createElement("div");
  row.className = "graph-row";
  row.innerHTML = `
    <span>${label}</span>
    <div class="bar ${bad ? "bad" : ""}"><i style="--value: ${Math.max(0, Math.min(100, percent))}%"></i></div>
    <strong>${value}</strong>
  `;
  return row;
}

function renderNetwork(payload) {
  const connectivity = $("#network-connectivity");
  const bandwidth = $("#network-bandwidth");
  connectivity.replaceChildren();
  bandwidth.replaceChildren();

  const robots = payload.robots ?? [];
  const online = robots.filter((robot) => robot.online).length;
  text("#network-online", `${online}/${robots.length}`);
  text("#network-mode", payload.middleware_mode.toUpperCase());
  text("#network-loss", robots.length ? `${Math.round(((robots.length - online) / robots.length) * 100)}%` : "n/a");

  for (const robot of robots) {
    const latency = typeof robot.latency_ms === "number" ? robot.latency_ms : null;
    const score = robot.online ? Math.max(8, 100 - Math.min(100, latency ?? 50)) : 0;
    connectivity.append(graphRow(robot.label, score, robot.online ? `${latency?.toFixed(0) ?? "?"} ms` : "down", !robot.online));
  }

  for (const sample of payload.ros?.bandwidth ?? []) {
    const match = String(sample.sample ?? "").match(/([0-9.]+)\s*(KB|MB|B)\/s/i);
    let value = match ? Number.parseFloat(match[1]) : 0;
    if (match?.[2]?.toUpperCase() === "MB") {
      value *= 1024;
    }
    const percent = Math.min(100, value / 20);
    bandwidth.append(graphRow(sample.topic, percent, sample.sample || "no sample", !sample.ok));
  }

  if (!bandwidth.children.length) {
    bandwidth.append(graphRow("ros2 topic bw", 0, "no samples", true));
  }
}

function renderTools(groups) {
  const root = $("#tools");
  root.replaceChildren();
  for (const group of groups) {
    const title = document.createElement("h3");
    title.textContent = group.category;
    root.append(title);
    for (const tool of group.tools) {
      const row = document.createElement("div");
      row.className = "row";
      const available = tool.available === null ? "manual" : tool.available ? "ok" : "missing";
      row.innerHTML = `
        <div class="title"><strong>${tool.name}</strong><span>${available}</span></div>
        <span class="muted">${tool.required ? "required" : "optional"}</span>
      `;
      root.append(row);
    }
  }
}

function formatBytes(value) {
  if (!value) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function selectedBag() {
  return state.bags.find((bag) => bag.path === state.selectedBagPath) ?? state.bags[0] ?? null;
}

function renderPostProcessingControls() {
  const select = $("#post-bag-select");
  const summary = $("#post-bag-summary");
  const topicsRoot = $("#post-topic-list");
  const current = selectedBag();
  select.replaceChildren();
  summary.replaceChildren();
  topicsRoot.replaceChildren();

  for (const bag of state.bags) {
    const option = document.createElement("option");
    option.value = bag.path;
    option.textContent = bag.name;
    option.selected = bag.path === current?.path;
    select.append(option);
  }

  if (!current) {
    summary.textContent = "No bags available under bag_root.";
    return;
  }

  state.selectedBagPath = current.path;
  summary.innerHTML = `
    <span>${current.path}</span>
    <strong>${current.message_count} messages · ${current.topic_count} topics · ${current.duration_sec ?? "?"}s · ${formatBytes(current.size_bytes)}</strong>
    <span>visual: ${(current.capabilities?.visualizable ?? []).join(", ") || "none"}</span>
  `;

  for (const topic of current.topics ?? []) {
    const label = document.createElement("label");
    label.className = "topic-option";
    label.innerHTML = `
      <input type="checkbox" value="${topic.name}" />
      <span><strong>${topic.name}</strong><span>${topic.type}</span></span>
      <span>${topic.messages}</span>
    `;
    topicsRoot.append(label);
  }
}

function renderBags(payload) {
  const root = $("#bags");
  root.replaceChildren();
  if (!payload.available) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<strong>Unavailable</strong><span class="muted">${payload.error}</span>`;
    root.append(row);
    return;
  }

  for (const bag of payload.bags) {
    const topTopics = (bag.topics ?? [])
      .slice()
      .sort((left, right) => right.messages - left.messages)
      .slice(0, 3)
      .map((topic) => `${topic.name} (${topic.messages})`)
      .join(" | ");
    const row = document.createElement("div");
    row.className = "row bag-row";
    row.innerHTML = `
      <div class="title"><strong>${bag.name}</strong><span>${bag.duration_sec ?? "?"}s</span></div>
      <span class="muted">${bag.message_count} msgs · ${bag.topic_count} topics · ${formatBytes(bag.size_bytes)}</span>
      <span class="muted">${topTopics || "no topics"}</span>
      <span class="muted">visual: ${(bag.capabilities?.visualizable ?? []).join(", ") || "none"} · missing: ${(bag.capabilities?.missing_for_full_monitoring ?? []).join(", ") || "none"}</span>
    `;
    root.append(row);
  }

  state.bags = payload.bags ?? [];
  if (!state.selectedBagPath && state.bags.length) {
    state.selectedBagPath = state.bags[0].path;
  }
  renderPostProcessingControls();
}

function optionLabel(topic) {
  return `${topic.name} [${topic.source}]`;
}

function entityFromTopicName(name) {
  return String(name || "").split("/").filter(Boolean)[0] || "base";
}

function fillTopicSelect(select, topics, emptyLabel, entity = "all") {
  const selected = select.value;
  select.replaceChildren();
  const filtered = entity === "all" ? topics : topics.filter((topic) => entityFromTopicName(topic.name) === entity);
  if (!filtered.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = emptyLabel;
    select.append(option);
    select.disabled = true;
    return;
  }
  select.disabled = false;
  for (const topic of filtered) {
    const option = document.createElement("option");
    option.value = topic.name;
    option.textContent = optionLabel(topic);
    option.selected = topic.name === selected;
    select.append(option);
  }
}

function fillEntitySelect(select, entities) {
  const selected = select.value || "all";
  select.replaceChildren(new Option("All entities", "all"));
  for (const entity of entities ?? []) {
    select.append(new Option(entity, entity));
  }
  select.value = [...select.options].some((option) => option.value === selected) ? selected : "all";
}

function selectedTopic(topics, name) {
  return (topics ?? []).find((topic) => topic.name === name) ?? null;
}

function renderVisualTopics(payload) {
  state.visualTopics = payload;
  if (payload.next_refresh_sec) {
    scheduleTopicDiscovery(payload.next_refresh_sec);
  }
  fillEntitySelect($("#map-entity-select"), payload.entities ?? []);
  fillEntitySelect($("#camera-entity-select"), payload.entities ?? []);
  fillEntitySelect($("#costmap-entity-select"), payload.entities ?? []);
  fillTopicSelect($("#cloud-topic-select"), payload.point_cloud ?? [], "no point cloud topics");
  fillTopicSelect($("#camera-topic-select"), payload.camera ?? [], "no camera topics", $("#camera-entity-select").value || "all");
  fillTopicSelect($("#camera-info-topic-select"), payload.camera_info ?? [], "no camera metadata topics", $("#camera-entity-select").value || "all");
  fillTopicSelect($("#map-topic-select"), payload.costmap ?? [], "no costmap topics", $("#map-entity-select").value || "all");
  fillTopicSelect($("#costmap-topic-select"), payload.costmap ?? [], "no costmap topics", $("#costmap-entity-select").value || "all");
  $("#cloud-status").textContent = (payload.point_cloud ?? []).length ? "PointCloud2 topic available" : "no PointCloud2 topic detected";
  $("#camera-status").textContent = (payload.camera ?? []).length ? "camera topic available" : "no Image topic detected";
  $("#map-status").textContent = (payload.costmap ?? []).length ? "costmap topic available" : "no OccupancyGrid topic detected";
  $("#costmap-status").textContent = (payload.costmap ?? []).length ? "costmap topic available" : "no OccupancyGrid topic detected";
  if (state.latest) {
    renderCommandTargets(state.latest);
  }
}

function render(payload) {
  state.latest = payload;
  text("#mission-name", payload.mission.name);
  const online = payload.robots.filter((robot) => robot.online).length;
  text("#robot-count", `${online}/${payload.robots.length}`);
  text("#mode-state", payload.middleware_mode.toUpperCase());
  $("#mode-dds").classList.toggle("active", payload.middleware_mode === "dds");
  $("#mode-zenoh").classList.toggle("active", payload.middleware_mode === "zenoh");
  renderRobots(payload.robots);
  renderBatteries(payload.batteries);
  renderCommandTargets(payload);
  renderRos(payload.ros);
  renderNetwork(payload);
  renderTools(payload.tools);
}

function renderCommandTargets(payload) {
  const select = $("#command-target-select");
  const targets = new Map([["all", "All targets"]]);
  for (const robot of payload.robots ?? []) {
    targets.set(robot.id, robot.label);
  }
  for (const entity of state.visualTopics.entities ?? []) {
    if (!targets.has(entity)) targets.set(entity, entity);
  }
  const current = state.commandTarget;
  select.replaceChildren();
  for (const [value, label] of targets) {
    select.append(new Option(label, value));
  }
  state.commandTarget = targets.has(current) ? current : "all";
  select.value = state.commandTarget;
  renderCommands(payload.commands);
}

function activateTab(button) {
  const targetId = button.dataset.tabTarget;
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  const group = button.closest(".stage-tabs, .inspector-tabs, .bottom-tabs");
  const scope = target.parentElement;
  if (!group || !scope) {
    return;
  }
  group.querySelectorAll(".tab-button").forEach((tab) => {
    tab.classList.toggle("active", tab === button);
  });
  scope.querySelectorAll(".tab-panel, .inspector-panel, .console-panel").forEach((panel) => {
    panel.classList.toggle("active", panel === target);
  });
}

async function refresh() {
  const response = await fetch("/api/status");
  render(await response.json());
}

async function refreshBags() {
  const response = await fetch("/api/bags");
  renderBags(await response.json());
}

async function refreshVisualTopics() {
  const response = await fetch("/api/visual/topics");
  renderVisualTopics(await response.json());
}

async function refreshVisualTopicsNow() {
  const response = await fetch("/api/visual/topics?refresh=true");
  renderVisualTopics(await response.json());
}

function scheduleTopicDiscovery(intervalSec) {
  const nextMs = Math.max(5000, Number(intervalSec || 30) * 1000);
  if (state.topicDiscoveryTimer && state.topicDiscoveryIntervalMs === nextMs) {
    return;
  }
  if (state.topicDiscoveryTimer) {
    clearInterval(state.topicDiscoveryTimer);
  }
  state.topicDiscoveryIntervalMs = nextMs;
  state.topicDiscoveryTimer = setInterval(refreshVisualTopics, nextMs);
}

async function refreshPostProcessingStatus() {
  const response = await fetch("/api/post-processing/status");
  const status = await response.json();
  const progress = Math.max(0, Math.min(100, status.progress_percent ?? 0));
  $("#post-progress-fill").style.width = `${progress}%`;
  $("#post-progress-label").textContent = `${progress.toFixed(0)}%`;
  $("#post-play").disabled = Boolean(status.running);
  $("#post-stop").disabled = !status.running;
  $("#post-status").textContent = [
    `state: ${status.state ?? (status.running ? "running" : "idle")}`,
    status.running ? `pid: ${status.pid}` : "",
    status.bag_path,
    status.topics?.length ? `topics: ${status.topics.join(", ")}` : "topics: all",
    `rate: ${status.rate ?? 1}`,
    `loop: ${status.loop ? "yes" : "no"}`,
    status.duration_sec ? `duration: ${status.duration_sec}s` : "",
    status.returncode != null ? `returncode: ${status.returncode}` : "",
    status.log_tail ? `\nlog:\n${status.log_tail}` : "",
  ].filter(Boolean).join("\n");
}

async function loadPointCloudSample(button) {
  stopPointCloudStream("loading bag sample");
  const bag = selectedBag();
  const topic = $("#cloud-topic-select").value;
  if (!bag || !topic) {
    cloudViewer.clear("select a bag and PointCloud2 topic");
    return;
  }

  button.disabled = true;
  cloudViewer.clear("loading bag cloud...");
  try {
    const response = await fetch("/api/visual/pointcloud-sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bag_path: bag.path,
        topic,
        max_points: Number.parseInt($("#cloud-point-budget").value, 10) || 50000,
      }),
    });
    const payload = await response.json();
    if (!payload.ok) {
      cloudViewer.clear(payload.error || "could not load PointCloud2 sample");
      return;
    }
    cloudViewer.loadPoints(payload.points ?? []);
    $("#cloud-status").textContent = `${payload.topic} · ${payload.point_count} pts`;
    $("#selected-cloud-topic").textContent = payload.topic;
  } catch (error) {
    cloudViewer.clear(`point cloud load failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function stopPointCloudStream(message = "stream stopped") {
  if (state.cloudSocket) {
    state.cloudSocket.close();
    state.cloudSocket = null;
  }
  $("#cloud-stream").disabled = false;
  $("#cloud-stop").disabled = true;
  if (message) {
    $("#cloud-status").textContent = message;
  }
}

function stopSocket(key, messageNode, message = "") {
  if (state[key]) {
    state[key].close();
    state[key] = null;
  }
  if (messageNode && message) {
    messageNode.textContent = message;
  }
}

function openVisualSocket(path, params, key, onMessage, onClose) {
  stopSocket(key);
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}${path}?${params.toString()}`);
  state[key] = socket;
  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (!payload.ok) {
      onMessage(payload);
      return;
    }
    onMessage(payload);
  });
  socket.addEventListener("close", () => {
    if (state[key] === socket) {
      state[key] = null;
      onClose?.();
    }
  });
  socket.addEventListener("error", () => {
    onMessage({ ok: false, error: "stream error" });
  });
  return socket;
}

function startPointCloudStream(button) {
  const topic = $("#cloud-topic-select").value;
  if (!topic) {
    cloudViewer.clear("select a PointCloud2 topic");
    return;
  }
  stopPointCloudStream("");
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const params = new URLSearchParams({
    topic,
    max_points: $("#cloud-point-budget").value || "50000",
    rate_hz: "5",
  });
  const socket = new WebSocket(`${protocol}://${location.host}/api/visual/pointcloud-live?${params.toString()}`);
  state.cloudSocket = socket;
  button.disabled = true;
  $("#cloud-stop").disabled = false;
  cloudViewer.clear(`streaming ${topic}...`);

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (!payload.ok) {
      cloudViewer.clear(payload.error || "point cloud stream failed");
      return;
    }
    cloudViewer.loadPoints(payload.points ?? [], "live cloud frame");
    $("#cloud-status").textContent = `${payload.topic} · ${payload.point_count} live pts`;
    $("#selected-cloud-topic").textContent = payload.topic;
  });
  socket.addEventListener("close", () => {
    if (state.cloudSocket === socket) {
      state.cloudSocket = null;
      $("#cloud-stream").disabled = false;
      $("#cloud-stop").disabled = true;
    }
  });
  socket.addEventListener("error", () => {
    cloudViewer.clear("point cloud stream error");
  });
}

function startCameraStream() {
  const topicName = $("#camera-topic-select").value;
  const topic = selectedTopic(state.visualTopics.camera, topicName);
  if (!topic) {
    cameraViewer.clear("select an Image or CompressedImage topic");
    return;
  }
  cameraViewer.clear(`streaming ${topic.name}...`);
  openVisualSocket(
    "/api/visual/camera-live",
    new URLSearchParams({ topic: topic.name, topic_type: topic.type, rate_hz: "10" }),
    "cameraSocket",
    (payload) => {
      if (!payload.ok) {
        cameraViewer.clear(payload.error || "camera stream failed");
        return;
      }
      cameraViewer.loadFrame(payload);
    },
  );
}

function startCostmapStream(selectId, socketKey, viewer, statusId) {
  const topic = $(selectId).value;
  if (!topic) {
    viewer.clear("select an OccupancyGrid topic");
    return;
  }
  viewer.clear(`streaming ${topic}...`);
  openVisualSocket(
    "/api/visual/costmap-live",
    new URLSearchParams({ topic, rate_hz: "2" }),
    socketKey,
    (payload) => {
      if (!payload.ok) {
        viewer.clear(payload.error || "costmap stream failed");
        return;
      }
      viewer.loadGrid(payload);
    },
    () => {
      $(statusId).textContent = "stream stopped";
    },
  );
}

async function playPostProcessingBag() {
  const bag = selectedBag();
  if (!bag) {
    $("#post-status").textContent = "No bag selected.";
    return;
  }
  const topics = Array.from(document.querySelectorAll("#post-topic-list input:checked")).map((input) => input.value);
  const response = await fetch("/api/post-processing/play", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bag_path: bag.path,
      topics,
      rate: Number.parseFloat($("#post-rate").value || "1"),
      loop: $("#post-loop").checked,
    }),
  });
  const payload = await response.json();
  $("#post-status").textContent = payload.ok ? "playback started" : payload.error;
  await refreshPostProcessingStatus();
}

async function stopPostProcessingBag() {
  const response = await fetch("/api/post-processing/stop", { method: "POST" });
  const payload = await response.json();
  $("#post-status").textContent = payload.ok ? "playback stopped" : payload.error;
  await refreshPostProcessingStatus();
}

async function setMode(mode) {
  await fetch("/api/middleware", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  await refresh();
}

async function runCommand(commandId, button) {
  button.disabled = true;
  const output = $("#console-log");
  output.textContent = "running...";
  try {
    const response = await fetch("/api/commands/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command_id: commandId }),
    });
    const result = await response.json();
    output.textContent = [
      `${result.label}: ${result.ok ? "ok" : "failed"}`,
      result.stdout,
      result.stderr,
    ].filter(Boolean).join("\n");
  } finally {
    button.disabled = false;
  }
}

function connectLive() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/live`);
  socket.addEventListener("message", (event) => render(JSON.parse(event.data)));
  socket.addEventListener("close", () => setTimeout(connectLive, 3000));
}

document.querySelectorAll("[data-tab-target]").forEach((button) => {
  button.addEventListener("click", () => activateTab(button));
});

on("#refresh", "click", () => {
  refresh();
  refreshVisualTopicsNow();
});
on("#mode-dds", "click", () => setMode("dds"));
on("#mode-zenoh", "click", () => setMode("zenoh"));
on("#post-bag-select", "change", (event) => {
  state.selectedBagPath = event.target.value;
  renderPostProcessingControls();
});
on("#post-play", "click", playPostProcessingBag);
on("#post-stop", "click", stopPostProcessingBag);
const cloudViewer = new PointCloudViewer($("#cloud-canvas"), $("#cloud-stats"), $("#cloud-status"));
const cameraViewer = new CameraViewer($("#camera-canvas"), $("#camera-stats"), $("#camera-status"));
const mapViewer = new CostmapViewer($("#map-canvas"), $("#map-stats"), $("#map-status"), "map");
const costmapViewer = new CostmapViewer($("#costmap-canvas"), $("#costmap-stats"), $("#costmap-status"), "costmap");
if ($("#cloud-stop")) {
  $("#cloud-stop").disabled = true;
}
on("#cloud-point-budget", "change", (event) => cloudViewer.setBudget(event.target.value));
on("#cloud-color-mode", "change", (event) => cloudViewer.setColorMode(event.target.value));
on("#cloud-reset", "click", () => cloudViewer.reset());
on("#cloud-load", "click", (event) => loadPointCloudSample(event.target));
on("#cloud-stream", "click", (event) => startPointCloudStream(event.target));
on("#cloud-stop", "click", () => stopPointCloudStream());
on("#cloud-topic-select", "change", (event) => {
  stopPointCloudStream("");
  cloudViewer.clear(event.target.value ? `selected ${event.target.value}` : "no PointCloud2 topic detected");
  $("#selected-cloud-topic").textContent = event.target.value || "none";
});
on("#camera-pause", "click", (event) => {
  event.target.textContent = cameraViewer.togglePause() ? "Resume" : "Pause";
});
on("#camera-topic-select", "change", (event) => {
  stopSocket("cameraSocket");
  cameraViewer.clear(event.target.value ? `selected ${event.target.value}` : "no Image topic detected");
  if (event.target.value) {
    startCameraStream();
  }
});
on("#camera-info-topic-select", "change", (event) => {
  $("#camera-status").textContent = event.target.value ? `metadata ${event.target.value}` : "no metadata selected";
});
on("#camera-entity-select", "change", () => {
  const entity = $("#camera-entity-select").value;
  fillTopicSelect($("#camera-topic-select"), state.visualTopics.camera ?? [], "no camera topics", entity);
  fillTopicSelect($("#camera-info-topic-select"), state.visualTopics.camera_info ?? [], "no camera metadata topics", entity);
  stopSocket("cameraSocket");
  if ($("#camera-topic-select").value) {
    startCameraStream();
  }
});
on("#map-entity-select", "change", () => {
  stopSocket("mapSocket");
  fillTopicSelect($("#map-topic-select"), state.visualTopics.costmap ?? [], "no costmap topics", $("#map-entity-select").value);
});
on("#map-load", "click", () => {
  startCostmapStream("#map-topic-select", "mapSocket", mapViewer, "#map-status");
});
on("#costmap-entity-select", "change", () => {
  stopSocket("costmapSocket");
  fillTopicSelect($("#costmap-topic-select"), state.visualTopics.costmap ?? [], "no costmap topics", $("#costmap-entity-select").value);
});
on("#costmap-load", "click", () => {
  startCostmapStream("#costmap-topic-select", "costmapSocket", costmapViewer, "#costmap-status");
});
on("#command-target-select", "change", (event) => {
  state.commandTarget = event.target.value;
  renderCommands(state.latest?.commands ?? []);
});

refresh();
refreshBags();
refreshVisualTopics();
refreshPostProcessingStatus();
setInterval(refreshPostProcessingStatus, 2000);
connectLive();
