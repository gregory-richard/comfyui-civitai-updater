import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const TAB_ID = "civitai-updater";
const EXTENSION_NAME = "civitai-updater.ui";
const MODEL_TYPES = ["checkpoint", "lora", "vae", "unet"];
const PAGE_SIZES = [25, 50, 100];
const POLL_MS = 800;

const SETTINGS = {
  apiKey: "CivitaiUpdater.APIKey",
  requestTimeoutSeconds: "CivitaiUpdater.RequestTimeoutSeconds",
  maxRetries: "CivitaiUpdater.MaxRetries",
  requestDelayMs: "CivitaiUpdater.RequestDelayMs",
  useComfyPaths: "CivitaiUpdater.PathSources.UseComfy",
  useExtraModelPaths: "CivitaiUpdater.PathSources.UseExtraModelPaths",
  useCustomPaths: "CivitaiUpdater.PathSources.UseCustom",
  customCheckpoint: "CivitaiUpdater.CustomPaths.Checkpoint",
  customLora: "CivitaiUpdater.CustomPaths.Lora",
  customVae: "CivitaiUpdater.CustomPaths.VAE",
  customUnet: "CivitaiUpdater.CustomPaths.UNet",
};

const state = {
  roots: {},
  rootsExpanded: false,
  currentJobId: null,
  currentJobType: null,
  currentJobStatus: null,
  currentSummary: null,
  currentProgress: 0,
  currentTotal: 0,
  currentItemCount: 0,
  pollTimer: null,
  lastStatus: "",
  lastItemCount: -1,

  checkJobId: null,
  checkSummary: null,
  scanSummary: null,
  resultItems: [],
  resultTotal: 0,
  resultOffset: 0,
  pageSize: PAGE_SIZES[0],
  pageOffset: 0,
  scanHint: "",

  rootEl: null,
  statusEl: null,
  helperEl: null,
  progressFillEl: null,
  progressTextEl: null,
  progressCountsEl: null,
  scanReportEl: null,
  checkSummaryEl: null,
  resultsEl: null,
  pageInfoEl: null,
  prevEl: null,
  nextEl: null,
  rootsSummaryEl: null,
  rootsDetailsEl: null,
  pauseEl: null,
  stopEl: null,

  settingsSyncTimer: null,
  suspendSettingsSync: false,
};

app.registerExtension({
  name: EXTENSION_NAME,
  settings: [
    { id: SETTINGS.apiKey, name: "API Key", type: "text", defaultValue: "", attrs: { type: "password", autocomplete: "off" }, tooltip: "Optional Civitai API key for restricted resources.", category: ["Civitai Updater", "Network", "API Key"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.requestTimeoutSeconds, name: "Request Timeout (seconds)", type: "number", defaultValue: 30, attrs: { min: 5, max: 300, step: 1 }, category: ["Civitai Updater", "Network", "Request Timeout"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.maxRetries, name: "Max Retries", type: "number", defaultValue: 4, attrs: { min: 0, max: 10, step: 1 }, category: ["Civitai Updater", "Network", "Max Retries"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.requestDelayMs, name: "Delay Between Models (ms)", type: "number", defaultValue: 120, attrs: { min: 0, max: 3000, step: 10 }, tooltip: "Small delay between model checks to reduce request bursts.", category: ["Civitai Updater", "Network", "Request Delay"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.useComfyPaths, name: "Use Comfy Default Paths", type: "boolean", defaultValue: true, category: ["Civitai Updater", "Path Sources", "Comfy Defaults"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.useExtraModelPaths, name: "Use extra_model_paths.yaml", type: "boolean", defaultValue: true, category: ["Civitai Updater", "Path Sources", "Extra Model Paths"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.useCustomPaths, name: "Use Custom Paths", type: "boolean", defaultValue: true, category: ["Civitai Updater", "Path Sources", "Custom Paths"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.customCheckpoint, name: "Checkpoint Paths", type: "text", defaultValue: "", tooltip: "Optional extra checkpoint roots. Use ';' or new lines.", category: ["Civitai Updater", "Custom Paths", "Checkpoint"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.customLora, name: "LoRA Paths", type: "text", defaultValue: "", tooltip: "Optional extra LoRA roots. Use ';' or new lines.", category: ["Civitai Updater", "Custom Paths", "LoRA"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.customVae, name: "VAE Paths", type: "text", defaultValue: "", tooltip: "Optional extra VAE roots. Use ';' or new lines.", category: ["Civitai Updater", "Custom Paths", "VAE"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.customUnet, name: "UNet Paths", type: "text", defaultValue: "", tooltip: "Optional extra UNet roots. Use ';' or new lines.", category: ["Civitai Updater", "Custom Paths", "UNet"], onChange: () => scheduleSettingsSync() },
  ],
  async setup() {
    injectStyles();
    await hydrateSettingsFromBackend();
    scheduleSettingsSync(true);
    app.extensionManager.registerSidebarTab({
      id: TAB_ID,
      icon: "pi pi-globe",
      title: "Civitai",
      tooltip: "Check local Comfy models for newer Civitai versions",
      type: "custom",
      render: (el) => renderTab(el),
    });
  },
});

async function renderTab(el) {
  el.innerHTML = "";
  const root = document.createElement("div");
  root.className = "cu-root";
  root.innerHTML = `
    <header class="cu-hero">
      <div class="cu-hero-title">Civitai</div>
      <p class="cu-hero-sub">Check update availability for local ComfyUI models.</p>
      <p class="cu-hero-note"><strong>Version</strong> means a specific Civitai release. Configure paths/network in <strong>Settings -> Civitai Updater</strong>.</p>
    </header>
    <section class="cu-card">
      <h3>Quick Actions</h3>
      <div class="cu-row">
        <button id="cu-check" class="cu-btn cu-btn-primary" title="Compares local releases with latest Civitai releases.">Check Updates</button>
        <button id="cu-pause" class="cu-btn" disabled title="Pause or resume current job.">Pause</button>
        <button id="cu-stop" class="cu-btn cu-btn-danger" disabled title="Stop current job.">Stop</button>
      </div>
      <p class="cu-help">Use <strong>Check Updates</strong> for actionable results. Metadata scan is in Advanced.</p>
      <div id="cu-helper" class="cu-helper"></div>
    </section>
    <section class="cu-card">
      <h3>Progress</h3>
      <div class="cu-progress-wrap"><div class="cu-progress"><div id="cu-progress-fill" class="cu-progress-fill"></div></div><div id="cu-progress-text" class="cu-mono">0% (0/0)</div></div>
      <div id="cu-progress-counts" class="cu-mono">Idle.</div>
      <div id="cu-status" class="cu-mono">Idle</div>
      <div id="cu-scan-report" class="cu-scan-report"></div>
    </section>
    <section class="cu-card">
      <div class="cu-head"><h3>Updates Results</h3><div class="cu-row"><label class="cu-small" for="cu-size">Page</label><select id="cu-size">${PAGE_SIZES.map((v) => `<option value="${v}">${v}</option>`).join("")}</select></div></div>
      <div id="cu-check-summary" class="cu-mono">No update check has run yet.</div>
      <div class="cu-head"><button id="cu-prev" class="cu-btn" disabled>Prev</button><span id="cu-page" class="cu-mono">Page 1 / 1</span><button id="cu-next" class="cu-btn" disabled>Next</button></div>
      <div id="cu-results" class="cu-results"></div>
    </section>
    <section class="cu-card">
      <details><summary>Advanced</summary>
        <p class="cu-help">Optional controls for model scope and scan behavior.</p>
        <div class="cu-label">Model Scope</div>
        <div class="cu-row">${MODEL_TYPES.map((t) => `<label class="cu-chip" title="Include ${t} in jobs."><input type="checkbox" data-type="${t}" checked><span>${t}</span></label>`).join("")}</div>
        <div class="cu-label">Check Options</div>
        <label class="cu-row cu-small" title="Recompute SHA256 even if metadata sidecar exists."><input id="cu-rehash" type="checkbox"><span>Force rehash during checks</span></label>
        <details class="cu-scan-opts">
          <summary>Scan Controls</summary>
          <p class="cu-help">Scan refreshes metadata only. It does not calculate update availability.</p>
          <div class="cu-row"><button id="cu-scan" class="cu-btn cu-btn-secondary" title="Refresh sidecar metadata only, no update check.">Scan Metadata</button></div>
          <label class="cu-row cu-small" title="If disabled, models with metadata are skipped."><input id="cu-refetch" type="checkbox"><span>Refetch metadata during scan</span></label>
        </details>
      </details>
    </section>
    <section class="cu-card">
      <div class="cu-head"><h3>Resolved Roots</h3><button id="cu-roots-toggle" class="cu-btn">Show paths</button></div>
      <div id="cu-roots-summary" class="cu-mono"></div>
      <div id="cu-roots" class="cu-roots" style="display:none"></div>
    </section>
  `;
  state.rootEl = root;
  state.statusEl = root.querySelector("#cu-status");
  state.helperEl = root.querySelector("#cu-helper");
  state.progressFillEl = root.querySelector("#cu-progress-fill");
  state.progressTextEl = root.querySelector("#cu-progress-text");
  state.progressCountsEl = root.querySelector("#cu-progress-counts");
  state.scanReportEl = root.querySelector("#cu-scan-report");
  state.checkSummaryEl = root.querySelector("#cu-check-summary");
  state.resultsEl = root.querySelector("#cu-results");
  state.pageInfoEl = root.querySelector("#cu-page");
  state.prevEl = root.querySelector("#cu-prev");
  state.nextEl = root.querySelector("#cu-next");
  state.rootsSummaryEl = root.querySelector("#cu-roots-summary");
  state.rootsDetailsEl = root.querySelector("#cu-roots");
  state.pauseEl = root.querySelector("#cu-pause");
  state.stopEl = root.querySelector("#cu-stop");
  bindEvents(root);
  renderRoots();
  renderScanReport();
  renderResults();
  updateControlButtons();
  root.querySelector("#cu-size").value = String(state.pageSize);
  el.appendChild(root);
}

function bindEvents(root) {
  root.querySelector("#cu-check").addEventListener("click", async () => startJob("/civitai-updater/jobs/check-updates", "check-updates"));
  root.querySelector("#cu-scan").addEventListener("click", async () => startJob("/civitai-updater/jobs/scan", "scan"));
  root.querySelector("#cu-pause").addEventListener("click", async () => togglePauseResume());
  root.querySelector("#cu-stop").addEventListener("click", async () => stopCurrentJob());
  root.querySelector("#cu-roots-toggle").addEventListener("click", () => {
    state.rootsExpanded = !state.rootsExpanded;
    renderRoots();
  });
  root.querySelector("#cu-size").addEventListener("change", async (ev) => {
    const next = Number(ev.target.value || PAGE_SIZES[0]);
    state.pageSize = PAGE_SIZES.includes(next) ? next : PAGE_SIZES[0];
    state.pageOffset = 0;
    await loadResultPage(true);
  });
  root.querySelector("#cu-prev").addEventListener("click", async () => {
    if (state.pageOffset <= 0) return;
    state.pageOffset = Math.max(0, state.pageOffset - state.pageSize);
    await loadResultPage(true);
  });
  root.querySelector("#cu-next").addEventListener("click", async () => {
    if (state.pageOffset + state.pageSize >= state.resultTotal) return;
    state.pageOffset += state.pageSize;
    await loadResultPage(true);
  });
}

async function startJob(endpoint, type) {
  if (state.currentJobId) {
    setStatus("A job is already running.");
    return;
  }
  const modelTypes = selectedTypes();
  if (!modelTypes.length) {
    setStatus("Select at least one model type in Advanced.");
    return;
  }
  const payload = {
    modelTypes,
    refetchMetadata: Boolean(state.rootEl?.querySelector("#cu-refetch")?.checked),
    forceRehash: Boolean(state.rootEl?.querySelector("#cu-rehash")?.checked),
  };
  try {
    const data = await postJson(endpoint, payload);
    state.currentJobId = data.jobId;
    state.currentJobType = type;
    state.currentJobStatus = "queued";
    state.currentSummary = null;
    state.currentProgress = 0;
    state.currentTotal = 0;
    state.currentItemCount = 0;
    state.lastStatus = "";
    state.lastItemCount = -1;
    if (type === "check-updates") {
      state.checkJobId = data.jobId;
      state.checkSummary = null;
      state.pageOffset = 0;
      state.resultItems = [];
      state.resultTotal = 0;
      state.resultOffset = 0;
      setHelper("Checking for updates. Page 1 auto-refreshes while running.");
    } else {
      setHelper("Scan running: metadata only. Run Check Updates for update cards.");
    }
    renderResults();
    renderProgressCounts();
    updateProgress(0, 0, "queued");
    updateControlButtons();
    setStatus(`Job started: ${data.jobId}`);
    pollJob(data.jobId);
  } catch (error) {
    setStatus(`Failed to start job: ${error.message}`);
  }
}

async function togglePauseResume() {
  if (!state.currentJobId) return;
  try {
    if (state.currentJobStatus === "paused") {
      await postJson(`/civitai-updater/jobs/${state.currentJobId}/resume`, {});
      setHelper("Job resumed.");
    } else {
      await postJson(`/civitai-updater/jobs/${state.currentJobId}/pause`, {});
      setHelper("Job paused.");
    }
  } catch (error) {
    setStatus(`Failed to pause/resume: ${error.message}`);
  }
}

async function stopCurrentJob() {
  if (!state.currentJobId) return;
  try {
    await postJson(`/civitai-updater/jobs/${state.currentJobId}/stop`, {});
    setHelper("Stop requested.");
  } catch (error) {
    setStatus(`Failed to stop: ${error.message}`);
  }
}

function pollJob(jobId) {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      const job = await getJson(`/civitai-updater/jobs/${jobId}`);
      const status = job.status || "running";
      const progress = Number(job.progress || 0);
      const total = Number(job.total || 0);
      const itemCount = Number(job.itemCount || 0);

      state.currentJobStatus = status;
      state.currentSummary = job.summary || null;
      state.currentProgress = progress;
      state.currentTotal = total;
      state.currentItemCount = itemCount;
      updateProgress(progress, total, status);
      renderProgressCounts();
      updateControlButtons();
      setStatus(`${status} ${progress}/${total} ${(job.message || "").trim()}`.trim());

      const statusChanged = status !== state.lastStatus;
      const countChanged = itemCount !== state.lastItemCount;

      if (state.currentJobType === "check-updates") {
        if (job.summary && Object.keys(job.summary).length > 0) state.checkSummary = job.summary;
        const onPage1 = state.pageOffset === 0;
        const running = status === "running" || status === "queued" || status === "paused";
        if ((statusChanged || countChanged || (running && onPage1)) && isTabVisible()) await loadResultPage(false);
      }

      if (state.currentJobType === "scan" && job.summary && Object.keys(job.summary).length > 0) {
        state.scanSummary = job.summary;
        state.scanHint = "Run Check Updates to see available updates.";
        renderScanReport();
      }

      state.lastStatus = status;
      state.lastItemCount = itemCount;

      if (["completed", "failed", "cancelled"].includes(status)) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        if (state.currentJobType === "check-updates") {
          if (job.summary && Object.keys(job.summary).length > 0) state.checkSummary = job.summary;
          await loadResultPage(true);
        }
        if (state.currentJobType === "scan") {
          if (job.summary && Object.keys(job.summary).length > 0) state.scanSummary = job.summary;
          state.scanHint = "Run Check Updates to see available updates.";
          renderScanReport();
          renderResults();
        }
        if (status === "failed" && Array.isArray(job.errors) && job.errors.length) setStatus(`Failed: ${job.errors[0]}`);
        state.currentJobId = null;
        state.currentJobType = null;
        state.currentJobStatus = null;
        state.currentSummary = null;
        state.currentProgress = 0;
        state.currentTotal = 0;
        state.currentItemCount = 0;
        updateControlButtons();
      }
    } catch (error) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      state.currentJobId = null;
      state.currentJobType = null;
      state.currentJobStatus = null;
      state.currentSummary = null;
      state.currentProgress = 0;
      state.currentTotal = 0;
      state.currentItemCount = 0;
      updateControlButtons();
      setStatus(`Failed to fetch job: ${error.message}`);
    }
  }, POLL_MS);
}

async function loadResultPage(force) {
  if (!state.checkJobId) {
    renderResults();
    return;
  }
  if (!isTabVisible() && !force) return;
  try {
    const query = new URLSearchParams({
      offset: String(state.pageOffset),
      limit: String(state.pageSize),
      mode: "updates",
    });
    const data = await getJson(`/civitai-updater/jobs/${state.checkJobId}/items?${query.toString()}`);
    state.resultItems = Array.isArray(data.items) ? data.items : [];
    state.resultTotal = Number(data.totalItems || 0);
    state.resultOffset = Number(data.offset || 0);
    state.pageOffset = state.resultOffset;
    if (state.resultTotal > 0 && state.resultOffset >= state.resultTotal) {
      state.pageOffset = Math.max(0, Math.floor((state.resultTotal - 1) / state.pageSize) * state.pageSize);
      if (!force) {
        await loadResultPage(true);
        return;
      }
    }
    renderResults();
  } catch (error) {
    setStatus(`Failed to fetch result page: ${error.message}`);
  }
}

function renderProgressCounts() {
  if (!state.progressCountsEl) return;
  const s = state.currentSummary;
  if (!s || !s.mode) {
    if (state.currentJobId) {
      state.progressCountsEl.textContent = `Running: processed ${state.currentProgress}/${state.currentTotal} | streamed ${state.currentItemCount}`;
      return;
    }
    state.progressCountsEl.textContent = "Idle.";
    return;
  }
  if (s.mode === "scan") {
    state.progressCountsEl.textContent = `Scan: total ${s.total || 0} | refreshed ${s.refreshed || 0} | skipped ${s.skipped || 0} | not found ${s.notFound || 0} | errors ${s.errors || 0}`;
    return;
  }
  state.progressCountsEl.textContent = `Check: total ${s.total || 0} | resolved ${s.resolved || 0} | updates ${s.withUpdates || 0} | not found ${s.notFound || 0} | errors ${s.errors || 0}`;
}

function renderScanReport() {
  if (!state.scanReportEl) return;
  if (!state.scanSummary) {
    state.scanReportEl.innerHTML = "";
    state.scanReportEl.classList.remove("is-visible");
    return;
  }
  state.scanReportEl.classList.add("is-visible");
  const s = state.scanSummary;
  state.scanReportEl.innerHTML = `<div class="cu-small"><strong>Latest Scan Report</strong> | Total ${s.total || 0} | Refreshed ${s.refreshed || 0} | Skipped ${s.skipped || 0} | Not found ${s.notFound || 0} | Errors ${s.errors || 0}<br>${escapeHtml(state.scanHint || "Run Check Updates to see available updates.")}</div>`;
}

function renderResults() {
  if (!state.resultsEl || !state.checkSummaryEl) return;
  if (state.checkSummary) {
    const s = state.checkSummary;
    state.checkSummaryEl.textContent = `Updates | Total ${s.total || 0} | Resolved ${s.resolved || 0} | Updates ${s.withUpdates || 0} | Not found ${s.notFound || 0} | Errors ${s.errors || 0}`;
  } else {
    state.checkSummaryEl.textContent = "No update check has run yet.";
  }
  state.resultsEl.innerHTML = "";
  if (!state.checkJobId) {
    appendEmpty("Run Check Updates to populate update results.");
    renderPagination();
    return;
  }
  if (!state.resultItems.length) {
    appendEmpty(state.resultTotal === 0 ? "No updates found for this check." : "No items on this page.");
    renderPagination();
    return;
  }
  for (const item of state.resultItems) {
    const card = document.createElement("article");
    card.className = "cu-item";
    card.innerHTML = `
      <div class="cu-thumb">${item.previewUrl ? `<img src="${escapeHtml(item.previewUrl)}" alt="preview" loading="lazy">` : `<div class="cu-thumb-empty">No image</div>`}</div>
      <div>
        <h4>${escapeHtml(item.modelPath || "unknown")}</h4>
        <div class="cu-meta">
          <span><strong>Type:</strong> ${escapeHtml(item.modelType || "-")}</span>
          <span><strong>Local:</strong> ${escapeHtml(item.localVersionName || "-")}</span>
          <span><strong>Latest:</strong> ${escapeHtml(item.latestVersionName || "-")}</span>
          <span><strong>Status:</strong> ${item.hasUpdate ? "Update available" : "Up to date"}</span>
        </div>
        <div class="cu-links"></div>
      </div>`;
    const links = card.querySelector(".cu-links");
    addLink(links, "Model", item.modelUrl);
    addLink(links, "Release", item.versionUrl);
    addLink(links, "File URL", item.downloadUrl);
    state.resultsEl.appendChild(card);
  }
  renderPagination();
}

function renderPagination() {
  if (!state.pageInfoEl || !state.prevEl || !state.nextEl) return;
  const total = Math.max(0, state.resultTotal);
  const size = Math.max(1, state.pageSize);
  const page = total === 0 ? 1 : Math.floor(state.resultOffset / size) + 1;
  const pages = Math.max(1, Math.ceil(total / size));
  state.pageInfoEl.textContent = `Page ${page} / ${pages} (${total} updates)`;
  state.prevEl.disabled = state.resultOffset <= 0;
  state.nextEl.disabled = state.resultOffset + size >= total;
}

function appendEmpty(text) {
  const el = document.createElement("div");
  el.className = "cu-empty";
  el.textContent = text;
  state.resultsEl.appendChild(el);
}

function renderRoots() {
  if (!state.rootsSummaryEl || !state.rootsDetailsEl || !state.rootEl) return;
  const counts = MODEL_TYPES.map((t) => `${t}: ${(state.roots[t] || []).length}`);
  state.rootsSummaryEl.textContent = counts.join(" | ");
  const toggle = state.rootEl.querySelector("#cu-roots-toggle");
  if (toggle) toggle.textContent = state.rootsExpanded ? "Hide paths" : "Show paths";
  state.rootsDetailsEl.style.display = state.rootsExpanded ? "block" : "none";
  state.rootsDetailsEl.innerHTML = "";
  for (const type of MODEL_TYPES) {
    const row = document.createElement("div");
    row.className = "cu-root-row";
    const items = state.roots[type] || [];
    row.innerHTML = `<span class="cu-root-name">${type}</span><span>${escapeHtml(items.length ? items.join("\n") : "(none)").replaceAll("\n", "<br>")}</span>`;
    state.rootsDetailsEl.appendChild(row);
  }
}

function updateControlButtons() {
  if (!state.pauseEl || !state.stopEl) return;
  const active = Boolean(state.currentJobId);
  state.pauseEl.disabled = !active;
  state.stopEl.disabled = !active;
  state.pauseEl.textContent = active && state.currentJobStatus === "paused" ? "Resume" : "Pause";
}

function selectedTypes() {
  if (!state.rootEl) return [...MODEL_TYPES];
  const selected = [];
  for (const box of state.rootEl.querySelectorAll("[data-type]")) {
    if (box.checked) selected.push(box.dataset.type);
  }
  return selected;
}

function updateProgress(current, total, status) {
  if (!state.progressFillEl || !state.progressTextEl) return;
  const safeTotal = Math.max(0, Number(total || 0));
  const safeCurrent = Math.max(0, Number(current || 0));
  const pct = safeTotal > 0 ? Math.min(100, Math.round((safeCurrent / safeTotal) * 100)) : 0;
  state.progressFillEl.style.width = `${pct}%`;
  state.progressTextEl.textContent = `${pct}% (${safeCurrent}/${safeTotal}) ${status || ""}`.trim();
}

function addLink(parent, label, href) {
  if (!href) return;
  const link = document.createElement("a");
  link.href = href;
  link.target = "_blank";
  link.rel = "noreferrer noopener";
  link.textContent = label;
  parent.appendChild(link);
}

function setStatus(message) {
  if (state.statusEl) state.statusEl.textContent = message;
}

function setHelper(message) {
  if (state.helperEl) state.helperEl.textContent = message || "";
}

function getSetting(id, fallback) {
  const value = app.extensionManager.setting.get(id, fallback);
  return value ?? fallback;
}

function setSetting(id, value) {
  app.extensionManager.setting.set(id, value);
}

async function hydrateSettingsFromBackend() {
  try {
    const data = await getJson("/civitai-updater/config");
    const cfg = data.config || {};
    state.suspendSettingsSync = true;
    setSetting(SETTINGS.requestTimeoutSeconds, Number(cfg.requestTimeoutSeconds ?? 30));
    setSetting(SETTINGS.maxRetries, Number(cfg.maxRetries ?? 4));
    setSetting(SETTINGS.requestDelayMs, Number(cfg.requestDelayMs ?? 120));
    setSetting(SETTINGS.useComfyPaths, Boolean(cfg.useComfyPaths ?? true));
    setSetting(SETTINGS.useExtraModelPaths, Boolean(cfg.useExtraModelPaths ?? true));
    setSetting(SETTINGS.useCustomPaths, Boolean(cfg.useCustomPaths ?? true));
    const custom = cfg.customPaths || {};
    setSetting(SETTINGS.customCheckpoint, listToSettingString(custom.checkpoint));
    setSetting(SETTINGS.customLora, listToSettingString(custom.lora));
    setSetting(SETTINGS.customVae, listToSettingString(custom.vae));
    setSetting(SETTINGS.customUnet, listToSettingString(custom.unet));
    state.roots = data.effectiveRoots || {};
  } catch (error) {
    console.warn("Civitai updater: failed to hydrate settings", error);
  } finally {
    state.suspendSettingsSync = false;
  }
}

function scheduleSettingsSync(immediate = false) {
  if (state.suspendSettingsSync) return;
  if (state.settingsSyncTimer) clearTimeout(state.settingsSyncTimer);
  state.settingsSyncTimer = setTimeout(() => syncSettingsToBackend(), immediate ? 0 : 300);
}

async function syncSettingsToBackend() {
  const payload = {
    apiKey: String(getSetting(SETTINGS.apiKey, "") || ""),
    requestTimeoutSeconds: Number(getSetting(SETTINGS.requestTimeoutSeconds, 30)),
    maxRetries: Number(getSetting(SETTINGS.maxRetries, 4)),
    requestDelayMs: Number(getSetting(SETTINGS.requestDelayMs, 120)),
    useComfyPaths: Boolean(getSetting(SETTINGS.useComfyPaths, true)),
    useExtraModelPaths: Boolean(getSetting(SETTINGS.useExtraModelPaths, true)),
    useCustomPaths: Boolean(getSetting(SETTINGS.useCustomPaths, true)),
    customPaths: {
      checkpoint: parsePathSetting(getSetting(SETTINGS.customCheckpoint, "")),
      lora: parsePathSetting(getSetting(SETTINGS.customLora, "")),
      vae: parsePathSetting(getSetting(SETTINGS.customVae, "")),
      unet: parsePathSetting(getSetting(SETTINGS.customUnet, "")),
    },
  };
  try {
    const data = await postJson("/civitai-updater/config", payload);
    state.roots = data.effectiveRoots || state.roots;
    if (state.rootEl) renderRoots();
  } catch (error) {
    console.warn("Civitai updater: failed syncing settings", error);
  }
}

function parsePathSetting(value) {
  if (!value) return [];
  return String(value)
    .replace(/;/g, "\n")
    .split(/\r?\n/g)
    .map((line) => line.trim())
    .filter(Boolean);
}

function listToSettingString(value) {
  return Array.isArray(value) ? value.join("; ") : "";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function isTabVisible() {
  return Boolean(state.rootEl && state.rootEl.offsetParent !== null);
}

async function getJson(path) {
  const response = await api.fetchApi(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postJson(path, payload) {
  const response = await api.fetchApi(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function injectStyles() {
  if (document.getElementById("cu-styles")) return;
  const style = document.createElement("style");
  style.id = "cu-styles";
  style.textContent = `
    .cu-root {
      --cu-bg-0: #0f1218;
      --cu-bg-1: #151c2a;
      --cu-card: #182033;
      --cu-card-2: #1b2538;
      --cu-text: #e9eefb;
      --cu-muted: #a2afc8;
      --cu-border: #2a3852;
      --cu-accent: #1ccf98;
      --cu-accent-2: #4fb4ff;
      --cu-danger: #ff6f7d;
      font-family: "Manrope", "Avenir Next", "Segoe UI", sans-serif;
      color: var(--cu-text);
      display: flex;
      flex-direction: column;
      gap: 14px;
      padding: 14px;
      font-size: 13px;
      line-height: 1.45;
      background:
        radial-gradient(68% 36% at 5% -8%, rgba(31, 218, 166, 0.2), transparent 64%),
        radial-gradient(52% 26% at 100% 0%, rgba(80, 178, 255, 0.17), transparent 62%),
        linear-gradient(180deg, var(--cu-bg-0), var(--cu-bg-1));
    }

    .cu-hero,
    .cu-card {
      position: relative;
      border: 1px solid var(--cu-border);
      border-radius: 16px;
      padding: 14px;
      background: linear-gradient(180deg, var(--cu-card), var(--cu-card-2));
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.03);
      overflow: hidden;
    }

    .cu-hero::before,
    .cu-card::before {
      content: "";
      position: absolute;
      inset: 0 0 auto 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(79, 180, 255, 0.45), transparent);
      pointer-events: none;
    }

    .cu-hero {
      background:
        radial-gradient(70% 80% at 0% 0%, rgba(28, 207, 152, 0.16), transparent 62%),
        linear-gradient(170deg, #17263a 0%, #162033 45%, #192236 100%);
    }

    .cu-hero-title {
      font-family: "Sora", "Avenir Next", "Segoe UI", sans-serif;
      font-size: 39px;
      line-height: 1;
      font-weight: 700;
      letter-spacing: 0.01em;
      margin: 0 0 7px 0;
      color: #f7fbff;
    }

    .cu-hero-sub {
      margin: 0;
      color: #b6c4dd;
      font-size: 20px;
    }

    .cu-hero-note {
      margin: 8px 0 0 0;
      color: #a6b4ce;
      font-size: 17px;
    }

    .cu-hero-note strong {
      color: #d9e4f7;
      font-weight: 700;
    }

    .cu-card h3 {
      margin: 0 0 10px 0;
      color: #dbe4f7;
      font-size: 14px;
      text-transform: none;
      letter-spacing: 0.03em;
      font-weight: 700;
    }

    .cu-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }

    .cu-row {
      display: flex;
      gap: 9px;
      flex-wrap: wrap;
      align-items: center;
    }

    .cu-label {
      margin-top: 10px;
      color: #b5c1d8;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }

    .cu-help,
    .cu-small {
      margin: 0;
      color: var(--cu-muted);
      line-height: 1.35;
    }

    .cu-helper {
      margin-top: 7px;
      min-height: 16px;
      color: #d7f8eb;
      font-weight: 600;
    }

    .cu-btn {
      border: 1px solid var(--cu-border);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.045);
      color: #dbe6fa;
      padding: 7px 13px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 700;
      transition: border-color 120ms ease, filter 120ms ease, transform 120ms ease;
    }

    .cu-btn:hover {
      border-color: #446086;
      filter: brightness(1.08);
      transform: translateY(-1px);
    }

    .cu-btn:disabled {
      opacity: 0.42;
      transform: none;
      cursor: default;
      filter: none;
    }

    .cu-btn-primary {
      border-color: rgba(0, 0, 0, 0);
      color: #07160f;
      background: linear-gradient(145deg, var(--cu-accent), #22b886);
      box-shadow: 0 6px 18px rgba(28, 207, 152, 0.3);
    }

    .cu-btn-secondary {
      color: #a9e2ff;
      border-color: rgba(79, 180, 255, 0.36);
      background: rgba(79, 180, 255, 0.15);
    }

    .cu-btn-danger {
      color: #ff9ca6;
      border-color: rgba(255, 111, 125, 0.36);
      background: rgba(255, 111, 125, 0.12);
    }

    .cu-chip {
      border: 1px solid #334866;
      border-radius: 999px;
      padding: 4px 8px;
      display: inline-flex;
      gap: 5px;
      align-items: center;
      background: rgba(79, 180, 255, 0.07);
      color: #d7e6ff;
    }

    .cu-scan-opts {
      margin-top: 9px;
      border-top: 1px dashed #2e405c;
      padding-top: 8px;
    }

    .cu-scan-opts > summary,
    details > summary {
      cursor: pointer;
      color: #d5e2f8;
      font-size: 13px;
      font-weight: 700;
    }

    .cu-progress-wrap {
      display: flex;
      gap: 10px;
      align-items: center;
    }

    .cu-progress {
      position: relative;
      flex: 1;
      height: 12px;
      border-radius: 999px;
      border: 1px solid #2e415f;
      background: rgba(255, 255, 255, 0.035);
      overflow: hidden;
    }

    .cu-progress-fill {
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 0;
      background: linear-gradient(90deg, var(--cu-accent), var(--cu-accent-2));
      transition: width 160ms linear;
    }

    .cu-mono {
      font-family: "Manrope", "Avenir Next", "Segoe UI", sans-serif;
      color: #b3c1db;
      font-size: 13px;
      letter-spacing: 0.01em;
    }

    #cu-progress-text,
    #cu-page {
      font-family: "JetBrains Mono", "Consolas", monospace;
      font-size: 12px;
      color: #a7b6d0;
    }

    .cu-scan-report {
      display: none;
      margin-top: 9px;
      border: 1px solid rgba(243, 166, 56, 0.46);
      border-radius: 12px;
      background: linear-gradient(180deg, rgba(243, 166, 56, 0.12), rgba(243, 166, 56, 0.08));
      padding: 9px 10px;
      color: #ffe4b7;
    }

    .cu-scan-report.is-visible {
      display: block;
    }

    .cu-results {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 9px;
    }

    .cu-item {
      display: grid;
      grid-template-columns: 84px 1fr;
      gap: 11px;
      border: 1px solid #30405d;
      border-radius: 14px;
      padding: 10px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.015));
    }

    .cu-thumb {
      width: 84px;
      height: 84px;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #334a6a;
      background: rgba(255, 255, 255, 0.05);
    }

    .cu-thumb img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    .cu-thumb-empty {
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      color: #a8b8d3;
      font-size: 11px;
      padding: 4px;
    }

    .cu-item h4 {
      margin: 0 0 5px 0;
      font-size: 13px;
      color: #eaf1ff;
      font-weight: 700;
      word-break: break-word;
    }

    .cu-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: #a9b8d2;
      font-size: 12px;
      margin-bottom: 7px;
    }

    .cu-links {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
    }

    .cu-links a {
      text-decoration: none;
      border: 1px solid rgba(79, 180, 255, 0.45);
      border-radius: 999px;
      padding: 2px 9px;
      background: rgba(79, 180, 255, 0.14);
      color: #a4e0ff;
      font-weight: 700;
      font-size: 11px;
    }

    .cu-empty {
      font-style: italic;
      color: #a9b7d0;
    }

    .cu-roots {
      display: flex;
      flex-direction: column;
      gap: 7px;
      margin-top: 8px;
      color: #afbdd6;
      font-size: 12px;
    }

    .cu-root-row {
      display: grid;
      grid-template-columns: 96px 1fr;
      gap: 8px;
      border-bottom: 1px dashed rgba(255, 255, 255, 0.11);
      padding-bottom: 5px;
    }

    .cu-root-name {
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #b1c0dc;
      font-weight: 700;
    }

    #cu-size {
      border: 1px solid #3a4d6e;
      border-radius: 8px;
      padding: 4px 8px;
      background: rgba(255, 255, 255, 0.05);
      color: #e0e9fb;
      font-size: 12px;
    }

    @media (max-width: 880px) {
      .cu-hero-title {
        font-size: 33px;
      }

      .cu-hero-sub {
        font-size: 17px;
      }

      .cu-hero-note {
        font-size: 15px;
      }

      .cu-item {
        grid-template-columns: 1fr;
      }

      .cu-thumb {
        width: 100%;
        height: 170px;
      }

      .cu-progress-wrap {
        flex-direction: column;
        align-items: stretch;
      }
    }
  `;
  document.head.appendChild(style);
}
