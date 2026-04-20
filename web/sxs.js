const state = {
  health: null,
  models: [],
  evaluations: [],
  isEditedA: false,
  isEditedB: false,
  resultA: null,
  resultB: null,
};

const API_BASE =
  window.location.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://127.0.0.1:8765";

  seed: document.querySelector("#seed"),
  toggleBlind: document.querySelector("#toggle-blind"),
  toggleDualPrompt: document.querySelector("#toggle-dual-prompt"),
  unifiedPromptGroup: document.querySelector("#unified-prompt-group"),
  dualPromptGroup: document.querySelector("#dual-prompt-group"),
  labelA: document.querySelector("#label-a"),
  labelB: document.querySelector("#label-b"),
  systemPromptA: document.querySelector("#system-prompt-a"),
  userPromptA: document.querySelector("#user-prompt-a"),
  systemPromptB: document.querySelector("#system-prompt-b"),
  userPromptB: document.querySelector("#user-prompt-b"),
  diffPanel: document.querySelector("#diff-panel"),
  diffOutput: document.querySelector("#diff-output"),
};

async function fetchJson(path, options = {}) {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = payload.error || payload.detail || "Erro na requisicao.";
    throw new Error(message);
  }

  return payload;
}

function setBusy(isBusy) {
  elements.runBtn.disabled = isBusy;
  elements.runBtn.textContent = isBusy ? "Executando..." : "Executar Comparacao";
}

function updateValueTag(slider, tag) {
  slider.addEventListener("input", () => {
    tag.textContent = slider.value;
  });
}

function nanosToMs(value) {
  if (typeof value !== "number") {
    return null;
  }
  return Math.round(value / 1e6);
}

function totalTokens(result) {
  const promptTokens = result?.prompt_eval_count ?? 0;
  const answerTokens = result?.eval_count ?? 0;
  const total = promptTokens + answerTokens;
  return total > 0 ? total : null;
}

function showNotice(message, options = {}) {
  const title = options.title || "Aviso";
  const buttonLabel = options.buttonLabel || "OK";

  const existing = document.querySelector(".app-modal-backdrop");
  if (existing) {
    existing.remove();
  }

  const backdrop = document.createElement("div");
  backdrop.className = "app-modal-backdrop";

  const modal = document.createElement("div");
  modal.className = "app-modal";
  modal.setAttribute("role", "alertdialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "app-modal-title");
  modal.setAttribute("aria-describedby", "app-modal-message");

  const heading = document.createElement("h3");
  heading.id = "app-modal-title";
  heading.className = "app-modal-title";
  heading.textContent = title;

  const body = document.createElement("p");
  body.id = "app-modal-message";
  body.className = "app-modal-message";
  body.textContent = message;

  const actions = document.createElement("div");
  actions.className = "app-modal-actions";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "app-modal-button";
  button.textContent = buttonLabel;

  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", handleKeydown);
  };

  const handleKeydown = (event) => {
    if (event.key === "Escape" || event.key === "Enter") {
      close();
    }
  };

  button.addEventListener("click", close);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) {
      close();
    }
  });

  actions.appendChild(button);
  modal.append(heading, body, actions);
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);
  document.addEventListener("keydown", handleKeydown);
  button.focus();
}

function renderMath(container, content) {
  container.textContent = content;

  if (typeof window.renderMathInElement !== "function") {
    return;
  }

  window.renderMathInElement(container, {
    throwOnError: false,
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "\\[", right: "\\]", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\(", right: "\\)", display: false },
    ],
  });
}

function buildMessages(systemPrompt, prompt) {
  const messages = [];

  if (systemPrompt) {
    messages.push({ role: "system", content: systemPrompt });
  }

  messages.push({ role: "user", content: prompt });
  return messages;
}

async function init() {
  updateValueTag(elements.scoreGrounding, elements.valGrounding);
  updateValueTag(elements.scoreHelpfulness, elements.valHelpfulness);
  updateValueTag(elements.scoreFactuality, elements.valFactuality);

  elements.outputA.addEventListener("input", () => {
    state.isEditedA = true;
  });
  elements.outputB.addEventListener("input", () => {
    state.isEditedB = true;
  });

  elements.toggleDualPrompt.addEventListener("change", (e) => {
    const isDual = e.target.checked;
    elements.unifiedPromptGroup.style.display = isDual ? "none" : "block";
    elements.dualPromptGroup.style.display = isDual ? "block" : "none";
  });

  await Promise.all([pollHealth(), loadModels()]);
  renderEvaluationHistory();
}

async function pollHealth() {
  try {
    state.health = await fetchJson("/api/health");
  } catch (error) {
    console.warn("Health check failed.", error);
    state.health = { unreachable: true, error: error.message };
  }

  renderHealth();
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
  const ollamaReady = Boolean(ollama?.ready);
  const ollamaOk = Boolean(ollama?.ok);

  if (health?.unreachable) {
    elements.ollamaStatusTitle.textContent = "Backend Offline";
    elements.ollamaEndpoint.textContent = "URL: n/d";
    elements.ollamaSummary.textContent = health.error || "Erro ao conectar";
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

  elements.ollamaStatusTitle.textContent = ollamaReady
    ? "Ollama Ativa"
    : ollamaOk
      ? "Ollama (Sem Modelos)"
      : "Ollama Indisponivel";
  elements.ollamaEndpoint.textContent = `URL: ${ollama.url || "n/d"}`;

  const warnings = [];
  if (health.database === "unreachable") {
    warnings.push("Banco indisponivel");
  }
  if (!ollamaReady && health.error) {
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
    item.innerHTML = `
      <p><b>${model.name || "Sem nome"}</b></p>
      <p class="subtle">${model.details?.parameter_size || "n/d"}</p>
    `;
    elements.ollamaModelList.appendChild(item);
  }
}

function renderModelSelect(select, models) {
  select.innerHTML = "";

  if (!models.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Nenhum modelo disponivel";
    select.appendChild(option);
    return;
  }

  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.name;
    option.textContent = model.name;
    select.appendChild(option);
  }
}

async function loadModels() {
  try {
    const models = await fetchJson("/api/llm/models");
    state.models = Array.isArray(models) ? models : [];
  } catch (error) {
    console.error("Failed to load models:", error);
    state.models = [];
  }

  renderModelSelect(elements.modelSelectA, state.models);
  renderModelSelect(elements.modelSelectB, state.models);

  if (state.models.length > 1) {
    elements.modelSelectB.selectedIndex = 1;
  }

  elements.modelCount.textContent = `${state.models.length} modelos`;
}

function renderResult(key, response) {
  const result = response?.result || response || {};
  const textarea = key === "a" ? elements.outputA : elements.outputB;
  const outputContainer = key === "a" ? elements.outputRenderA : elements.outputRenderB;
  const latField = key === "a" ? elements.latA : elements.latB;
  const tokField = key === "a" ? elements.tokA : elements.tokB;
  const labelEl = key === "a" ? elements.labelA : elements.labelB;
  const cotContainer =
    key === "a"
      ? document.querySelector("#cot-container-a")
      : document.querySelector("#cot-container-b");

  const content = result.message?.content || "Resposta vazia.";
  textarea.value = content;
  renderMath(outputContainer, content);

  if (elements.toggleBlind.checked) {
    labelEl.textContent = `Modelo ${key.toUpperCase()} (Oculto)`;
    labelEl.classList.remove("revealed");
  } else {
    labelEl.textContent = key === "a" ? elements.modelSelectA.value : elements.modelSelectB.value;
  }

  const latency = nanosToMs(result.total_duration);
  latField.textContent = latency == null ? "n/d" : `${latency}ms`;

  const tokens = totalTokens(result);
  tokField.textContent = tokens == null ? "n/d" : String(tokens);

  const reasoning = result.message?.reasoning || result.message?.thinking;
  if (reasoning) {
    cotContainer.innerHTML = `
      <details class="cot-details">
        <summary>Cadeia de Pensamento</summary>
        <p>${reasoning}</p>
      </details>
    `;
  } else {
    cotContainer.innerHTML = "";
  }
}

function renderDiff() {
  if (!state.resultA || !state.resultB || typeof window.Diff === "undefined") {
    elements.diffPanel.style.display = "none";
    return;
  }

  const textA = state.resultA.message?.content || "";
  const textB = state.resultB.message?.content || "";

  const diff = window.Diff.diffWords(textA, textB);
  
  elements.diffOutput.innerHTML = "";
  const fragment = document.createDocumentFragment();

  diff.forEach((part) => {
    if (part.added) {
      const ins = document.createElement("ins");
      ins.textContent = part.value;
      fragment.appendChild(ins);
    } else if (part.removed) {
      const del = document.createElement("del");
      del.textContent = part.value;
      fragment.appendChild(del);
    } else {
      const span = document.createElement("span");
      span.textContent = part.value;
      fragment.appendChild(span);
    }
  });

  elements.diffOutput.appendChild(fragment);
  elements.diffPanel.style.display = "block";
}

function renderEvaluationHistory() {
  elements.evalHistory.innerHTML = "";

  if (!state.evaluations.length) {
    elements.evalHistory.innerHTML = '<p class="subtle">As ultimas 10 avaliacoes aparecerao aqui.</p>';
    return;
  }

  for (const evaluation of state.evaluations.slice(0, 10)) {
    const item = document.createElement("div");
    item.className = "history-item";
    item.innerHTML = `
      <p><b>${evaluation.studyLabel}</b></p>
      <p class="subtle">${evaluation.chosenLabel} venceu</p>
      <p class="subtle">${evaluation.rationale}</p>
    `;
    elements.evalHistory.appendChild(item);
  }
}

elements.sxsForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const systemPrompt = elements.systemPrompt.value.trim();
  const prompt = elements.userPrompt.value.trim();
  const seed = parseInt(elements.seed.value, 10);
  const temperature = parseFloat(elements.temperature.value);
  const modelA = elements.modelSelectA.value;
  const modelB = elements.modelSelectB.value;

  if (!prompt) {
    showNotice("Escreva um prompt antes de executar.");
    return;
  }

  if (!modelA || !modelB) {
    showNotice("Selecione os dois modelos antes de executar.");
    return;
  }

  state.isEditedA = false;
  state.isEditedB = false;
  state.resultA = null;
  state.resultB = null;
  elements.annotationPanel.style.display = "none";
  elements.outputA.value = "Gerando resposta...";
  elements.outputB.value = "Gerando resposta...";
  elements.outputRenderA.textContent = "Gerando resposta...";
  elements.outputRenderB.textContent = "Gerando resposta...";
  elements.latA.textContent = "...";
  elements.latB.textContent = "...";
  elements.tokA.textContent = "...";
  elements.tokB.textContent = "...";

  elements.sidebarRight.classList.add("collapsed");
  elements.workspace.classList.add("sxs-mode");
  elements.diffPanel.style.display = "none";
  setBusy(true);

  const isDual = elements.toggleDualPrompt.checked;

  const requestFor = (modelName, key) => {
    let sys = elements.systemPrompt.value.trim();
    let usr = elements.userPrompt.value.trim();

    if (isDual) {
      if (key === "a") {
        sys = elements.systemPromptA.value.trim();
        usr = elements.userPromptA.value.trim();
      } else {
        sys = elements.systemPromptB.value.trim();
        usr = elements.userPromptB.value.trim();
      }
    }

    return {
      messages: buildMessages(sys, usr),
      generation: {
        model_name: modelName,
        seed: Number.isNaN(seed) ? 7 : seed,
        temperature: Number.isNaN(temperature) ? 0 : temperature,
        top_p: 0.9,
        top_k: 40,
        repeat_penalty: 1.1,
        max_tokens: 512,
        chunk_size: 512,
        chunk_overlap: 0,
        corpus_version: "v1",
        prompt_template_version: "v1",
      },
      metadata: {
        source: "sxs",
        study_label: elements.studyLabel.value.trim() || "SxS Eval",
        blind_mode: elements.toggleBlind.checked,
      },
    };
  };

  try {
    const [resA, resB] = await Promise.all([
      fetchJson("/api/llm/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestFor(modelA, "a")),
      }),
      fetchJson("/api/llm/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestFor(modelB, "b")),
      }),
    ]);

    state.resultA = resA.result || resA;
    state.resultB = resB.result || resB;

    renderResult("a", resA);
    renderResult("b", resB);
    renderDiff();

    elements.annotationPanel.style.display = "flex";
    elements.annotationPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    elements.outputA.value = "";
    elements.outputB.value = "";
    elements.outputRenderA.textContent = "";
    elements.outputRenderB.textContent = "";
    showNotice(`Erro na comparacao: ${error.message}`, { title: "Falha" });
  } finally {
    setBusy(false);
  }
});

async function submitSelection(chosenKey) {
  if (!state.resultA || !state.resultB) {
    showNotice("Execute a comparacao antes de salvar a avaliacao.");
    return;
  }

  const rationale = elements.rationale.value.trim();
  if (!rationale) {
    showNotice("Preencha o rationale para justificar sua escolha.");
    return;
  }

  const chosen = chosenKey.toUpperCase();
  const scoreG = parseInt(elements.scoreGrounding.value, 10);
  const scoreH = parseInt(elements.scoreHelpfulness.value, 10);
  const scoreF = parseInt(elements.scoreFactuality.value, 10);
  const rejected = chosen === "A" ? "B" : "A";

  const isDual = elements.toggleDualPrompt.checked;

  const payload = {
    study_label: elements.studyLabel.value.trim() || "SxS Eval",
    prompt_original: isDual ? null : elements.userPrompt.value.trim(),
    system_prompt: isDual ? null : elements.systemPrompt.value.trim(),
    prompt_original_a: isDual ? elements.userPromptA.value.trim() : null,
    prompt_original_b: isDual ? elements.userPromptB.value.trim() : null,
    system_prompt_a: isDual ? elements.systemPromptA.value.trim() : null,
    system_prompt_b: isDual ? elements.systemPromptB.value.trim() : null,
    output_a: elements.outputA.value,
    output_b: elements.outputB.value,
    candidate_a_label: elements.modelSelectA.value,
    candidate_b_label: elements.modelSelectB.value,
    candidate_a_params: {
      temperature: parseFloat(elements.temperature.value),
      seed: parseInt(elements.seed.value, 10),
    },
    candidate_b_params: {
      temperature: parseFloat(elements.temperature.value),
      seed: parseInt(elements.seed.value, 10),
    },
    factuality: { a: chosen === "A" ? scoreF : 3, b: chosen === "B" ? scoreF : 3 },
    helpfulness: { a: chosen === "A" ? scoreH : 3, b: chosen === "B" ? scoreH : 3 },
    grounding: { a: chosen === "A" ? scoreG : 3, b: chosen === "B" ? scoreG : 3 },
    chosen,
    rejected,
    rationale,
    metadata: {
      is_edited_a: state.isEditedA,
      is_edited_b: state.isEditedB,
      latency_a_ms: nanosToMs(state.resultA.total_duration),
      latency_b_ms: nanosToMs(state.resultB.total_duration),
      tokens_a: totalTokens(state.resultA),
      tokens_b: totalTokens(state.resultB),
      blind_mode: elements.toggleBlind.checked,
    },
    tags: Array.from(document.querySelectorAll(".flag-chip input:checked")).map((input) => input.value),
  };

  // Reveal model names
  elements.labelA.textContent = elements.modelSelectA.value;
  elements.labelB.textContent = elements.modelSelectB.value;
  elements.labelA.classList.add("revealed");
  elements.labelB.classList.add("revealed");

  try {
    await fetchJson("/api/annotations/sxs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    state.evaluations.unshift({
      studyLabel: payload.study_label,
      chosenLabel: chosen === "A" ? payload.candidate_a_label : payload.candidate_b_label,
      rationale,
    });
    renderEvaluationHistory();

    showNotice("Avaliacao salva com sucesso.", { title: "Tudo certo" });
    resetForm();
  } catch (error) {
    showNotice(`Erro ao salvar avaliacao: ${error.message}`, { title: "Falha" });
  }
}

function resetForm() {
  elements.annotationPanel.style.display = "none";
  elements.rationale.value = "";
  elements.outputA.value = "";
  elements.outputB.value = "";
  elements.outputRenderA.textContent = "";
  elements.outputRenderB.textContent = "";
  elements.latA.textContent = "-";
  elements.latB.textContent = "-";
  elements.tokA.textContent = "-";
  elements.tokB.textContent = "-";
  elements.diffPanel.style.display = "none";
  elements.sidebarRight.classList.remove("collapsed");
  elements.labelA.classList.remove("revealed");
  elements.labelB.classList.remove("revealed");
  elements.labelA.textContent = "Modelo A";
  elements.labelB.textContent = "Modelo B";
}

elements.chooseA.addEventListener("click", () => submitSelection("a"));
elements.chooseB.addEventListener("click", () => submitSelection("b"));

init();
