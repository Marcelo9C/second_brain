// Elementos globais mapeados da interface
const elements = {
  // Controle de Abas
  btnTabStudy: document.querySelector("#btn-tab-study"),
  btnTabAdvisor: document.querySelector("#btn-tab-advisor"),
  btnTabOrchestrator: document.querySelector("#btn-tab-orchestrator"),
  tabContentStudy: document.querySelector("#tab-content-study"),
  tabContentAdvisor: document.querySelector("#tab-content-advisor"),
  tabContentOrchestrator: document.querySelector("#tab-content-orchestrator"),
  sidebarDidactic: document.querySelector("#sidebar-didactic"),
  sidebarAdvisor: document.querySelector("#sidebar-advisor"),
  sidebarOrchestrator: document.querySelector("#sidebar-orchestrator"),

  // Módulo Didático (Ollama Widgets)
  didacticOllamaTitle: document.querySelector("#didactic-ollama-title"),
  didacticOllamaEndpoint: document.querySelector("#didactic-ollama-endpoint"),
  didacticOllamaModels: document.querySelector("#didactic-ollama-models"),

  // Módulo Advisor (Diagnósticos do Hermes)
  templateJsonSelect: document.querySelector("#template-json-select"),
  btnLoadTemplate: document.querySelector("#btn-load-template"),
  advisorForm: document.querySelector("#hermes-advisor-form"),
  adviseObjective: document.querySelector("#advise-objective"),
  adviseContext: document.querySelector("#advise-context"),
  advisorStatusBadge: document.querySelector("#advisor-status-badge"),
  advisorResultsArea: document.querySelector("#advisor-results-area"),
  askHermes: document.querySelector("#ask-hermes"),

  // Módulo Orquestrador (v0)
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
  healthBadge: document.querySelector("#health-badge"),
  pipPanel: document.querySelector("#hermes-pip-panel"),
  pipHeader: document.querySelector("#pip-header"),
  btnPipToggle: document.querySelector("#btn-pip-toggle"),
  pipPulse: document.querySelector("#pip-pulse"),
  pipCognition: document.querySelector("#pip-cognition-state"),
  pipAuditTrace: document.querySelector("#pip-audit-trace"),
  pipMetaLatency: document.querySelector("#pip-meta-latency"),
  pipMetaRules: document.querySelector("#pip-meta-rules"),
};

const state = {
  activeRunId: null,
  pollTimer: null,
  models: [],
  contextSource: "manual",
  defaults: null,
};

// Templates JSON estruturados para estudo didático
const RUN_TEMPLATES = {
  sxs_preference: {
    current_models: {
      generation: "llama3.2:3b",
      judge: "llama3.2:3b"
    },
    rubric: {
      criteria_count: 3,
      allowed_dimensions: ["Natural Language Fluency", "Logic and Formatting"]
    },
    result: {
      margin: 0.15,
      chosen_candidate: "candidate_a",
      rejected_candidate: "candidate_b"
    },
    current_thresholds: {
      margin: 0.50
    },
    num_conversations: 5,
    num_turns: 3
  },
  rubric_calibration: {
    rubric_case_id: "case-calib-ptbr-01",
    locale: "pt-BR",
    category: "Writing",
    status: "draft",
    validation: {
      structure_pass: true,
      format_pass: false,
      mismatch_detected: true
    },
    rubrics: [
      {
        id: "rubric-01",
        dimension: "Natural Language Fluency",
        score: 4
      }
    ]
  },
  rag_retrieval: {
    embedding_model: "nomic-embed-text",
    corpus_version: "v1",
    query: "como configurar o assistente hermes?",
    retrieved_chunks: [
      {
        rank: 1,
        similarity: 0.88,
        source: "manual.pdf",
        tokens: 120
      },
      {
        rank: 2,
        similarity: 0.72,
        source: "architecture.md",
        tokens: 310
      }
    ],
    selected_for_prompt_count: 1
  }
};

const ALLOWED_RUBRIC_DIMENSIONS = new Set([
  "Cultural Understanding and Application",
  "Local Facts and Awareness",
  "Logic and Formatting",
  "Natural Language Fluency",
]);

// -------------------------------------------------------------
// 1. GERENCIAMENTO DE ABAS
// -------------------------------------------------------------
function switchTab(activeBtn, targetContent, targetSidebar) {
  // Desativa todas as abas
  [elements.btnTabStudy, elements.btnTabAdvisor, elements.btnTabOrchestrator].forEach(btn => {
    btn.classList.remove("active");
  });
  [elements.tabContentStudy, elements.tabContentAdvisor, elements.tabContentOrchestrator].forEach(content => {
    content.style.display = "none";
  });
  [elements.sidebarDidactic, elements.sidebarAdvisor, elements.sidebarOrchestrator].forEach(sidebar => {
    sidebar.style.display = "none";
  });

  // Ativa a aba atual
  activeBtn.classList.add("active");
  targetContent.style.display = "block";
  targetSidebar.style.display = "block";
}

elements.btnTabStudy.addEventListener("click", () => {
  switchTab(elements.btnTabStudy, elements.tabContentStudy, elements.sidebarDidactic);
});

elements.btnTabAdvisor.addEventListener("click", () => {
  switchTab(elements.btnTabAdvisor, elements.tabContentAdvisor, elements.sidebarAdvisor);
  // Auto-carrega o primeiro template se o textarea estiver vazio
  if (!elements.adviseContext.value.trim()) {
    loadJsonTemplate();
  }
});

elements.btnTabOrchestrator.addEventListener("click", () => {
  switchTab(elements.btnTabOrchestrator, elements.tabContentOrchestrator, elements.sidebarOrchestrator);
});

// -------------------------------------------------------------
// 2. MÓDULO ADVISOR (PLAYGROUND INTEGRADO)
// -------------------------------------------------------------
function loadJsonTemplate() {
  const selectedType = elements.templateJsonSelect.value;
  const template = RUN_TEMPLATES[selectedType];
  if (template) {
    elements.adviseContext.value = JSON.stringify(template, null, 2);
    elements.adviseObjective.value = selectedType === "sxs_preference" ? "generate_dpo_pairs" : selectedType;
    setAdvisorStatus("neutral", "template loaded");
    elements.advisorResultsArea.innerHTML = `
      <div class="state-summary warning">
        Template carregado com sucesso. Ajuste os campos JSON à direita se desejar e clique em "Pedir Diagnóstico" na barra lateral para simular o Hermes.
      </div>
    `;
  }
}

elements.btnLoadTemplate.addEventListener("click", loadJsonTemplate);

function setAdvisorStatus(kind, label) {
  elements.advisorStatusBadge.className = `badge ${kind === "ok" ? "ok" : kind === "warning" ? "warning" : "neutral"}`;
  elements.advisorStatusBadge.textContent = label;
}

function parseContext() {
  const raw = elements.adviseContext.value.trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("Context JSON precisa ser um objeto.");
    }
    return parsed;
  } catch (error) {
    throw new Error(`Context JSON inválido: ${error.message}`);
  }
}

async function handleAdvisorSubmit(event) {
  event.preventDefault();
  setAdvisorStatus("warning", "advising");
  elements.askHermes.disabled = true;
  elements.advisorResultsArea.innerHTML = '<div class="empty-state">Hermes analisando contrato do run...</div>';
  
  // Real telemetry start
  logToPip(
    "Auditoria: Analisando...",
    `Solicitação de Diagnóstico iniciada pelo Cientista de Dados.\nInterpretando objetivo: "${elements.adviseObjective.value.trim()}"\nVerificando conformidade contratual do JSON de entrada...`,
    "Advise / Running",
    true,
    0,
    8
  );
  
  try {
    const payload = {
      objective: elements.adviseObjective.value.trim() || "manual_diagnostic",
      context: parseContext(),
      constraints: {},
      user_preferences: {},
    };
    const response = await fetchJson("/api/hermes/advise", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderAdvisorResponse(response);
    setAdvisorStatus("ok", "ready");
    
    // Real telemetry success
    const rulesEval = response.advisor_trace?.rules_evaluated || [];
    const rulesTrig = response.advisor_trace?.rules_triggered || [];
    const diagnoses = response.diagnosis || [];
    
    let logMsg = `Diagnóstico Concluído com Sucesso.\n`;
    logMsg += `Regras avaliadas pelo Hermes: ${rulesEval.join(", ") || "n/d"}\n`;
    logMsg += `Heurísticas disparadas: ${rulesTrig.length > 0 ? rulesTrig.join(", ") : "Nenhuma (Conformidade contratual 100%)"}\n`;
    if (diagnoses.length > 0) {
      logMsg += `\n⚠️ AVISOS E INCONSISTÊNCIAS DETECTADOS:\n`;
      diagnoses.forEach((d, i) => {
        logMsg += `${i + 1}. [${d.severity.toUpperCase()}] ${d.issue}: ${d.impact} (Evidência: ${d.evidence})\n`;
      });
    }
    
    logToPip(
      "Auditoria: Concluída",
      logMsg,
      "Observe & Advise",
      false,
      rulesTrig.length,
      rulesEval.length || 8
    );
  } catch (error) {
    setAdvisorStatus("offline", "failed");
    elements.advisorResultsArea.innerHTML = `<div class="state-summary offline">${escapeHtml(error.message)}</div>`;
    
    // Real telemetry error
    logToPip(
      "Cognição: Falhou",
      `Erro na Auditoria do Contrato:\n${error.message}`,
      "Advise / Error",
      false,
      0,
      8
    );
    if (elements.pipPulse) {
      elements.pipPulse.className = "pip-pulse error";
    }
  } finally {
    elements.askHermes.disabled = false;
  }
}

function renderAdvisorResponse(response) {
  const recommendations = response.recommendations || [];
  if (!recommendations.length) {
    elements.advisorResultsArea.innerHTML = `
      <div class="hermes-advise-summary">
        <span>Objective</span>
        <strong>${escapeHtml(response.interpreted_objective || "n/d")}</strong>
        <span>Source</span>
        <strong>manual diagnostic</strong>
      </div>
      <div class="empty-state">Nenhuma recomendação determinística ativa para este contexto JSON.</div>
    `;
    return;
  }

  elements.advisorResultsArea.innerHTML = "";
  const header = document.createElement("div");
  header.className = "hermes-advise-summary";
  header.innerHTML = `
    <span>Objective</span>
    <strong>${escapeHtml(response.interpreted_objective || "n/d")}</strong>
    <span>Source</span>
    <strong>MLOps Manual Run Ingestion</strong>
  `;
  elements.advisorResultsArea.append(header);

  for (const rec of recommendations) {
    const card = document.createElement("article");
    card.className = "hermes-advise-card";
    card.innerHTML = `
      <header>
        <div>
          <span>Ação Proposta</span>
          <h3>${escapeHtml(rec.action)}</h3>
        </div>
        <strong style="color: var(--accent-strong); font-size: 1.1rem;">${Math.round(Number(rec.confidence || 0) * 100)}%</strong>
      </header>
      <dl>
        <dt>Heurística / Motivo</dt>
        <dd>${escapeHtml(rec.reason)}</dd>
        <dt>Confirmação humana</dt>
        <dd>${rec.requires_confirmation ? "Exigida (Gatekeeper Act)" : "Isenta (Observe/Advise)"}</dd>
        <dt>Regra acionada</dt>
        <dd><code>${escapeHtml(rec.selected_by || "n/d")}</code></dd>
      </dl>
    `;
    elements.advisorResultsArea.append(card);
  }

  const diagnosis = response.diagnosis || [];
  if (diagnosis.length) {
    const block = document.createElement("section");
    block.className = "hermes-advise-diagnosis";
    block.innerHTML = `
      <span>Diagnósticos Detalhados da Rodada</span>
      ${diagnosis.map((item) => `
        <div>
          <strong>⚠️ ${escapeHtml(item.issue)} · Severidade: ${escapeHtml(item.severity)}</strong>
          <p><strong>Evidência:</strong> ${escapeHtml(item.evidence)}</p>
          <p><strong>Impacto MLOps:</strong> ${escapeHtml(item.impact)}</p>
        </div>
      `).join("")}
    `;
    elements.advisorResultsArea.append(block);
  }
}

elements.advisorForm.addEventListener("submit", handleAdvisorSubmit);

// -------------------------------------------------------------
// 3. MÓDULO ORQUESTRADOR (v0 PROTÓTIPO ORIGINAL)
// -------------------------------------------------------------
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
    const config = await fetchJson("/api/hermes/config");
    state.defaults = config;
  } catch (error) {
    console.error("Falha ao carregar defaults do backend:", error);
    state.defaults = {
      default_advisor_model: "hermes:latest",
      default_stress_model: "openhermes:latest",
      default_scoring_model: "llama3.2:3b"
    };
  }

  try {
    const health = await fetchJson("/api/health");
    const ollama = health.ollama || {};
    
    // Atualiza widgets globais
    elements.healthBadge.textContent = health.ok ? "Engine online" : "Engine degradada";
    elements.healthBadge.className = `badge ${health.ok ? "ok" : "offline"}`;
    
    elements.liveBackend.textContent = health.ok ? "online" : "degradado";
    elements.liveModels.textContent = ollama.ready
      ? "Ollama pronto; buscando modelos"
      : (health.error || "Ollama não pronto");

    // Atualiza widgets didáticos
    elements.didacticOllamaTitle.textContent = ollama.ready ? "Ollama Conectado" : "Ollama Indisponível";
    elements.didacticOllamaEndpoint.textContent = `Endpoint: ${ollama.endpoint || ollama.url || "n/d"}`;
  } catch (error) {
    elements.healthBadge.textContent = "Engine offline";
    elements.healthBadge.className = "badge offline";
    elements.liveBackend.textContent = `offline: ${error.message}`;
    elements.liveModels.textContent = "sem leitura";
    
    elements.didacticOllamaTitle.textContent = "Ollama Offline";
    elements.didacticOllamaEndpoint.textContent = `Erro: ${error.message}`;
  }

  try {
    const models = await fetchJson("/api/llm/models");
    state.models = models.map((item) => item.name).filter(Boolean);
    renderModelOptions(state.models);
    if (state.models.length) {
      elements.liveModels.textContent = `${state.models.length} modelo(s) carregados`;
      elements.didacticOllamaModels.textContent = `Modelos: ${state.models.join(", ")}`;
    } else {
      elements.liveModels.textContent = "nenhum modelo local retornado";
      elements.didacticOllamaModels.textContent = "Modelos: nenhum encontrado";
    }
  } catch (error) {
    elements.liveModels.textContent = `falha: ${error.message}`;
    elements.didacticOllamaModels.textContent = `Modelos: falha ao buscar`;
  }
}

function renderModelOptions(models) {
  const dropdowns = [
    { el: elements.stressModel, defaultKey: "default_stress_model", fallbackPrefix: "openhermes" },
    { el: elements.assistantModel, defaultKey: "default_advisor_model", fallbackPrefix: "hermes" },
    { el: elements.scoringModel, defaultKey: "default_scoring_model", fallbackPrefix: "llama3.2" }
  ];

  for (const { el, defaultKey, fallbackPrefix } of dropdowns) {
    if (!el) continue;
    const currentVal = el.value;
    el.innerHTML = "";
    if (models.length === 0) {
      el.append(new Option("Buscando...", ""));
      continue;
    }
    for (const model of models) {
      el.append(new Option(model, model));
    }
    // Restore previous selection or default to backend config
    if (currentVal && models.includes(currentVal)) {
      el.value = currentVal;
    } else {
      const backendDefault = state.defaults?.[defaultKey];
      if (backendDefault && models.includes(backendDefault)) {
        el.value = backendDefault;
      } else {
        const preferred = models.find((name) => name.includes(fallbackPrefix)) || models[0];
        el.value = preferred;
      }
    }
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
    elements.runsList.innerHTML = '<div class="empty-state">Nenhuma run registrada no laboratório.</div>';
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

async function handleRunSubmit(event) {
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
  
  // Real-time dynamic updates to PiP panel
  updateRunPiP(run);
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
  setStatus("pending", "Cancelamento solicitado; aguardando término da tarefa de inferência...");
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

// PiP Panel Logic and Event Listeners
let isDragging = false;
let startX = 0;
let startY = 0;
let currentX = 0;
let currentY = 0;
let hasMoved = false;

if (elements.pipHeader && elements.pipPanel && elements.btnPipToggle) {
  // Set initial cursor style
  elements.pipHeader.style.cursor = "grab";

  elements.pipHeader.addEventListener("mousedown", (e) => {
    if (e.target === elements.btnPipToggle) return;
    isDragging = true;
    startX = e.clientX - currentX;
    startY = e.clientY - currentY;
    elements.pipHeader.style.cursor = "grabbing";
    hasMoved = false;
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    e.preventDefault();
    const newX = e.clientX - startX;
    const newY = e.clientY - startY;
    if (Math.abs(newX - currentX) > 2 || Math.abs(newY - currentY) > 2) {
      hasMoved = true;
    }
    currentX = newX;
    currentY = newY;
    elements.pipPanel.style.transform = `translate(${currentX}px, ${currentY}px)`;
  });

  document.addEventListener("mouseup", () => {
    if (!isDragging) return;
    isDragging = false;
    elements.pipHeader.style.cursor = "grab";
  });

  elements.pipHeader.addEventListener("click", (e) => {
    if (e.target === elements.btnPipToggle) return;
    // Only toggle minimized if the user didn't actively drag the panel around
    if (!hasMoved) {
      elements.pipPanel.classList.toggle("minimized");
      elements.btnPipToggle.textContent = elements.pipPanel.classList.contains("minimized") ? "+" : "—";
    }
  });

  elements.btnPipToggle.addEventListener("click", (e) => {
    e.stopPropagation();
    elements.pipPanel.classList.toggle("minimized");
    elements.btnPipToggle.textContent = elements.pipPanel.classList.contains("minimized") ? "+" : "—";
  });
}

function updateExecutionTrace(stepStates) {
  const steps = ["ingestion", "validation", "conflict", "heuristic", "diagnostic", "recommendation"];
  for (const step of steps) {
    const el = document.querySelector(`#step-${step}`);
    if (!el) continue;
    el.className = "trace-step";
    const status = stepStates[step];
    if (status) {
      el.classList.add(status);
    }
  }
}

function logToPip(cognitionState, logText, mode = "Observe", active = false, rulesTriggered = 0, totalRules = 8) {
  if (elements.pipCognition) {
    elements.pipCognition.textContent = cognitionState.toUpperCase();
  }
  
  if (elements.pipPulse) {
    if (active) {
      elements.pipPulse.className = "pip-pulse active";
    } else {
      elements.pipPulse.className = "pip-pulse";
    }
  }
  
  if (elements.pipAuditTrace) {
    const timestamp = new Date().toLocaleTimeString("pt-BR");
    elements.pipAuditTrace.textContent = `[${timestamp}] ${logText}\n`;
    elements.pipAuditTrace.scrollTop = elements.pipAuditTrace.scrollHeight;
  }
  
  if (elements.pipMetaLatency) {
    elements.pipMetaLatency.textContent = mode;
  }
  if (elements.pipMetaRules) {
    elements.pipMetaRules.textContent = `${rulesTriggered} / ${totalRules}`;
  }

  // Handle active states on Advisor click
  if (mode.includes("Running") || active) {
    updateExecutionTrace({
      ingestion: "active",
      validation: "",
      conflict: "",
      heuristic: "",
      diagnostic: "",
      recommendation: ""
    });
    // Fast visual simulation triggers to map state progression for the user during the fetch call
    setTimeout(() => {
      const ingEl = document.querySelector("#step-ingestion");
      if (ingEl && ingEl.classList.contains("active")) {
        updateExecutionTrace({
          ingestion: "completed",
          validation: "active",
          conflict: "",
          heuristic: "",
          diagnostic: "",
          recommendation: ""
        });
      }
    }, 150);
    setTimeout(() => {
      const valEl = document.querySelector("#step-validation");
      if (valEl && valEl.classList.contains("active")) {
        updateExecutionTrace({
          ingestion: "completed",
          validation: "completed",
          conflict: "active",
          heuristic: "",
          diagnostic: "",
          recommendation: ""
        });
      }
    }, 300);
    setTimeout(() => {
      const conEl = document.querySelector("#step-conflict");
      if (conEl && conEl.classList.contains("active")) {
        updateExecutionTrace({
          ingestion: "completed",
          validation: "completed",
          conflict: "completed",
          heuristic: "active",
          diagnostic: "",
          recommendation: ""
        });
      }
    }, 450);
  } else if (cognitionState.includes("Concluída")) {
    updateExecutionTrace({
      ingestion: "completed",
      validation: "completed",
      conflict: "completed",
      heuristic: "completed",
      diagnostic: "completed",
      recommendation: "completed"
    });
  } else if (cognitionState.includes("Falhou")) {
    updateExecutionTrace({
      ingestion: "completed",
      validation: "failed",
      conflict: "",
      heuristic: "",
      diagnostic: "",
      recommendation: ""
    });
  }
}

function updateRunPiP(run) {
  const progress = run.progress || {};
  const events = progress.events || [];
  const currentStage = progress.stage || run.status || "idle";
  const currentModel = progress.current_model || "n/d";
  
  let logMsg = `Orquestrador MLOps: Status = ${run.status.toUpperCase()}\n`;
  logMsg += `Fase Cognitiva: ${currentStage.toUpperCase()}\n`;
  if (currentModel !== "n/d") {
    logMsg += `Modelo em Inferência: ${currentModel}\n`;
  }
  
  if (events.length > 0) {
    logMsg += `\nREGISTROS DA THREAD DE EXECUÇÃO:\n`;
    events.slice(-6).forEach(e => {
      const time = e.at ? new Date(e.at).toLocaleTimeString("pt-BR") : "";
      logMsg += `[${time}] ${e.message}\n`;
    });
  }
  
  const isActive = isActiveStatus(run.status);
  const isError = run.status === "failed";
  
  if (elements.pipCognition) {
    elements.pipCognition.textContent = currentStage.toUpperCase();
  }
  if (elements.pipMetaLatency) {
    elements.pipMetaLatency.textContent = `Act / Run ${run.run_id}`;
  }
  if (elements.pipMetaRules) {
    elements.pipMetaRules.textContent = `MLOps Act`;
  }
  
  if (elements.pipPulse) {
    if (isError) {
      elements.pipPulse.className = "pip-pulse error";
    } else if (isActive) {
      elements.pipPulse.className = "pip-pulse active";
    } else {
      elements.pipPulse.className = "pip-pulse";
    }
  }
  
  if (elements.pipAuditTrace) {
    elements.pipAuditTrace.textContent = logMsg;
    elements.pipAuditTrace.scrollTop = elements.pipAuditTrace.scrollHeight;
  }

  // Update Execution Trace nodes live from backend states!
  const stepStates = {
    ingestion: "completed",
    validation: "completed",
    conflict: "",
    heuristic: "",
    diagnostic: "",
    recommendation: ""
  };
  
  if (currentStage === "pending" || currentStage === "created" || currentStage === "starting") {
    stepStates.ingestion = "active";
    stepStates.validation = "";
  } else if (currentStage === "loading rubrics") {
    stepStates.validation = "active";
  } else if (currentStage === "generating stress prompts" || currentStage === "calling stress model" || currentStage === "generating stress follow-up model" || currentStage === "calling stress follow-up model") {
    stepStates.conflict = "active";
  } else if (currentStage === "generating candidates" || currentStage === "calling assistant model" || currentStage === "calling stress follow-up model") {
    stepStates.conflict = "completed";
    stepStates.heuristic = "active";
  } else if (currentStage === "scoring candidates") {
    stepStates.conflict = "completed";
    stepStates.heuristic = "completed";
    stepStates.diagnostic = "active";
  } else if (currentStage === "completed" || run.status === "success") {
    stepStates.conflict = "completed";
    stepStates.heuristic = "completed";
    stepStates.diagnostic = "completed";
    stepStates.recommendation = "completed";
  } else if (run.status === "failed") {
    stepStates.ingestion = "completed";
    stepStates.validation = "completed";
    stepStates.conflict = "failed";
    stepStates.heuristic = "failed";
    stepStates.diagnostic = "failed";
    stepStates.recommendation = "failed";
  }
  updateExecutionTrace(stepStates);
}

elements.form.addEventListener("submit", handleRunSubmit);
elements.cancelRun.addEventListener("click", cancelActiveRun);

// Inicialização
loadRubricCases();
loadRuntimeStatus();
loadRuns().catch((error) => {
  elements.runsList.innerHTML = `<div class="empty-state">Falha ao carregar runs: ${escapeHtml(error.message)}</div>`;
});
// Atualizações periódicas de status da engine
setInterval(loadRuntimeStatus, 10000);
