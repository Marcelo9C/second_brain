/**
 * SMFP Governance Dashboard — smfp_governance.js
 *
 * Fetches model registry, review board, dataset health, and governance timeline
 * from the SMFP backend API and renders them into the dashboard.
 *
 * PERSISTENCE: Dashboard state is persisted to sessionStorage so tab-switching
 * within the same browser session does not lose data. Data is only cleared by:
 *  - Clicking "Reset Cache" (the bottom button)
 *  - Explicit page refresh (F5 / Ctrl-R)
 */

const API_BASE =
  window.location.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://127.0.0.1:8765";

const CACHE_KEY = "smfp_governance.dashboard_cache";

/* ---------------------------------------------------------------
   State
   --------------------------------------------------------------- */
const dashState = {
  modelRegistry: null,    // raw model_registry.json data
  activeModel: null,      // active model entry or null
  mlStatus: null,         // string
  datasetSummary: null,   // dataset/summary response
  timeline: [],           // timeline events
  reviews: {},            // model_id -> [reviews]
  lastRefreshed: null,    // ISO string
};

/* ---------------------------------------------------------------
   DOM References
   --------------------------------------------------------------- */
const el = {
  // Sidebar — Active Model
  modelCard: document.getElementById("gov-model-card"),
  activeModelLabel: document.getElementById("gov-active-model-label"),
  mlStatus: document.getElementById("gov-ml-status"),
  accuracy: document.getElementById("gov-accuracy"),
  macroF1: document.getElementById("gov-macro-f1"),
  algorithm: document.getElementById("gov-algorithm"),
  labels: document.getElementById("gov-labels"),
  trainedAt: document.getElementById("gov-trained-at"),
  promotedAt: document.getElementById("gov-promoted-at"),
  promotedBy: document.getElementById("gov-promoted-by"),
  // Sidebar — Dataset
  totalSamples: document.getElementById("gov-total-samples"),
  labeledCount: document.getElementById("gov-labeled-count"),
  unlabeledCount: document.getElementById("gov-unlabeled-count"),
  labelDistribution: document.getElementById("gov-label-distribution"),
  splitDistribution: document.getElementById("gov-split-distribution"),
  // Main — Model Registry
  modelCount: document.getElementById("gov-model-count"),
  modelRegistry: document.getElementById("gov-model-registry"),
  // Main — Review Board
  reviewProfile: document.getElementById("gov-review-profile"),
  reviewBoard: document.getElementById("gov-review-board"),
  // Main — Timeline
  timelineFilterType: document.getElementById("gov-timeline-filter-type"),
  timelineCount: document.getElementById("gov-timeline-count"),
  timeline: document.getElementById("gov-timeline"),
  // Actions
  refreshBtn: document.getElementById("gov-refresh"),
  resetBtn: document.getElementById("gov-reset"),
};

/* ---------------------------------------------------------------
   Helpers
   --------------------------------------------------------------- */
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || payload.error || "request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatShortDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function shortId(modelId) {
  if (!modelId) return "—";
  return modelId.length > 12 ? modelId.slice(0, 12) + "…" : modelId;
}

function formatCounts(obj) {
  if (!obj || typeof obj !== "object") return "—";
  return Object.entries(obj)
    .map(([key, val]) => `${key}: ${val}`)
    .join(", ") || "—";
}

/* ---------------------------------------------------------------
   SessionStorage Persistence
   --------------------------------------------------------------- */
function saveCache() {
  try {
    dashState.lastRefreshed = new Date().toISOString();
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(dashState));
  } catch (err) {
    console.warn("[Governance] cache save failed", err);
  }
}

function loadCache() {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return false;
    const cached = JSON.parse(raw);
    Object.assign(dashState, cached);
    return true;
  } catch {
    return false;
  }
}

function clearCache() {
  sessionStorage.removeItem(CACHE_KEY);
  dashState.modelRegistry = null;
  dashState.activeModel = null;
  dashState.mlStatus = null;
  dashState.datasetSummary = null;
  dashState.timeline = [];
  dashState.reviews = {};
  dashState.lastRefreshed = null;
}

/* ---------------------------------------------------------------
   Data Fetching
   --------------------------------------------------------------- */
async function fetchModelRegistry() {
  try {
    // The model_registry.json endpoint — we use the training config endpoint
    const data = await fetchJson("/api/smfp/ml/train-baseline");
    // This might return a 405 for GET — let's try to get model registry via timeline
    dashState.modelRegistry = data;
  } catch {
    // Fallback: parse from timeline events
  }
}

async function fetchAllData() {
  el.refreshBtn.disabled = true;
  el.refreshBtn.textContent = "Loading…";

  const errors = [];

  // 1. Dataset summary
  try {
    dashState.datasetSummary = await fetchJson("/api/smfp/dataset/summary");
  } catch (err) {
    errors.push(`dataset: ${err.message}`);
  }

  // 2. Timeline (includes model events)
  try {
    dashState.timeline = await fetchJson("/api/smfp/governance/timeline");
  } catch (err) {
    errors.push(`timeline: ${err.message}`);
    dashState.timeline = [];
  }

  // 3. Extract model info from timeline events
  extractModelInfo();

  // 4. Fetch reviews for each model found
  await fetchReviewsForModels();

  saveCache();
  renderAll();

  el.refreshBtn.disabled = false;
  el.refreshBtn.textContent = "Refresh Dashboard";

  if (errors.length) {
    console.warn("[Governance] partial errors:", errors);
  }
}

function extractModelInfo() {
  const events = Array.isArray(dashState.timeline) ? dashState.timeline : [];

  // Find all unique model IDs from training/promotion/retirement events
  const modelMap = {};

  for (const event of events) {
    const mid = event.model_id;
    if (!mid) continue;

    if (!modelMap[mid]) {
      modelMap[mid] = {
        model_id: mid,
        status: "baseline",
        algorithm: null,
        accuracy: null,
        macro_f1: null,
        labels_trained: null,
        trained_at: null,
        promoted_at: null,
        retired_at: null,
        promoted_by: null,
      };
    }

    const m = modelMap[mid];

    if (event.event_type === "baseline_trained") {
      m.trained_at = event.timestamp;
      m.status = "baseline";
      if (event.details) {
        m.algorithm = event.details.algorithm || m.algorithm;
        m.accuracy = event.details.accuracy ?? m.accuracy;
        m.macro_f1 = event.details.macro_f1 ?? m.macro_f1;
        m.labels_trained = event.details.labels_trained ?? m.labels_trained;
      }
    }

    if (event.event_type === "model_promoted") {
      m.promoted_at = event.timestamp;
      m.status = "active";
      if (event.details) {
        m.promoted_by = event.details.promoted_by || m.promoted_by;
      }
    }

    if (event.event_type === "model_retired") {
      m.retired_at = event.timestamp;
      m.status = "retired";
    }
  }

  const models = Object.values(modelMap);
  dashState.modelRegistry = models;

  // Determine active model
  const active = models.find((m) => m.status === "active");
  dashState.activeModel = active || null;
  dashState.mlStatus = active ? "active" : "disabled";
}

async function fetchReviewsForModels() {
  const models = dashState.modelRegistry || [];
  const reviewMap = {};

  for (const model of models) {
    try {
      const reviews = await fetchJson(`/api/smfp/ml/models/${model.model_id}/reviews`);
      reviewMap[model.model_id] = Array.isArray(reviews) ? reviews : [];
    } catch {
      reviewMap[model.model_id] = [];
    }
  }

  dashState.reviews = reviewMap;
}

/* ---------------------------------------------------------------
   Rendering
   --------------------------------------------------------------- */
function renderAll() {
  renderActiveModel();
  renderDatasetHealth();
  renderModelRegistry();
  renderReviewBoard();
  renderTimeline();
}

function renderActiveModel() {
  const model = dashState.activeModel;

  if (!model) {
    el.activeModelLabel.textContent = "No model active";
    el.mlStatus.className = "badge warning";
    el.mlStatus.textContent = "disabled";
    el.modelCard.classList.remove("active-model");
    el.modelCard.classList.add("no-model");
    el.accuracy.textContent = "—";
    el.macroF1.textContent = "—";
    el.algorithm.textContent = "—";
    el.labels.textContent = "—";
    el.trainedAt.textContent = "—";
    el.promotedAt.textContent = "—";
    el.promotedBy.textContent = "—";
    return;
  }

  el.modelCard.classList.add("active-model");
  el.modelCard.classList.remove("no-model");
  el.activeModelLabel.textContent = shortId(model.model_id);
  el.mlStatus.className = "badge ok";
  el.mlStatus.textContent = "active";
  el.accuracy.textContent = model.accuracy != null ? Number(model.accuracy).toFixed(4) : "—";
  el.macroF1.textContent = model.macro_f1 != null ? Number(model.macro_f1).toFixed(4) : "—";
  el.algorithm.textContent = model.algorithm || "—";
  el.labels.textContent = model.labels_trained != null ? String(model.labels_trained) : "—";
  el.trainedAt.textContent = formatDate(model.trained_at);
  el.promotedAt.textContent = formatDate(model.promoted_at);

  if (model.promoted_by && typeof model.promoted_by === "object") {
    el.promotedBy.textContent = `${model.promoted_by.actor_type || "?"} / ${model.promoted_by.actor_id || "?"}`;
  } else {
    el.promotedBy.textContent = model.promoted_by || "—";
  }
}

function renderDatasetHealth() {
  const ds = dashState.datasetSummary;
  if (!ds) {
    el.totalSamples.textContent = "—";
    el.labeledCount.textContent = "—";
    el.unlabeledCount.textContent = "—";
    el.labelDistribution.textContent = "—";
    el.splitDistribution.textContent = "—";
    return;
  }

  const total = ds.total_samples || 0;
  const unlabeled = ds.unlabeled_count || 0;
  el.totalSamples.textContent = String(total);
  el.labeledCount.textContent = String(total - unlabeled);
  el.unlabeledCount.textContent = String(unlabeled);
  el.labelDistribution.textContent = formatCounts(ds.samples_by_label);
  el.splitDistribution.textContent = formatCounts(ds.samples_by_split);
}

function renderModelRegistry() {
  const models = dashState.modelRegistry || [];
  el.modelCount.textContent = String(models.length);

  if (!models.length) {
    el.modelRegistry.innerHTML = `
      <div class="gov-empty-state">
        <strong>No models registered</strong>
        <span>Train a baseline model to see it here.</span>
      </div>
    `;
    return;
  }

  // Sort: active first, then baseline, then candidate, then retired
  const order = { active: 0, candidate: 1, baseline: 2, retired: 3 };
  const sorted = [...models].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));

  el.modelRegistry.innerHTML = sorted
    .map((m) => {
      const reviewCount = (dashState.reviews[m.model_id] || []).length;
      return `
        <div class="gov-model-entry status-${m.status}">
          <span class="gov-model-entry-status ${m.status}">${m.status}</span>
          <div class="gov-model-entry-info">
            <strong title="${escapeHtml(m.model_id)}">${escapeHtml(shortId(m.model_id))}</strong>
            <span>${m.algorithm || "unknown"} · trained ${formatShortDate(m.trained_at)} · ${reviewCount} review${reviewCount !== 1 ? "s" : ""}</span>
          </div>
          <div class="gov-model-entry-metrics">
            <span>acc <code>${m.accuracy != null ? Number(m.accuracy).toFixed(3) : "—"}</code></span>
            <span>f1 <code>${m.macro_f1 != null ? Number(m.macro_f1).toFixed(3) : "—"}</code></span>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderReviewBoard() {
  const allReviews = [];

  for (const [modelId, reviews] of Object.entries(dashState.reviews || {})) {
    for (const review of reviews) {
      allReviews.push({ ...review, model_id: modelId });
    }
  }

  // Sort newest first
  allReviews.sort((a, b) => {
    const ta = a.reviewed_at || a.timestamp || "";
    const tb = b.reviewed_at || b.timestamp || "";
    return tb.localeCompare(ta);
  });

  if (!allReviews.length) {
    el.reviewBoard.innerHTML = `
      <div class="gov-empty-state">
        <strong>No reviews submitted</strong>
        <span>Submit a model review via the API to populate this panel.</span>
      </div>
    `;
    return;
  }

  el.reviewBoard.innerHTML = allReviews
    .map((r) => {
      const verdict = r.decision || r.verdict || "—";
      const icon = verdict === "approve" ? "✓" : verdict === "reject" ? "✕" : "?";
      const reviewer = r.reviewer && typeof r.reviewer === "object"
        ? `${r.reviewer.actor_id || "?"} (${r.reviewer.actor_type || "?"})`
        : r.reviewer || "unknown";
      const context = r.review_context || "pre_promotion";

      return `
        <div class="gov-review-entry">
          <span class="gov-review-verdict ${verdict}">${icon}</span>
          <div class="gov-review-info">
            <strong>${escapeHtml(verdict)}</strong>
            <span>${escapeHtml(reviewer)} · ${escapeHtml(context)} · model ${escapeHtml(shortId(r.model_id))}</span>
          </div>
          <div class="gov-review-meta">
            <strong>${formatShortDate(r.reviewed_at || r.timestamp)}</strong>
            ${r.notes ? `<span>${escapeHtml(r.notes.slice(0, 60))}</span>` : ""}
          </div>
        </div>
      `;
    })
    .join("");
}

function renderTimeline(filterOverride = null) {
  const events = Array.isArray(dashState.timeline) ? dashState.timeline : [];
  const filterType = filterOverride ?? el.timelineFilterType.value;

  const filtered = filterType
    ? events.filter((e) => e.event_type === filterType)
    : events;

  el.timelineCount.textContent = String(filtered.length);

  if (!filtered.length) {
    el.timeline.innerHTML = `
      <div class="gov-empty-state">
        <strong>No events${filterType ? ` of type "${filterType}"` : ""}</strong>
        <span>Governance events appear as the model lifecycle progresses.</span>
      </div>
    `;
    return;
  }

  // Timeline is already sorted chronologically from API, show newest first
  const reversed = [...filtered].reverse();

  const eventConfig = {
    dataset_sample_added: { icon: "+", iconClass: "sample", label: "Sample added" },
    dataset_sample_labeled: { icon: "L", iconClass: "labeled", label: "Sample labeled" },
    baseline_trained: { icon: "T", iconClass: "trained", label: "Baseline trained" },
    review_submitted: { icon: "R", iconClass: "review", label: "Review submitted" },
    model_approved: { icon: "✓", iconClass: "approved", label: "Model approved" },
    model_promoted: { icon: "↑", iconClass: "promoted", label: "Model promoted" },
    model_retired: { icon: "◉", iconClass: "retired", label: "Model retired" },
  };

  el.timeline.innerHTML = reversed
    .map((event) => {
      const config = eventConfig[event.event_type] || { icon: "?", iconClass: "sample", label: event.event_type };
      const detail = event.model_id
        ? `model ${shortId(event.model_id)}`
        : event.details?.sample_id
          ? `sample ${shortId(event.details.sample_id)}`
          : "";
      const detailExtra = event.details
        ? Object.entries(event.details)
            .filter(([k]) => !["sample_id", "model_id", "promoted_by"].includes(k))
            .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
            .slice(0, 3)
            .join(" · ")
        : "";

      return `
        <div class="gov-timeline-event" data-event-type="${escapeHtml(event.event_type)}">
          <span class="gov-event-icon ${config.iconClass}">${config.icon}</span>
          <div class="gov-event-body">
            <strong>${escapeHtml(config.label)}</strong>
            <span>${escapeHtml(detail)}${detailExtra ? ` · ${escapeHtml(detailExtra)}` : ""}</span>
          </div>
          <span class="gov-event-time">${formatShortDate(event.timestamp)}</span>
        </div>
      `;
    })
    .join("");
}

/* ---------------------------------------------------------------
   Snapshot DOM References
   --------------------------------------------------------------- */
const snapEl = {
  createBtn: document.getElementById("gov-create-snapshot"),
  snapshotCount: document.getElementById("gov-snapshot-count"),
  snapshotList: document.getElementById("gov-snapshot-list"),
  comparePanel: document.getElementById("gov-snapshot-compare-panel"),
  compareA: document.getElementById("gov-compare-a"),
  compareB: document.getElementById("gov-compare-b"),
  compareBtn: document.getElementById("gov-compare-btn"),
  compareResult: document.getElementById("gov-compare-result"),
};

/* ---------------------------------------------------------------
   Snapshot State (added to dashState)
   --------------------------------------------------------------- */
dashState.snapshots = [];

/* ---------------------------------------------------------------
   Snapshot Data Fetching
   --------------------------------------------------------------- */
async function fetchSnapshots() {
  try {
    const data = await fetchJson("/api/smfp/governance/snapshots");
    dashState.snapshots = data.snapshots || [];
  } catch (err) {
    console.warn("[Governance] snapshot fetch failed:", err.message);
    dashState.snapshots = [];
  }
}

async function createSnapshot() {
  snapEl.createBtn.disabled = true;
  snapEl.createBtn.textContent = "Creating…";

  try {
    const payload = {
      trigger: "manual",
      actor: {
        actor_type: "human",
        actor_id: "local_analyst",
        actor_source: "governance_dashboard",
      },
      notes: "Manual snapshot from Governance Dashboard.",
    };

    const response = await fetch(`${API_BASE}/api/smfp/governance/snapshots`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "snapshot creation failed");
    }

    await fetchSnapshots();
    saveCache();
    renderSnapshots();
  } catch (err) {
    console.error("[Governance] snapshot creation failed:", err.message);
    alert(`Snapshot creation failed: ${err.message}`);
  } finally {
    snapEl.createBtn.disabled = false;
    snapEl.createBtn.textContent = "Create Snapshot";
  }
}

async function compareSnapshots() {
  const idA = snapEl.compareA.value;
  const idB = snapEl.compareB.value;

  if (!idA || !idB) {
    snapEl.compareResult.textContent = "Select two snapshots to compare.";
    return;
  }

  if (idA === idB) {
    snapEl.compareResult.textContent = "Select two different snapshots.";
    return;
  }

  snapEl.compareBtn.disabled = true;
  snapEl.compareBtn.textContent = "Comparing…";

  try {
    const data = await fetchJson(
      `/api/smfp/governance/snapshots/compare?a=${encodeURIComponent(idA)}&b=${encodeURIComponent(idB)}`
    );
    renderComparison(data);
  } catch (err) {
    snapEl.compareResult.textContent = `Compare failed: ${err.message}`;
  } finally {
    snapEl.compareBtn.disabled = false;
    snapEl.compareBtn.textContent = "Compare";
  }
}

/* ---------------------------------------------------------------
   Snapshot Rendering
   --------------------------------------------------------------- */
function renderSnapshots() {
  const snapshots = dashState.snapshots || [];
  snapEl.snapshotCount.textContent = String(snapshots.length);

  if (!snapshots.length) {
    snapEl.snapshotList.innerHTML = `
      <div class="gov-empty-state">
        <strong>No snapshots recorded</strong>
        <span>Create a manual snapshot or let the system auto-snapshot on lifecycle events.</span>
      </div>
    `;
    snapEl.comparePanel.classList.add("hidden");
    return;
  }

  // Render list (newest first)
  const reversed = [...snapshots].reverse();

  snapEl.snapshotList.innerHTML = reversed
    .map((snap) => {
      const hashPreview = snap.snapshot_hash
        ? snap.snapshot_hash.slice(0, 16) + "…"
        : "—";
      const actorLabel = snap.actor
        ? `${snap.actor.actor_id} (${snap.actor.actor_type})`
        : "unknown";
      const activeModel = snap.active_model
        ? shortId(snap.active_model)
        : "none";

      return `
        <div class="gov-snapshot-entry" data-snapshot-id="${escapeHtml(snap.snapshot_id)}">
          <span class="gov-snapshot-trigger ${escapeHtml(snap.trigger)}">${escapeHtml(snap.trigger)}</span>
          <div class="gov-snapshot-info">
            <strong>${escapeHtml(snap.snapshot_id)}</strong>
            <span>${escapeHtml(actorLabel)} · active: ${escapeHtml(activeModel)} · ${escapeHtml(snap.ml_classifier_status || "—")}</span>
            <span class="gov-snapshot-hash">hash: ${escapeHtml(hashPreview)}</span>
          </div>
          <div class="gov-snapshot-meta">
            <strong>${formatShortDate(snap.timestamp)}</strong>
            ${snap.notes ? `<span>${escapeHtml(snap.notes.slice(0, 50))}</span>` : ""}
          </div>
        </div>
      `;
    })
    .join("");

  // Show compare panel if 2+ snapshots
  if (snapshots.length >= 2) {
    snapEl.comparePanel.classList.remove("hidden");
    populateCompareSelectors(snapshots);
  } else {
    snapEl.comparePanel.classList.add("hidden");
  }
}

function populateCompareSelectors(snapshots) {
  const reversed = [...snapshots].reverse();
  const optionsHtml = reversed
    .map(
      (s) =>
        `<option value="${escapeHtml(s.snapshot_id)}">${escapeHtml(s.snapshot_id)} (${formatShortDate(s.timestamp)})</option>`
    )
    .join("");

  snapEl.compareA.innerHTML = optionsHtml;
  snapEl.compareB.innerHTML = optionsHtml;

  // Pre-select the two most recent
  if (reversed.length >= 2) {
    snapEl.compareA.value = reversed[1].snapshot_id;
    snapEl.compareB.value = reversed[0].snapshot_id;
  }
}

function renderComparison(data) {
  if (!data.diffs || !data.diffs.length) {
    snapEl.compareResult.innerHTML = `
      <div class="gov-empty-state">
        <strong>No diff available</strong>
      </div>
    `;
    return;
  }

  const rowsHtml = data.diffs
    .map((d) => {
      const cls = d.changed ? "changed" : "unchanged";
      const valA = typeof d.value_a === "object" ? JSON.stringify(d.value_a, null, 1) : String(d.value_a ?? "—");
      const valB = typeof d.value_b === "object" ? JSON.stringify(d.value_b, null, 1) : String(d.value_b ?? "—");
      return `
        <div class="gov-diff-row ${cls}">
          <span class="gov-diff-field">${escapeHtml(d.field)}</span>
          <span class="gov-diff-value">${escapeHtml(valA)}</span>
          <span class="gov-diff-value">${escapeHtml(valB)}</span>
        </div>
      `;
    })
    .join("");

  snapEl.compareResult.innerHTML = `
    ${rowsHtml}
    <div class="gov-compare-summary">
      <span><strong>${data.total_changed}</strong> changed</span>
      <span><strong>${data.total_unchanged}</strong> unchanged</span>
      <span>A: ${formatShortDate(data.timestamp_a)}</span>
      <span>B: ${formatShortDate(data.timestamp_b)}</span>
    </div>
  `;
}

/* ---------------------------------------------------------------
   Event Listeners
   --------------------------------------------------------------- */
el.refreshBtn.addEventListener("click", () => fetchAllData());

el.resetBtn.addEventListener("click", () => {
  clearCache();
  renderAll();
  renderSnapshots();
});

el.timelineFilterType.addEventListener("change", () => {
  renderTimeline();
});

snapEl.createBtn.addEventListener("click", () => createSnapshot());
snapEl.compareBtn.addEventListener("click", () => compareSnapshots());

/* ---------------------------------------------------------------
   Extended fetchAllData to include snapshots
   --------------------------------------------------------------- */
const _originalFetchAllData = fetchAllData;
async function fetchAllDataWithSnapshots() {
  el.refreshBtn.disabled = true;
  el.refreshBtn.textContent = "Loading…";

  const errors = [];

  // 1. Dataset summary
  try {
    dashState.datasetSummary = await fetchJson("/api/smfp/dataset/summary");
  } catch (err) {
    errors.push(`dataset: ${err.message}`);
  }

  // 2. Timeline (includes model events)
  try {
    dashState.timeline = await fetchJson("/api/smfp/governance/timeline");
  } catch (err) {
    errors.push(`timeline: ${err.message}`);
    dashState.timeline = [];
  }

  // 3. Extract model info from timeline events
  extractModelInfo();

  // 4. Fetch reviews for each model found
  await fetchReviewsForModels();

  // 5. Fetch snapshots
  await fetchSnapshots();

  saveCache();
  renderAll();
  renderSnapshots();

  el.refreshBtn.disabled = false;
  el.refreshBtn.textContent = "Refresh Dashboard";

  if (errors.length) {
    console.warn("[Governance] partial errors:", errors);
  }
}

// Override the original fetchAllData
fetchAllData = fetchAllDataWithSnapshots;

/* ---------------------------------------------------------------
   Initialization
   --------------------------------------------------------------- */
(function init() {
  const hasCached = loadCache();
  if (hasCached && dashState.lastRefreshed) {
    // Render from cache immediately (persistence on tab switch)
    renderAll();
    renderSnapshots();
    console.info("[Governance] restored from cache, last refreshed:", dashState.lastRefreshed);
  } else {
    // First load — fetch everything
    fetchAllData();
  }
})();
