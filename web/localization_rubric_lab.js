const REQUIRED_RUBRIC_FIELDS = [
  "Rubric_dimensions",
  "Rubric_title",
  "Rubrics_description",
  "Rubrics_weight",
  "is_response_specific",
];

const state = {
  templates: [],
  currentTemplate: null,
  cases: [],
  providers: [],
  models: [],
  selectedCaseId: null,
  lastGenerationMetadata: null,
  lastRawModelResponse: null,
};

const API_BASE =
  window.location.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://127.0.0.1:8765";

const elements = {
  localeSelect: document.querySelector("#locale-select"),
  categorySelect: document.querySelector("#category-select"),
  statusSelect: document.querySelector("#status-select"),
  rubricProviderSelect: document.querySelector("#rubric-provider-select"),
  rubricModelSelect: document.querySelector("#rubric-model-select"),
  tagsInput: document.querySelector("#tags-input"),
  loadTemplate: document.querySelector("#load-template"),
  newCase: document.querySelector("#new-case"),
  templateSummary: document.querySelector("#template-summary"),
  caseState: document.querySelector("#case-state"),
  caseCategory: document.querySelector("#case-category"),
  chatHistory: document.querySelector("#chat-history"),
  prompt: document.querySelector("#prompt"),
  responseRaw: document.querySelector("#response-raw"),
  goldenResponse: document.querySelector("#golden-response"),
  evaluatorNotes: document.querySelector("#evaluator-notes"),
  rubricsEditor: document.querySelector("#rubrics-editor"),
  jsonStatus: document.querySelector("#json-status"),
  validationOutput: document.querySelector("#validation-output"),
  generateRubrics: document.querySelector("#generate-rubrics"),
  aiWarning: document.querySelector("#ai-warning"),
  generationDiagnostics: document.querySelector("#generation-diagnostics"),
  rawModelResponse: document.querySelector("#raw-model-response"),
  saveCase: document.querySelector("#save-case"),
  markReviewed: document.querySelector("#mark-reviewed"),
  markApproved: document.querySelector("#mark-approved"),
  rubricHistory: document.querySelector("#rubric-history"),
  exportJsonl: document.querySelector("#export-jsonl"),
  exportCsv: document.querySelector("#export-csv"),
  exportOutput: document.querySelector("#export-output"),
};

async function fetchJson(path, options = {}) {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg).join(" | ")
      : payload.detail;
    throw new Error(payload.error || detail || "Erro inesperado.");
  }

  return payload;
}

function formatDate(value) {
  if (!value) {
    return "n/d";
  }
  try {
    return new Date(value).toLocaleString("pt-BR");
  } catch {
    return value;
  }
}

function setJsonStatus(kind, message) {
  elements.jsonStatus.classList.remove("ok", "offline", "warning");
  elements.jsonStatus.classList.add(kind);
  elements.jsonStatus.textContent = message;
}

function parseChatHistory() {
  const raw = elements.chatHistory.value.trim();
  if (!raw) {
    return [];
  }

  try {
    return JSON.parse(raw);
  } catch {
    return [{ role: "transcript", content: raw }];
  }
}

function parseTags() {
  return elements.tagsInput.value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function validateRubrics() {
  let rubrics;
  try {
    rubrics = JSON.parse(elements.rubricsEditor.value);
  } catch (error) {
    setJsonStatus("offline", "JSON inválido");
    return { ok: false, message: error.message, rubrics: null };
  }

  if (!Array.isArray(rubrics) || !rubrics.length) {
    setJsonStatus("offline", "Estrutura inválida");
    return {
      ok: false,
      message: "As rubrics devem ser uma lista JSON não vazia.",
      rubrics: null,
    };
  }

  const issues = [];
  rubrics.forEach((rubric, index) => {
    if (!rubric || typeof rubric !== "object" || Array.isArray(rubric)) {
      issues.push(`Item ${index + 1}: precisa ser um objeto.`);
      return;
    }

    const missing = REQUIRED_RUBRIC_FIELDS.filter((field) => !(field in rubric));
    if (missing.length) {
      issues.push(`Item ${index + 1}: faltam ${missing.join(", ")}.`);
    }
  });

  if (issues.length) {
    setJsonStatus("warning", "Campos faltando");
    return { ok: false, message: issues.join("\n"), rubrics };
  }

  setJsonStatus("ok", "JSON válido");
  return { ok: true, message: `${rubrics.length} rubrics válidas.`, rubrics };
}

function renderValidation() {
  const result = validateRubrics();
  elements.validationOutput.textContent = result.message;
  return result;
}

function renderTemplateSummary() {
  if (!state.currentTemplate) {
    elements.templateSummary.textContent = "Nenhum template carregado.";
    return;
  }

  elements.templateSummary.textContent =
    `${state.currentTemplate.template_name} | ${state.currentTemplate.locale} | ` +
    `${state.currentTemplate.category} | ${state.currentTemplate.rubrics.length} rubrics`;
}

function renderCaseState(record = null) {
  elements.caseState.innerHTML = "";
  const status = document.createElement("span");
  status.className = "metric";
  status.textContent = record
    ? `${record.status} | ${formatDate(record.updated_at)}`
    : "Novo draft";
  elements.caseState.appendChild(status);
}

function renderGenerationDiagnostics(metadata = null) {
  elements.generationDiagnostics.innerHTML = "";
  elements.generationDiagnostics.classList.remove("mismatch");

  if (!metadata) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhuma geração realizada.";
    elements.generationDiagnostics.appendChild(empty);
    return;
  }

  if (hasGenerationMismatch(metadata) || metadata.validation_status === "failed") {
    elements.generationDiagnostics.classList.add("mismatch");
    const alert = document.createElement("div");
    alert.className = "diagnostic-alert";
    alert.textContent = hasGenerationMismatch(metadata)
      ? "Alerta: modelo/provider usado difere do solicitado. Reviewed e Approved ficam bloqueados."
      : "Alerta: a resposta do modelo falhou na validação. Reviewed e Approved ficam bloqueados.";
    elements.generationDiagnostics.appendChild(alert);
  }

  const fields = [
    "provider_requested",
    "model_requested",
    "provider_used",
    "model_used",
    "exact_url_called",
    "response_status",
    "generation_duration_ms",
    "approx_prompt_tokens",
    "approx_response_tokens",
    "response_char_count",
    "generation_timestamp",
    "validation_status",
    "validation_error",
  ];

  for (const field of fields) {
    const item = document.createElement("div");
    item.className = "diagnostic-item";

    const label = document.createElement("span");
    label.textContent = field;

    const value = document.createElement("strong");
    value.textContent = metadata[field] ?? "n/d";

    item.append(label, value);
    elements.generationDiagnostics.appendChild(item);
  }
}

function renderRawModelResponse(raw = null) {
  elements.rawModelResponse.textContent = raw || "Nenhuma resposta bruta registrada.";
}

function hasGenerationMismatch(metadata) {
  const requestedProvider = metadata?.provider_requested;
  const requestedModel = metadata?.model_requested;
  const usedProvider = metadata?.provider_used;
  const usedModel = metadata?.model_used;

  return Boolean(
    (requestedProvider && requestedProvider !== usedProvider) ||
      (requestedModel && requestedModel !== usedModel),
  );
}

function assertGenerationMatch(metadata) {
  const requestedProvider = metadata?.provider_requested;
  const requestedModel = metadata?.model_requested;
  const usedProvider = metadata?.provider_used;
  const usedModel = metadata?.model_used;

  if (requestedProvider && requestedProvider !== usedProvider) {
    throw new Error(
      `Provider usado (${usedProvider}) difere do solicitado (${requestedProvider}).`,
    );
  }

  if (requestedModel && requestedModel !== usedModel) {
    throw new Error(`Modelo usado (${usedModel}) difere do solicitado (${requestedModel}).`);
  }
}

function assertCanUseStatus(status) {
  const validationStatus = state.lastGenerationMetadata?.validation_status;
  if (
    (status === "reviewed" || status === "approved") &&
    (hasGenerationMismatch(state.lastGenerationMetadata) || validationStatus === "failed")
  ) {
    throw new Error(
      `Status ${status} bloqueado: geração por IA divergente ou inválida.`,
    );
  }
}

function fillCase(record) {
  state.selectedCaseId = record?.id || null;
  elements.localeSelect.value = record?.locale || elements.localeSelect.value;
  elements.categorySelect.value = record?.category || elements.categorySelect.value;
  elements.statusSelect.value = record?.status || "draft";
  elements.caseCategory.value = record?.category || elements.categorySelect.value;
  elements.chatHistory.value = record?.chat_history
    ? JSON.stringify(record.chat_history, null, 2)
    : "";
  elements.prompt.value = record?.prompt || "";
  elements.responseRaw.value = record?.response_raw || "";
  elements.goldenResponse.value = record?.golden_response || "";
  elements.evaluatorNotes.value = record?.evaluator_notes || "";
  elements.tagsInput.value = Array.isArray(record?.tags) ? record.tags.join(", ") : "";
  state.lastGenerationMetadata = record?.metadata?.rubric_generation || null;
  state.lastRawModelResponse = record?.metadata?.raw_model_response || null;
  renderGenerationDiagnostics(state.lastGenerationMetadata);
  renderRawModelResponse(state.lastRawModelResponse);
  elements.rubricsEditor.value = record?.rubrics
    ? JSON.stringify(record.rubrics, null, 2)
    : elements.rubricsEditor.value;
  renderCaseState(record);
  renderValidation();
}

function resetCase() {
  state.selectedCaseId = null;
  elements.statusSelect.value = "draft";
  elements.caseCategory.value = elements.categorySelect.value;
  elements.chatHistory.value = "";
  elements.prompt.value = "";
  elements.responseRaw.value = "";
  elements.goldenResponse.value = "";
  elements.evaluatorNotes.value = "";
  elements.tagsInput.value = "";
  state.lastGenerationMetadata = null;
  state.lastRawModelResponse = null;
  renderGenerationDiagnostics();
  renderRawModelResponse();
  if (state.currentTemplate) {
    elements.rubricsEditor.value = JSON.stringify(state.currentTemplate.rubrics, null, 2);
  }
  renderCaseState();
  renderValidation();
}

function buildPayload(statusOverride = null) {
  const validation = renderValidation();
  if (!validation.ok) {
    throw new Error("Corrija o JSON de rubrics antes de salvar.");
  }
  const status = statusOverride || elements.statusSelect.value;
  assertCanUseStatus(status);

  return {
    locale: elements.localeSelect.value,
    category: elements.categorySelect.value,
    chat_history: parseChatHistory(),
    prompt: elements.prompt.value.trim() || null,
    response_raw: elements.responseRaw.value.trim() || null,
    golden_response: elements.goldenResponse.value.trim() || null,
    evaluator_notes: elements.evaluatorNotes.value.trim() || null,
    template_name: state.currentTemplate?.template_name || `${elements.categorySelect.value.toLowerCase()}_template.json`,
    template_version: state.currentTemplate?.template_version || "v1",
    rubrics: validation.rubrics,
    status,
    tags: parseTags(),
    metadata: {
      source: "localization_rubric_lab",
      prepared_for_llm_generation: true,
      rubric_generation: state.lastGenerationMetadata,
      raw_model_response: state.lastRawModelResponse,
    },
  };
}

async function loadTemplates() {
  state.templates = await fetchJson("/api/localization/templates").catch(() => []);
}

async function loadProviders() {
  try {
    const providers = await fetchJson("/api/localization/providers");
    state.providers = Array.isArray(providers) ? providers : [];
  } catch {
    state.providers = [];
  }

  renderProviderSelect();
  await loadProviderModels();
}

function renderProviderSelect() {
  elements.rubricProviderSelect.innerHTML = "";

  if (!state.providers.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Fallback do backend";
    elements.rubricProviderSelect.appendChild(option);
    return;
  }

  for (const provider of state.providers) {
    const option = document.createElement("option");
    option.value = provider.name;
    option.textContent = provider.implemented
      ? provider.label || provider.name
      : `${provider.label || provider.name} (em breve)`;
    elements.rubricProviderSelect.appendChild(option);
  }
}

async function loadProviderModels() {
  const provider = elements.rubricProviderSelect.value;
  if (!provider) {
    state.models = [];
    renderModelSelect();
    return;
  }

  try {
    const models = await fetchJson(`/api/localization/providers/${provider}/models`);
    state.models = Array.isArray(models) ? models : [];
  } catch {
    state.models = [];
  }

  renderModelSelect();
}

function renderModelSelect() {
  elements.rubricModelSelect.innerHTML = "";

  if (!state.models.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Fallback do provider";
    elements.rubricModelSelect.appendChild(option);
    return;
  }

  for (const model of state.models) {
    const option = document.createElement("option");
    option.value = model.name;
    option.textContent = model.name;
    elements.rubricModelSelect.appendChild(option);
  }

  const defaultModel = state.models.find((model) => model.default);
  if (defaultModel) {
    elements.rubricModelSelect.value = defaultModel.name;
  }
}

async function loadTemplate() {
  const locale = elements.localeSelect.value;
  const category = elements.categorySelect.value;
  state.currentTemplate = await fetchJson(`/api/localization/templates/${locale}/${category}`);
  elements.caseCategory.value = category;
  elements.rubricsEditor.value = JSON.stringify(state.currentTemplate.rubrics, null, 2);
  renderTemplateSummary();
  renderValidation();
}

async function loadCases() {
  const query = new URLSearchParams({
    locale: elements.localeSelect.value,
    limit: "100",
  });
  const cases = await fetchJson(`/api/localization/rubric-cases?${query.toString()}`).catch(() => []);
  state.cases = Array.isArray(cases) ? cases : [];
  renderHistory();
}

function renderHistory() {
  elements.rubricHistory.innerHTML = "";

  if (!state.cases.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhuma rubric salva ainda.";
    elements.rubricHistory.appendChild(empty);
    return;
  }

  for (const record of state.cases) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "history-item";
    if (record.id === state.selectedCaseId) {
      item.classList.add("active");
    }

    const title = document.createElement("strong");
    title.textContent = `${record.category} | ${record.status}`;

    const meta = document.createElement("div");
    meta.className = "history-meta";
    meta.textContent = `${record.template_name} | ${formatDate(record.updated_at)}`;

    const prompt = document.createElement("div");
    prompt.className = "history-meta";
    prompt.textContent = record.prompt || "Sem prompt";

    item.append(title, meta, prompt);
    item.addEventListener("click", async () => {
      const full = await fetchJson(`/api/localization/rubric-cases/${record.id}`);
      fillCase(full);
      renderHistory();
    });
    elements.rubricHistory.appendChild(item);
  }
}

async function saveCase(statusOverride = null) {
  const payload = buildPayload(statusOverride);
  const path = state.selectedCaseId
    ? `/api/localization/rubric-cases/${state.selectedCaseId}`
    : "/api/localization/rubric-cases";
  const method = state.selectedCaseId ? "PATCH" : "POST";

  const response = await fetchJson(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const record = response.rubric_case || response;
  fillCase(record);
  await loadCases();
}

async function generateRubrics() {
  if (!state.currentTemplate) {
    await loadTemplate();
  }

  const validation = renderValidation();
  const baseTemplate = state.currentTemplate?.rubrics || validation.rubrics;
  if (!baseTemplate) {
    throw new Error("Carregue um template válido antes de gerar rubrics.");
  }

  elements.generateRubrics.disabled = true;
  elements.generateRubrics.textContent = "Gerando...";
  elements.aiWarning.textContent = "Gerando rubrics via IA. Revise antes de aprovar.";

  try {
    const result = await fetchJson("/api/localization/rubrics/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        locale: elements.localeSelect.value,
        category: elements.categorySelect.value,
        chat_history: parseChatHistory(),
        prompt: elements.prompt.value.trim() || null,
        response_raw: elements.responseRaw.value.trim() || null,
        golden_response: elements.goldenResponse.value.trim() || null,
        base_template: baseTemplate,
        provider: elements.rubricProviderSelect.value || undefined,
        model: elements.rubricModelSelect.value || null,
      }),
    });

    state.lastGenerationMetadata = {
      ...(result.metadata || {}),
      template_used: state.currentTemplate?.template_name || result.metadata?.template_used,
    };
    state.lastRawModelResponse = result.raw_model_response || null;
    renderGenerationDiagnostics(state.lastGenerationMetadata);
    renderRawModelResponse(state.lastRawModelResponse);
    assertGenerationMatch(state.lastGenerationMetadata);

    if (!result.success) {
      elements.aiWarning.textContent =
        result.warning || result.error || "A geração falhou na validação.";
      elements.validationOutput.textContent =
        result.error || "A resposta do modelo não passou na validação.";
      return;
    }

    elements.rubricsEditor.value = JSON.stringify(result.rubrics, null, 2);
    elements.statusSelect.value = "draft";
    elements.aiWarning.textContent =
      result.warning || "Rubrics geradas por IA devem ser revisadas antes da aprovação.";
    renderValidation();
  } finally {
    elements.generateRubrics.disabled = false;
    elements.generateRubrics.textContent = "Gerar rubrics com IA";
  }
}

async function exportCases(format) {
  const endpoint =
    format === "csv"
      ? "/api/localization/rubric-cases/export-csv"
      : "/api/localization/rubric-cases/export-jsonl";
  const result = await fetchJson(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      locale: elements.localeSelect.value,
      limit: 5000,
    }),
  });
  elements.exportOutput.textContent = JSON.stringify(result, null, 2);
  await loadCases();
}

elements.loadTemplate.addEventListener("click", () => {
  loadTemplate().catch((error) => {
    elements.templateSummary.textContent = error.message;
  });
});

elements.newCase.addEventListener("click", resetCase);
elements.rubricsEditor.addEventListener("input", renderValidation);
elements.categorySelect.addEventListener("change", () => {
  loadTemplate().catch((error) => {
    elements.templateSummary.textContent = error.message;
  });
});

elements.rubricProviderSelect.addEventListener("change", () => {
  loadProviderModels().catch((error) => {
    elements.aiWarning.textContent = error.message;
  });
});

elements.saveCase.addEventListener("click", () => {
  saveCase().catch((error) => {
    elements.validationOutput.textContent = error.message;
  });
});

elements.generateRubrics.addEventListener("click", () => {
  generateRubrics().catch((error) => {
    elements.aiWarning.textContent = error.message;
  });
});

elements.markReviewed.addEventListener("click", () => {
  saveCase("reviewed").catch((error) => {
    elements.validationOutput.textContent = error.message;
  });
});

elements.markApproved.addEventListener("click", () => {
  saveCase("approved").catch((error) => {
    elements.validationOutput.textContent = error.message;
  });
});

elements.exportJsonl.addEventListener("click", () => {
  exportCases("jsonl").catch((error) => {
    elements.exportOutput.textContent = error.message;
  });
});

elements.exportCsv.addEventListener("click", () => {
  exportCases("csv").catch((error) => {
    elements.exportOutput.textContent = error.message;
  });
});

async function init() {
  await Promise.all([loadTemplates(), loadProviders()]);
  await loadTemplate();
  await loadCases();
  resetCase();
}

init().catch((error) => {
  elements.validationOutput.textContent = error.message;
});
