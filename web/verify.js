const API_BASE =
  window.location.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://127.0.0.1:8765";

const state = {
  file: null,
  fileBase64: null,
  localHash: null,
  manifest: null,
};

const elements = {
  form: document.querySelector("#verify-form"),
  file: document.querySelector("#verify-file"),
  dropzone: document.querySelector("#verify-dropzone"),
  fileSummary: document.querySelector("#verify-file-summary"),
  localHash: document.querySelector("#verify-local-hash"),
  manifest: document.querySelector("#verify-manifest"),
  manifestFile: document.querySelector("#verify-manifest-file"),
  importManifest: document.querySelector("#verify-import"),
  run: document.querySelector("#verify-run"),
  result: document.querySelector("#verify-result"),
  evidenceSummary: document.querySelector("#verify-evidence-summary"),
  origin: document.querySelector("#verify-origin"),
  status: document.querySelector("#verify-status"),
};

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || payload.error || "SMFP request failed.";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function setStatus(kind, label) {
  elements.status.className = `badge ${kind}`;
  elements.status.textContent = label;
}

function updateRunState() {
  elements.run.disabled = !state.fileBase64 || !parseManifest();
}

function parseManifest() {
  const raw = elements.manifest.value.trim();
  if (!raw) {
    state.manifest = null;
    return null;
  }
  try {
    state.manifest = JSON.parse(raw);
    return state.manifest;
  } catch {
    state.manifest = null;
    return null;
  }
}

async function handleFile(file) {
  if (!file) {
    return;
  }
  state.file = file;
  elements.dropzone.classList.add("has-file");
  setStatus("warning", "hashing");

  const buffer = await file.arrayBuffer();
  state.fileBase64 = arrayBufferToBase64(buffer);
  state.localHash = await sha256Hex(buffer);
  const mimeType = file.type || inferMimeFromName(file.name);
  elements.fileSummary.innerHTML = fileSummaryHtml(file, mimeType, state.localHash);
  elements.localHash.textContent = state.localHash;
  setStatus("ok", "file ready");
  updateRunState();
}

async function verifyPublicManifest(event) {
  event.preventDefault();
  const manifest = parseManifest();
  if (!state.fileBase64 || !manifest) {
    setStatus("warning", "missing input");
    return;
  }
  elements.run.disabled = true;
  setStatus("warning", "verifying");
  try {
    const verification = await fetchJson("/api/smfp/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content_base64: state.fileBase64,
        manifest,
      }),
    });
    renderVerification(verification);
    const origin = await analyzeOrigin(verification, manifest);
    const frequency = await analyzeFrequency();
    await fuseEvidence(verification, origin, frequency);
    setStatus("ok", "verified");
  } catch (error) {
    elements.result.textContent = error.message;
    setStatus("offline", "failed");
  } finally {
    updateRunState();
  }
}

function renderVerification(verification) {
  const trust = verification.audit_report?.trust || {};
  const score = trust.trust_score ?? 0;
  const checks = [
    ["content hash valid", verification.content_hash_valid],
    ["Ed25519 signature valid", verification.signature_valid],
    [`key status ${verification.key_status || "unknown"}`, verification.key_status === "active" || verification.key_status === "retired"],
    ["revision chain intact", verification.chain_valid],
    [`tampering ${verification.tampering || "unknown"}`, verification.tampering === "none"],
  ];
  elements.result.className = `smfp-trust-card ${score >= 85 ? "ok" : score >= 50 ? "warning" : "offline"}`;
  elements.result.innerHTML = `
    <div class="smfp-score-line">
      <span>Trust score</span>
      <strong>${score}</strong>
    </div>
    <div class="smfp-checklist">
      ${checks
        .map(([label, passed]) => `<span class="${passed ? "pass" : "fail"}">${escapeHtml(label)} ${passed ? "OK" : "FAIL"}</span>`)
        .join("")}
    </div>
    <div class="smfp-report-meta">
      <span>key_id ${escapeHtml(verification.key_id || "n/d")}</span>
      <span>signature ${escapeHtml(trust.signature || "unknown")} / tampering ${escapeHtml(trust.tampering || "unknown")}</span>
    </div>
  `;
}

async function analyzeOrigin(verification, manifest) {
  const result = await fetchJson("/api/smfp/origin/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: state.file?.name || manifest.filename || "",
      mime_type: state.file?.type || manifest.mime_type || "application/octet-stream",
      content_hash: verification.audit_report?.trust?.content_hash || manifest.content_hash || state.localHash,
      manifest,
      content_base64: state.fileBase64,
    }),
  });
  renderOrigin(result);
  return result;
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
  if (!state.fileBase64 || !String(state.file?.type || "").startsWith("image/")) {
    return null;
  }
  try {
    const result = await fetchJson("/api/smfp/frequency/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: state.file?.name || "",
        mime_type: state.file?.type || inferMimeFromName(state.file?.name || ""),
        content_base64: state.fileBase64,
      }),
    });
    renderFrequency(result);
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

async function importManifestFile(file) {
  if (!file) {
    return;
  }
  elements.manifest.value = await file.text();
  updateRunState();
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

elements.file.addEventListener("change", (event) => handleFile(event.target.files?.[0]));
elements.manifest.addEventListener("input", updateRunState);
elements.form.addEventListener("submit", verifyPublicManifest);
elements.importManifest.addEventListener("click", () => elements.manifestFile.click());
elements.manifestFile.addEventListener("change", (event) => importManifestFile(event.target.files?.[0]));

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
