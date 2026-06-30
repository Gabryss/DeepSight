const state = {
  latest: null,
  bags: [],
  selectedBagPath: null,
};

const $ = (selector) => document.querySelector(selector);

function text(selector, value) {
  $(selector).textContent = value;
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
  root.replaceChildren();
  for (const command of commands) {
    const row = document.createElement("div");
    row.className = "command";
    row.innerHTML = `<strong>${command.label}</strong><button type="button" title="Run command">▶</button>`;
    row.querySelector("button").addEventListener("click", () => runCommand(command.id, row.querySelector("button")));
    root.append(row);
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
  renderCommands(payload.commands);
  renderRos(payload.ros);
  renderNetwork(payload);
  renderTools(payload.tools);
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

$("#refresh").addEventListener("click", refresh);
$("#mode-dds").addEventListener("click", () => setMode("dds"));
$("#mode-zenoh").addEventListener("click", () => setMode("zenoh"));
$("#post-bag-select").addEventListener("change", (event) => {
  state.selectedBagPath = event.target.value;
  renderPostProcessingControls();
});
$("#post-play").addEventListener("click", playPostProcessingBag);
$("#post-stop").addEventListener("click", stopPostProcessingBag);
document.querySelectorAll("[data-tab-target]").forEach((button) => {
  button.addEventListener("click", () => activateTab(button));
});

refresh();
refreshBags();
refreshPostProcessingStatus();
setInterval(refreshPostProcessingStatus, 2000);
connectLive();
