const state = {
  health: null,
  models: [],
  embeddingModels: [],
  experiments: [],
  history: [],
  selectedExperimentId: null,
  lastChatPayload: null,
  lastEmbeddingResult: null,
};

const API_BASE =
  window.location.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://127.0.0.1:8765";

const elements = {
  healthBadge: document.querySelector("#health-badge"),
  modelCount: document.querySelector("#model-count"),
  ollamaStatusTitle: document.querySelector("#ollama-status-title"),
  ollamaEndpoint: document.querySelector("#ollama-endpoint"),
  ollamaSummary: document.querySelector("#ollama-summary"),
  ollamaModelList: document.querySelector("#ollama-model-list"),
  modelSelect: document.querySelector("#model-select"),
  embeddingModelSelect: document.querySelector("#embedding-model-select"),
  chatForm: document.querySelector("#chat-form"),
  retrievalForm: document.querySelector("#retrieval-form"),
  conversation: document.querySelector("#conversation"),
  assistantOutput: document.querySelector("#assistant-output"),
  experimentJson: document.querySelector("#experiment-json"),
  metricsBar: document.querySelector("#metrics-bar"),
  historyList: document.querySelector("#history-list"),
  retrievalSummary: document.querySelector("#retrieval-summary"),
  retrievalOutput: document.querySelector("#retrieval-output"),
  studyLabel: document.querySelector("#study-label"),
  systemPrompt: document.querySelector("#system-prompt"),
  userPrompt: document.querySelector("#user-prompt"),
  includeHistory: document.querySelector("#include-history"),
  temperature: document.querySelector("#temperature"),
  topP: document.querySelector("#top-p"),
  topK: document.querySelector("#top-k"),
  repeatPenalty: document.querySelector("#repeat-penalty"),
  seed: document.querySelector("#seed"),
  numPredict: document.querySelector("#num-predict"),
  chunkSize: document.querySelector("#chunk-size"),
  chunkOverlap: document.querySelector("#chunk-overlap"),
  corpusVersion: document.querySelector("#corpus-version"),
  keepAlive: document.querySelector("#keep-alive"),
  rerunChat: document.querySelector("#rerun-chat"),
  clearSession: document.querySelector("#clear-session"),
  downloadHistory: document.querySelector("#download-history"),
  retrievalQuery: document.querySelector("#retrieval-query"),
  retrievalCorpusVersion: document.querySelector("#retrieval-corpus-version"),
  retrievalSource: document.querySelector("#retrieval-source"),
  retrievalSection: document.querySelector("#retrieval-section"),
  messageTemplate: document.querySelector("#message-template"),
};

function formatDate(value) {
  try {
    return new Date(value).toLocaleString("pt-BR");
  } catch {
    return value;
  }
}

function nanosToMs(value) {
  if (typeof value !== "number") {
    return null;
  }
  return Math.round(value / 1e6);
}

async function fetchJson(path, options = {}) {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = payload.error || payload.detail || "Erro inesperado.";
    throw new Error(message);
  }

  return payload;
}

function setBusy(button, busyLabel, originalLabel) {
  button.disabled = Boolean(busyLabel);
  button.textContent = busyLabel || originalLabel;
}

function totalTokens(metrics) {
  const promptTokens = metrics?.prompt_eval_count ?? 0;
  const answerTokens = metrics?.eval_count ?? 0;
  const total = promptTokens + answerTokens;
  return total > 0 ? total : null;
}

function renderHealth() {
  const badge = elements.healthBadge;
  const ready = Boolean(state.health?.ready ?? state.health?.ollama?.ready);

  if (!badge) {
    return;
  }

  badge.classList.remove("ok", "offline", "warning");

  if (!state.health) {
    badge.textContent = "Verificando Engine...";
    badge.classList.add("warning");
    renderOllamaStatus();
    return;
  }

  if (state.health.unreachable) {
    badge.textContent = "Engine Inacessivel";
    badge.classList.add("offline");
    renderOllamaStatus();
    return;
  }

  if (ready) {
    badge.textContent = "Engine Pronta";
    badge.classList.add("ok");
  } else {
    badge.textContent = "Engine Alerta";
    badge.classList.add("warning");
  }

  renderOllamaStatus();
}

function renderOllamaStatus() {
  const health = state.health;
  const ollama = health?.ollama || null;
  const ready = Boolean(health?.ready ?? ollama?.ready);
  const ollamaOk = Boolean(ollama?.ok);

  if (health?.unreachable) {
    elements.ollamaStatusTitle.textContent = "Backend Offline";
    elements.ollamaEndpoint.textContent = "URL: n/d";
    elements.ollamaSummary.textContent = health.error || "Erro ao tentar conectar";
    elements.ollamaModelList.innerHTML = "";
    return;
  }

  if (!ollama) {
    elements.ollamaStatusTitle.textContent = "Aguardando...";
    elements.ollamaEndpoint.textContent = "URL: n/d";
    elements.ollamaSummary.textContent = "Verificando status...";
    elements.ollamaModelList.innerHTML = "";
    return;
  }

  elements.ollamaStatusTitle.textContent = ready
    ? "Ollama Ativa"
    : ollamaOk
      ? "Ollama (Sem Modelos)"
      : "Ollama Indisponivel";
  elements.ollamaEndpoint.textContent = `URL: ${ollama.url || "n/d"}`;

  const warnings = [];
  if (health.database === "unreachable") {
    warnings.push("Banco indisponivel");
  }
  if (!ready && health.error) {
    warnings.push(health.error);
  }

  elements.ollamaSummary.textContent = warnings.length
    ? warnings.join(" | ")
    : `Modelos carregados: ${ollama.model_count ?? 0}`;

  elements.ollamaModelList.innerHTML = "";

  if (!Array.isArray(ollama.models) || !ollama.models.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = ollamaOk ? "Nenhum modelo carregado." : "Ollama indisponivel.";
    elements.ollamaModelList.appendChild(empty);
    return;
  }

  for (const model of ollama.models) {
    const item = document.createElement("div");
    item.className = "history-item";

    const title = document.createElement("strong");
    title.textContent = model.name || "Sem nome";

    const meta = document.createElement("div");
    meta.className = "history-meta";
    meta.textContent = model.details?.parameter_size || model.model || "modelo";

    item.append(title, meta);
    elements.ollamaModelList.appendChild(item);
  }
}

function populateModelSelects() {
  elements.modelSelect.innerHTML = "";
  if (!state.models.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Nenhum modelo disponivel";
    elements.modelSelect.appendChild(option);
  } else {
    for (const model of state.models) {
      const option = document.createElement("option");
      option.value = model.name;
      option.textContent = `${model.name} (${model.details?.parameter_size || "?"})`;
      elements.modelSelect.appendChild(option);
    }
  }

  elements.embeddingModelSelect.innerHTML = "";
  if (!state.embeddingModels.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Nenhum modelo de embedding disponivel";
    elements.embeddingModelSelect.appendChild(option);
    return;
  }

  for (const model of state.embeddingModels) {
    const option = document.createElement("option");
    option.value = model.name;
    option.textContent = model.label || `${model.name} (${model.source || "embedding"})`;
    elements.embeddingModelSelect.appendChild(option);
  }
}

function renderConversation() {
  elements.conversation.innerHTML = "";

  if (!state.history.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Rode um prompt para comecar a sessao.";
    elements.conversation.appendChild(empty);
    return;
  }

  for (const message of state.history) {
    const fragment = elements.messageTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".message");
    article.classList.add(message.role);
    fragment.querySelector(".message-role").textContent =
      message.role === "user" ? "Researcher" : "Assistant";
    fragment.querySelector(".message-content").textContent = message.content;
    elements.conversation.appendChild(fragment);
  }

  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function renderMetrics(metrics = null) {
  elements.metricsBar.innerHTML = "";

  if (!metrics) {
    const span = document.createElement("span");
    span.className = "metric";
    span.textContent = "Nenhuma execucao ainda.";
    elements.metricsBar.appendChild(span);
    return;
  }

  const items = [
    ["Total", nanosToMs(metrics.total_duration) ? `${nanosToMs(metrics.total_duration)} ms` : "n/d"],
    ["Prompt tokens", metrics.prompt_eval_count ?? "n/d"],
    ["Resposta tokens", metrics.eval_count ?? "n/d"],
    ["Total tokens", totalTokens(metrics) ?? "n/d"],
    ["Finalizacao", metrics.done_reason || "n/d"],
  ];

  for (const [label, value] of items) {
    const span = document.createElement("span");
    span.className = "metric";
    span.textContent = `${label}: ${value}`;
    elements.metricsBar.appendChild(span);
  }
}

function renderExperimentDetails(experiment) {
  if (!experiment) {
    elements.assistantOutput.textContent = "Ainda nao ha resposta.";
    elements.experimentJson.textContent = "Nenhum experimento selecionado.";
    renderMetrics();
    return;
  }

  if (experiment.experiment_kind === "chat") {
    elements.assistantOutput.textContent =
      experiment.response_payload?.message?.content ||
      experiment.response_payload?.message ||
      "Resposta vazia.";
    renderMetrics(experiment.metrics);
  } else {
    elements.assistantOutput.textContent = "Experimento de busca/RAG selecionado.";
    renderMetrics();
  }

  elements.experimentJson.textContent = JSON.stringify(experiment, null, 2);
}

function renderHistory() {
  elements.historyList.innerHTML = "";

  if (!state.experiments.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhum experimento salvo ainda.";
    elements.historyList.appendChild(empty);
    return;
  }

  for (const experiment of state.experiments) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "history-item";

    if (experiment.id === state.selectedExperimentId) {
      item.classList.add("active");
    }

    const title = document.createElement("strong");
    title.textContent = experiment.title || "Sem titulo";

    const metaKind = document.createElement("div");
    metaKind.className = "history-meta";
    metaKind.textContent = `${experiment.experiment_kind} · ${experiment.model_name || "modelo"}`;

    const metaDate = document.createElement("div");
    metaDate.className = "history-meta";
    metaDate.textContent = formatDate(experiment.created_at);

    item.append(title, metaKind, metaDate);
    item.addEventListener("click", () => {
      state.selectedExperimentId = experiment.id;
      renderHistory();
      renderExperimentDetails(experiment);
    });
    elements.historyList.appendChild(item);
  }
}

function prependExperiment(experiment) {
  state.experiments = [experiment, ...state.experiments].slice(0, 200);
  state.selectedExperimentId = experiment.id;
  renderHistory();
  renderExperimentDetails(experiment);
}

function currentChatPayload() {
  return {
    model: elements.modelSelect.value,
    studyLabel: elements.studyLabel.value.trim(),
    systemPrompt: elements.systemPrompt.value.trim(),
    prompt: elements.userPrompt.value.trim(),
    includeHistory: elements.includeHistory.checked,
    history: state.history,
    temperature: elements.temperature.value,
    top_p: elements.topP.value,
    top_k: elements.topK.value,
    repeat_penalty: elements.repeatPenalty.value,
    seed: elements.seed.value,
    max_tokens: elements.numPredict.value,
    chunk_size: elements.chunkSize.value,
    chunk_overlap: elements.chunkOverlap.value,
    corpus_version: elements.corpusVersion.value.trim(),
    keep_alive: elements.keepAlive.value.trim(),
  };
}

async function loadInitialData() {
  const [health, models, embeddingModels, experiments] = await Promise.all([
    fetchJson("/api/health").catch((error) => ({
      ok: false,
      unreachable: true,
      error: error.message,
      model_count: 0,
    })),
    fetchJson("/api/llm/models").catch(() => []),
    fetchJson("/api/rag/embedding-models").catch(() => []),
    fetchJson("/api/experiments").catch(() => []),
  ]);

  state.health = health;
  state.models = Array.isArray(models) ? models : [];
  state.embeddingModels = Array.isArray(embeddingModels) ? embeddingModels : [];
  state.experiments = Array.isArray(experiments) ? experiments : [];
  state.selectedExperimentId = state.experiments[0]?.id || null;

  renderHealth();
  populateModelSelects();
  renderConversation();
  renderHistory();
  renderExperimentDetails(state.experiments[0] || null);
}

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const button = document.querySelector("#submit-chat");
  const originalLabel = button.textContent;
  const payload = currentChatPayload();

  if (!payload.prompt) {
    elements.assistantOutput.textContent = "Escreva um prompt antes de executar.";
    return;
  }

  if (!payload.model) {
    elements.assistantOutput.textContent = "Selecione um modelo antes de executar.";
    return;
  }

  setBusy(button, "Executando...", originalLabel);

  try {
    const messages = payload.includeHistory
      ? [...payload.history, { role: "user", content: payload.prompt }]
      : [{ role: "user", content: payload.prompt }];

    if (payload.systemPrompt) {
      messages.unshift({ role: "system", content: payload.systemPrompt });
    }

    const chatResponse = await fetchJson("/api/llm/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages,
        generation: {
          model_name: payload.model,
          seed: parseInt(payload.seed, 10),
          temperature: parseFloat(payload.temperature),
          top_p: parseFloat(payload.top_p),
          top_k: parseInt(payload.top_k, 10),
          repeat_penalty: parseFloat(payload.repeat_penalty),
          max_tokens: parseInt(payload.max_tokens, 10),
          chunk_size: parseInt(payload.chunk_size, 10),
          chunk_overlap: parseInt(payload.chunk_overlap, 10),
          corpus_version: payload.corpus_version || "v1",
          prompt_template_version: "v1",
        },
        keep_alive: payload.keep_alive,
        metadata: {
          study_label: payload.studyLabel,
        },
      }),
    });

    const result = chatResponse.result || {};
    const assistantMsg = result.message?.content || "";

    state.lastChatPayload = payload;
    state.history = [
      ...state.history,
      { role: "user", content: payload.prompt },
      { role: "assistant", content: assistantMsg },
    ];

    renderConversation();
    elements.assistantOutput.textContent = assistantMsg || "Resposta vazia.";
    renderMetrics(result);

    try {
      const experimentResponse = await fetchJson("/api/experiments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          experiment_kind: "chat",
          title: `Chat: ${payload.prompt.substring(0, 30)}...`,
          study_label: payload.studyLabel,
          generation: {
            model_name: payload.model,
            seed: parseInt(payload.seed, 10),
            temperature: parseFloat(payload.temperature),
            top_p: parseFloat(payload.top_p),
            top_k: parseInt(payload.top_k, 10),
            repeat_penalty: parseFloat(payload.repeat_penalty),
            max_tokens: parseInt(payload.max_tokens, 10),
            chunk_size: parseInt(payload.chunk_size, 10),
            chunk_overlap: parseInt(payload.chunk_overlap, 10),
            corpus_version: payload.corpus_version || "v1",
            prompt_template_version: "v1",
            retrieval_strategy: "none",
            retrieved_top_k: 0,
          },
          prompt_messages: messages,
          request_payload: payload,
          response_payload: result,
          metrics: result,
        }),
      });

      const experiment = experimentResponse.experiment || experimentResponse;
      prependExperiment(experiment);
    } catch (saveError) {
      console.warn("Falha ao salvar experimento.", saveError);
      elements.experimentJson.textContent = JSON.stringify(
        {
          warning: "Falha ao salvar experimento.",
          error: saveError.message,
          response_payload: result,
        },
        null,
        2,
      );
    }
  } catch (error) {
    elements.assistantOutput.textContent = error.message;
  } finally {
    setBusy(button, "", originalLabel);
  }
});

elements.rerunChat.addEventListener("click", () => {
  elements.chatForm.requestSubmit();
});

elements.clearSession.addEventListener("click", () => {
  state.history = [];
  renderConversation();
  renderMetrics();
  elements.assistantOutput.textContent = "Sessao limpa. Pronto para o proximo teste.";
});

elements.retrievalForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const button = document.querySelector("#run-retrieval");
  const originalLabel = button.textContent;
  const payload = {
    embedding_model: elements.embeddingModelSelect.value,
    corpus_version: elements.retrievalCorpusVersion.value.trim(),
    query_text: elements.retrievalQuery.value.trim(),
    limit: 5,
    source: elements.retrievalSource.value.trim() || null,
    section: elements.retrievalSection.value.trim() || null,
  };

  setBusy(button, "Buscando...", originalLabel);
  try {
    const result = await fetchJson("/api/rag/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    elements.retrievalSummary.textContent = `${result.count} fragmentos encontrados.`;
    elements.retrievalOutput.textContent = JSON.stringify(result.results, null, 2);
  } catch (error) {
    elements.retrievalSummary.textContent = error.message;
  } finally {
    setBusy(button, "", originalLabel);
  }
});

elements.downloadHistory.addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(state.experiments, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "llm-study-history.json";
  anchor.click();
  URL.revokeObjectURL(url);
});

loadInitialData();
