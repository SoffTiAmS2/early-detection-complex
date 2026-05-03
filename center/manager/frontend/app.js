const state = {
  project: null,
  catalog: null,
  jobs: [],
  runtimeSensors: [],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.stderr || response.statusText);
  }
  return data;
}

function setStatus(message) {
  $("#statusLine").textContent = message;
}

function defaultSettings(type) {
  const settings = {};
  state.catalog.honeypots[type].settings.forEach((field) => {
    settings[field.key] = field.default;
  });
  return settings;
}

function defaultHoneypot(type) {
  const catalog = state.catalog.honeypots[type];
  return {
    type,
    enabled: true,
    services: [...catalog.default_services],
    settings: defaultSettings(type),
  };
}

function ensureSensorShape(sensor) {
  if (!Array.isArray(sensor.honeypots) || !sensor.honeypots.length) {
    const type = state.catalog.honeypots[sensor.profile] ? sensor.profile : "cowrie";
    const honeypot = defaultHoneypot(type);
    if (Array.isArray(sensor.services)) {
      const allowed = new Set(state.catalog.honeypots[type].services);
      honeypot.services = sensor.services
        .map((service) => normalizeServiceForUi(service, type))
        .filter((service) => service && allowed.has(service.name));
    }
    sensor.honeypots = [honeypot];
  }
  sensor.honeypots.forEach((honeypot) => {
    const catalog = state.catalog.honeypots[honeypot.type] || state.catalog.honeypots.cowrie;
    honeypot.type = catalog === state.catalog.honeypots[honeypot.type] ? honeypot.type : "cowrie";
    honeypot.enabled = honeypot.enabled !== false;
    honeypot.services = Array.isArray(honeypot.services)
      ? honeypot.services.map((service) => normalizeServiceForUi(service, honeypot.type)).filter((service) => service && catalog.services.includes(service.name))
      : [];
    if (!honeypot.services.length) {
      honeypot.services = catalog.default_services.map((service) => normalizeServiceForUi(service, honeypot.type));
    }
    honeypot.settings = { ...defaultSettings(honeypot.type), ...(honeypot.settings || {}) };
  });
  syncLegacyFields(sensor);
}

function normalizeServiceForUi(raw, type) {
  const name = typeof raw === "string" ? raw : raw?.name;
  if (!name || !state.catalog.services[name] || !state.catalog.honeypots[type].services.includes(name)) return null;
  return {
    name,
    enabled: typeof raw === "object" ? raw.enabled !== false : true,
    host_port: Number(raw?.host_port || state.catalog.services[name].default_host_port),
  };
}

function syncLegacyFields(sensor) {
  const enabled = sensor.honeypots.filter((honeypot) => honeypot.enabled);
  const primary = enabled[0] || sensor.honeypots[0] || defaultHoneypot("cowrie");
  sensor.profile = primary.type;
  sensor.services = [...new Set(enabled.flatMap((honeypot) => honeypot.services.filter((service) => service.enabled).map((service) => service.name)))];
  if (!sensor.role) sensor.role = state.catalog.honeypots[primary.type].role;
}

function sensorDefaults(index = 1) {
  const type = "cowrie";
  return {
    name: `sensor${index}`,
    host: `192.168.10.${10 + index}`,
    role: state.catalog.honeypots[type].role,
    profile: type,
    services: [...state.catalog.honeypots[type].default_services],
    honeypots: [defaultHoneypot(type)],
    mask: {
      hostname: `sensor${index}-node`,
      os: "Debian GNU/Linux 13",
      department: "Lab",
      asset_tag: `SENSOR${index}`,
      notes: "deception node",
    },
  };
}

function jobLabel(job) {
  const step = job.step ? ` · ${job.step}` : "";
  return `${job.sensor || job.type}: ${job.status}${step}`;
}

function renderJobs() {
  const box = $("#jobs");
  if (!state.jobs.length) {
    box.innerHTML = '<span class="muted">Нет активных установок</span>';
    return;
  }
  box.innerHTML = "";
  state.jobs.slice(0, 5).forEach((job) => {
    const item = document.createElement("div");
    item.className = "job-item";
    item.innerHTML = `
      <div><strong>${job.sensor || job.type}</strong><span>${job.status} · ${job.progress || 0}%</span></div>
      <div class="progress"><span style="width: ${job.progress || 0}%"></span></div>
    `;
    box.append(item);
  });
}

async function refreshCenterStatus() {
  const health = await requestJson("/api/health");
  const center = await requestJson("/api/center/status");
  state.jobs = health.jobs || [];
  state.runtimeSensors = center.sensors || [];
  const collector = center.collector?.status || "offline";
  const events = center.collector?.events ?? 0;
  const error = center.collector_error ? ` · ${center.collector_error}` : "";
  $("#centerStatus").textContent = `${collector} · ${center.central_url} · events ${events}${error}`;
  renderJobs();
  renderRuntimeSensors();
}

function formatLastSeen(value) {
  if (!value) return "нет событий";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return new Date(numeric * 1000).toLocaleString();
}

function renderRuntimeSensors() {
  const box = $("#runtimeSensors");
  const configured = state.project?.sensors || [];
  if (!configured.length && !state.runtimeSensors.length) {
    box.innerHTML = '<span class="muted">Сенсоры не настроены</span>';
    return;
  }
  box.innerHTML = "";
  const byName = new Map(state.runtimeSensors.map((sensor) => [sensor.sensor, sensor]));
  const rows = configured.length
    ? configured.map((sensor) => ({ ...sensor, runtime: byName.get(sensor.name) }))
    : state.runtimeSensors.map((sensor) => ({ name: sensor.sensor, host: "", runtime: sensor }));

  rows.forEach((sensor) => {
    const runtime = sensor.runtime;
    const item = document.createElement("div");
    item.className = "job-item";
    item.innerHTML = `
      <div><strong>${sensor.name}</strong><span>${runtime ? "online" : "waiting"} · ${runtime?.events || 0} events</span></div>
      <span>${sensor.host || "no host"} · ${runtime?.last_type || "no events"} · ${formatLastSeen(runtime?.last_seen)}</span>
    `;
    box.append(item);
  });
}

function renderCatalog() {
  const box = $("#honeypotCatalog");
  box.innerHTML = "";
  Object.entries(state.catalog.honeypots).forEach(([key, value]) => {
    const item = document.createElement("div");
    item.className = "catalog-item";
    item.innerHTML = `<strong>${value.title}</strong><span>${value.description}</span>`;
    box.append(item);
  });
}

function syncNetworkToDom() {
  $("#subnet").value = state.project.network.subnet || "";
  $("#gateway").value = state.project.network.gateway || "";
  $("#centralNode").value = state.project.network.central_node || "";
}

function syncNetworkFromDom() {
  state.project.network.subnet = $("#subnet").value.trim();
  state.project.network.gateway = $("#gateway").value.trim();
  state.project.network.central_node = $("#centralNode").value.trim();
}

function renderSensors() {
  const container = $("#sensors");
  const template = $("#sensorTemplate");
  container.innerHTML = "";

  state.project.sensors.forEach((sensor, index) => {
    ensureSensorShape(sensor);
    const node = template.content.firstElementChild.cloneNode(true);
    $("h3", node).textContent = sensor.name || `sensor${index + 1}`;
    $(".honeypot-pill", node).textContent = sensor.honeypots.map((honeypot) => honeypot.type).join(" + ");

    $$("[data-field]", node).forEach((input) => {
      const field = input.dataset.field;
      input.value = sensor[field] || "";
      input.addEventListener("input", () => {
        sensor[field] = input.value;
        $("h3", node).textContent = sensor.name || `sensor${index + 1}`;
        if (field === "role" && !sensor.mask.department) sensor.mask.department = input.value;
      });
    });

    $$("[data-mask]", node).forEach((input) => {
      const field = input.dataset.mask;
      sensor.mask ||= {};
      input.value = sensor.mask[field] || "";
      input.addEventListener("input", () => {
        sensor.mask[field] = input.value;
      });
    });

    setupHoneypotControls(node, sensor);
    setupDeployControls(node, sensor);
    $(".remove-sensor", node).addEventListener("click", () => {
      state.project.sensors.splice(index, 1);
      renderSensors();
      setStatus("Сенсор удален");
    });

    container.append(node);
  });

  setStatus(`${state.project.sensors.length} сенсоров`);
}

function setupHoneypotControls(node, sensor) {
  const select = $(".honeypot-type", node);
  select.innerHTML = "";
  Object.entries(state.catalog.honeypots).forEach(([type, catalog]) => {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = catalog.title;
    select.append(option);
  });
  $(".add-honeypot", node).addEventListener("click", () => {
    sensor.honeypots.push(defaultHoneypot(select.value));
    syncLegacyFields(sensor);
    renderSensors();
  });
  renderHoneypotTree(node, sensor);
}

function renderHoneypotTree(node, sensor) {
  const box = $(".honeypots", node);
  box.innerHTML = "";
  sensor.honeypots.forEach((honeypot, index) => {
    const catalog = state.catalog.honeypots[honeypot.type];
    const item = document.createElement("section");
    item.className = "honeypot-node";
    item.innerHTML = `
      <div class="honeypot-head">
        <label class="switch"><input type="checkbox" class="honeypot-enabled" ${honeypot.enabled ? "checked" : ""}><span>${catalog.title}</span></label>
        <button class="danger remove-honeypot" type="button">Удалить</button>
      </div>
      <p>${catalog.description}</p>
      <div class="honeypot-branch">
        <h5>Сервисы</h5>
        <div class="checks honeypot-services"></div>
        <h5>Настройки</h5>
        <div class="settings-grid"></div>
      </div>
    `;
    $(".honeypot-enabled", item).addEventListener("change", (event) => {
      honeypot.enabled = event.target.checked;
      syncLegacyFields(sensor);
    });
    $(".remove-honeypot", item).addEventListener("click", () => {
      sensor.honeypots.splice(index, 1);
      if (!sensor.honeypots.length) sensor.honeypots.push(defaultHoneypot("cowrie"));
      syncLegacyFields(sensor);
      renderSensors();
    });
    renderHoneypotServices(item, sensor, honeypot);
    renderHoneypotSettings(item, sensor, honeypot);
    box.append(item);
  });
}

function renderHoneypotServices(root, sensor, honeypot) {
  const box = $(".honeypot-services", root);
  const catalog = state.catalog.honeypots[honeypot.type];
  box.innerHTML = "";
  catalog.services.forEach((service) => {
    const serviceInfo = state.catalog.services[service];
    const current = honeypot.services.find((item) => item.name === service) || {
      name: service,
      enabled: false,
      host_port: serviceInfo.default_host_port,
    };
    const label = document.createElement("label");
    label.className = "check";
    label.innerHTML = `
      <input type="checkbox" value="${service}" ${current.enabled ? "checked" : ""}>
      <span>${serviceInfo.title}<small>${serviceInfo.protocol} container:${serviceInfo.container_port}</small></span>
      <input class="port-input" type="number" min="1" max="65535" value="${current.host_port}" aria-label="${serviceInfo.title} host port">
    `;
    const checkbox = $("input[type='checkbox']", label);
    const port = $(".port-input", label);
    checkbox.addEventListener("change", () => {
      let item = honeypot.services.find((entry) => entry.name === service);
      if (!item) {
        item = { name: service, enabled: true, host_port: serviceInfo.default_host_port };
        honeypot.services.push(item);
      }
      item.enabled = checkbox.checked;
      item.host_port = Number(port.value || serviceInfo.default_host_port);
      syncLegacyFields(sensor);
    });
    port.addEventListener("input", () => {
      let item = honeypot.services.find((entry) => entry.name === service);
      if (!item) {
        item = { name: service, enabled: checkbox.checked, host_port: serviceInfo.default_host_port };
        honeypot.services.push(item);
      }
      item.host_port = Number(port.value || serviceInfo.default_host_port);
      syncLegacyFields(sensor);
    });
    box.append(label);
  });
}

function renderHoneypotSettings(root, sensor, honeypot) {
  const box = $(".settings-grid", root);
  const catalog = state.catalog.honeypots[honeypot.type];
  box.innerHTML = "";
  catalog.settings.forEach((field) => {
    const label = document.createElement("label");
    label.textContent = field.title;
    const input = field.type === "select" ? document.createElement("select") : document.createElement("input");
    if (field.type === "boolean") input.type = "checkbox";
    if (field.type === "number") input.type = "number";
    if (field.type === "select") {
      field.options.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        input.append(option);
      });
    }
    const value = honeypot.settings[field.key] ?? field.default;
    if (field.type === "boolean") {
      input.checked = Boolean(value);
    } else {
      input.value = value;
    }
    input.addEventListener("input", () => {
      honeypot.settings[field.key] = field.type === "boolean" ? input.checked : input.value;
      syncLegacyFields(sensor);
    });
    label.append(input);
    box.append(label);
  });
}

function setupDeployControls(node, sensor) {
  const deploy = {
    ssh_host: sensor.host || "",
    ssh_port: "22",
    ssh_user: "root",
    ssh_password: "",
    become_password: "",
  };
  $$("[data-deploy]", node).forEach((input) => {
    const field = input.dataset.deploy;
    input.value = deploy[field];
    input.addEventListener("input", () => {
      deploy[field] = input.value;
    });
  });
  $(".deploy-sensor", node).addEventListener("click", () => deploySensor(sensor, deploy, node));
}

async function deploySensor(sensor, deploy, node) {
  const button = $(".deploy-sensor", node);
  const status = $(".deploy-status", node);
  const output = $(".deploy-output", node);
  const cancel = $(".cancel-deploy", node);
  const progress = $(".progress", node);
  const progressFill = $(".progress span", node);
  output.hidden = true;
  output.textContent = "";
  progress.hidden = false;
  progressFill.style.width = "0%";
  cancel.hidden = true;
  button.disabled = true;
  status.textContent = "Подготовка...";

  try {
    await saveProject("Сохранено перед установкой");
    status.textContent = "Запуск установки...";
    const started = await requestJson("/api/deploy-sensor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sensor: sensor.name,
        ssh_host: deploy.ssh_host,
        ssh_port: deploy.ssh_port || 22,
        ssh_user: deploy.ssh_user,
        ssh_password: deploy.ssh_password,
        become_password: deploy.become_password,
      }),
    });
    const jobId = started.job.id;
    cancel.hidden = false;
    cancel.onclick = () => cancelDeploy(jobId, cancel);
    await watchDeployJob(jobId, { button, cancel, status, output, progressFill });
  } catch (error) {
    status.textContent = "Ошибка";
    output.textContent = error.message;
    output.hidden = false;
  } finally {
    button.disabled = false;
  }
}

async function cancelDeploy(jobId, button) {
  button.disabled = true;
  await requestJson(`/api/jobs/${jobId}/cancel`, { method: "POST" });
}

async function watchDeployJob(jobId, controls) {
  while (true) {
    const job = await requestJson(`/api/jobs/${jobId}`);
    controls.status.textContent = jobLabel(job);
    controls.progressFill.style.width = `${job.progress || 0}%`;
    controls.output.textContent = (job.output || []).join("\n");
    controls.output.hidden = !(job.output || []).length;
    await refreshCenterStatus().catch(() => {});
    if (["succeeded", "failed", "cancelled"].includes(job.status)) {
      controls.cancel.hidden = true;
      controls.cancel.disabled = false;
      controls.button.disabled = false;
      if (job.result) {
        controls.output.textContent = [job.result.stdout, job.result.stderr].filter(Boolean).join("\n\n").trim();
        controls.output.hidden = !controls.output.textContent;
      }
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

async function saveProject(message = "Сохранено") {
  syncNetworkFromDom();
  state.project.sensors.forEach((sensor) => {
    ensureSensorShape(sensor);
    syncLegacyFields(sensor);
  });
  await requestJson("/api/project", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.project),
  });
  setStatus(message);
}

async function generateProject() {
  await saveProject();
  const result = await requestJson("/api/generate", { method: "POST" });
  setStatus(result.ok ? "Конфигурации сгенерированы" : "Ошибка генерации");
}

async function init() {
  state.catalog = await requestJson("/api/catalog");
  state.project = await requestJson("/api/project");
  state.project.sensors ||= [];
  state.project.sensors.forEach(ensureSensorShape);
  renderCatalog();
  syncNetworkToDom();
  renderSensors();

  $("#addSensor").addEventListener("click", () => {
    state.project.sensors.push(sensorDefaults(state.project.sensors.length + 1));
    renderSensors();
  });
  $("#saveProject").addEventListener("click", () => saveProject().catch((error) => setStatus(error.message)));
  $("#generateProject").addEventListener("click", () => generateProject().catch((error) => setStatus(error.message)));
  $("#refreshStatus").addEventListener("click", () => refreshCenterStatus().catch((error) => setStatus(error.message)));
  refreshCenterStatus().catch(() => {});
  setInterval(() => refreshCenterStatus().catch(() => {}), 5000);
}

init().catch((error) => setStatus(error.message));
