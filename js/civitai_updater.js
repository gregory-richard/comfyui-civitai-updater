import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const TAB_ID = "civitai-updater";
const EXTENSION_NAME = "civitai-updater.ui";
const TAB_ICON_CLASS = "cu-tab-icon";
const TAB_ICON = `pi pi-refresh ${TAB_ICON_CLASS}`;
const TAB_ICON_URL = new URL("./icon-monochrome.svg", import.meta.url).href;
const MODEL_TYPES = ["checkpoint", "lora", "vae", "unet", "embedding"];
const PAGE_SIZES = [25, 50, 100];
const POLL_MS = 800;

const SETTINGS = {
  apiKey: "CivitaiUpdater.APIKey",
  cacheTtlMinutes: "CivitaiUpdater.CacheTtlMinutes",
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
  forceNextRecheck: false,
  cachedJobId: null,
  cacheFilesChanged: null,

  checkJobId: null,
  checkSummary: null,
  cachedAt: null,
  scanSummary: null,
  resultItems: [],
  resultTotal: 0,
  resultOffset: 0,
  pageSize: PAGE_SIZES[0],
  pageOffset: 0,
  scanHint: "",
  filterType: "",
  filterBase: "",
  sortOrder: "name",
  facets: { modelTypes: [], baseModels: [] },

  rootEl: null,
  cacheInfoEl: null,
  statusEl: null,
  progressWrapEl: null,
  progressFillEl: null,
  progressTextEl: null,
  scanReportEl: null,
  checkSummaryEl: null,
  filterTypeEl: null,
  filterBaseEl: null,
  resultsEl: null,
  pageInfoEl: null,
  prevEl: null,
  nextEl: null,
  rootsSummaryEl: null,
  rootsDetailsEl: null,
  pauseEl: null,
  stopEl: null,
  jobControlsEl: null,

  settingsSyncTimer: null,
  suspendSettingsSync: false,
};

app.registerExtension({
  name: EXTENSION_NAME,
  settings: [
    { id: SETTINGS.apiKey, name: "API Key", type: "text", defaultValue: "", attrs: { type: "password", autocomplete: "off" }, tooltip: "Optional Civitai API key for restricted resources.", category: ["Civitai Updater", "Network", "API Key"], onChange: () => scheduleSettingsSync() },
    { id: SETTINGS.cacheTtlMinutes, name: "Cache Duration (minutes)", type: "number", defaultValue: 240, attrs: { min: 0, max: 10080, step: 30 }, tooltip: "How long to reuse cached check results before re-checking. 0 = always check fresh.", category: ["Civitai Updater", "General", "Cache Duration"], onChange: () => scheduleSettingsSync() },
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
      icon: TAB_ICON,
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
      <p class="cu-hero-sub">Check local models for newer versions on Civitai</p>
    </header>

    <section class="cu-card">
      <details class="cu-settings">
        <summary>Settings</summary>
        <div class="cu-settings-body">
          <div class="cu-label">Model Scope</div>
          <div class="cu-row">${MODEL_TYPES.map((t) => `<label class="cu-chip" title="Include ${t} in jobs"><input type="checkbox" data-type="${t}" checked><span>${t.charAt(0).toUpperCase() + t.slice(1)}</span></label>`).join("")}</div>
          <div class="cu-label">Options</div>
          <label class="cu-option" title="Re-identify every model by recomputing its SHA256 hash, even if cached metadata exists. Use this after manually replacing model files — the cache won't know the file changed otherwise."><input id="cu-rehash" type="checkbox"><span>Force rehash</span></label>
          <p class="cu-option-hint">Re-identify models from scratch. Use after replacing files.</p>
          <label class="cu-option" title="During metadata scans, re-fetch info from Civitai even for models that already have a .civitai.info file."><input id="cu-refetch" type="checkbox"><span>Refetch existing metadata during scans</span></label>
          <div class="cu-divider"></div>
          <div class="cu-head">
            <div class="cu-label">Resolved Roots</div>
            <button id="cu-roots-toggle" class="cu-text-btn">Show</button>
          </div>
          <div id="cu-roots-summary" class="cu-roots-sum"></div>
          <div id="cu-roots" class="cu-roots" style="display:none"></div>
        </div>
      </details>
    </section>

    <section class="cu-card">
      <div class="cu-action-bar">
        <button id="cu-check" class="cu-btn cu-btn-primary" title="Compare local versions with latest Civitai releases">Check Updates</button>
        <button id="cu-scan" class="cu-btn cu-btn-outline" title="Refresh sidecar metadata only — no update check. Run this first if Check Updates seems to miss files.">Scan Metadata</button>
      </div>
      <div id="cu-cache-info" class="cu-cache-info"></div>
      <div id="cu-progress-wrap" class="cu-progress-wrap" style="display:none">
        <div class="cu-progress"><div id="cu-progress-fill" class="cu-progress-fill"></div></div>
        <span id="cu-progress-text" class="cu-progress-pct"></span>
      </div>
      <div id="cu-status" class="cu-status"></div>
      <div id="cu-job-controls" class="cu-job-controls" style="display:none">
        <button id="cu-pause" class="cu-btn cu-btn-sm" title="Pause or resume the current job">Pause</button>
        <button id="cu-stop" class="cu-btn cu-btn-sm cu-btn-danger" title="Abort the current job">Stop</button>
      </div>
    </section>

    <section class="cu-card">
      <div class="cu-head">
        <h3>Results</h3>
        <select id="cu-size" title="Results per page">${PAGE_SIZES.map((v) => `<option value="${v}">${v}</option>`).join("")}</select>
      </div>
      <div id="cu-scan-report" class="cu-scan-report"></div>
      <div id="cu-check-summary" class="cu-summary">No check has run yet.</div>
      <div class="cu-filters">
        <select id="cu-filter-type" title="Filter by model type"><option value="">All types</option></select>
        <select id="cu-filter-base" title="Filter by base model"><option value="">All bases</option></select>
        <select id="cu-sort" title="Sort results">
          <option value="name">Name A\u2013Z</option>
          <option value="name-desc">Name Z\u2013A</option>
          <option value="type">Type</option>
          <option value="latest-date-desc">Newest first</option>
          <option value="latest-date">Oldest first</option>
        </select>
      </div>
      <div id="cu-results" class="cu-results"></div>
      <div class="cu-pagination">
        <button id="cu-prev" class="cu-page-btn" disabled title="Previous page">&lsaquo;</button>
        <span id="cu-page" class="cu-page-info">1 / 1</span>
        <button id="cu-next" class="cu-page-btn" disabled title="Next page">&rsaquo;</button>
      </div>
    </section>
  `;

  state.rootEl = root;
  state.cacheInfoEl = root.querySelector("#cu-cache-info");
  state.statusEl = root.querySelector("#cu-status");
  state.progressWrapEl = root.querySelector("#cu-progress-wrap");
  state.progressFillEl = root.querySelector("#cu-progress-fill");
  state.progressTextEl = root.querySelector("#cu-progress-text");
  state.scanReportEl = root.querySelector("#cu-scan-report");
  state.checkSummaryEl = root.querySelector("#cu-check-summary");
  state.filterTypeEl = root.querySelector("#cu-filter-type");
  state.filterBaseEl = root.querySelector("#cu-filter-base");
  state.resultsEl = root.querySelector("#cu-results");
  state.pageInfoEl = root.querySelector("#cu-page");
  state.prevEl = root.querySelector("#cu-prev");
  state.nextEl = root.querySelector("#cu-next");
  state.rootsSummaryEl = root.querySelector("#cu-roots-summary");
  state.rootsDetailsEl = root.querySelector("#cu-roots");
  state.pauseEl = root.querySelector("#cu-pause");
  state.stopEl = root.querySelector("#cu-stop");
  state.jobControlsEl = root.querySelector("#cu-job-controls");
  bindEvents(root);
  renderRoots();
  renderScanReport();
  renderResults();
  updateControlButtons();
  root.querySelector("#cu-size").value = String(state.pageSize);
  el.appendChild(root);

  if (!state.currentJobId && !state.checkJobId) {
    loadCachedResults();
  }
}

async function loadCachedResults() {
  try {
    const resp = await getJson("/civitai-updater/last-check");
    if (!resp.data) return;

    if (resp.data.inProgress) {
      const activeResp = await getJson("/civitai-updater/jobs/active");
      if (activeResp.job) {
        state.currentJobId = activeResp.job.jobId;
        state.currentJobType = activeResp.job.type;
        state.currentJobStatus = activeResp.job.status;
        state.currentProgress = activeResp.job.progress || 0;
        state.currentTotal = activeResp.job.total || 0;
        state.currentItemCount = activeResp.job.itemCount || 0;
        if (activeResp.job.type === "check-updates") {
          state.checkJobId = activeResp.job.jobId;
        }
        updateProgress(state.currentProgress, state.currentTotal, true);
        updateControlButtons();
        setStatus(`Reconnected \u2014 ${activeResp.job.message || "running"}`);
        pollJob(activeResp.job.jobId);
        return;
      }
      setStatus("Previous check was interrupted. Run Check Updates again.");
      return;
    }

    state.cachedJobId = resp.data.jobId;
    state.checkSummary = resp.data.summary || null;
    state.cachedAt = resp.data.checkedAt || null;
    state.cacheFilesChanged = resp.data.filesChanged
      ? { added: resp.data.filesAdded || 0, removed: resp.data.filesRemoved || 0 }
      : null;
    renderCacheInfo();
    renderResults();
  } catch (_) {
    // cache load is best-effort
  }
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
  root.querySelector("#cu-filter-type").addEventListener("change", async (ev) => {
    state.filterType = ev.target.value;
    state.pageOffset = 0;
    await loadResultPage(true);
  });
  root.querySelector("#cu-filter-base").addEventListener("change", async (ev) => {
    state.filterBase = ev.target.value;
    state.pageOffset = 0;
    await loadResultPage(true);
  });
  root.querySelector("#cu-sort").addEventListener("change", async (ev) => {
    state.sortOrder = ev.target.value;
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
    setStatus("Select at least one model type in Settings.");
    return;
  }
  const forceRehash = Boolean(state.rootEl?.querySelector("#cu-rehash")?.checked);
  const payload = {
    modelTypes,
    refetchMetadata: Boolean(state.rootEl?.querySelector("#cu-refetch")?.checked),
    forceRehash,
  };

  if (type === "check-updates" && !state.forceNextRecheck && !state.cacheFilesChanged && !forceRehash && state.cachedAt) {
    const ttl = Number(getSetting(SETTINGS.cacheTtlMinutes, 240)) * 60 * 1000;
    const age = Date.now() - new Date(state.cachedAt).getTime();
    if (ttl > 0 && age < ttl && state.cachedJobId) {
      // Cache is still fresh — load the cached results without re-running.
      state.checkJobId = state.cachedJobId;
      state.pageOffset = 0;
      state.filterType = "";
      state.filterBase = "";
      state.facets = { modelTypes: [], baseModels: [] };
      renderFilters();
      await loadResultPage(true);
      renderCacheInfo();
      setStatus(`Showing cached results from ${timeAgo(state.cachedAt)} \u2014 click Refresh to re-check.`);
      return;
    }
  }
  state.forceNextRecheck = false;

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
      state.cachedJobId = data.jobId;
      state.checkSummary = null;
      state.pageOffset = 0;
      state.resultItems = [];
      state.resultTotal = 0;
      state.resultOffset = 0;
      state.filterType = "";
      state.filterBase = "";
      state.facets = { modelTypes: [], baseModels: [] };
      renderFilters();
    }
    renderResults();
    updateProgress(0, 0, true);
    updateControlButtons();
    setStatus(type === "check-updates" ? "Checking for updates\u2026" : "Scanning metadata\u2026");
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
      setStatus("Job resumed.");
    } else {
      await postJson(`/civitai-updater/jobs/${state.currentJobId}/pause`, {});
      setStatus("Job paused.");
    }
  } catch (error) {
    setStatus(`Failed to pause/resume: ${error.message}`);
  }
}

async function stopCurrentJob() {
  if (!state.currentJobId) return;
  try {
    await postJson(`/civitai-updater/jobs/${state.currentJobId}/stop`, {});
    setStatus("Stop requested.");
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
      updateProgress(progress, total, true);
      renderProgressCounts();
      updateControlButtons();

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
        if (status === "failed") {
          const msg = Array.isArray(job.errors) && job.errors.length ? job.errors[0] : "Unknown error";
          setStatus(`Failed: ${msg}`);
        } else if (status === "cancelled") {
          setStatus("Job cancelled");
        } else if (state.currentJobType === "check-updates") {
          const updates = job.summary?.withUpdates || 0;
          state.cachedAt = new Date().toISOString();
          state.cacheFilesChanged = null;
          renderCacheInfo();
          setStatus(`Done \u2014 ${updates} update${updates !== 1 ? "s" : ""} found`);
        } else {
          setStatus("Scan complete");
        }
        updateProgress(progress, total, false);
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
      updateProgress(0, 0, false);
      updateControlButtons();
      setStatus(`Poll error: ${error.message}`);
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
      sort: state.sortOrder || "name",
    });
    if (state.filterType) query.set("modelType", state.filterType);
    if (state.filterBase) query.set("baseModel", state.filterBase);
    const data = await getJson(`/civitai-updater/jobs/${state.checkJobId}/items?${query.toString()}`);
    state.resultItems = Array.isArray(data.items) ? data.items : [];
    state.resultTotal = Number(data.totalItems || 0);
    state.resultOffset = Number(data.offset || 0);
    state.pageOffset = state.resultOffset;
    if (data.facets) {
      state.facets = data.facets;
      renderFilters();
    }
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
  if (!state.statusEl) return;
  const s = state.currentSummary;
  if (!s || !s.mode) {
    if (state.currentJobId) {
      state.statusEl.textContent = `Processing ${state.currentProgress} of ${state.currentTotal}`;
    }
    return;
  }
  if (s.mode === "scan") {
    state.statusEl.textContent = `Scan: ${s.total || 0} total \u00b7 ${s.refreshed || 0} refreshed \u00b7 ${s.skipped || 0} skipped \u00b7 ${s.errors || 0} errors`;
    return;
  }
  state.statusEl.textContent = `${s.total || 0} checked \u00b7 ${s.withUpdates || 0} updates \u00b7 ${s.notFound || 0} not found \u00b7 ${s.errors || 0} errors`;
}

function renderCacheInfo() {
  if (!state.cacheInfoEl) return;
  if (!state.cachedAt) {
    state.cacheInfoEl.innerHTML = "";
    state.cacheInfoEl.style.display = "none";
    return;
  }
  const ttl = Number(getSetting(SETTINGS.cacheTtlMinutes, 240));
  const age = Date.now() - new Date(state.cachedAt).getTime();
  const fresh = ttl > 0 && age < ttl * 60 * 1000;
  const dirty = state.cacheFilesChanged;

  let dot, label;
  if (dirty) {
    const parts = [];
    if (dirty.added) parts.push(`${dirty.added} added`);
    if (dirty.removed) parts.push(`${dirty.removed} removed`);
    dot = `<span class="cu-cache-stale">\u25cf</span>`;
    label = `models changed (${parts.join(", ")}) \u2014 re-check recommended`;
  } else if (fresh) {
    dot = `<span class="cu-cache-fresh">\u25cf</span>`;
    label = "cached";
  } else {
    dot = `<span class="cu-cache-stale">\u25cf</span>`;
    label = "stale";
  }

  const showRefresh = fresh && !dirty;
  const refreshPart = showRefresh ? ` \u00b7 <button id="cu-force-recheck" class="cu-text-btn">Refresh</button>` : "";
  state.cacheInfoEl.innerHTML = `${dot} Last checked ${timeAgo(state.cachedAt)} \u00b7 ${label}${refreshPart}`;
  state.cacheInfoEl.style.display = "";
  const refreshEl = state.cacheInfoEl.querySelector("#cu-force-recheck");
  if (refreshEl) {
    refreshEl.addEventListener("click", () => {
      state.forceNextRecheck = true;
      startJob("/civitai-updater/jobs/check-updates", "check-updates");
    });
  }
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
  state.scanReportEl.innerHTML = `<div class="cu-small"><strong>Last Scan</strong> \u00b7 ${s.total || 0} total \u00b7 ${s.refreshed || 0} refreshed \u00b7 ${s.skipped || 0} skipped \u00b7 ${s.errors || 0} errors<br>${escapeHtml(state.scanHint || "")}</div>`;
}

function renderResults() {
  if (!state.resultsEl || !state.checkSummaryEl) return;
  if (state.checkSummary) {
    const s = state.checkSummary;
    state.checkSummaryEl.textContent = `${s.total || 0} checked \u00b7 ${s.withUpdates || 0} updates \u00b7 ${s.notFound || 0} not found \u00b7 ${s.errors || 0} errors`;
  } else {
    state.checkSummaryEl.textContent = "No check has run yet.";
  }
  state.resultsEl.innerHTML = "";
  if (!state.checkJobId) {
    appendEmpty("Run Check Updates to see results.");
    renderPagination();
    return;
  }
  if (!state.resultItems.length) {
    appendEmpty(state.resultTotal === 0 ? "No updates found." : "No items on this page.");
    renderPagination();
    return;
  }
  for (const item of state.resultItems) {
    const card = document.createElement("article");
    card.className = "cu-item";
    const localVersions = item.localVersions || [];
    const firstPath = localVersions.length ? localVersions[0].modelPath : "";
    const displayName = item.modelName ? escapeHtml(item.modelName) : escapeHtml(extractFilename(firstPath || "unknown"));

    const typePill = item.modelType ? `<span class="cu-type-pill" data-type="${escapeHtml(item.modelType)}">${escapeHtml(capitalize(item.modelType))}</span>` : "";
    const creatorHtml = item.creatorName ? `<span class="cu-creator">by ${escapeHtml(item.creatorName)}</span>` : "";

    const latestDate = item.latestVersionDate ? shortDate(item.latestVersionDate) : "";
    const latestNameHtml = item.versionUrl
      ? `<a class="cu-ver-link" href="${escapeHtml(item.versionUrl)}" target="_blank" rel="noreferrer noopener">${escapeHtml(item.latestVersionName || "?")}</a>`
      : `<span class="cu-ver-link">${escapeHtml(item.latestVersionName || "?")}</span>`;
    const latestBasePill = item.latestBaseModel ? `<span class="cu-ver-tag">${escapeHtml(item.latestBaseModel)}</span>` : "";
    const latestDatePill = latestDate ? `<span class="cu-ver-tag">${latestDate}</span>` : "";

    const localRows = localVersions.map((v) => {
      const date = v.publishedAt ? shortDate(v.publishedAt) : "";
      const basePill = v.baseModel ? `<span class="cu-ver-tag">${escapeHtml(v.baseModel)}</span>` : "";
      const datePill = date ? `<span class="cu-ver-tag">${date}</span>` : "";
      return `<div class="cu-ver-row"><span class="cu-ver-label" data-role="saved">Saved</span>${datePill}${basePill}<span class="cu-ver-link cu-copy-path" data-path="${escapeHtml(v.modelPath || "")}" title="Click to copy file path">${escapeHtml(v.versionName || "?")}</span></div>`;
    }).join("");

    let thumbHtml;
    if (item.previewUrl && item.previewType === "video") {
      thumbHtml = `<video src="${escapeHtml(item.previewUrl)}#t=0.5" preload="metadata" muted playsinline></video>`;
    } else if (item.previewUrl) {
      thumbHtml = `<img src="${escapeHtml(item.previewUrl)}" alt="" loading="lazy">`;
    } else {
      thumbHtml = `<div class="cu-thumb-empty">No preview</div>`;
    }

    card.innerHTML = `
      <div class="cu-thumb">${thumbHtml}</div>
      <div class="cu-item-body">
        <div class="cu-item-header">
          <h4 title="${escapeHtml(firstPath)}">${displayName}</h4>
          ${creatorHtml}
        </div>
        ${typePill ? `<div class="cu-pills">${typePill}</div>` : ""}
        <div class="cu-versions">
          ${localRows}
          <div class="cu-ver-row"><span class="cu-ver-label" data-role="new">New</span>${latestDatePill}${latestBasePill}${latestNameHtml}</div>
        </div>
      </div>`;
    for (const el of card.querySelectorAll(".cu-copy-path")) {
      el.addEventListener("click", (e) => {
        const target = e.currentTarget;
        const path = target.dataset.path || "";
        const original = target.textContent;
        navigator.clipboard.writeText(path).then(() => {
          target.textContent = "Copied!";
          setTimeout(() => { target.textContent = original; }, 1500);
        }).catch(() => {
          target.textContent = "Failed";
          setTimeout(() => { target.textContent = original; }, 1500);
        });
      });
    }
    card.querySelector(".cu-thumb").addEventListener("click", () => openLightbox(item));
    state.resultsEl.appendChild(card);
  }
  renderPagination();
}

function renderFilters() {
  if (!state.filterTypeEl || !state.filterBaseEl) return;
  const prevType = state.filterType;
  const prevBase = state.filterBase;
  state.filterTypeEl.innerHTML = `<option value="">All types</option>` + state.facets.modelTypes.map((t) => `<option value="${escapeHtml(t)}"${t === prevType ? " selected" : ""}>${escapeHtml(capitalize(t))}</option>`).join("");
  state.filterBaseEl.innerHTML = `<option value="">All bases</option>` + state.facets.baseModels.map((b) => `<option value="${escapeHtml(b)}"${b === prevBase ? " selected" : ""}>${escapeHtml(b)}</option>`).join("");
}

function renderPagination() {
  if (!state.pageInfoEl || !state.prevEl || !state.nextEl) return;
  const total = Math.max(0, state.resultTotal);
  const size = Math.max(1, state.pageSize);
  const page = total === 0 ? 1 : Math.floor(state.resultOffset / size) + 1;
  const pages = Math.max(1, Math.ceil(total / size));
  state.pageInfoEl.textContent = `${page} / ${pages}`;
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
  state.rootsSummaryEl.textContent = counts.join(" \u00b7 ");
  const toggle = state.rootEl.querySelector("#cu-roots-toggle");
  if (toggle) toggle.textContent = state.rootsExpanded ? "Hide" : "Show";
  state.rootsDetailsEl.style.display = state.rootsExpanded ? "block" : "none";
  state.rootsDetailsEl.innerHTML = "";
  for (const type of MODEL_TYPES) {
    const row = document.createElement("div");
    row.className = "cu-root-row";
    const items = state.roots[type] || [];
    row.innerHTML = `<span class="cu-root-type">${type}</span><span>${escapeHtml(items.length ? items.join("\n") : "(none)").replaceAll("\n", "<br>")}</span>`;
    state.rootsDetailsEl.appendChild(row);
  }
}

function updateControlButtons() {
  if (!state.pauseEl || !state.stopEl || !state.jobControlsEl) return;
  const active = Boolean(state.currentJobId);
  state.pauseEl.textContent = active && state.currentJobStatus === "paused" ? "Resume" : "Pause";
  state.jobControlsEl.style.display = active ? "flex" : "none";
}

function selectedTypes() {
  if (!state.rootEl) return [...MODEL_TYPES];
  const selected = [];
  for (const box of state.rootEl.querySelectorAll("[data-type]")) {
    if (box.checked) selected.push(box.dataset.type);
  }
  return selected;
}

function updateProgress(current, total, visible) {
  if (!state.progressWrapEl || !state.progressFillEl || !state.progressTextEl) return;
  state.progressWrapEl.style.display = visible ? "" : "none";
  const safeTotal = Math.max(0, Number(total || 0));
  const safeCurrent = Math.max(0, Number(current || 0));
  const pct = safeTotal > 0 ? Math.min(100, Math.round((safeCurrent / safeTotal) * 100)) : 0;
  state.progressFillEl.style.width = `${pct}%`;
  state.progressTextEl.textContent = safeTotal > 0 ? `${pct}%` : "";
}

function setStatus(message) {
  if (state.statusEl) state.statusEl.textContent = message;
}

function extractFilename(path) {
  const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return i >= 0 ? path.substring(i + 1) : path;
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
    setSetting(SETTINGS.cacheTtlMinutes, Number(cfg.cacheTtlMinutes ?? 240));
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
    cacheTtlMinutes: Number(getSetting(SETTINGS.cacheTtlMinutes, 240)),
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

function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function shortDate(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch (_) {
    return "";
  }
}

function timeAgo(isoString) {
  const ms = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
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

function openLightbox(item) {
  closeLightbox();
  const localVersions = item.localVersions || [];
  const hasComparison = localVersions.some((v) => v.previewUrl) && item.previewUrl;

  let sections = "";
  for (const v of localVersions) {
    if (!v.previewUrl) continue;
    const base = v.baseModel ? ` <span class="cu-lb-base">${escapeHtml(v.baseModel)}</span>` : "";
    const media = v.previewType === "video"
      ? `<video src="${escapeHtml(v.previewUrl)}" preload="auto" muted playsinline controls></video>`
      : `<img src="${escapeHtml(v.previewUrl)}" alt="">`;
    sections += `<div class="cu-lb-card"><div class="cu-lb-label">Local</div><div class="cu-lb-vname">${escapeHtml(v.versionName || "?")}${base}</div>${media}</div>`;
  }
  if (item.previewUrl) {
    const latestBase = item.latestBaseModel ? ` <span class="cu-lb-base">${escapeHtml(item.latestBaseModel)}</span>` : "";
    const media = item.previewType === "video"
      ? `<video src="${escapeHtml(item.previewUrl)}" preload="auto" muted playsinline controls></video>`
      : `<img src="${escapeHtml(item.previewUrl)}" alt="">`;
    sections += `<div class="cu-lb-card"><div class="cu-lb-label">Latest</div><div class="cu-lb-vname">${escapeHtml(item.latestVersionName || "?")}${latestBase}</div>${media}</div>`;
  }

  const overlay = document.createElement("div");
  overlay.className = "cu-lightbox";
  overlay.id = "cu-lightbox";
  overlay.innerHTML = `
    <div class="cu-lb-backdrop"></div>
    <div class="cu-lb-container">
      <div class="cu-lb-header">
        <span class="cu-lb-title">${escapeHtml(item.modelName || "Preview")}${item.creatorName ? ` <span class="cu-creator">by ${escapeHtml(item.creatorName)}</span>` : ""}</span>
        <button class="cu-lb-close" title="Close">&times;</button>
      </div>
      <div class="cu-lb-body ${hasComparison ? "cu-lb-compare" : ""}">
        ${sections || '<div style="color:#5a6a85;font-style:italic;padding:20px">No previews available</div>'}
      </div>
    </div>`;

  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add("cu-lb-open"));

  overlay.querySelector(".cu-lb-backdrop").addEventListener("click", closeLightbox);
  overlay.querySelector(".cu-lb-close").addEventListener("click", closeLightbox);

  const onKey = (e) => { if (e.key === "Escape") { closeLightbox(); document.removeEventListener("keydown", onKey); } };
  document.addEventListener("keydown", onKey);
}

function closeLightbox() {
  const el = document.getElementById("cu-lightbox");
  if (el) el.remove();
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
    .${TAB_ICON_CLASS} {
      display: inline-block;
      width: 1em;
      height: 1em;
      vertical-align: middle;
    }

    @supports ((mask: url("")) or (-webkit-mask: url(""))) {
      .${TAB_ICON_CLASS} {
        background-color: currentColor;
        -webkit-mask: url("${TAB_ICON_URL}") center / contain no-repeat;
        mask: url("${TAB_ICON_URL}") center / contain no-repeat;
      }

      .${TAB_ICON_CLASS}::before {
        content: none !important;
      }
    }

    .cu-root {
      --cu-bg-0: #0f1218;
      --cu-bg-1: #151c2a;
      --cu-card: #182033;
      --cu-text: #e4eaf5;
      --cu-muted: #8d9bb5;
      --cu-border: #263048;
      --cu-accent: #1ccf98;
      --cu-accent-2: #4fb4ff;
      --cu-danger: #ff6f7d;
      --cu-warn: #f3a638;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      color: var(--cu-text);
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 12px;
      font-size: 12.5px;
      line-height: 1.4;
      background: linear-gradient(180deg, var(--cu-bg-0), var(--cu-bg-1));
    }

    /* ---- Hero ---- */

    .cu-hero {
      padding: 14px 12px 12px;
      border-radius: 12px;
      border: 1px solid var(--cu-border);
      background: linear-gradient(135deg, rgba(28, 207, 152, 0.08) 0%, var(--cu-card) 60%);
    }

    .cu-hero-title {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.02em;
      margin: 0 0 2px 0;
      color: #f0f5ff;
    }

    .cu-hero-sub {
      margin: 0;
      color: var(--cu-muted);
      font-size: 12px;
    }

    /* ---- Cards ---- */

    .cu-card {
      border: 1px solid var(--cu-border);
      border-radius: 12px;
      padding: 12px;
      background: var(--cu-card);
    }

    .cu-card > h3,
    .cu-head h3 {
      margin: 0;
      color: #a0b0c8;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-weight: 700;
    }

    .cu-card > h3 {
      margin-bottom: 8px;
    }

    .cu-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }

    /* ---- Layout helpers ---- */

    .cu-action-bar {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }

    .cu-action-bar .cu-btn-primary {
      flex: 1;
      min-width: 110px;
    }

    .cu-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      align-items: center;
    }

    .cu-label {
      margin: 10px 0 4px 0;
      color: var(--cu-muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .cu-head .cu-label {
      margin: 0;
    }

    .cu-help {
      margin: 2px 0 6px 0;
      color: var(--cu-muted);
      font-size: 11.5px;
      line-height: 1.35;
    }

    .cu-small {
      font-size: 11.5px;
      color: var(--cu-muted);
    }

    .cu-divider {
      border: none;
      border-top: 1px solid var(--cu-border);
      margin: 10px 0;
    }

    /* ---- Buttons ---- */

    .cu-btn {
      border: 1px solid var(--cu-border);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.04);
      color: #c0cfea;
      padding: 5px 11px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      line-height: 1.3;
      transition: border-color 100ms, background 100ms;
    }

    .cu-btn:hover {
      border-color: #3d5478;
      background: rgba(255, 255, 255, 0.07);
    }

    .cu-btn:disabled {
      opacity: 0.35;
      cursor: default;
      pointer-events: none;
    }

    .cu-btn-primary {
      border-color: transparent;
      color: #072016;
      background: linear-gradient(135deg, var(--cu-accent), #1ab583);
      font-weight: 700;
    }

    .cu-btn-primary:hover {
      filter: brightness(1.1);
    }

    .cu-btn-secondary {
      color: #8dd4f5;
      border-color: rgba(79, 180, 255, 0.3);
      background: rgba(79, 180, 255, 0.1);
    }

    .cu-btn-danger {
      color: #ff9ca6;
      border-color: rgba(255, 111, 125, 0.3);
      background: rgba(255, 111, 125, 0.08);
    }

    .cu-btn-outline {
      color: var(--cu-muted);
      border-color: var(--cu-border);
      background: transparent;
      font-weight: 500;
      font-size: 11px;
    }

    .cu-btn-sm {
      padding: 3px 9px;
      font-size: 11px;
    }

    .cu-text-btn {
      background: none;
      border: none;
      color: var(--cu-accent-2);
      cursor: pointer;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 0;
    }

    .cu-text-btn:hover {
      text-decoration: underline;
    }

    /* ---- Job controls ---- */

    .cu-job-controls {
      gap: 6px;
      align-items: center;
      margin-top: 6px;
    }

    /* ---- Progress ---- */

    .cu-progress-wrap {
      display: flex;
      gap: 8px;
      align-items: center;
      margin-top: 6px;
      margin-bottom: 4px;
    }

    .cu-progress {
      flex: 1;
      height: 6px;
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.06);
      overflow: hidden;
    }

    .cu-progress-fill {
      height: 100%;
      width: 0;
      background: linear-gradient(90deg, var(--cu-accent), var(--cu-accent-2));
      border-radius: 3px;
      transition: width 200ms linear;
    }

    .cu-progress-pct {
      font-family: "JetBrains Mono", "Consolas", monospace;
      font-size: 11px;
      color: var(--cu-muted);
      min-width: 28px;
      text-align: right;
    }

    /* ---- Cache info ---- */

    .cu-cache-info {
      font-size: 11px;
      color: var(--cu-muted);
      margin-bottom: 4px;
    }

    .cu-cache-fresh {
      color: var(--cu-accent);
      font-size: 9px;
    }

    .cu-cache-stale {
      color: var(--cu-warn);
      font-size: 9px;
    }

    /* ---- Status ---- */

    .cu-status {
      font-size: 11.5px;
      color: var(--cu-muted);
      min-height: 16px;
      margin-top: 2px;
    }

    /* ---- Scan report banner ---- */

    .cu-scan-report {
      display: none;
      margin-bottom: 8px;
      border: 1px solid rgba(79, 180, 255, 0.2);
      border-radius: 8px;
      background: rgba(79, 180, 255, 0.06);
      padding: 8px 10px;
      color: #b8d4f0;
      font-size: 11.5px;
    }

    .cu-scan-report.is-visible {
      display: block;
    }

    /* ---- Results ---- */

    .cu-summary {
      font-size: 11.5px;
      color: var(--cu-muted);
      margin-bottom: 8px;
    }

    .cu-filters {
      display: flex;
      gap: 6px;
      margin-bottom: 8px;
    }

    .cu-filters select {
      flex: 1;
      border: 1px solid var(--cu-border);
      border-radius: 6px;
      padding: 4px 6px;
      background: rgba(255, 255, 255, 0.04);
      color: #c0cfea;
      font-size: 11px;
    }

    .cu-results {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .cu-empty {
      font-style: italic;
      color: #5a6a85;
      font-size: 11.5px;
      padding: 4px 0;
    }

    /* ---- Result cards ---- */

    .cu-item {
      display: grid;
      grid-template-columns: 56px 1fr;
      gap: 10px;
      border: 1px solid var(--cu-border);
      border-radius: 10px;
      padding: 8px;
      background: rgba(255, 255, 255, 0.02);
    }

    .cu-thumb {
      width: 56px;
      height: 56px;
      border-radius: 8px;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.04);
      flex-shrink: 0;
      cursor: pointer;
      position: relative;
    }

    .cu-thumb::after {
      content: "";
      position: absolute;
      inset: 0;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.35);
      opacity: 0;
      transition: opacity 150ms;
      pointer-events: none;
    }

    .cu-thumb:hover::after {
      opacity: 1;
    }

    .cu-thumb img,
    .cu-thumb video {
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
      color: #5a6a85;
      font-size: 9px;
      text-align: center;
    }

    .cu-item-body {
      min-width: 0;
    }

    .cu-item-header {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 3px;
    }

    .cu-item-header h4 {
      margin: 0;
      font-size: 12px;
      font-weight: 600;
      color: #dce5f5;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }

    .cu-pills {
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
      margin-bottom: 4px;
    }

    .cu-type-pill {
      display: inline-block;
      font-size: 9px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #7a8aa5;
      border: 1px solid var(--cu-border);
      border-radius: 4px;
      padding: 1px 5px;
    }

    .cu-type-pill[data-type="checkpoint"] { color: #7eb0ff; border-color: rgba(126, 176, 255, 0.3); background: rgba(126, 176, 255, 0.06); }
    .cu-type-pill[data-type="lora"] { color: #1ccf98; border-color: rgba(28, 207, 152, 0.3); background: rgba(28, 207, 152, 0.06); }
    .cu-type-pill[data-type="vae"] { color: #c49bff; border-color: rgba(196, 155, 255, 0.3); background: rgba(196, 155, 255, 0.06); }
    .cu-type-pill[data-type="unet"] { color: #f3a638; border-color: rgba(243, 166, 56, 0.3); background: rgba(243, 166, 56, 0.06); }
    .cu-type-pill[data-type="embedding"] { color: #ff8eb3; border-color: rgba(255, 142, 179, 0.3); background: rgba(255, 142, 179, 0.06); }

    .cu-versions {
      display: flex;
      flex-direction: column;
      gap: 5px;
      margin-bottom: 5px;
      font-size: 11px;
    }

    .cu-ver-row {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .cu-ver-label {
      font-size: 9px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      padding: 1px 5px;
      border-radius: 3px;
      white-space: nowrap;
      flex-shrink: 0;
      min-width: 32px;
      text-align: center;
    }

    .cu-ver-label[data-role="saved"] {
      color: #8d9bb5;
      background: rgba(141, 155, 181, 0.1);
      border: 1px solid rgba(141, 155, 181, 0.15);
    }

    .cu-ver-label[data-role="new"] {
      color: #7eb0ff;
      background: rgba(126, 176, 255, 0.1);
      border: 1px solid rgba(126, 176, 255, 0.2);
    }

    .cu-ver-link {
      color: var(--cu-accent-2);
      cursor: pointer;
      text-decoration: none;
      transition: color 100ms;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      min-width: 0;
    }

    .cu-ver-link:hover {
      color: #a0d8ff;
      text-decoration: underline;
    }

    .cu-ver-tag {
      font-size: 9px;
      padding: 1px 5px;
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.06);
      color: #6e7e99;
      white-space: nowrap;
      flex-shrink: 0;
    }

    .cu-creator {
      font-size: 11px;
      color: #5a6a85;
      font-weight: 400;
      white-space: nowrap;
      flex-shrink: 0;
    }

    /* ---- Pagination ---- */

    .cu-pagination {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      margin-top: 8px;
    }

    .cu-page-btn {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--cu-border);
      border-radius: 6px;
      color: #c0cfea;
      cursor: pointer;
      font-size: 14px;
      font-weight: 700;
      width: 28px;
      height: 28px;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      line-height: 1;
      transition: border-color 100ms;
    }

    .cu-page-btn:hover {
      border-color: #3d5478;
    }

    .cu-page-btn:disabled {
      opacity: 0.3;
      cursor: default;
      pointer-events: none;
    }

    .cu-page-info {
      font-family: "JetBrains Mono", "Consolas", monospace;
      font-size: 11px;
      color: var(--cu-muted);
    }

    /* ---- Chips ---- */

    .cu-chip {
      border: 1px solid #2a3d58;
      border-radius: 6px;
      padding: 3px 7px;
      display: inline-flex;
      gap: 4px;
      align-items: center;
      background: rgba(79, 180, 255, 0.05);
      color: #b0c4e0;
      font-size: 11px;
      cursor: pointer;
    }

    .cu-option {
      display: flex;
      align-items: center;
      gap: 6px;
      color: #a0b0c8;
      font-size: 11.5px;
      cursor: pointer;
      margin: 4px 0;
    }

    .cu-option-hint {
      margin: -2px 0 4px 0;
      padding-left: 22px;
      font-size: 10.5px;
      color: #5f7090;
      line-height: 1.3;
    }

    /* ---- Settings collapsible ---- */

    .cu-settings > summary {
      cursor: pointer;
      color: #a0b0c8;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-weight: 700;
      list-style: none;
      user-select: none;
    }

    .cu-settings > summary::-webkit-details-marker {
      display: none;
    }

    .cu-settings > summary::before {
      content: "\\25B8  ";
      font-size: 9px;
    }

    .cu-settings[open] > summary::before {
      content: "\\25BE  ";
    }

    .cu-settings-body {
      margin-top: 8px;
    }

    /* ---- Select ---- */

    #cu-size {
      border: 1px solid var(--cu-border);
      border-radius: 6px;
      padding: 3px 6px;
      background: rgba(255, 255, 255, 0.04);
      color: #c0cfea;
      font-size: 11px;
    }

    /* ---- Resolved Roots ---- */

    .cu-roots-sum {
      font-size: 11px;
      color: var(--cu-muted);
    }

    .cu-roots {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 6px;
      font-size: 11px;
      color: var(--cu-muted);
    }

    .cu-root-row {
      display: grid;
      grid-template-columns: 80px 1fr;
      gap: 6px;
      padding-bottom: 4px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }

    .cu-root-type {
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #7a8aa5;
      font-weight: 700;
      font-size: 10px;
    }

    /* ---- Responsive ---- */

    @media (max-width: 600px) {
      .cu-item {
        grid-template-columns: 1fr;
      }

      .cu-thumb {
        width: 100%;
        height: 120px;
      }
    }

    /* ---- Lightbox (appended to body, not inside .cu-root) ---- */

    .cu-lightbox {
      position: fixed;
      inset: 0;
      z-index: 99999;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: opacity 150ms ease;
    }

    .cu-lightbox.cu-lb-open {
      opacity: 1;
    }

    .cu-lb-backdrop {
      position: absolute;
      inset: 0;
      background: rgba(0, 0, 0, 0.82);
    }

    .cu-lb-container {
      position: relative;
      background: #1a2235;
      border: 1px solid #2a3d58;
      border-radius: 14px;
      max-width: 92vw;
      max-height: 92vh;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      box-shadow: 0 12px 48px rgba(0, 0, 0, 0.6);
    }

    .cu-lb-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid #263048;
      flex-shrink: 0;
    }

    .cu-lb-title {
      color: #e4eaf5;
      font-size: 15px;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }

    .cu-lb-close {
      background: none;
      border: none;
      color: #6a7a95;
      font-size: 26px;
      cursor: pointer;
      padding: 0 2px;
      line-height: 1;
      flex-shrink: 0;
      transition: color 120ms;
    }

    .cu-lb-close:hover {
      color: #e4eaf5;
    }

    .cu-lb-body {
      padding: 18px;
      display: flex;
      gap: 18px;
      justify-content: center;
      flex-wrap: wrap;
    }

    .cu-lb-body:not(.cu-lb-compare) {
      justify-content: center;
    }

    .cu-lb-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      min-width: 0;
      flex: 0 1 auto;
    }

    .cu-lb-label {
      font-size: 9px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #5a6a85;
    }

    .cu-lb-vname {
      font-size: 12px;
      color: #b0c4e0;
      text-align: center;
      max-width: 400px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .cu-lb-base {
      font-size: 10px;
      color: #6a7a95;
    }

    .cu-lb-card img,
    .cu-lb-card video {
      max-width: min(420px, 42vw);
      max-height: 65vh;
      border-radius: 10px;
      object-fit: contain;
      background: rgba(0, 0, 0, 0.3);
    }

    .cu-lb-body:not(.cu-lb-compare) .cu-lb-card img,
    .cu-lb-body:not(.cu-lb-compare) .cu-lb-card video {
      max-width: min(600px, 80vw);
      max-height: 75vh;
    }
  `;
  document.head.appendChild(style);
}
