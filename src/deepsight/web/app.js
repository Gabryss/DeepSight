const state = {
  latest: null,
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
  renderTools(payload.tools);
}

function activateTab(button) {
  const targetId = button.dataset.tabTarget;
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  const group = button.closest("nav");
  const scope = target.parentElement;
  group.querySelectorAll(".tab-button").forEach((tab) => {
    tab.classList.toggle("active", tab === button);
  });
  scope.querySelectorAll(".tab-panel, .inspector-panel").forEach((panel) => {
    panel.classList.toggle("active", panel === target);
  });
}

async function refresh() {
  const response = await fetch("/api/status");
  render(await response.json());
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
  const output = $("#command-output");
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
document.querySelectorAll("[data-tab-target]").forEach((button) => {
  button.addEventListener("click", () => activateTab(button));
});

refresh();
connectLive();
