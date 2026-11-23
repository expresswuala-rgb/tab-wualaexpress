const state = {
  tariffs: [],
  selected: new Set(),
  style: "oscuro",
  generated: [],
  search: "",
  sort: "name",
  deselectAfter: false,
};

const el = (id) => document.getElementById(id);
const routeList = el("routeList");
const routeCount = el("routeCount");
const selectionHint = el("selectionHint");
const generateBtn = el("generateBtn");
const zipBtn = el("zipBtn");
const previewBtn = el("previewBtn");
const results = el("results");

function toast(message, isError = false) {
  const t = el("toast");
  t.textContent = message;
  t.classList.toggle("error", isError);
  t.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { t.hidden = true; }, 3800);
}

async function loadRoutes() {
  try {
    const res = await fetch("/api/routes");
    const data = await res.json();
    state.tariffs = data.tariffs || [];
    state.dataDir = data.dataDir || "";
  } catch (err) {
    toast("No se pudo cargar la lista de rutas", true);
    return;
  }
  routeCount.textContent = `${allRoutes().length} rutas`;
  const dd = el("dataDirHint");
  if (dd && state.dataDir) dd.textContent = state.dataDir;
  renderRoutes();
  syncButtons();
}

function allRoutes() {
  return state.tariffs.flatMap((t) => t.routes.map((r) => ({ ...r, tariff: t })));
}

function filteredRoutes() {
  const q = state.search.trim().toLowerCase();
  let list = allRoutes();
  if (q) list = list.filter((r) => r.name.toLowerCase().includes(q) || r.tariff.name.toLowerCase().includes(q));
  list = [...list].sort((a, b) => {
    if (state.sort === "tariff") return a.tariff.name.localeCompare(b.tariff.name) || a.name.localeCompare(b.name);
    if (state.sort === "dest") return b.destinations - a.destinations || a.name.localeCompare(b.name);
    return a.name.localeCompare(b.name);
  });
  return list;
}

function renderRoutes() {
  routeList.innerHTML = "";
  const list = filteredRoutes();
  if (allRoutes().length === 0) {
    routeList.innerHTML = `<p class="muted">No hay CSV en <code>data/</code>.</p>`;
    syncButtons();
    return;
  }
  if (list.length === 0) {
    routeList.innerHTML = `<p class="muted">Sin resultados.</p>`;
    syncButtons();
    return;
  }
  // agrupar por tabulador preservando el orden filtrado
  const groups = new Map();
  for (const r of list) {
    if (!groups.has(r.tariff.id)) groups.set(r.tariff.id, { tariff: r.tariff, routes: [] });
    groups.get(r.tariff.id).routes.push(r);
  }
  for (const g of groups.values()) {
    const group = document.createElement("div");
    group.className = "route-group";
    const head = document.createElement("div");
    head.className = "group-head";
    const allChecked = g.routes.every((r) => state.selected.has(r.id));
    const someChecked = g.routes.some((r) => state.selected.has(r.id));
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = allChecked;
    cb.indeterminate = !allChecked && someChecked;
    cb.addEventListener("change", () => {
      if (cb.checked) g.routes.forEach((r) => state.selected.add(r.id));
      else g.routes.forEach((r) => state.selected.delete(r.id));
      renderRoutes();
      syncButtons();
    });
    const label = document.createElement("span");
    label.textContent = g.tariff.name;
    const sub = document.createElement("span");
    sub.textContent = `${g.routes.length} salidas · ${g.tariff.zones} destinos`;
    head.append(cb, label, sub);
    group.appendChild(head);

    for (const route of g.routes) {
      const row = document.createElement("div");
      row.className = "route-item" + (state.selected.has(route.id) ? " selected" : "");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = route.id;
      input.id = `chk-${route.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
      input.checked = state.selected.has(route.id);
      input.addEventListener("change", () => {
        if (input.checked) state.selected.add(route.id);
        else state.selected.delete(route.id);
        renderRoutes();
        syncButtons();
      });
      const lbl = document.createElement("label");
      lbl.htmlFor = input.id;
      lbl.textContent = route.name;
      const count = document.createElement("span");
      count.className = "zone-count";
      count.textContent = `${route.destinations} destinos`;
      lbl.appendChild(count);
      row.append(input, lbl);
      group.appendChild(row);
    }
    routeList.appendChild(group);
  }
  selectionHint.textContent = `${state.selected.size} seleccionada${state.selected.size === 1 ? "" : "s"} de ${allRoutes().length}`;
}

function syncButtons() {
  const has = state.selected.size > 0;
  generateBtn.disabled = !has;
  previewBtn.disabled = !has;
  zipBtn.disabled = !has && state.generated.length === 0;
}

function selectedRoutes() {
  const byId = new Map(allRoutes().map((r) => [r.id, r]));
  return [...state.selected].map((id) => byId.get(id)).filter(Boolean);
}

async function generateSelected() {
  const routes = selectedRoutes();
  if (!routes.length) return;
  generateBtn.disabled = true;
  generateBtn.textContent = "Generando…";
  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: routes.map((r) => r.id), options: { estilo: state.style } }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error al generar");
    state.generated = data.results.concat(state.generated);
    renderResults(data.results);
    if (state.deselectAfter) {
      state.selected.clear();
      renderRoutes();
    }
    toast(`${data.results.length} ${data.results.length === 1 ? "imagen generada" : "imágenes generadas"}`);
  } catch (err) {
    toast(err.message, true);
  } finally {
    generateBtn.textContent = "Generar imágenes";
    syncButtons();
  }
}

function removeResult(item) {
  const card = [...results.querySelectorAll(".result-card")].find((c) => c._item === item);
  if (card) {
    if (item.url && item.url.startsWith("blob:")) URL.revokeObjectURL(item.url);
    card.remove();
  }
  state.generated = state.generated.filter((g) => g !== item);
  if (state.generated.length === 0 && !el("emptyState")) {
    const empty = document.createElement("div");
    empty.className = "empty"; empty.id = "emptyState";
    empty.innerHTML = `<div class="empty-icon">▦</div><h3>Nada generado todavía</h3><p>Selecciona una o varias rutas y pulsa <strong>Generar imágenes</strong>.</p>`;
    results.appendChild(empty);
  }
  syncButtons();
}

function clearResults() {
  for (const item of [...state.generated]) {
    const card = [...results.querySelectorAll(".result-card")].find((c) => c._item === item);
    if (card) card.remove();
    if (item.url && item.url.startsWith("blob:")) URL.revokeObjectURL(item.url);
  }
  state.generated = [];
  if (!el("emptyState")) {
    const empty = document.createElement("div");
    empty.className = "empty"; empty.id = "emptyState";
    empty.innerHTML = `<div class="empty-icon">▦</div><h3>Nada generado todavía</h3><p>Selecciona una o varias rutas y pulsa <strong>Generar imágenes</strong>.</p>`;
    results.appendChild(empty);
  }
  syncButtons();
  toast("Resultados limpiados");
}

function renderResults(items) {
  if (items.length) el("emptyState")?.remove();
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "result-card";
    const head = document.createElement("div");
    head.className = "result-head";
    const title = document.createElement("div");
    const h3 = document.createElement("h3");
    h3.textContent = `Salida desde ${item.name}`;
    const meta = document.createElement("span");
    meta.textContent = `${item.destinations} destinos`;
    title.append(h3, meta);
    const actions = document.createElement("div");
    actions.className = "result-actions";
    const view = document.createElement("a");
    view.href = item.url; view.target = "_blank"; view.textContent = "Abrir PNG";
    const download = document.createElement("a");
    download.href = item.url; download.download = item.file; download.textContent = "Descargar";
    const remove = document.createElement("button");
    remove.type = "button"; remove.className = "result-remove"; remove.textContent = "×";
    remove.title = "Quitar";
    remove.addEventListener("click", () => removeResult(item));
    actions.append(view, download, remove);
    head.append(title, actions);
    const img = document.createElement("img");
    img.src = item.url; img.alt = `Tabulador salida desde ${item.name}`;
    card.append(head, img);
    card._item = item;
    results.prepend(card);
  }
}

// Vista previa
const previewModal = el("previewModal");
const previewImg = el("previewImg");
const previewTitle = el("previewTitle");
const previewMeta = el("previewMeta");

async function openPreview() {
  const routes = selectedRoutes();
  if (!routes.length) return;
  const route = routes[0];
  const box = el("previewBox");
  const img = el("previewImgInline");
  const placeholder = box.querySelector(".preview-placeholder");
  const meta = el("previewMetaInline");
  box.classList.add("loading");
  meta.textContent = "Generando…";
  img.hidden = true;
  if (placeholder) placeholder.hidden = false;
  try {
    const url = `/api/preview?id=${encodeURIComponent(route.id)}&estilo=${encodeURIComponent(state.style)}&t=${Date.now()}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("No se pudo generar la vista previa");
    const blob = await res.blob();
    img.src = URL.createObjectURL(blob);
    img.hidden = false;
    if (placeholder) placeholder.hidden = true;
    meta.textContent = `${route.name} · ${route.destinations} destinos · estilo ${state.style}`;
  } catch (err) {
    if (placeholder) placeholder.hidden = false;
    meta.textContent = err.message;
    toast(err.message, true);
  } finally {
    box.classList.remove("loading");
  }
}
function closePreview() { if (previewModal) previewModal.hidden = true; }
el("previewClose").addEventListener("click", closePreview);
previewModal.addEventListener("click", (e) => { if (e.target === previewModal) closePreview(); });
el("previewGenerate").addEventListener("click", () => { closePreview(); generateSelected(); });

// Config export/import
function exportConfig() {
  const config = {
    version: 1,
    style: state.style,
    selected: [...state.selected],
    deselectAfter: state.deselectAfter,
    exportedAt: new Date().toISOString(),
  };
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `tabuladores-config-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  toast("Configuración exportada");
}

async function importConfig(file) {
  try {
    const text = await file.text();
    const config = JSON.parse(text);
    if (config.style && ["oscuro", "claro"].includes(config.style)) state.style = config.style;
    if (typeof config.deselectAfter === "boolean") {
      state.deselectAfter = config.deselectAfter;
      if (deselectCb) deselectCb.checked = state.deselectAfter;
      try { localStorage.setItem("deselectAfter", state.deselectAfter ? "1" : "0"); } catch (e) {}
    }
    state.selected = new Set(Array.isArray(config.selected) ? config.selected : []);
    document.querySelectorAll(".style-card").forEach((c) => c.classList.toggle("active", c.dataset.style === state.style));
    renderRoutes();
    syncButtons();
    toast("Configuración importada");
  } catch (err) {
    toast("Archivo de configuración inválido", true);
  }
}

// CSV import
async function importCsv(file) {
  try {
    const content = await file.text();
    const res = await fetch("/api/import-csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: file.name, content }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error al importar");
    toast(`Tabulador agregado: ${data.tariff.name}`);
    window.__lastImportedId = data.tariff.id;
    await loadRoutes();
    return data.tariff.id;
  } catch (err) {
    toast(err.message, true);
    return null;
  }
}

// Eventos
el("routeSearch").addEventListener("input", (e) => { state.search = e.target.value; renderRoutes(); });
el("routeSort").addEventListener("change", (e) => { state.sort = e.target.value; renderRoutes(); });
el("selectAll").addEventListener("click", () => {
  filteredRoutes().forEach((r) => state.selected.add(r.id));
  renderRoutes(); syncButtons();
});
el("selectNone").addEventListener("click", () => {
  state.selected.clear(); renderRoutes(); syncButtons();
});
el("toggleAll")?.addEventListener("click", () => {
  const all = state.selected.size === allRoutes().length;
  state.selected = all ? new Set() : new Set(allRoutes().map((r) => r.id));
  renderRoutes(); syncButtons();
});

el("stylePicker").addEventListener("click", (event) => {
  const button = event.target.closest(".style-card");
  if (!button) return;
  state.style = button.dataset.style;
  document.querySelectorAll(".style-card").forEach((card) => card.classList.toggle("active", card === button));
});

generateBtn.addEventListener("click", generateSelected);
previewBtn.addEventListener("click", openPreview);
zipBtn.addEventListener("click", () => {
  const ids = [...state.selected];
  if (!ids.length) { toast("Selecciona rutas para el ZIP", true); return; }
  window.location.href = `/api/zip?ids=${encodeURIComponent(ids.join(","))}&estilo=${state.style}`;
});

el("exportConfigBtn").addEventListener("click", exportConfig);
el("clearResults").addEventListener("click", clearResults);
el("importConfigBtn").addEventListener("click", () => el("configFileInput").click());
el("changeDataDirBtn").addEventListener("click", async () => {
  const current = state.dataDir || "";
  const path = prompt("Ruta de la carpeta de datos (CSV):", current);
  if (path === null) return;
  const trimmed = path.trim();
  if (!trimmed) return;
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataDir: trimmed }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error");
    state.dataDir = data.dataDir;
    const dd = el("dataDirHint");
    if (dd) dd.textContent = data.dataDir;
    toast("Carpeta de datos actualizada");
    await loadRoutes();
  } catch (err) {
    toast(err.message, true);
  }
});
el("configFileInput").addEventListener("change", (e) => {
  const file = e.target.files && e.target.files[0];
  if (file) importConfig(file);
  e.target.value = "";
});

// ---- Pestañas ----
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    const tab = btn.dataset.tab;
    document.getElementById("generateView").hidden = tab !== "generate";
    document.getElementById("editorView").hidden = tab !== "editor";
    if (tab === "editor") loadEditorTariffs();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});

// ---- Editor de tabulador ----
const editorTariff = el("editorTariff");
const editorWrap = el("editorWrap");
const editorStatus = el("editorStatus");

async function loadEditorTariffs() {
  if (!state.tariffs.length) await loadRoutes();
  editorTariff.innerHTML = "";
  for (const t of state.tariffs) {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = `${t.name} (${t.routes.length} salidas)`;
    editorTariff.appendChild(opt);
  }
  if (state.tariffs.length) await loadEditorGrid(editorTariff.value);
}

async function loadEditorGrid(tariffId) {
  editorWrap.innerHTML = `<p class="muted">Cargando…</p>`;
  editorStatus.textContent = "";
  try {
    const res = await fetch(`/api/tariff?id=${encodeURIComponent(tariffId)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error");
    renderEditorGrid(data);
  } catch (err) {
    editorWrap.innerHTML = `<p class="muted">${err.message}</p>`;
  }
}

function renderEditorGrid(data) {
  const zones = data.zones;
  const origins = data.origins;
  const grid = data.grid;
  const table = document.createElement("table");
  table.className = "zone-grid";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  const corner = document.createElement("th");
  corner.className = "corner";
  corner.textContent = "De \\\\ A";
  hr.appendChild(corner);
  zones.forEach((z) => {
    const th = document.createElement("th");
    th.textContent = z;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  origins.forEach((origin, ri) => {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.className = "rowhead";
    th.textContent = origin;
    tr.appendChild(th);
    zones.forEach((z, ci) => {
      const td = document.createElement("td");
      const input = document.createElement("input");
      input.type = "text";
      input.value = (grid[ri] && grid[ri][ci] != null) ? grid[ri][ci] : "";
      input.dataset.r = ri;
      input.dataset.c = ci;
      td.appendChild(input);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  editorWrap.innerHTML = "";
  editorWrap.appendChild(table);
  editorStatus.textContent = `${origins.length} salidas × ${zones.length} destinos`;
}

editorTariff.addEventListener("change", () => loadEditorGrid(editorTariff.value));
el("editorReload").addEventListener("click", () => loadEditorGrid(editorTariff.value));
el("editorImport").addEventListener("click", () => el("editorCsvInput").click());
el("editorCsvInput").addEventListener("change", (e) => {
  const file = e.target.files && e.target.files[0];
  if (file) importCsv(file).then(async (newId) => {
    await loadEditorTariffs();
    if (newId && [...editorTariff.options].some((o) => o.value === newId)) {
      editorTariff.value = newId;
    }
    await loadEditorGrid(editorTariff.value);
  });
  e.target.value = "";
});
el("editorExport").addEventListener("click", () => {
  const id = editorTariff.value;
  if (!id) return;
  window.location.href = `/api/export-tariff?id=${encodeURIComponent(id)}`;
});

el("editorAddZone").addEventListener("click", () => {
  const name = prompt("Nombre de la nueva zona:");
  if (!name || !name.trim()) return;
  const table = editorWrap.querySelector("table");
  if (!table) return;
  const theadRow = table.querySelector("thead tr");
  const th = document.createElement("th");
  th.textContent = name.trim();
  theadRow.appendChild(th);
  table.querySelectorAll("tbody tr").forEach((tr) => {
    const td = document.createElement("td");
    const input = document.createElement("input");
    input.type = "text";
    input.value = "";
    td.appendChild(input);
    tr.appendChild(td);
  });
  const tbody = table.querySelector("tbody");
  const tr = document.createElement("tr");
  const thh = document.createElement("th");
  thh.className = "rowhead";
  thh.textContent = name.trim();
  tr.appendChild(thh);
  const ncols = table.querySelector("thead tr").children.length - 1;
  for (let i = 0; i < ncols; i++) {
    const td = document.createElement("td");
    const input = document.createElement("input");
    input.type = "text";
    input.value = "";
    td.appendChild(input);
    tr.appendChild(td);
  }
  tbody.appendChild(tr);
  editorStatus.textContent = "Zona agregada. Recuerda guardar.";
});

el("editorSave").addEventListener("click", async () => {
  const table = editorWrap.querySelector("table");
  if (!table) return;
  const zones = [...table.querySelectorAll("thead th")].slice(1).map((th) => th.textContent.trim());
  const origins = [...table.querySelectorAll("tbody tr .rowhead")].map((th) => th.textContent.trim());
  const grid = [...table.querySelectorAll("tbody tr")].map((tr) =>
    [...tr.querySelectorAll("td input")].map((inp) => inp.value.trim())
  );
  el("editorSave").disabled = true;
  el("editorSave").textContent = "Guardando…";
  try {
    const res = await fetch("/api/save-tariff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: editorTariff.value, zones, origins, grid }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error al guardar");
    toast("Tabulador guardado");
    await loadRoutes();
    if ([...editorTariff.options].some((o) => o.value === data.tariff.id)) {
      editorTariff.value = data.tariff.id;
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    el("editorSave").disabled = false;
    el("editorSave").textContent = "Guardar tabulador";
  }
});

// Atajos de teclado
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); generateSelected(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") { e.preventDefault(); el("selectAll").click(); }
  if (e.key === "Escape" && !previewModal.hidden) { previewModal.hidden = true; }
});

// ---- Google Drive ----
async function refreshDriveStatus() {
  try {
    const res = await fetch("/api/drive/status");
    const data = await res.json();
    const statusEl = el("driveStatus");
    const syncStatus = el("driveSyncStatus");
    if (!data.available) { statusEl.textContent = "Módulo no disponible"; return; }
    if (!data.hasCredentials) {
      statusEl.textContent = "Sin credenciales. Introduce Client ID/Secret.";
      if (syncStatus) syncStatus.textContent = "";
      return;
    }
    if (data.authenticated) {
      statusEl.textContent = "Conectado a Google Drive";
    } else {
      statusEl.textContent = "Credenciales guardadas. Pulsa 'Conectar Google Drive'.";
    }
  } catch (err) {
    const s = el("driveStatus");
    if (s) s.textContent = "Error al verificar estado";
  }
}

el("driveSaveCreds").addEventListener("click", async () => {
  const clientId = el("driveClientId").value.trim();
  const clientSecret = el("driveClientSecret").value.trim();
  if (!clientId || !clientSecret) { toast("Introduce Client ID y Client Secret", true); return; }
  try {
    const res = await fetch("/api/drive/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId, clientSecret }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error");
    toast("Credenciales guardadas");
    refreshDriveStatus();
  } catch (err) { toast(err.message, true); }
});

el("driveConnect").addEventListener("click", async () => {
  toast("Abriendo navegador para autorizar…");
  try {
    const res = await fetch("/api/drive/connect", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error de conexión");
    toast("Conectado a Google Drive");
    refreshDriveStatus();
  } catch (err) { toast(err.message, true); }
});

el("driveSync").addEventListener("click", async () => {
  toast("Sincronizando…");
  try {
    const res = await fetch("/api/drive/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error de sincronización");
    toast(data.message || "Sincronizado");
    el("driveSyncStatus").textContent = data.message || "";
    await loadRoutes();
  } catch (err) { toast(err.message, true); }
});

el("driveDisconnect").addEventListener("click", async () => {
  try {
    await fetch("/api/drive/disconnect", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    toast("Desconectado de Google Drive");
    refreshDriveStatus();
  } catch (err) { toast(err.message, true); }
});

// Preferencia: deseleccionar tras generar
try {
  state.deselectAfter = localStorage.getItem("deselectAfter") === "1";
} catch (e) {}
const deselectCb = el("deselectAfter");
if (deselectCb) {
  deselectCb.checked = state.deselectAfter;
  deselectCb.addEventListener("change", () => {
    state.deselectAfter = deselectCb.checked;
    try { localStorage.setItem("deselectAfter", state.deselectAfter ? "1" : "0"); } catch (e) {}
  });
}

refreshDriveStatus();
loadRoutes();