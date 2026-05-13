const REQUIRED_RUBRIC_FIELDS = [
  "Rubric_dimensions",
  "Rubric_title",
  "Rubrics_description",
  "Rubrics_weight",
  "is_response_specific",
];

const ACCEPTED_RUBRIC_DIMENSIONS = new Set([
  "Cultural Understanding and Application",
  "Local Facts and Awareness",
  "Logic and Formatting",
  "Natural Language Fluency",
]);

const state = {
  templates: [],
  currentTemplate: null,
  cases: [],
  providers: [],
  models: [],
  selectedCaseId: null,
  lastGenerationMetadata: null,
  lastRawModelResponse: null,
  humanQualityReviewed: false,
  lastValidationReport: null,
  backendValidationRequestId: 0,
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
  rubricCards: document.querySelector("#rubric-cards"),
  jsonStatus: document.querySelector("#json-status"),
  editorStateSummary: document.querySelector("#editor-state-summary"),
  validationOutput: document.querySelector("#validation-output"),
  validationLayers: document.querySelector("#validation-layers"),
  qualityHeuristics: document.querySelector("#quality-heuristics"),
  qualityHeuristicsStatus: document.querySelector("#quality-heuristics-status"),
  qualityHeuristicsMessage: document.querySelector("#quality-heuristics-message"),
  qualityHeuristicsMessages: document.querySelector("#quality-heuristics-messages"),
  qualityHeuristicsSignals: document.querySelector("#quality-heuristics-signals"),
  qualityHeuristicsSignalList: document.querySelector("#quality-heuristics-signal-list"),
  generateRubrics: document.querySelector("#generate-rubrics"),
  copyJson: document.querySelector("#copy-json"),
  aiWarning: document.querySelector("#ai-warning"),
  nextStep: document.querySelector("#next-step"),
  generationSummary: document.querySelector("#generation-summary"),
  generationDiagnostics: document.querySelector("#generation-diagnostics"),
  rawModelResponse: document.querySelector("#raw-model-response"),
  rawModelNote: document.querySelector("#raw-model-note"),
  saveCase: document.querySelector("#save-case"),
  markReviewed: document.querySelector("#mark-reviewed"),
  markApproved: document.querySelector("#mark-approved"),
  rubricHistory: document.querySelector("#rubric-history"),
  exportJsonl: document.querySelector("#export-jsonl"),
  exportCsv: document.querySelector("#export-csv"),
  exportOutput: document.querySelector("#export-output"),
  toast: document.querySelector("#toast"),
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
  elements.jsonStatus.classList.remove("ok", "offline", "warning", "neutral");
  elements.jsonStatus.classList.add(kind);
  elements.jsonStatus.textContent = message;
}

function setStateSummary(element, kind, title, message) {
  element.classList.remove("ok", "offline", "warning", "neutral");
  element.classList.add(kind);
  element.innerHTML = "";

  const strong = document.createElement("strong");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = message;
  element.append(strong, span);
}

function showToast(message, kind = "neutral") {
  elements.toast.className = `toast show ${kind}`;
  elements.toast.textContent = message;
  clearTimeout(showToast.timeoutId);
  showToast.timeoutId = setTimeout(() => {
    elements.toast.className = "toast";
  }, 2800);
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

function renderTemplateSummary() {
  if (!state.currentTemplate) {
    elements.templateSummary.textContent = "Nenhum template carregado.";
    return;
  }

  elements.templateSummary.textContent =
    `${state.currentTemplate.template_name} | ${state.currentTemplate.locale} | ` +
    `${state.currentTemplate.category} | ${state.currentTemplate.rubrics.length} slots de scaffold. ` +
    "Template carregado; preencha o caso real e revise antes de aprovar.";
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
    setStateSummary(
      elements.generationSummary,
      "neutral",
      "Nenhuma geracao executada",
      "A IA ainda nao foi chamada para este caso.",
    );
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhuma geração realizada.";
    elements.generationDiagnostics.appendChild(empty);
    return;
  }

  renderGenerationSummary(metadata);

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
    "model_to_call",
    "default_model_used",
    "fallback_applied",
    "model_allowed_by_backend",
    "exact_url_called",
    "response_status",
    "generation_duration_ms",
    "approx_prompt_tokens",
    "approx_response_tokens",
    "response_char_count",
    "generation_timestamp",
    "validation_status",
    "validation_error",
    "result_discarded",
    "blocked_reason",
    "raw_error"
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
  if (!raw) {
    elements.rawModelNote.textContent = "Nenhuma resposta bruta registrada.";
    return;
  }
  if (state.lastGenerationMetadata?.validation_status === "failed") {
    elements.rawModelNote.textContent =
      "Resposta bruta preservada apenas para auditoria. Nao foi aplicada como rubrics validas.";
    return;
  }
  elements.rawModelNote.textContent =
    "Resposta bruta preservada para auditoria. O JSON do editor deve ser revisado separadamente.";
}

function renderGenerationSummary(metadata) {
  if (metadata.generation_state === "stale" || metadata.validation_status === "stale") {
    setStateSummary(
      elements.generationSummary,
      "warning",
      "Geracao stale",
      "O caso foi alterado depois da ultima geracao. Gere novamente ou revise manualmente.",
    );
    return;
  }

  if (metadata.generation_executed === false) {
    setStateSummary(
      elements.generationSummary,
      "neutral",
      "Nenhuma geracao executada",
      metadata.workflow_decision?.message || "O workflow decidiu nao chamar o modelo.",
    );
    return;
  }

  if (metadata.raw_error || metadata.workflow_decision?.decision === "generation_failed") {
    setStateSummary(
      elements.generationSummary,
      "offline",
      "Geracao falhou",
      metadata.raw_error || metadata.workflow_decision?.message || "A chamada ao provider falhou.",
    );
    return;
  }

  if (metadata.validation_status === "failed" || metadata.result_discarded === true) {
    setStateSummary(
      elements.generationSummary,
      "offline",
      "Resultado nao aplicado",
      "Geracao executada, mas o resultado falhou na validacao ou foi descartado.",
    );
    return;
  }

  setStateSummary(
    elements.generationSummary,
    "ok",
    "Geracao executada",
    `Provider: ${metadata.provider_used || "n/d"} | Modelo: ${metadata.model_used || "n/d"} | Fallback: ${
      metadata.fallback_applied === true ? "sim" : "nao"
    }`,
  );
}

function hasGenerationMismatch(metadata) {
  return metadata?.fallback_applied === true || metadata?.result_discarded === true;
}

function assertGenerationMatch(metadata) {
  if (metadata?.fallback_applied === true || metadata?.result_discarded === true) {
    throw new Error(
      metadata?.blocked_reason || "Geração bloqueada por fallback ou erro de validação de modelo/provider."
    );
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
  state.humanQualityReviewed = Boolean(record?.metadata?.human_quality_reviewed);
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
  state.humanQualityReviewed = false;
  renderGenerationDiagnostics();
  renderRawModelResponse();
  elements.rubricsEditor.value = "[]";
  renderCaseState();
  renderValidation();
}

function buildPayload(statusOverride = null) {
  if (statusOverride === "reviewed") {
    state.humanQualityReviewed = true;
  }
  const validation = renderValidation();
  const status = statusOverride || elements.statusSelect.value;
  if (!validation.ok && (status !== "draft" || validation.rubrics === null)) {
    throw new Error("Corrija o JSON de rubrics antes de salvar.");
  }
  assertCanUseStatus(status);
  const caseDataReadyForGeneration = requiredCaseFieldsMissing().length === 0;

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
    rubrics: validation.rubrics || [],
    status,
    tags: parseTags(),
    metadata: {
      source: "localization_rubric_lab",
      case_data_ready_for_generation: caseDataReadyForGeneration,
      rubric_source: validation.rubrics?.length ? "editor_draft" : "empty_draft",
      template_scaffold: state.currentTemplate
        ? {
            template_name: state.currentTemplate.template_name,
            template_version: state.currentTemplate.template_version,
            category: state.currentTemplate.category,
            scaffold_slots: state.currentTemplate.rubrics?.length || 0,
          }
        : null,
      human_quality_reviewed: state.humanQualityReviewed,
      validation_report: validation.report,
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
  state.lastGenerationMetadata = null;
  state.lastRawModelResponse = null;
  state.humanQualityReviewed = false;
  state.lastValidationReport = null;
  renderGenerationDiagnostics();
  renderRawModelResponse();
  renderTemplateSummary();
  renderValidation();
  elements.validationOutput.textContent =
    "Template carregado como scaffold. O editor de rubrics nao foi preenchido automaticamente; use o scaffold apenas como referencia.";
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
  elements.generateRubrics.classList.add("generating");
  elements.generateRubrics.setAttribute("aria-busy", "true");
  elements.generateRubrics.textContent = "Gerando rubrics...";
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
    try {
      assertGenerationMatch(state.lastGenerationMetadata);
    } catch (e) {
      elements.aiWarning.textContent = e.message;
      elements.validationOutput.textContent = e.message;
      return;
    }

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
    elements.generateRubrics.classList.remove("generating");
    elements.generateRubrics.removeAttribute("aria-busy");
    elements.generateRubrics.textContent = "Gerar com IA";
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

async function copyEditorJson() {
  const text = elements.rubricsEditor.value;
  let validJson = true;
  try {
    JSON.parse(text);
  } catch {
    validJson = false;
  }

  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
  } else {
    elements.rubricsEditor.focus();
    elements.rubricsEditor.select();
    document.execCommand("copy");
  }

  const message = validJson
    ? "JSON copiado."
    : "Texto copiado. Atencao: nao e JSON valido.";
  showToast(message, validJson ? "ok" : "warning");
}

function validateRubrics() {
  let rubrics;
  try {
    rubrics = elements.rubricsEditor.value.trim()
      ? JSON.parse(elements.rubricsEditor.value)
      : [];
  } catch (error) {
    const report = {
      structureValidation: layer("fail", error.message, true, { count: 0 }),
      formatValidation: layer("pending", "Formato pendente ate a estrutura passar.", true),
      qualityValidation: layer("pending", "Qualidade pendente ate estrutura e formato passarem.", true),
      approvalReadiness: layer("blocked", "Aprovacao bloqueada: camadas pendentes ou falhando.", true),
    };
    setJsonStatus("offline", "JSON invalido");
    return { ok: false, message: error.message, rubrics: null, report };
  }

  const structureValidation = validateStructure(rubrics);
  const formatValidation = validateFormat(rubrics, structureValidation);
  const qualityValidation = validateQuality(structureValidation, formatValidation);
  const approvalReadiness = validateApprovalReadiness(
    structureValidation,
    formatValidation,
    qualityValidation,
  );
  const report = {
    structureValidation,
    formatValidation,
    qualityValidation,
    approvalReadiness,
  };

  if (structureValidation.status === "empty") {
    setJsonStatus("neutral", "Draft vazio");
  } else if (approvalReadiness.status === "pass") {
    setJsonStatus("ok", "Aprovacao pronta");
  } else if (formatValidation.status === "fail") {
    setJsonStatus("offline", "Formato invalido");
  } else if (formatValidation.status === "pass") {
    setJsonStatus("warning", "Qualidade pendente");
  } else if (structureValidation.status === "pass") {
    setJsonStatus("warning", "Formato pendente");
  } else {
    setJsonStatus("offline", "Estrutura invalida");
  }

  return {
    ok: structureValidation.status === "pass",
    message: structureValidation.message,
    rubrics: Array.isArray(rubrics) ? rubrics : null,
    report,
  };
}

function validateStructure(rubrics) {
  if (!Array.isArray(rubrics)) {
    return layer("fail", "Estrutura invalida: o JSON de rubrics precisa ser uma lista.", true, {
      count: 0,
    });
  }

  if (!rubrics.length) {
    return layer("empty", "Nenhuma rubric real no editor. Preencha o caso e gere rubrics, ou escreva/copie rubrics manualmente.", true, {
      count: 0,
    });
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
    return layer("fail", issues.join("\n"), true, { count: rubrics.length });
  }

  return layer("pass", `${rubrics.length} rubrics encontradas. Campos obrigatorios presentes.`, false, {
    count: rubrics.length,
  });
}

function validateFormat(rubrics, structureValidation) {
  if (structureValidation.status !== "pass") {
    return layer("pending", "Formato pendente ate a estrutura passar.", true);
  }

  const issues = [];
  rubrics.forEach((rubric, index) => {
    const dimension = rubric.Rubric_dimensions;
    if (typeof dimension !== "string" || !dimension.trim()) {
      issues.push(`Item ${index + 1}: Rubric_dimensions deve ser texto.`);
    } else if (!ACCEPTED_RUBRIC_DIMENSIONS.has(dimension)) {
      issues.push(`Item ${index + 1}: Rubric_dimensions nao aceito.`);
    }

    const title = rubric.Rubric_title;
    if (typeof title !== "string" || !title.trim()) {
      issues.push(`Item ${index + 1}: Rubric_title deve ser texto.`);
    } else if (title.trim().length > 120) {
      issues.push(`Item ${index + 1}: Rubric_title deve ser curto e claro.`);
    }

    const description = rubric.Rubrics_description;
    if (typeof description !== "string" || !description.trim()) {
      issues.push(`Item ${index + 1}: Rubrics_description deve ser texto.`);
    } else if (description.trim().length < 20) {
      issues.push(`Item ${index + 1}: Rubrics_description curta demais para avaliar.`);
    }

    const weight = rubric.Rubrics_weight;
    if (typeof weight !== "number" || Number.isNaN(weight)) {
      issues.push(`Item ${index + 1}: Rubrics_weight deve ser numerico.`);
    } else if (weight < -5 || weight > 10 || weight === 0) {
      issues.push(`Item ${index + 1}: Rubrics_weight fora da escala configurada.`);
    }

    if (typeof rubric.is_response_specific !== "boolean") {
      issues.push(`Item ${index + 1}: is_response_specific deve ser true ou false.`);
    }
  });

  if (issues.length) {
    return layer("fail", issues.join("\n"), true, { count: rubrics.length });
  }

  return layer("pass", "Estrutura e formato OK. Qualidade ainda nao avaliada.", false, {
    count: rubrics.length,
  });
}

function validateQuality(structureValidation, formatValidation) {
  if (structureValidation.status !== "pass" || formatValidation.status !== "pass") {
    return layer("pending", "Qualidade pendente ate estrutura e formato passarem.", true);
  }

  if (state.humanQualityReviewed) {
    return layer("pass", "Qualidade marcada como revisada por avaliador humano.");
  }

  return layer(
    "pending",
    "Qualidade pendente: revise atomicidade, cobertura, pesos, relevancia e is_response_specific.",
    true,
  );
}

function validateApprovalReadiness(structureValidation, formatValidation, qualityValidation) {
  const missing = requiredCaseFieldsMissing();
  if (missing.length) {
    return layer("blocked", `Aprovacao bloqueada: faltam ${missing.join(", ")}.`, true, {
      missing_fields: missing,
    });
  }

  if (
    structureValidation.status !== "pass" ||
    formatValidation.status !== "pass" ||
    qualityValidation.status !== "pass"
  ) {
    return layer("blocked", "Aprovacao bloqueada: camadas pendentes ou falhando.", true);
  }

  return layer("pass", "Rubrics prontas para aprovacao.");
}

function requiredCaseFieldsMissing() {
  const fields = [
    ["locale", elements.localeSelect.value],
    ["category", elements.categorySelect.value],
    ["prompt", elements.prompt.value],
    ["response_raw", elements.responseRaw.value],
    ["golden_response", elements.goldenResponse.value],
  ];
  return fields.filter(([, value]) => !String(value || "").trim()).map(([field]) => field);
}

function layer(status, message, blocking = false, extra = {}) {
  return { status, message, blocking, ...extra };
}

function renderValidation() {
  const result = validateRubrics();
  elements.validationOutput.textContent = result.message;
  state.lastValidationReport = result.report;
  renderEditorState(result);
  renderRubricCards(result.rubrics);
  renderValidationLayers(result.report);
  renderQualityHeuristics(result.report?.qualityHeuristics);
  requestBackendQualityHeuristics(result);
  updateActionStates(result.report);
  return result;
}

function requestBackendQualityHeuristics(result) {
  const requestId = ++state.backendValidationRequestId;
  const structureOk = result.report?.structureValidation?.status === "pass";
  const formatOk = result.report?.formatValidation?.status === "pass";

  if (!Array.isArray(result.rubrics) || !structureOk || !formatOk) {
    renderQualityHeuristics({
      status: "pending",
      blocking: false,
      messages: ["Quality heuristics pending until structure and format pass."],
      signals: {
        rubric_count: Array.isArray(result.rubrics) ? result.rubrics.length : 0,
      },
    });
    return;
  }

  fetchJson("/api/localization/rubrics/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      locale: elements.localeSelect.value,
      category: elements.categorySelect.value,
      prompt: elements.prompt.value.trim() || null,
      response_raw: elements.responseRaw.value.trim() || null,
      golden_response: elements.goldenResponse.value.trim() || null,
      rubrics: result.rubrics,
      metadata: {
        human_quality_reviewed: state.humanQualityReviewed,
      },
    }),
  })
    .then((report) => {
      if (requestId !== state.backendValidationRequestId) {
        return;
      }
      state.lastValidationReport = {
        ...state.lastValidationReport,
        qualityHeuristics: report.qualityHeuristics,
      };
      renderQualityHeuristics(report.qualityHeuristics);
    })
    .catch(() => {
      if (requestId !== state.backendValidationRequestId) {
        return;
      }
      renderQualityHeuristics();
    });
}

function renderRubricCards(rubrics) {
  elements.rubricCards.innerHTML = "";

  if (!Array.isArray(rubrics)) {
    const empty = document.createElement("div");
    empty.className = "empty-state compact";
    empty.textContent = "Sem cards: o JSON precisa ser uma lista de rubrics.";
    elements.rubricCards.appendChild(empty);
    return;
  }

  if (!rubrics.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state compact";
    empty.textContent = "Nenhuma rubric real no editor.";
    elements.rubricCards.appendChild(empty);
    return;
  }

  for (const [index, rubric] of rubrics.entries()) {
    const issues = rubricIssues(rubric);
    const card = document.createElement("article");
    card.className = `rubric-card ${issues.length ? "has-issues" : "ok"}`;

    const header = document.createElement("div");
    header.className = "rubric-card-header";

    const titleBox = document.createElement("div");
    const dimension = document.createElement("span");
    dimension.className = "rubric-dimension";
    dimension.textContent = rubric?.Rubric_dimensions || "Dimensao ausente";
    const title = document.createElement("h3");
    title.textContent = rubric?.Rubric_title || `Rubric ${index + 1}`;
    titleBox.append(dimension, title);

    const weight = document.createElement("div");
    weight.className = "rubric-weight";
    weight.textContent = `Peso ${rubric?.Rubrics_weight ?? "n/d"}`;
    header.append(titleBox, weight);

    const description = document.createElement("p");
    description.className = "rubric-description";
    description.textContent = rubric?.Rubrics_description || "Descricao ausente.";

    const meta = document.createElement("div");
    meta.className = "rubric-card-meta";
    const specific = document.createElement("span");
    specific.textContent = rubric?.is_response_specific === true ? "response-specific" : "universal";
    const status = document.createElement("span");
    status.textContent = issues.length ? "problemas detectados" : "estrutura OK";
    meta.append(specific, status);

    card.append(header, description, meta);
    if (issues.length) {
      const list = document.createElement("ul");
      list.className = "rubric-issues";
      for (const issue of issues) {
        const item = document.createElement("li");
        item.textContent = issue;
        list.appendChild(item);
      }
      card.appendChild(list);
    }

    elements.rubricCards.appendChild(card);
  }
}

function rubricIssues(rubric) {
  const issues = [];
  if (!rubric || typeof rubric !== "object" || Array.isArray(rubric)) {
    return ["Item precisa ser um objeto."];
  }
  const missing = REQUIRED_RUBRIC_FIELDS.filter((field) => !(field in rubric));
  if (missing.length) {
    issues.push(`Campos faltando: ${missing.join(", ")}.`);
  }
  if (!ACCEPTED_RUBRIC_DIMENSIONS.has(rubric.Rubric_dimensions)) {
    issues.push("Dimensao nao aceita.");
  }
  if (typeof rubric.Rubric_title !== "string" || !rubric.Rubric_title.trim()) {
    issues.push("Titulo ausente.");
  }
  if (typeof rubric.Rubrics_description !== "string" || rubric.Rubrics_description.trim().length < 20) {
    issues.push("Descricao curta ou ausente.");
  }
  if (
    typeof rubric.Rubrics_weight !== "number" ||
    Number.isNaN(rubric.Rubrics_weight) ||
    rubric.Rubrics_weight < -5 ||
    rubric.Rubrics_weight > 10 ||
    rubric.Rubrics_weight === 0
  ) {
    issues.push("Peso fora da escala.");
  }
  if (typeof rubric.is_response_specific !== "boolean") {
    issues.push("is_response_specific precisa ser booleano.");
  }
  return issues;
}

function renderEditorState(result) {
  const report = result.report;
  let kind = "neutral";
  let title = "Aguardando rubrics";
  let message = result.message;

  if (result.rubrics === null) {
    kind = "offline";
    title = "JSON invalido";
    message = "O editor contem texto que nao pode ser interpretado como JSON.";
  } else if (report.structureValidation.status === "empty") {
    kind = "neutral";
    title = "Draft vazio";
  } else if (report.formatValidation.status === "fail") {
    kind = "offline";
    title = "Formato invalido";
  } else if (report.formatValidation.status === "pass" && report.qualityValidation.status !== "pass") {
    kind = "warning";
    title = "Qualidade pendente";
  } else if (report.approvalReadiness.status === "pass") {
    kind = "ok";
    title = "Aprovacao pronta";
  } else if (report.structureValidation.status === "pass") {
    kind = "warning";
    title = "Estrutura OK";
  }

  setStateSummary(elements.editorStateSummary, kind, title, message);
  elements.nextStep.textContent = getRecommendedNextStep(result, state.lastGenerationMetadata);
}

function getRecommendedNextStep(result, generationMetadata) {
  const report = result.report;
  if (generationMetadata?.generation_state === "stale" || generationMetadata?.validation_status === "stale") {
    return "O caso mudou depois da ultima geracao. Gere novamente ou revise manualmente antes de avancar.";
  }
  if (result.rubrics === null) {
    return "Corrija o JSON ou copie o texto bruto para revisar fora do editor.";
  }
  if (report.structureValidation.status === "empty") {
    return "Preencha o caso e gere rubrics, ou escreva/copie rubrics manualmente.";
  }
  if (report.formatValidation.status === "fail") {
    return "Corrija dimensoes, pesos, campos obrigatorios e tipos antes de revisar qualidade.";
  }
  if (generationMetadata?.validation_status === "failed") {
    return "A geracao rodou, mas o resultado falhou na validacao. Corrija as rubrics ou gere novamente.";
  }
  if (report.qualityValidation.status !== "pass") {
    return "Revise atomicidade, cobertura, pesos e relevancia antes de marcar reviewed.";
  }
  if (report.approvalReadiness.status !== "pass") {
    return "Complete os campos do caso e confirme a prontidao antes de aprovar.";
  }
  return "Caso pronto para aprovacao ou exportacao conforme o fluxo.";
}

function renderValidationLayers(report) {
  elements.validationLayers.innerHTML = "";
  const fields = [
    ["structureValidation", "Structure"],
    ["formatValidation", "Format"],
    ["qualityValidation", "Quality"],
    ["approvalReadiness", "Approval"],
  ];

  for (const [key, labelText] of fields) {
    const result = report?.[key] || layer("pending", "Pendente.", true);
    const item = document.createElement("div");
    item.className = "diagnostic-item";

    const label = document.createElement("span");
    label.textContent = labelText;

    const value = document.createElement("strong");
    value.textContent = `${result.status}: ${result.message}`;

    item.append(label, value);
    elements.validationLayers.appendChild(item);
  }
}

function renderQualityHeuristics(qualityHeuristics) {
  const result = qualityHeuristics || {
    status: "pending",
    messages: ["Quality heuristics pending until backend validation runs."],
    signals: {},
  };
  const status = result.status || "pending";
  const signals = result.signals || {};
  elements.qualityHeuristics.classList.remove("pass", "warning", "pending");
  elements.qualityHeuristics.classList.add(status);
  elements.qualityHeuristicsStatus.className = `badge ${status === "pass" ? "ok" : status === "warning" ? "warning" : "neutral"}`;
  elements.qualityHeuristicsStatus.textContent = status;
  elements.qualityHeuristicsMessages.innerHTML = "";
  elements.qualityHeuristicsSignalList.innerHTML = "";

  if (status === "pass") {
    elements.qualityHeuristicsMessage.textContent = "No quality warnings.";
  } else if (status === "warning") {
    elements.qualityHeuristicsMessage.textContent =
      "Esses alertas não bloqueiam o draft, mas indicam pontos que devem ser revisados antes de marcar como reviewed.";
    for (const message of result.messages || []) {
      const item = document.createElement("li");
      item.textContent = message;
      elements.qualityHeuristicsMessages.appendChild(item);
    }
  } else {
    elements.qualityHeuristicsMessage.textContent =
      result.messages?.[0] || "Quality heuristics pending until backend validation runs.";
  }

  const signalEntries = qualitySignalEntries(signals);
  elements.qualityHeuristicsSignals.hidden = signalEntries.length === 0;
  for (const [label, value] of signalEntries) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    elements.qualityHeuristicsSignalList.append(term, description);
  }
}

function qualitySignalEntries(signals) {
  const keys = [
    ["rubric_count", "Rubrics"],
    ["has_negative_rubric", "Has negative rubric"],
    ["has_response_specific_rubric", "Has response-specific rubric"],
    ["weight_distribution", "Weights"],
    ["possible_overlap_count", "Possible overlaps"],
    ["unsupported_inference_count", "Unsupported inference signals"],
    ["dominant_dimension", "Dominant dimension"],
  ];
  return keys
    .filter(([key]) => Object.prototype.hasOwnProperty.call(signals, key))
    .map(([key, label]) => [label, formatQualitySignal(signals[key])]);
}

function formatQualitySignal(value) {
  if (Array.isArray(value)) {
    return value.join(", ") || "none";
  }
  if (value === true) {
    return "yes";
  }
  if (value === false) {
    return "no";
  }
  if (value === null || value === undefined || value === "") {
    return "none";
  }
  return String(value);
}

function updateActionStates(report = state.lastValidationReport) {
  const structureOk = report?.structureValidation?.status === "pass";
  const formatOk = report?.formatValidation?.status === "pass";
  const approvalOk = report?.approvalReadiness?.status === "pass";
  elements.markReviewed.disabled = !(structureOk && formatOk);
  elements.markApproved.disabled = !approvalOk;
}

elements.loadTemplate.addEventListener("click", () => {
  invalidateGenerationMetadata();
  loadTemplate().catch((error) => {
    elements.templateSummary.textContent = error.message;
  });
});

elements.newCase.addEventListener("click", () => {
  invalidateGenerationMetadata();
  resetCase();
});
function invalidateQualityReview() {
  state.humanQualityReviewed = false;
  renderValidation();
}

function invalidateGenerationMetadata() {
  const hadGeneration = Boolean(state.lastGenerationMetadata || state.lastRawModelResponse);
  state.lastGenerationMetadata = null;
  state.lastRawModelResponse = null;
  state.lastValidationReport = null;
  if (hadGeneration) {
    state.lastGenerationMetadata = {
      generation_state: "stale",
      validation_status: "stale",
      generation_executed: false,
    };
  }
  renderGenerationDiagnostics(state.lastGenerationMetadata);
  renderRawModelResponse();
  renderValidation();
}

elements.rubricsEditor.addEventListener("input", () => {
  invalidateQualityReview();
  invalidateGenerationMetadata();
});
elements.prompt.addEventListener("input", () => {
  invalidateQualityReview();
  invalidateGenerationMetadata();
});
elements.responseRaw.addEventListener("input", () => {
  invalidateQualityReview();
  invalidateGenerationMetadata();
});
elements.goldenResponse.addEventListener("input", () => {
  invalidateQualityReview();
  invalidateGenerationMetadata();
});
elements.chatHistory.addEventListener("input", () => {
  invalidateQualityReview();
  invalidateGenerationMetadata();
});
elements.categorySelect.addEventListener("change", () => {
  invalidateGenerationMetadata();
  loadTemplate().catch((error) => {
    elements.templateSummary.textContent = error.message;
  });
});
elements.localeSelect.addEventListener("change", () => {
  invalidateGenerationMetadata();
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

elements.copyJson.addEventListener("click", () => {
  copyEditorJson().catch((error) => {
    elements.validationOutput.textContent = error.message;
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
