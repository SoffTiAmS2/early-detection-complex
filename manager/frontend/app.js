const state = {
  project: null,
  catalog: null,
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

function sensorDefaults(index = 1) {
  return {
    name: `sensor${index}`,
    host: `192.168.10.${10 + index}`,
    role: "custom",
    profile: "opencanary",
    services: ["ssh", "http"],
    mask: {
      hostname: `sensor${index}-node`,
      os: "Debian GNU/Linux 13",
      department: "Lab",
      asset_tag: `SENSOR${index}`,
      notes: "deception node",
    },
  };
}

function renderCatalog() {
  const profiles = $("#profileCatalog");
  profiles.innerHTML = "";
  Object.entries(state.catalog.profiles).forEach(([key, value]) => {
    const item = document.createElement("div");
    item.className = "catalog-item";
    item.innerHTML = `<strong>${key}</strong><span>${value.description}</span>`;
    profiles.append(item);
  });

  const services = $("#serviceCatalog");
  services.innerHTML = "";
  Object.entries(state.catalog.services).forEach(([key, value]) => {
    const item = document.createElement("div");
    item.className = "service-item";
    item.innerHTML = `<strong>${value.title}</strong><span>tcp/${value.port} · ${key}</span>`;
    services.append(item);
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
    const node = template.content.firstElementChild.cloneNode(true);
    $("h3", node).textContent = sensor.name || `sensor${index + 1}`;
    $(".profile-pill", node).textContent = `${sensor.profile} · ${sensor.role}`;

    $$("[data-field]", node).forEach((input) => {
      const field = input.dataset.field;
      if (field === "profile") {
        input.innerHTML = "";
        Object.keys(state.catalog.profiles).forEach((profile) => {
          const option = document.createElement("option");
          option.value = profile;
          option.textContent = profile;
          input.append(option);
        });
      }
      input.value = sensor[field] || "";
      input.addEventListener("input", () => {
        sensor[field] = input.value;
        if (field === "profile") {
          applyProfileDefaults(sensor);
          renderSensors();
        } else {
          $("h3", node).textContent = sensor.name || `sensor${index + 1}`;
          $(".profile-pill", node).textContent = `${sensor.profile} · ${sensor.role}`;
        }
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

    renderServiceChecks(node, sensor);
    $(".remove-sensor", node).addEventListener("click", () => {
      state.project.sensors.splice(index, 1);
      renderSensors();
      setStatus("Сенсор удален");
    });

    container.append(node);
  });

  setStatus(`${state.project.sensors.length} сенсоров`);
}

function renderServiceChecks(node, sensor) {
  const box = $(".services", node);
  box.innerHTML = "";
  Object.entries(state.catalog.services).forEach(([key, value]) => {
    const label = document.createElement("label");
    label.className = "check";
    const checked = sensor.services?.includes(key) ? "checked" : "";
    label.innerHTML = `<input type="checkbox" value="${key}" ${checked}><span>${value.title} <small>tcp/${value.port}</small></span>`;
    $("input", label).addEventListener("change", (event) => {
      sensor.services ||= [];
      if (event.target.checked && !sensor.services.includes(key)) {
        sensor.services.push(key);
      }
      if (!event.target.checked) {
        sensor.services = sensor.services.filter((item) => item !== key);
      }
    });
    box.append(label);
  });
}

function applyProfileDefaults(sensor) {
  const profile = state.catalog.profiles[sensor.profile];
  if (!profile) return;
  sensor.role = profile.role;
  sensor.services = [...profile.services];
  sensor.mask ||= {};
  if (!sensor.mask.hostname) sensor.mask.hostname = `${sensor.name}-node`;
  if (!sensor.mask.os) sensor.mask.os = "Debian GNU/Linux 13";
  if (!sensor.mask.department) sensor.mask.department = profile.role;
  if (!sensor.mask.asset_tag) sensor.mask.asset_tag = sensor.name.toUpperCase();
  if (!sensor.mask.notes) sensor.mask.notes = `${sensor.profile} decoy`;
}

async function saveProject() {
  syncNetworkFromDom();
  await requestJson("/api/project", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.project),
  });
  setStatus("Сохранено");
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
  renderCatalog();
  syncNetworkToDom();
  renderSensors();

  $("#addSensor").addEventListener("click", () => {
    const sensor = sensorDefaults(state.project.sensors.length + 1);
    applyProfileDefaults(sensor);
    state.project.sensors.push(sensor);
    renderSensors();
  });
  $("#saveProject").addEventListener("click", () => saveProject().catch((error) => setStatus(error.message)));
  $("#generateProject").addEventListener("click", () => generateProject().catch((error) => setStatus(error.message)));
}

init().catch((error) => setStatus(error.message));

