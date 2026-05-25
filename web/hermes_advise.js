const elements = {
  form: document.querySelector("#hermes-advise-form"),
  objective: document.querySelector("#advise-objective"),
  context: document.querySelector("#advise-context"),
  status: document.querySelector("#advise-status"),
  results: document.querySelector("#advise-results"),
  loadExample: document.querySelector("#load-example"),
  askHermes: document.querySelector("#ask-hermes"),
};

let contextSource = "manual";

const exampleContext = {
  current_models: {
    generation: "llama3.2:3b",
    judge: "llama3.2:3b",
  },
  rubric: {
    criteria_count: 2,
  },
  result: {
    margin: 0.2,
  },
  current_thresholds: {
    margin: 1.0,
  },
  num_conversations: 1,
  num_turns: 1,
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || data?.error || `HTTP ${response.status}`);
  }
  return data;
}

function setStatus(kind, label) {
  elements.status.className = `badge ${kind}`;
  elements.status.textContent = label;
}

function parseContext() {
  const raw = elements.context.value.trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("Context JSON precisa ser um objeto.");
    }
    return parsed;
  } catch (error) {
    throw new Error(`Context JSON invalido: ${error.message}`);
  }
}

async function askHermes(event) {
  event.preventDefault();
  setStatus("warning", "advising");
  elements.askHermes.disabled = true;
  elements.results.innerHTML = '<div class="empty-state">Hermes analisando contrato...</div>';
  try {
    const payload = {
      objective: elements.objective.value.trim() || "manual_diagnostic",
      context: parseContext(),
      constraints: {},
      user_preferences: {},
    };
    const response = await fetchJson("/api/hermes/advise", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderResponse(response);
    setStatus("ok", "ready");
  } catch (error) {
    setStatus("offline", "failed");
    elements.results.innerHTML = `<div class="state-summary offline">${escapeHtml(error.message)}</div>`;
  } finally {
    elements.askHermes.disabled = false;
  }
}

function renderResponse(response) {
  const recommendations = response.recommendations || [];
  if (!recommendations.length) {
    elements.results.innerHTML = `
      <div class="hermes-advise-summary">
        <span>Source</span>
        <strong>${sourceLabel()}</strong>
      </div>
      <div class="empty-state">Nenhuma recomendacao deterministica para este contexto.</div>
    `;
    return;
  }

  elements.results.innerHTML = "";
  const header = document.createElement("div");
  header.className = "hermes-advise-summary";
  header.innerHTML = `
    <span>Objective</span>
    <strong>${escapeHtml(response.interpreted_objective || "n/d")}</strong>
    <span>Source</span>
    <strong>${sourceLabel()}</strong>
  `;
  elements.results.append(header);

  for (const recommendation of recommendations) {
    const card = document.createElement("article");
    card.className = "hermes-advise-card";
    card.innerHTML = `
      <header>
        <div>
          <span>Action</span>
          <h3>${escapeHtml(recommendation.action)}</h3>
        </div>
        <strong>${Math.round(Number(recommendation.confidence || 0) * 100)}%</strong>
      </header>
      <dl>
        <dt>Reason</dt>
        <dd>${escapeHtml(recommendation.reason)}</dd>
        <dt>Requires confirmation</dt>
        <dd>${recommendation.requires_confirmation ? "true" : "false"}</dd>
        <dt>Selected by</dt>
        <dd>${escapeHtml(recommendation.selected_by || "n/d")}</dd>
      </dl>
    `;
    elements.results.append(card);
  }

  const diagnosis = response.diagnosis || [];
  if (diagnosis.length) {
    const block = document.createElement("section");
    block.className = "hermes-advise-diagnosis";
    block.innerHTML = `
      <span>Diagnosis</span>
      ${diagnosis.map((item) => `
        <div>
          <strong>${escapeHtml(item.issue)} · ${escapeHtml(item.severity)}</strong>
          <p>${escapeHtml(item.evidence)}</p>
          <p>${escapeHtml(item.impact)}</p>
        </div>
      `).join("")}
    `;
    elements.results.append(block);
  }
}

function loadExample() {
  contextSource = "synthetic_example";
  elements.objective.value = "generate_dpo_pairs";
  elements.context.value = JSON.stringify(exampleContext, null, 2);
  setStatus("neutral", "example loaded");
  elements.results.innerHTML = `
    <div class="state-summary warning">
      Exemplo sintetico carregado. Nenhum run real foi lido ou executado.
      Clique em "Pedir diagnostico" para testar as regras deterministicas.
    </div>
  `;
}

function sourceLabel() {
  return contextSource === "synthetic_example"
    ? "synthetic example, not a real run"
    : "manual context";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

elements.form.addEventListener("submit", askHermes);
elements.loadExample.addEventListener("click", loadExample);
