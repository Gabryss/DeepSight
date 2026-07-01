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
  visibleEntities: [],
  networkHistory: new Map(),
  selectedNetworkTopics: new Set(),
  previousPlaybackRunning: false,
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

const GLOBAL_TOPIC_NAMES = new Set([
  "/battery_state",
  "/clock",
  "/events",
  "/parameter_events",
  "/rosout",
  "/rousout",
  "/tf",
  "/tf_static",
  "/tf_statics",
]);

function renderRobots(entities) {
  const root = $("#robots");
  root.replaceChildren();
  for (const entity of entities) {
    const card = document.createElement("div");
    card.className = "robot";
    card.innerHTML = `
      <div class="title"><strong>${entity}</strong><span class="dot ok"></span></div>
      <span class="muted">ROS namespace</span>
      <span>visible in topic graph</span>
    `;
    root.append(card);
  }
  if (!entities.length) {
    const empty = document.createElement("div");
    empty.className = "row";
    empty.textContent = "No robot namespaces visible.";
    root.append(empty);
  }
}

function batteryTopicsForEntity(entity, topics) {
  const prefix = `/${entity}/`;
  return (topics ?? []).filter((topic) => String(topic).startsWith(prefix) && String(topic).toLowerCase().includes("battery"));
}

function renderBatteries(entities, topics) {
  const root = $("#batteries");
  root.replaceChildren();
  for (const entity of entities) {
    const batteryTopics = batteryTopicsForEntity(entity, topics);
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="title"><strong>${entity}</strong><span>${batteryTopics.length ? "topic" : "n/a"}</span></div>
      <div class="meter"><span style="width: 0%"></span></div>
      <span class="muted">${batteryTopics[0] || "no namespace battery topic detected"}</span>
    `;
    root.append(row);
  }
  if (!entities.length) {
    const empty = document.createElement("div");
    empty.className = "row";
    empty.textContent = "No robot namespaces visible.";
    root.append(empty);
  }
}

function renderCommands(commands) {
  const root = $("#commands");
  const targetSelect = $("#command-target-select");
  root.replaceChildren();
  if (!targetSelect.children.length) {
    targetSelect.replaceChildren(new Option("All visible", "all"));
  }
  const visible = new Set(state.visibleEntities);
  for (const command of commands) {
    if (state.commandTarget === "all" && command.target && !visible.has(command.target)) {
      continue;
    }
    if (state.commandTarget !== "all" && command.target && command.target !== state.commandTarget) {
      continue;
    }
    if (state.commandTarget !== "all" && !command.target) {
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

function renderRosActivity(activity) {
  const stateName = activity?.state ?? "idle";
  const detail = activity?.detail ? ` · ${activity.detail}` : "";
  text("#ros-activity", `${stateName}${detail}`);
}

function stateRow(label, value, ok = true) {
  const row = document.createElement("div");
  row.className = "state-row";
  row.innerHTML = `
    <i class="${ok ? "ok" : "bad"}"></i>
    <span>${label}</span>
    <strong>${value}</strong>
  `;
  return row;
}

function parseBandwidth(sample) {
  const match = String(sample ?? "").match(/([0-9.]+)\s*(KB|MB|B)\/s/i);
  if (!match) return 0;
  let value = Number.parseFloat(match[1]);
  if (match[2].toUpperCase() === "MB") value *= 1024;
  if (match[2].toUpperCase() === "B") value /= 1024;
  return value;
}

const NETWORK_COLORS = ["#d9dcdb", "#ff5a4d", "#72d0ff", "#d4ba63", "#90d8a2", "#c89cff"];

function renderNetworkTopicPicker(samples) {
  const root = $("#network-topic-picker");
  if (!root) return;
  const topics = samples.map((sample) => sample.topic);
  if (!state.selectedNetworkTopics.size && topics.length) {
    topics.slice(0, 3).forEach((topic) => state.selectedNetworkTopics.add(topic));
  }
  for (const topic of [...state.selectedNetworkTopics]) {
    if (!topics.includes(topic)) state.selectedNetworkTopics.delete(topic);
  }
  root.replaceChildren();
  for (const topic of topics) {
    const label = document.createElement("label");
    label.className = "topic-toggle";
    label.innerHTML = `<input type="checkbox" value="${topic}" ${state.selectedNetworkTopics.has(topic) ? "checked" : ""} /><span>${topic}</span>`;
    label.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) state.selectedNetworkTopics.add(topic);
      else state.selectedNetworkTopics.delete(topic);
      drawNetworkGraph();
    });
    root.append(label);
  }
}

function drawNetworkGraph() {
  const canvas = $("#network-graph");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const width = Math.max(1, canvas.clientWidth);
  const height = Math.max(1, canvas.clientHeight);
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * scale);
  canvas.height = Math.floor(height * scale);
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.fillStyle = "#050607";
  context.fillRect(0, 0, width, height);
  context.strokeStyle = "rgba(255,255,255,.10)";
  context.lineWidth = 1;
  for (let index = 1; index < 4; index += 1) {
    const y = (height / 4) * index;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }
  const selected = [...state.selectedNetworkTopics];
  const histories = selected.map((topic) => state.networkHistory.get(topic) ?? []);
  const maxValue = Math.max(1, ...histories.flat().map((sample) => sample.value));
  const now = performance.now();
  const windowSec = Math.max(2, Math.min(120, Number.parseFloat($("#network-window-sec")?.value || "10") || 10));
  selected.forEach((topic, topicIndex) => {
    const samples = (state.networkHistory.get(topic) ?? []).filter((sample) => now - sample.at <= windowSec * 1000);
    context.strokeStyle = NETWORK_COLORS[topicIndex % NETWORK_COLORS.length];
    context.lineWidth = 2;
    context.beginPath();
    samples.forEach((sample, index) => {
      const age = Math.max(0, now - sample.at);
      const x = width - (age / (windowSec * 1000)) * width;
      const y = height - (sample.value / maxValue) * (height - 12) - 6;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.stroke();
  });

  const legend = $("#network-legend");
  if (legend) {
    legend.replaceChildren();
    selected.forEach((topic, index) => {
      const item = document.createElement("span");
      item.innerHTML = `<i style="background:${NETWORK_COLORS[index % NETWORK_COLORS.length]}"></i>${topic}`;
      legend.append(item);
    });
  }
}

function renderNetwork(payload) {
  const connectivity = $("#network-connectivity");
  const bandwidth = $("#network-bandwidth");
  connectivity.replaceChildren();
  bandwidth.replaceChildren();

  const robots = payload.robots ?? [];
  const visibleEntities = payload.visible_entities ?? state.visibleEntities ?? [];
  const online = robots.filter((robot) => robot.online).length;
  text("#network-online", visibleEntities.length ? `${visibleEntities.length}/${visibleEntities.length}` : `${online}/${robots.length}`);
  text("#network-mode", payload.middleware_mode.toUpperCase());
  text("#network-loss", visibleEntities.length ? "0%" : robots.length ? `${Math.round(((robots.length - online) / robots.length) * 100)}%` : "n/a");

  for (const entity of visibleEntities) {
    connectivity.append(stateRow(entity, `online · ${payload.middleware_mode.toUpperCase()}`, true));
  }
  if (!visibleEntities.length) {
    for (const robot of robots) {
      const latency = typeof robot.latency_ms === "number" ? robot.latency_ms : null;
      connectivity.append(stateRow(robot.label, robot.online ? `${latency?.toFixed(0) ?? "?"} ms` : "down", robot.online));
    }
  }

  let totalBandwidthKb = 0;
  for (const sample of payload.ros?.bandwidth ?? []) {
    const value = parseBandwidth(sample.sample);
    totalBandwidthKb += value;
    const history = state.networkHistory.get(sample.topic) ?? [];
    history.push({ at: performance.now(), value });
    state.networkHistory.set(sample.topic, history.slice(-240));
    bandwidth.append(stateRow(sample.topic, sample.sample || sample.error || "no sample", sample.ok));
  }

  if (!bandwidth.children.length) {
    bandwidth.append(stateRow("ros2 topic bw", "no samples", false));
  }
  renderNetworkTopicPicker(payload.ros?.bandwidth ?? []);
  drawNetworkGraph(totalBandwidthKb);
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
  const metrics = $("#post-bag-metrics");
  const topicStats = $("#post-topic-stats");
  const topicsRoot = $("#post-topic-list");
  if (!select || !summary || !topicsRoot) {
    return;
  }
  const current = selectedBag();
  select.replaceChildren();
  summary.replaceChildren();
  metrics?.replaceChildren();
  topicStats?.replaceChildren();
  topicsRoot.replaceChildren();

  for (const bag of state.bags) {
    const option = document.createElement("option");
    option.value = bag.path;
    option.textContent = bag.name;
    option.selected = bag.path === current?.path;
    select.append(option);
  }

  if (!current) {
    select.append(new Option("No bags found", ""));
    select.disabled = true;
    summary.textContent = "No bags available under bag_root.";
    return;
  }

  select.disabled = false;
  state.selectedBagPath = current.path;
  const capabilities = current.capabilities ?? {};
  const available = Object.entries(capabilities.available ?? {}).filter(([, value]) => value).map(([name]) => name);
  const missing = capabilities.missing_for_full_monitoring ?? [];
  summary.innerHTML = `
    <strong>${current.name}</strong>
    <span>${current.path}</span>
    <span>storage: ${current.storage || "unknown"} · ROS: ${current.ros_distro || "unknown"}</span>
  `;
  if (metrics) {
    const metricValues = [
      ["duration", `${current.duration_sec ?? "?"}s`],
      ["messages", current.message_count ?? 0],
      ["topics", current.topic_count ?? 0],
      ["size", formatBytes(current.size_bytes)],
    ];
    for (const [label, value] of metricValues) {
      const card = document.createElement("div");
      card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
      metrics.append(card);
    }
  }
  if (topicStats) {
    topicStats.innerHTML = `
      <span>available: ${available.join(", ") || "none"}</span>
      <span>missing: ${missing.join(", ") || "none"}</span>
      <span>selected topics play as a filtered rosbag; leave unchecked to play all topics.</span>
    `;
  }

  for (const topic of (current.topics ?? []).slice().sort((left, right) => right.messages - left.messages)) {
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
  const select = $("#post-bag-select");
  const summary = $("#post-bag-summary");
  const metrics = $("#post-bag-metrics");
  const topicStats = $("#post-topic-stats");
  const topicsRoot = $("#post-topic-list");
  root.replaceChildren();
  if (!payload.available) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<strong>Unavailable</strong><span class="muted">${payload.error}</span>`;
    root.append(row);
    state.bags = [];
    if (select && summary && topicsRoot) {
      select.replaceChildren(new Option(`Unavailable: ${payload.error || "bag inventory failed"}`, ""));
      select.disabled = true;
      summary.textContent = `Bag root ${payload.root || "not configured"}: ${payload.error || "unavailable"}`;
      metrics?.replaceChildren();
      topicStats?.replaceChildren();
      topicsRoot.replaceChildren();
    }
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
  if (!state.bags.length) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<strong>No bags found</strong><span class="muted">${payload.root || "bag_root"}</span>`;
    root.append(row);
  }
  if (!state.selectedBagPath && state.bags.length) {
    state.selectedBagPath = state.bags[0].path;
  }
  renderPostProcessingControls();
}

function optionLabel(topic) {
  return `${topic.name} [${topic.source}]`;
}

function entityFromTopicName(name) {
  const topic = String(name || "");
  if (GLOBAL_TOPIC_NAMES.has(topic)) return "";
  const entity = topic.split("/").filter(Boolean)[0] || "";
  return GLOBAL_TOPIC_NAMES.has(`/${entity}`) ? "" : entity;
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
  state.visibleEntities = payload.visible_entities ?? [];
  text("#mission-name", payload.mission.name);
  if ($("#ros-domain-id") && document.activeElement !== $("#ros-domain-id")) {
    $("#ros-domain-id").value = payload.mission.ros_domain_id ?? "";
  }
  text("#robot-count", `${state.visibleEntities.length}/${state.visibleEntities.length}`);
  text("#mode-state", payload.middleware_mode.toUpperCase());
  $("#mode-dds").classList.toggle("active", payload.middleware_mode === "dds");
  $("#mode-zenoh").classList.toggle("active", payload.middleware_mode === "zenoh");
  renderRobots(state.visibleEntities);
  renderBatteries(state.visibleEntities, payload.ros?.topics ?? []);
  renderCommandTargets(payload);
  renderRos(payload.ros);
  renderRosActivity(payload.ros_activity);
  renderNetwork(payload);
  renderTools(payload.tools);
}

function renderCommandTargets(payload) {
  const select = $("#command-target-select");
  const targets = new Map([["all", "All visible"]]);
  for (const entity of state.visibleEntities ?? []) {
    targets.set(entity, entity);
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
  const select = $("#post-bag-select");
  const summary = $("#post-bag-summary");
  if (select && !select.children.length) {
    select.replaceChildren(new Option("Loading bags...", ""));
    select.disabled = true;
  }
  try {
    const response = await fetch("/api/bags");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    renderBags(await response.json());
  } catch (error) {
    renderBags({ available: false, root: null, bags: [], error: error.message });
    if (summary) {
      summary.textContent = `Could not load bag inventory: ${error.message}`;
    }
  }
}

async function refreshVisualTopics() {
  const response = await fetch("/api/visual/topics");
  renderVisualTopics(await response.json());
}

async function refreshVisualTopicsNow() {
  renderRosActivity({ state: "updating", detail: "manual topic refresh" });
  const response = await fetch("/api/visual/topics?refresh=true");
  renderVisualTopics(await response.json());
  await refresh();
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
  const wasRunning = state.previousPlaybackRunning;
  state.previousPlaybackRunning = Boolean(status.running);
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
  if (wasRunning && !status.running) {
    await refreshVisualTopicsNow();
  }
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
    const points = Array.isArray(payload.points) ? payload.points : [];
    cloudViewer.loadPoints(points);
    $("#cloud-status").textContent = `${payload.topic} · ${points.length}/${payload.point_count} pts`;
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

function stopVisualStreams() {
  const wasStreaming = {
    cloud: Boolean(state.cloudSocket),
    camera: Boolean(state.cameraSocket),
    map: Boolean(state.mapSocket),
    costmap: Boolean(state.costmapSocket),
  };
  stopPointCloudStream("stream stopped for ROS_DOMAIN_ID update");
  stopSocket("cameraSocket", $("#camera-status"), "stream stopped for ROS_DOMAIN_ID update");
  stopSocket("mapSocket", $("#map-status"), "stream stopped for ROS_DOMAIN_ID update");
  stopSocket("costmapSocket", $("#costmap-status"), "stream stopped for ROS_DOMAIN_ID update");
  return wasStreaming;
}

function restartVisualStreams(wasStreaming) {
  if (wasStreaming.cloud && $("#cloud-topic-select").value) {
    startPointCloudStream($("#cloud-stream"));
  }
  if (wasStreaming.camera && $("#camera-topic-select").value) {
    startCameraStream();
  }
  if (wasStreaming.map && $("#map-topic-select").value) {
    startCostmapStream("#map-topic-select", "mapSocket", mapViewer, "#map-status");
  }
  if (wasStreaming.costmap && $("#costmap-topic-select").value) {
    startCostmapStream("#costmap-topic-select", "costmapSocket", costmapViewer, "#costmap-status");
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
    const points = Array.isArray(payload.points) ? payload.points : [];
    cloudViewer.loadPoints(points, "live cloud frame");
    $("#cloud-status").textContent = `${payload.topic} · ${points.length}/${payload.point_count} live pts`;
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
  await refreshVisualTopicsNow();
}

async function stopPostProcessingBag() {
  const response = await fetch("/api/post-processing/stop", { method: "POST" });
  const payload = await response.json();
  $("#post-status").textContent = payload.ok ? "playback stopped" : payload.error;
  await refreshPostProcessingStatus();
  await refreshVisualTopicsNow();
}

async function setMode(mode) {
  $("#mode-dds").classList.toggle("active", mode === "dds");
  $("#mode-zenoh").classList.toggle("active", mode === "zenoh");
  text("#mode-state", mode.toUpperCase());
  text("#network-mode", mode.toUpperCase());
  const response = await fetch("/api/middleware", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  const payload = await response.json();
  $("#console-log").textContent = `middleware mode: ${payload.mode?.toUpperCase?.() ?? mode.toUpperCase()}`;
  await refresh();
}

async function setRosDomain() {
  const input = $("#ros-domain-id");
  const rawValue = input.value.trim();
  const domainId = rawValue === "" ? null : Number.parseInt(rawValue, 10);
  if (rawValue !== "" && (!Number.isInteger(domainId) || domainId < 0 || domainId > 232)) {
    $("#console-log").textContent = "ROS_DOMAIN_ID must be empty or an integer from 0 to 232.";
    return;
  }
  const wasStreaming = stopVisualStreams();
  input.disabled = true;
  $("#console-log").textContent = `setting ROS_DOMAIN_ID=${domainId ?? "unset"} and restarting ROS daemon...`;
  try {
    const response = await fetch("/api/ros-domain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain_id: domainId }),
    });
    const payload = await response.json();
    $("#console-log").textContent = [
      `ROS_DOMAIN_ID=${payload.ros_domain_id ?? "unset"}`,
      `daemon stop: ${payload.daemon_stop ? "ok" : "failed"}`,
      `daemon start: ${payload.daemon_start ? "ok" : "failed"}`,
      payload.playback_restarted ? "bag playback restarted" : "",
      payload.playback_error ? `playback: ${payload.playback_error}` : "",
      payload.daemon_stdout,
      payload.daemon_stderr,
    ].filter(Boolean).join("\n");
    await refresh();
    await refreshVisualTopicsNow();
    restartVisualStreams(wasStreaming);
  } catch (error) {
    $("#console-log").textContent = `ROS_DOMAIN_ID update failed: ${error.message}`;
  } finally {
    input.disabled = false;
  }
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
on("#topics-refresh", "click", refreshVisualTopicsNow);
on("#network-window-sec", "change", () => drawNetworkGraph());
on("#mode-dds", "click", () => setMode("dds"));
on("#mode-zenoh", "click", () => setMode("zenoh"));
on("#ros-domain-id", "change", setRosDomain);
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
on("#cloud-point-size", "change", (event) => cloudViewer.setPointSize(event.target.value));
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
