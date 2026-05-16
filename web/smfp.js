const API_BASE =
  window.location.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://127.0.0.1:8765";

const state = {
  activeAssetId: null,
  file: null,
  fileBase64: null,
  localHash: null,
  manifest: null,
  verification: null,
  report: null,
  originAnalysis: null,
  frequencyAnalysis: null,
  evidenceFusion: null,
  exportedReport: null,
};

const SMFP_CACHE_KEY = "smfp.session_cache";

function saveCache() {
  try {
    const serializable = {
      activeAssetId: state.activeAssetId,
      localHash: state.localHash,
      manifest: state.manifest,
      verification: state.verification,
      report: state.report,
      originAnalysis: state.originAnalysis,
      frequencyAnalysis: state.frequencyAnalysis,
      evidenceFusion: state.evidenceFusion,
      exportedReport: state.exportedReport,
      _filename: elements.filename?.value || null,
      _mime: elements.mime?.value || null,
      _model: elements.model?.value || null,
      _source: elements.source?.value || null,
      _content: elements.content?.value || null,
      _prompt: elements.prompt?.value || null,
      _datasetNotes: elements.datasetNotes?.value || null,
      _datasetLabel: elements.datasetLabel?.value || null,
      _datasetSplit: elements.datasetSplit?.value || null,
      _datasetSource: elements.datasetSource?.value || null,
      _datasetLicense: elements.datasetLicense?.value || null,
      _savedAt: new Date().toISOString(),
    };
    sessionStorage.setItem(SMFP_CACHE_KEY, JSON.stringify(serializable));
  } catch (_) { /* quota exceeded — silently skip */ }
}

function restoreFromCache() {
  try {
    const raw = sessionStorage.getItem(SMFP_CACHE_KEY);
    if (!raw) return false;
    const cached = JSON.parse(raw);
    if (!cached.activeAssetId) return false;

    state.activeAssetId = cached.activeAssetId;
    state.localHash = cached.localHash;
    state.manifest = cached.manifest;
    state.verification = cached.verification;
    state.report = cached.report;
    state.originAnalysis = cached.originAnalysis;
    state.frequencyAnalysis = cached.frequencyAnalysis;
    state.evidenceFusion = cached.evidenceFusion;
    state.exportedReport = cached.exportedReport;

    if (cached._filename) elements.filename.value = cached._filename;
    if (cached._mime) elements.mime.value = cached._mime;
    if (cached._model) elements.model.value = cached._model;
    if (cached._source) elements.source.value = cached._source;
    if (cached._content && elements.content) elements.content.value = cached._content;
    if (cached._prompt && elements.prompt) elements.prompt.value = cached._prompt;
    if (cached._datasetNotes && elements.datasetNotes) elements.datasetNotes.value = cached._datasetNotes;
    if (cached._datasetLabel && elements.datasetLabel) elements.datasetLabel.value = cached._datasetLabel;
    if (cached._datasetSplit && elements.datasetSplit) elements.datasetSplit.value = cached._datasetSplit;
    if (cached._datasetSource && elements.datasetSource) elements.datasetSource.value = cached._datasetSource;
    if (cached._datasetLicense && elements.datasetLicense) elements.datasetLicense.value = cached._datasetLicense;
    if (cached.localHash) {
      elements.localHash.textContent = cached.localHash;
      elements.fileSummary.innerHTML = `
        <span class="smfp-file-meta"><b>Filename</b>${escapeHtml(cached._filename || 'cached asset')}</span>
        <span class="smfp-file-meta"><b>MIME</b>${escapeHtml(cached._mime || 'n/d')}</span>
        <span class="smfp-file-meta wide"><b>SHA-256</b>${escapeHtml(cached.localHash)}</span>
        <span class="smfp-file-meta"><b>Restored</b>${escapeHtml(cached._savedAt || 'session')}</span>
      `;
    }

    if (cached.manifest) {
      renderManifest(cached.manifest);
    }
    if (cached.report && cached.verification) {
      const keyStatus = cached.verification?.key_status ||
        cached.report?.trust?.key_status || "unknown";
      renderTrust(cached.report, cached.verification, keyStatus);
    }
    if (cached.originAnalysis) {
      renderOrigin(cached.originAnalysis);
    }
    if (cached.frequencyAnalysis) {
      renderFrequency(cached.frequencyAnalysis);
    }
    if (cached.evidenceFusion) {
      renderEvidenceSummary(cached.evidenceFusion);
    }

    const done = ["drop", "hash", "signature", "manifest"];
    if (cached.verification) done.push("chain", "trust");
    setPipeline(done, cached.verification ? "trust" : "manifest");
    setStatus("ok", "restored from session");
    elements.dropzone.classList.add("has-file");
    elements.dropzone.classList.remove("needs-file");
    updateActions();
    return true;
  } catch (_) {
    return false;
  }
}

function clearCache() {
  sessionStorage.removeItem(SMFP_CACHE_KEY);
}

const elements = {
  form: document.querySelector("#smfp-form"),
  file: document.querySelector("#smfp-file"),
  dropzone: document.querySelector("#smfp-dropzone"),
  fileSummary: document.querySelector("#smfp-file-summary"),
  localHash: document.querySelector("#smfp-local-hash"),
  filename: document.querySelector("#smfp-filename"),
  mime: document.querySelector("#smfp-mime"),
  model: document.querySelector("#smfp-model"),
  source: document.querySelector("#smfp-source"),
  prompt: document.querySelector("#smfp-prompt"),
  content: document.querySelector("#smfp-content"),
  ingest: document.querySelector("#smfp-ingest"),
  addRevision: document.querySelector("#smfp-add-revision"),
  verify: document.querySelector("#smfp-verify"),
  publicKey: document.querySelector("#smfp-public-key"),
  exportReport: document.querySelector("#smfp-export-report"),
  addDataset: document.querySelector("#smfp-add-dataset"),
  datasetLabel: document.querySelector("#smfp-dataset-label"),
  datasetSplit: document.querySelector("#smfp-dataset-split"),
  datasetSource: document.querySelector("#smfp-dataset-source"),
  datasetLicense: document.querySelector("#smfp-dataset-license"),
  datasetNotes: document.querySelector("#smfp-dataset-notes"),
  datasetStatus: document.querySelector("#smfp-dataset-status"),
  datasetSummary: document.querySelector("#smfp-dataset-summary"),
  refreshDatasetSummary: document.querySelector("#smfp-refresh-dataset-summary"),
  status: document.querySelector("#smfp-status"),
  trust: document.querySelector("#smfp-trust"),
  evidenceSummary: document.querySelector("#smfp-evidence-summary"),
  origin: document.querySelector("#smfp-origin"),
  manifest: document.querySelector("#smfp-manifest"),
  publicKeyOutput: document.querySelector("#smfp-public-key-output"),
  pipelineSteps: document.querySelectorAll("[data-pipeline-step]"),
};

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 405 && path === "/api/smfp/assets") {
      throw new Error("SMFP API route is not accepting POST yet. Restart the backend server and reload this page.");
    }
    const detail = payload.detail || payload.error || "SMFP request failed.";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function setStatus(kind, label) {
  elements.status.className = `badge ${kind}`;
  elements.status.textContent = label;
}

function setPipeline(doneSteps = [], activeStep = "drop", failedSteps = []) {
  elements.pipelineSteps.forEach((step) => {
    const key = step.dataset.pipelineStep;
    step.classList.toggle("done", doneSteps.includes(key));
    step.classList.toggle("active", key === activeStep);
    step.classList.toggle("failed", failedSteps.includes(key));
  });
}

function updateActions() {
  elements.verify.disabled = !state.activeAssetId;
  elements.publicKey.disabled = !state.manifest?.key_id;
  elements.exportReport.disabled = !state.report || !state.verification;
  elements.addRevision.disabled = !state.activeAssetId;
  if (elements.addDataset) {
    elements.addDataset.disabled = !state.report || !state.verification || !state.evidenceFusion;
  }
}

function renderManifest(payload) {
  elements.manifest.textContent = JSON.stringify(payload, null, 2);
}

function renderTrust(report, verification = {}, keyStatus = "unknown") {
  const trust = report?.trust || {};
  const score = trust.trust_score ?? 0;
  const checks = [
    ["SHA256 valid", verification.content_hash_valid],
    ["Ed25519 signature valid", verification.signature_valid ?? trust.signature === "valid"],
    [`Key status ${keyStatus}`, keyStatus === "active" || keyStatus === "retired"],
    ["Revision chain intact", verification.chain_valid ?? report?.chain_valid],
  ];

  elements.trust.className = `smfp-trust-card ${score >= 85 ? "ok" : score >= 50 ? "warning" : "offline"}`;
  elements.trust.innerHTML = `
    <div class="smfp-score-line">
      <span>Trust score</span>
      <strong>${score}</strong>
    </div>
    <div class="smfp-checklist">
      ${checks
        .map(([label, passed]) => `<span class="${passed ? "pass" : "fail"}">${label} ${passed ? "OK" : "check"}</span>`)
        .join("")}
    </div>
    <div class="smfp-report-meta">
      <span>${trust.provenance || "unverified"} / tampering ${trust.tampering || "unknown"}</span>
      <span>key ${trust.key_id || "n/d"} / ${trust.signature_mode || "PUBLIC_ED25519"}</span>
      <span>key status ${keyStatus}</span>
      <span>possible model ${report?.possible_model || "unknown"} / confidence ${report?.confidence ?? "n/d"}</span>
    </div>
  `;
}

async function handleFile(file) {
  if (!file) {
    return;
  }
  state.file = file;
  state.fileBase64 = null;
  state.localHash = null;
  state.verification = null;
  state.report = null;
  state.originAnalysis = null;
  state.frequencyAnalysis = null;
  state.evidenceFusion = null;
  state.exportedReport = null;
  elements.dropzone.classList.add("has-file");
  elements.dropzone.classList.remove("needs-file");
  elements.filename.value = file.name;
  elements.mime.value = file.type || inferMimeFromName(file.name);
  elements.fileSummary.innerHTML = fileSummaryHtml(file, elements.mime.value, "calculating...");
  elements.localHash.textContent = "SHA256 calculating...";
  updateActions();
  setStatus("warning", "hashing");
  setPipeline(["drop"], "hash");

  const buffer = await file.arrayBuffer();
  state.localHash = await sha256Hex(buffer);
  state.fileBase64 = arrayBufferToBase64(buffer);
  elements.localHash.textContent = state.localHash;
  elements.fileSummary.innerHTML = fileSummaryHtml(file, elements.mime.value, state.localHash);
  setPipeline(["drop", "hash"], "signature");
  setStatus("ok", "file ready");
  updateActions();
}

async function ingestAsset(event) {
  event.preventDefault();
  const content = elements.content.value.trim();
  if (!state.fileBase64 && !content) {
    setStatus("warning", "missing file");
    elements.trust.textContent = "Drop a file here, or paste text as evidence.";
    elements.dropzone.classList.add("needs-file");
    return;
  }

  elements.ingest.disabled = true;
  setStatus("warning", "signing");
  setPipeline(["drop", "hash"], "signature");
  try {
    const result = await fetchJson("/api/smfp/assets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: elements.filename.value.trim() || state.file?.name || "asset.txt",
        mime_type: elements.mime.value,
        source: elements.source.value.trim() || "lab",
        content_base64: state.fileBase64,
        content_text: state.fileBase64 ? null : content,
        model: elements.model.value.trim() || null,
        prompt: elements.prompt.value.trim() || null,
        metadata: {
          ui: "smfp.html",
          browser_sha256: state.localHash,
          original_size_bytes: state.file?.size ?? null,
        },
      }),
    });
    state.activeAssetId = result.asset_id;
    state.manifest = result.manifest;
    state.verification = null;
    state.report = null;
    state.originAnalysis = null;
    state.frequencyAnalysis = null;
    state.evidenceFusion = null;
    state.exportedReport = null;
    window.Session?.patch({
      smfpActiveAssetId: result.asset_id,
      smfpTrustScore: result.audit_report?.trust?.trust_score ?? null,
    });
    renderManifest(result.manifest);
    setPipeline(["drop", "hash", "signature", "manifest"], "chain");
    updateActions();
    await verifyAsset({ silent: true });
    saveCache();
    setStatus("ok", "report ready");
  } catch (error) {
    setStatus("offline", "failed");
    elements.trust.textContent = error.message;
    setPipeline(["drop", "hash"], "signature", ["signature"]);
  } finally {
    elements.ingest.disabled = false;
    updateActions();
  }
}

async function addRevision() {
  if (!state.activeAssetId) {
    return;
  }
  const content = elements.content.value.trim();
  if (!state.fileBase64 && !content) {
    setStatus("warning", "missing revision");
    elements.trust.textContent = "Drop a replacement file or paste revision text before Add Revision.";
    return;
  }
  elements.addRevision.disabled = true;
  setStatus("warning", "revising");
  try {
    const result = await fetchJson(`/api/smfp/assets/${state.activeAssetId}/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content_base64: state.fileBase64,
        content_text: state.fileBase64 ? null : content,
        editor: "smfp-ui",
        operation: "revision",
        metadata: {
          browser_sha256: state.localHash,
          filename: elements.filename.value.trim() || state.file?.name || null,
        },
      }),
    });
    state.manifest = result.manifest;
    state.verification = null;
    state.report = null;
    state.originAnalysis = null;
    state.frequencyAnalysis = null;
    state.evidenceFusion = null;
    state.exportedReport = null;
    renderManifest(result.manifest);
    updateActions();
    await verifyAsset({ silent: true });
    saveCache();
    setStatus("ok", "revision added");
  } catch (error) {
    elements.trust.textContent = error.message;
    setStatus("offline", "revision failed");
  } finally {
    elements.addRevision.disabled = false;
  }
}

async function verifyAsset(options = {}) {
  if (!state.activeAssetId) {
    return;
  }
  if (!options.silent) {
    elements.verify.disabled = true;
    setStatus("warning", "verifying");
  }
  try {
    const result = await fetchJson(`/api/smfp/assets/${state.activeAssetId}/verify`);
    const keyStatus = await getKeyStatus(result.key_id || state.manifest?.key_id);
    state.verification = result;
    state.report = result.audit_report;
    renderTrust(result.audit_report, result, keyStatus);
    const origin = await analyzeOrigin(result);
    const frequency = await analyzeFrequency();
    await fuseEvidence(result, origin, frequency);
    renderManifest({
      verification: {
        content_hash_valid: result.content_hash_valid,
        signature_valid: result.signature_valid,
        key_status: keyStatus,
        chain_valid: result.chain_valid,
        trust_score: result.audit_report?.trust?.trust_score ?? null,
      },
      manifest: state.manifest,
    });
    const failedSteps = [
      result.content_hash_valid ? null : "hash",
      result.signature_valid ? null : "signature",
      keyStatus === "revoked" ? "signature" : null,
      result.chain_valid ? null : "chain",
    ].filter(Boolean);
    setPipeline(
      [
        "drop",
        result.content_hash_valid ? "hash" : null,
        result.signature_valid ? "signature" : null,
        state.manifest ? "manifest" : null,
        result.chain_valid ? "chain" : null,
        "trust",
      ].filter(Boolean),
      "trust",
      failedSteps,
    );
    saveCache();
    setStatus("ok", "verified");
  } catch (error) {
    elements.trust.textContent = error.message;
    setStatus("offline", "failed");
  } finally {
    updateActions();
  }
}

async function analyzeOrigin(verification) {
  if (!elements.origin) {
    return null;
  }
  try {
    const result = await fetchJson("/api/smfp/origin/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: elements.filename.value.trim() || state.file?.name || state.manifest?.filename || "",
        mime_type: elements.mime.value || state.manifest?.mime_type || "application/octet-stream",
        content_hash: state.manifest?.content_hash || state.localHash,
        metadata: {
          browser_sha256: state.localHash,
          original_size_bytes: state.file?.size ?? null,
        },
        manifest: state.manifest,
        content_base64: state.fileBase64,
      }),
    });
    renderOrigin(result);
    state.originAnalysis = result;
    return result;
  } catch (error) {
    elements.origin.textContent = error.message;
    return null;
  }
}

function renderOrigin(origin) {
  const evidence = origin.evidence || [];
  const metadataSignals = origin.metadata_signals || [];
  elements.origin.innerHTML = `
    <div class="smfp-origin-summary">
      <span>Likely producer</span>
      <strong>${producerLabel(origin.likely_producer)}</strong>
      <span>Confidence ${Number(origin.confidence || 0).toFixed(2)}</span>
    </div>
    <div class="smfp-origin-section">
      <span>Metadata Signals</span>
      <div class="smfp-origin-evidence">
        ${
          metadataSignals.length
            ? metadataSignals
                .map((item) => `<span class="${item.matched ? "pass" : "fail"}">${item.matched ? "OK" : "NO"} ${escapeHtml(item.label)}</span>`)
                .join("")
            : '<span class="fail">NO no metadata signals extracted</span>'
        }
      </div>
    </div>
    <div class="smfp-origin-evidence">
      ${evidence
        .map((item) => `<span class="${item.matched ? "pass" : "fail"}">${item.matched ? "OK" : "NO"} ${escapeHtml(item.label)}</span>`)
        .join("")}
    </div>
    <p class="subtle">${(origin.limitations || []).map(escapeHtml).join(" / ")}</p>
  `;
}

async function analyzeFrequency() {
  if (!elements.origin || !state.fileBase64 || !String(elements.mime.value).startsWith("image/")) {
    return null;
  }
  try {
    const result = await fetchJson("/api/smfp/frequency/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: elements.filename.value.trim() || state.file?.name || "",
        mime_type: elements.mime.value || "image/png",
        content_base64: state.fileBase64,
      }),
    });
    renderFrequency(result);
    state.frequencyAnalysis = result;
    return result;
  } catch (error) {
    appendOriginSection("Frequency Signals", [`NO ${escapeHtml(error.message)}`]);
    return null;
  }
}

function renderFrequency(frequency) {
  const signals = frequency.signals || [];
  const rows = signals.length
    ? signals.map(
        (signal) =>
          `<span class="${signal.matched ? "pass" : "fail"}">${signal.matched ? "OK" : "NO"} ${escapeHtml(signal.label)} (${Number(signal.value || 0).toFixed(2)})</span>`,
      )
    : ['<span class="fail">NO no frequency signals extracted</span>'];
  appendOriginSection(
    "Frequency Signals",
    rows,
    `synthetic ${Number(frequency.synthetic_likelihood || 0).toFixed(2)} / camera ${Number(frequency.camera_likelihood || 0).toFixed(2)}`,
  );
}

function appendOriginSection(title, rows, summary = "") {
  const section = document.createElement("div");
  section.className = "smfp-origin-section";
  section.innerHTML = `
    <span>${escapeHtml(title)}</span>
    ${summary ? `<p class="subtle">${escapeHtml(summary)}</p>` : ""}
    <div class="smfp-origin-evidence">${rows.join("")}</div>
  `;
  elements.origin.append(section);
}

async function fuseEvidence(provenance, origin, frequency) {
  if (!elements.evidenceSummary) {
    return;
  }
  try {
    const result = await fetchJson("/api/smfp/evidence/fuse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provenance,
        origin_analysis: origin || {},
        frequency_analysis: frequency || {},
      }),
    });
    state.evidenceFusion = result;
    renderEvidenceSummary(result);
  } catch (error) {
    elements.evidenceSummary.textContent = error.message;
  }
}

function renderEvidenceSummary(fusion) {
  elements.evidenceSummary.innerHTML = `
    <div class="smfp-evidence-summary__head">
      <span>Evidence Summary</span>
      <strong>${assessmentLabel(fusion.overall_assessment)}</strong>
    </div>
    <div class="smfp-evidence-summary__scores">
      <span>Origin confidence ${Number(fusion.origin_confidence || 0).toFixed(2)}</span>
      <span>Synthetic likelihood ${Number(fusion.synthetic_likelihood || 0).toFixed(2)}</span>
    </div>
    <ul>
      ${(fusion.evidence_summary || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ul>
    <p class="subtle">${(fusion.limitations || []).slice(0, 3).map(escapeHtml).join(" / ")}</p>
  `;
}

function assessmentLabel(value) {
  const labels = {
    verified_synthetic_like: "Verified synthetic-like",
    verified_unknown: "Verified unknown",
    unverified_synthetic_like: "Unverified synthetic-like",
    tampered: "Tampered",
    unknown: "Unknown",
  };
  return labels[value] || "Unknown";
}

function producerLabel(value) {
  const labels = {
    openai_like: "OpenAI-like",
    midjourney_like: "Midjourney-like",
    flux_like: "Flux-like",
    stable_diffusion_like: "Stable Diffusion-like",
    gemini_like: "Gemini-like",
    sora_like: "Sora-like",
    unknown: "Unknown",
  };
  return labels[value] || "Unknown";
}

async function getKeyStatus(keyId) {
  if (!keyId) {
    return "unknown";
  }
  try {
    const result = await fetchJson(`/api/smfp/public-keys/${encodeURIComponent(keyId)}`);
    elements.publicKeyOutput.textContent = JSON.stringify(result, null, 2);
    return result.status || "unknown";
  } catch (error) {
    elements.publicKeyOutput.textContent = error.message;
    return "unknown";
  }
}

async function loadPublicKey() {
  const keyId = state.manifest?.key_id || state.manifest?.public_key_id;
  if (!keyId) {
    return;
  }
  elements.publicKey.disabled = true;
  setStatus("warning", "loading key");
  try {
    const result = await fetchJson(`/api/smfp/public-keys/${encodeURIComponent(keyId)}`);
    elements.publicKeyOutput.textContent = JSON.stringify(result, null, 2);
    setStatus("ok", "public verify");
  } catch (error) {
    elements.publicKeyOutput.textContent = error.message;
    setStatus("offline", "key failed");
  } finally {
    elements.publicKey.disabled = false;
  }
}

function exportReport() {
  if (!state.activeAssetId || !state.report || !state.verification) {
    return;
  }
  exportReportFromBackend();
}

async function exportReportFromBackend() {
  elements.exportReport.disabled = true;
  setStatus("warning", "exporting report");
  try {
    const result = await fetchJson("/api/smfp/reports/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        asset_id: state.activeAssetId,
        case_id: null,
        filename: elements.filename.value.trim() || state.file?.name || state.manifest?.filename || "",
        mime_type: elements.mime.value || state.manifest?.mime_type || "application/octet-stream",
        sha256: state.manifest?.content_hash || state.localHash,
        timestamp: state.manifest?.created_at || null,
        provenance_verification: state.verification,
        origin_analysis: state.originAnalysis || {},
        metadata_signals: state.originAnalysis?.metadata_signals || [],
        frequency_signals: state.frequencyAnalysis?.signals || [],
        evidence_fusion: state.evidenceFusion || {},
        limitations: [
          ...(state.originAnalysis?.limitations || []),
          ...(state.frequencyAnalysis?.limitations || []),
          ...(state.evidenceFusion?.limitations || []),
        ],
        analyst_notes: elements.content.value.trim(),
      }),
    });
    state.exportedReport = result;
    renderReportExport(result);
    const blob = new Blob([result.canonical_json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${result.report_id}.forensic-report.json`;
    link.click();
    URL.revokeObjectURL(url);
    setStatus("ok", "report exported");
  } catch (error) {
    elements.evidenceSummary.textContent = error.message;
    setStatus("offline", "export failed");
  } finally {
    updateActions();
  }
}

function renderReportExport(result) {
  if (!elements.evidenceSummary) {
    return;
  }
  const block = document.createElement("div");
  block.className = "smfp-report-export";
  block.innerHTML = `
    <span>Signed Report</span>
    <strong>${escapeHtml(result.report_id)}</strong>
    <code>${escapeHtml(result.report_hash)}</code>
    <a href="${escapeHtml(result.public_verify_url)}" target="_blank" rel="noreferrer">${escapeHtml(result.public_verify_url)}</a>
    <button type="button" disabled>PDF coming soon</button>
  `;
  elements.evidenceSummary.append(block);
}

async function exportMlFeatures(label = null) {
  return fetchJson("/api/smfp/ml/features/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: elements.filename.value.trim() || state.file?.name || state.manifest?.filename || "",
      mime_type: elements.mime.value || state.manifest?.mime_type || "application/octet-stream",
      content_hash: state.manifest?.content_hash || state.localHash,
      label,
      metadata_extraction: {
        extracted: state.originAnalysis?.metadata || {},
        signals: state.originAnalysis?.metadata_signals || [],
      },
      origin_analysis: state.originAnalysis || {},
      frequency_analysis: state.frequencyAnalysis || {},
      provenance_verification: state.verification || {},
      manifest: state.manifest || {},
    }),
  });
}

async function addToDataset() {
  if (!state.verification || !state.evidenceFusion) {
    return;
  }
  elements.addDataset.disabled = true;
  setStatus("warning", "saving sample");
  try {
    const label = elements.datasetLabel.value || null;
    const featureExport = await exportMlFeatures(label);
    const result = await fetchJson("/api/smfp/dataset/samples", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_hash: state.manifest?.content_hash || state.localHash,
        filename: elements.filename.value.trim() || state.file?.name || state.manifest?.filename || "",
        mime_type: elements.mime.value || state.manifest?.mime_type || "application/octet-stream",
        label,
        split: elements.datasetSplit.value,
        source: elements.datasetSource.value,
        license: elements.datasetLicense.value.trim() || "unknown",
        feature_schema_version: featureExport.feature_schema_version,
        features: featureExport.features,
        analyst_notes: elements.datasetNotes.value.trim(),
      }),
    });
    elements.datasetStatus.textContent = `Dataset sample saved: ${result.sample_id}`;
    await loadDatasetSummary();
    saveCache();
    setStatus("ok", "sample saved");
  } catch (error) {
    elements.datasetStatus.textContent = error.message;
    setStatus("offline", "sample failed");
  } finally {
    updateActions();
  }
}

async function loadDatasetSummary() {
  if (!elements.datasetSummary) {
    return;
  }
  try {
    const summary = await fetchJson("/api/smfp/dataset/summary");
    renderDatasetSummary(summary);
  } catch (error) {
    elements.datasetSummary.textContent = error.message;
  }
}

function renderDatasetSummary(summary) {
  const labels = summary.samples_by_label || {};
  const splits = summary.samples_by_split || {};
  const warnings = [...(summary.label_balance_warnings || []), ...(summary.split_balance_warnings || [])];
  elements.datasetSummary.innerHTML = `
    <div class="smfp-summary-row">
      <span>Total</span>
      <strong>${summary.total_samples || 0}</strong>
    </div>
    <div class="smfp-summary-row">
      <span>Unlabeled</span>
      <strong>${summary.unlabeled_count || 0}</strong>
    </div>
    <div class="smfp-summary-row wide">
      <span>Labels</span>
      <code>${escapeHtml(formatCounts(labels))}</code>
    </div>
    <div class="smfp-summary-row wide">
      <span>Splits</span>
      <code>${escapeHtml(formatCounts(splits))}</code>
    </div>
    <div class="smfp-summary-row wide">
      <span>Warnings</span>
      <ul>${warnings.length ? warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("") : "<li>No balance warnings.</li>"}</ul>
    </div>
  `;
}

function formatCounts(counts) {
  return Object.entries(counts)
    .map(([key, value]) => `${key}:${value}`)
    .join(" / ");
}

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileSummaryHtml(file, mimeType, hash) {
  return `
    <span class="smfp-file-meta"><b>Filename</b>${escapeHtml(file.name)}</span>
    <span class="smfp-file-meta"><b>Size</b>${formatBytes(file.size)}</span>
    <span class="smfp-file-meta"><b>MIME</b>${escapeHtml(mimeType || "application/octet-stream")}</span>
    <span class="smfp-file-meta wide"><b>SHA-256</b>${escapeHtml(hash)}</span>
  `;
}

function inferMimeFromName(filename) {
  const extension = filename.toLowerCase().split(".").pop();
  const mimeTypes = {
    txt: "text/plain",
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    pdf: "application/pdf",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    wav: "audio/wav",
    mp4: "video/mp4",
  };
  return mimeTypes[extension] || "application/octet-stream";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

elements.form.addEventListener("submit", ingestAsset);
elements.addRevision.addEventListener("click", addRevision);
elements.verify.addEventListener("click", () => verifyAsset());
elements.publicKey.addEventListener("click", loadPublicKey);
elements.exportReport.addEventListener("click", exportReport);
elements.addDataset?.addEventListener("click", addToDataset);
elements.refreshDatasetSummary?.addEventListener("click", loadDatasetSummary);
elements.file.addEventListener("change", (event) => handleFile(event.target.files?.[0]));

document.querySelector("#smfp-reset")?.addEventListener("click", () => {
  clearCache();
  window.location.reload();
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.remove("dragging");
  });
});

elements.dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer?.files?.[0];
  if (file) {
    handleFile(file);
  }
});

const wasRestored = restoreFromCache();
if (!wasRestored) {
  updateActions();
}
loadDatasetSummary();
