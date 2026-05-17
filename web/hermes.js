const elements = {
  form: document.querySelector("#hermes-form"),
  rubricCase: document.querySelector("#rubric-case"),
  locale: document.querySelector("#locale"),
  category: document.querySelector("#category"),
  personaName: document.querySelector("#persona-name"),
  personaContext: document.querySelector("#persona-context"),
  personaProfile: document.querySelector("#persona-profile"),
  stressModel: document.querySelector("#stress-model"),
  assistantModel: document.querySelector("#assistant-model"),
  temperatureLow: document.querySelector("#temperature-low"),
  temperatureHigh: document.querySelector("#temperature-high"),
  numConversations: document.querySelector("#num-conversations"),
  numTurns: document.querySelector("#num-turns"),
  maxHistoryTurns: document.querySelector("#max-history-turns"),
  scoringModel: document.querySelector("#scoring-model"),
  modelOptions: document.querySelector("#model-options"),
  startRun: document.querySelector("#start-run"),
  cancelRun: document.querySelector("#cancel-run"),
  refreshRuns: document.querySelector("#refresh-runs"),
  runTitle: document.querySelector("#run-title"),
  runStatus: document.querySelector("#run-status"),
  runSummary: document.querySelector("#run-summary"),
  metricResults: document.querySelector("#metric-results"),
  metricPersona: document.querySelector("#metric-persona"),
  metricConversation: document.querySelector("#metric-conversation"),
  metricTurn: document.querySelector("#metric-turn"),
  resultsList: document.querySelector("#results-list"),
  runsList: document.querySelector("#runs-list"),
  liveBackend: document.querySelector("#live-backend"),
  liveModels: document.querySelector("#live-models"),
  liveStage: document.querySelector("#live-stage"),
  liveModel: document.querySelector("#live-model"),
  livePoll: document.querySelector("#live-poll"),
  contextPersona: document.querySelector("#context-persona"),
  contextPrompt: document.querySelector("#context-prompt"),
  contextHistory: document.querySelector("#context-history"),
  contextCandidates: document.querySelector("#context-candidates"),
  contextEvents: document.querySelector("#context-events"),
};

const state = {
  activeRunId: null,
  pollTimer: null,
  models: [],
};

const ALLOWED_RUBRIC_DIMENSIONS = new Set([
  "Cultural Understanding and Application",
  "Local Facts and Awareness",
  "Logic and Formatting",
  "Natural Language Fluency",
]);

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

function numberValue(input, fallback) {
  const value = Number(String(input.value).replace(",", "."));
  return Number.isFinite(value) ? value : fallback;
}

function textValue(input) {
  return input.value.trim();
}

function requiredModel(input, label) {
  const model = textValue(input);
  if (!model) {
    throw new Error(`Informe o ${label}. Use um modelo listado pelo Ollama ou digite um nome manualmente.`);
  }
  return model;
}

function setStatus(status, message) {
  const normalized = status || "idle";
  elements.runStatus.textContent = normalized;
  elements.runStatus.className = `badge ${statusClass(normalized)}`;
  elements.runSummary.textContent = message || "";
  elements.runSummary.className = `state-summary ${statusClass(normalized)}`;
}

function statusClass(status) {
  if (status === "success") return "ok";
  if (status === "failed" || status === "canceled") return "offline";
  if (status === "processing" || status === "pending") return "warning";
  return "neutral";
}

function isActiveStatus(status) {
  return status === "processing" || status === "pending";
}

function buildPayload() {
  const stressModel = requiredModel(elements.stressModel, "modelo de stress/user");
  const assistantModel = requiredModel(elements.assistantModel, "modelo assistant");
  return {
    manifest: {
      personas: [
        {
          name: textValue(elements.personaName),
          context: textValue(elements.personaContext),
          profile: textValue(elements.personaProfile),
        },
      ],
      stress_model: stressModel,
      response_models: [assistantModel],
      rubric_set_id: elements.rubricCase.value,
      locale: textValue(elements.locale) || "pt-BR",
      category: textValue(elements.category) || null,
      num_conversations: numberValue(elements.numConversations, 1),
      num_turns: numberValue(elements.numTurns, 1),
      max_history_turns: numberValue(elements.maxHistoryTurns, 1),
      temperature_low: numberValue(elements.temperatureLow, 0.2),
      temperature_high: numberValue(elements.temperatureHigh, 0.8),
      scoring_model: requiredModel(elements.scoringModel, "scoring model"),
      scoring_provider: "ollama",
      max_parallel: 1,
    },
  };
}

async function loadRuntimeStatus() {
  try {
    const health = await fetchJson("/api/health");
    const ollama = health.ollama || {};
    elements.liveBackend.textContent = health.ok ? "online" : "degradado";
    elements.liveModels.textContent = ollama.ready
      ? "Ollama pronto; buscando modelos"
      : (health.error || "Ollama nao pronto");
  } catch (error) {
    elements.liveBackend.textContent = `offline: ${error.message}`;
    elements.liveModels.textContent = "sem leitura";
  }

  try {
    const models = await fetchJson("/api/llm/models");
    state.models = models.map((item) => item.name).filter(Boolean);
    renderModelOptions(state.models);
    if (state.models.length) {
      const preferred = state.models.find((name) => name.includes("llama3.2")) || state.models[0];
      for (const input of [elements.stressModel, elements.assistantModel, elements.scoringModel]) {
        if (!textValue(input)) input.value = preferred;
      }
      elements.liveModels.textContent = `${state.models.length} modelo(s): ${compactText(state.models.join(", "), 80)}`;
    } else {
      elements.liveModels.textContent = "nenhum modelo local retornado";
    }
  } catch (error) {
    elements.liveModels.textContent = `falha: ${error.message}`;
  }
}

function renderModelOptions(models) {
  elements.modelOptions.innerHTML = "";
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model;
    elements.modelOptions.append(option);
  }
}

async function loadRubricCases() {
  try {
    const cases = await fetchJson("/api/localization/rubric-cases?limit=100");
    elements.rubricCase.innerHTML = "";
    const usableCases = cases.filter(isUsableRubricCase);
    if (!usableCases.length) {
      elements.rubricCase.append(new Option("Nenhum case compatível", ""));
      return;
    }
    for (const item of usableCases) {
      const label = [
        item.category || "sem categoria",
        item.locale || "locale n/d",
        `${item.rubrics.length} rubricas`,
        item.status || "status n/d",
        item.id,
      ].join(" · ");
      elements.rubricCase.append(new Option(label, item.id));
    }
  } catch (error) {
    elements.rubricCase.innerHTML = "";
    elements.rubricCase.append(new Option(`Falha ao carregar: ${error.message}`, ""));
  }
}

function isUsableRubricCase(item) {
  const rubrics = item?.rubrics;
  if (!Array.isArray(rubrics) || !rubrics.length) return false;
  return rubrics.every((rubric) =>
    ALLOWED_RUBRIC_DIMENSIONS.has(rubric?.Rubric_dimensions),
  );
}

async function loadRuns() {
  const runs = await fetchJson("/api/hermes/runs");
  renderRuns(runs);
  const activeRun = runs.find((run) => isActiveStatus(run.status));
  if (!state.activeRunId && activeRun) {
    state.activeRunId = activeRun.run_id;
    renderRun(activeRun);
    startPolling();
  }
  return runs;
}

function renderRuns(runs) {
  elements.runsList.innerHTML = "";
  if (!runs.length) {
    elements.runsList.innerHTML = '<div class="empty-state">Nenhuma run registrada.</div>';
    return;
  }
  for (const run of runs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item hermes-run-item";
    button.innerHTML = `
      <span>
        <strong>${escapeHtml(run.run_id)}</strong>
        <small>${escapeHtml(run.status)} · ${run.results_count || 0} resultados</small>
      </span>
    `;
    button.addEventListener("click", () => {
      state.activeRunId = run.run_id;
      pollActiveRun();
    });
    elements.runsList.append(button);
  }
}

async function startRun(event) {
  event.preventDefault();
  if (!elements.rubricCase.value) {
    setStatus("failed", "Escolha um rubric case com rubricas antes de iniciar.");
    return;
  }
  elements.startRun.disabled = true;
  elements.cancelRun.disabled = true;
  setStatus("pending", "Criando run do Hermes...");
  try {
    const payload = buildPayload();
    const created = await fetchJson("/api/hermes/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.activeRunId = created.run_id;
    elements.runTitle.textContent = `Run ${created.run_id}`;
    setStatus(created.status, created.message);
    startPolling();
    await loadRuns();
  } catch (error) {
    setStatus("failed", `Falha ao iniciar: ${error.message}`);
  } finally {
    elements.startRun.disabled = Boolean(state.activeRunId);
  }
}

function startPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  pollActiveRun();
  state.pollTimer = setInterval(pollActiveRun, 2000);
}

async function pollActiveRun() {
  if (!state.activeRunId) return;
  try {
    const run = await fetchJson(`/api/hermes/status/${state.activeRunId}`);
    renderRun(run);
    if (!isActiveStatus(run.status)) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      state.activeRunId = null;
      await loadRuns();
    }
  } catch (error) {
    setStatus("failed", `Falha ao consultar run: ${error.message}`);
  }
}

function renderRun(run) {
  const progress = run.progress || {};
  elements.runTitle.textContent = `Run ${run.run_id}`;
  const estimate = progress.results_total_estimate || 0;
  const summary = run.error
    ? run.error
    : `${run.results_count || 0}/${estimate || "?"} resultados gerados.`;
  setStatus(run.status, summary);
  elements.startRun.disabled = isActiveStatus(run.status);
  elements.cancelRun.disabled = !isActiveStatus(run.status);
  elements.metricResults.textContent = String(run.results_count || 0);
  elements.metricPersona.textContent = compactText(progress.current_persona || "n/d", 24);
  elements.metricConversation.textContent = progress.current_conversation || "n/d";
  elements.metricTurn.textContent = progress.current_turn || "n/d";
  elements.liveStage.textContent = compactText(progress.stage || run.status || "idle", 80);
  elements.liveModel.textContent = compactText(progress.current_model || "n/d", 80);
  elements.livePoll.textContent = new Date().toLocaleTimeString("pt-BR");
  renderContextWindow(run);
  renderResults(run.results || []);
}

function renderContextWindow(run) {
  const context = run.progress?.context || {};
  const events = run.progress?.events || [];
  elements.contextPersona.textContent = formatContextValue(context.persona);
  elements.contextPrompt.textContent = formatContextValue(context.prompt);
  elements.contextHistory.textContent = formatContextValue(context.history);
  elements.contextCandidates.textContent = formatContextValue(context.candidates);
  elements.contextEvents.innerHTML = "";
  if (!events.length) {
    const item = document.createElement("li");
    item.textContent = "Aguardando eventos da run.";
    elements.contextEvents.append(item);
    return;
  }
  for (const event of events.slice().reverse()) {
    const item = document.createElement("li");
    const time = event.at ? new Date(event.at).toLocaleTimeString("pt-BR") : "sem hora";
    item.innerHTML = `<strong>${escapeHtml(time)}</strong> ${escapeHtml(event.message || "")}`;
    elements.contextEvents.append(item);
  }
}

function formatContextValue(value) {
  if (value === null || value === undefined || value === "") return "n/d";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

async function cancelActiveRun() {
  if (!state.activeRunId) return;
  elements.cancelRun.disabled = true;
  setStatus("pending", "Cancelamento solicitado; aguardando a chamada atual do modelo terminar...");
  try {
    const run = await fetchJson(`/api/hermes/runs/${state.activeRunId}/cancel`, {
      method: "POST",
    });
    renderRun(run);
  } catch (error) {
    setStatus("failed", `Falha ao cancelar: ${error.message}`);
  }
}

function compactText(value, maxLength) {
  const text = String(value || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
}

function renderResults(results) {
  elements.resultsList.innerHTML = "";
  if (!results.length) {
    elements.resultsList.innerHTML = '<div class="empty-state">Nenhum resultado ainda.</div>';
    return;
  }
  for (const result of results.slice().reverse().slice(0, 20)) {
    const pair = result.preference_pair;
    const scoring = result.scoring || {};
    const preference = scoring.preference || {};
    const card = document.createElement("article");
    card.className = "hermes-result-card";
    const scoringMessage = scoring.error
      || preference.warnings?.join("; ")
      || (pair ? "Par produzido pelo scoring." : "Scoring real nao escolheu chosen/rejected.");
    card.innerHTML = `
      <header>
        <span class="badge ${pair ? "ok" : "warning"}">${pair ? "pair" : "sem par"}</span>
        <strong>Conversa ${(result.conversation_index ?? 0) + 1} · Turno ${(result.turn_index ?? 0) + 1}</strong>
      </header>
      <p class="hermes-prompt">${escapeHtml(result.prompt || "")}</p>
      <p class="hermes-diagnostic">${escapeHtml(scoringMessage)}</p>
      <div class="hermes-pair-grid">
        <section>
          <span>Chosen</span>
          <strong>${escapeHtml(pair?.chosen_label || preference.chosen_candidate_id || "n/d")}</strong>
          <p>${escapeHtml(pair?.chosen || "Scoring não produziu preferência automática.")}</p>
        </section>
        <section>
          <span>Rejected</span>
          <strong>${escapeHtml(pair?.rejected_label || preference.rejected_candidate_id || "n/d")}</strong>
          <p>${escapeHtml(pair?.rejected || "Sem candidata rejeitada pelo scoring.")}</p>
        </section>
      </div>
    `;
    elements.resultsList.append(card);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

elements.form.addEventListener("submit", startRun);
elements.cancelRun.addEventListener("click", cancelActiveRun);
elements.refreshRuns.addEventListener("click", async () => {
  await loadRuntimeStatus();
  await loadRuns();
  if (state.activeRunId) {
    await pollActiveRun();
  }
});

loadRubricCases();
loadRuntimeStatus();
loadRuns().catch((error) => {
  elements.runsList.innerHTML = `<div class="empty-state">Falha ao carregar runs: ${escapeHtml(error.message)}</div>`;
});
