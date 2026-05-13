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
  modelsLoading: false,
  providerModelRequestId: 0,
  selectedCaseId: null,
  lastGenerationMetadata: null,
  lastRawModelResponse: null,
  editorArtifactMetadata: null,
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
  contractMismatchWarning: document.querySelector("#contract-mismatch-warning"),
  validationOutput: document.querySelector("#validation-output"),
  validationLayers: document.querySelector("#validation-layers"),
  failedGenerationPanel: document.querySelector("#failed-generation-panel"),
  failedGenerationReason: document.querySelector("#failed-generation-reason"),
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
  generationDiagnosticsDetails: document.querySelector("#generation-diagnostics-details"),
  rawModelResponse: document.querySelector("#raw-model-response"),
  rawModelNote: document.querySelector("#raw-model-note"),
  rawModelDetails: document.querySelector("#raw-model-details"),
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
    throw new Error(payload.error || detail || "Falha sem detalhe retornado pelo backend.");
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

function editorHasAppliedRubrics() {
  try {
    const parsed = JSON.parse(elements.rubricsEditor.value || "[]");
    return Array.isArray(parsed) && parsed.length > 0;
  } catch {
    return false;
  }
}

function stableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function contractsEqual(left, right) {
  if (!left || !right) {
    return false;
  }
  return stableJson(left) === stableJson(right);
}

function templateSnapshotFromCurrent() {
  if (!state.currentTemplate) {
    return null;
  }
  return {
    locale: state.currentTemplate.locale,
    category: state.currentTemplate.category,
    template_name: state.currentTemplate.template_name,
    template_version: state.currentTemplate.template_version,
    template_contract: state.currentTemplate.contract || null,
  };
}

function templateSnapshotFromRecord(record) {
  const metadata = record?.metadata || {};
  const scaffold = metadata.template_scaffold || {};
  const contract = metadata.template_contract || null;
  if (!contract && !scaffold.template_name && !record?.template_name && !record?.category) {
    return null;
  }
  return {
    locale: record?.locale || scaffold.locale || elements.localeSelect.value,
    category: record?.category || scaffold.category || null,
    template_name: record?.template_name || scaffold.template_name || null,
    template_version: record?.template_version || scaffold.template_version || null,
    template_contract: contract,
  };
}

function activeEditorArtifactMetadata() {
  if (state.editorArtifactMetadata?.template_contract) {
    return state.editorArtifactMetadata;
  }
  if (state.lastGenerationMetadata?.template_contract) {
    return {
      locale: state.lastGenerationMetadata.locale || elements.localeSelect.value,
      category: state.lastGenerationMetadata.category || elements.categorySelect.value,
      template_name: state.lastGenerationMetadata.template_used || null,
      template_version: state.currentTemplate?.template_version || null,
      template_contract: state.lastGenerationMetadata.template_contract,
    };
  }
  return null;
}

function contractWeightSummary(contract) {
  const policy = contract?.weight_policy || {};
  const negativeMin = policy.negative_min ?? "n/d";
  const negativeMax = policy.negative_max ?? "n/d";
  const positiveMin = policy.positive_min ?? "n/d";
  const positiveMax = policy.positive_max ?? "n/d";
  return `pesos negativos ${negativeMin}..${negativeMax}, positivos ${positiveMin}..${positiveMax}`;
}

function contractDescriptor(snapshot, fallbackCategory = "n/d") {
  const category = snapshot?.category || fallbackCategory;
  const templateName = snapshot?.template_name || "template n/d";
  return `${category} / ${templateName} / ${contractWeightSummary(snapshot?.template_contract)}`;
}

function editorContractState() {
  const hasRubrics = editorHasAppliedRubrics();
  const editorArtifact = activeEditorArtifactMetadata();
  const currentTemplate = templateSnapshotFromCurrent();
  const editorContract = hasRubrics
    ? editorArtifact?.template_contract || currentTemplate?.template_contract || null
    : null;
  const currentTemplateContract = currentTemplate?.template_contract || null;
  const hasContractMismatch = Boolean(
    hasRubrics &&
      editorArtifact?.template_contract &&
      currentTemplateContract &&
      !contractsEqual(editorArtifact.template_contract, currentTemplateContract),
  );
  const message = hasContractMismatch
    ? [
        "Contrato do editor difere da selecao atual.",
        `Editor: ${contractDescriptor(editorArtifact, "categoria n/d")}.`,
        `Selecao atual: ${contractDescriptor(currentTemplate, elements.categorySelect.value)}.`,
        "Gere novamente ou limpe o editor antes de revisar/aprovar.",
      ].join(" ")
    : "";

  return {
    editorContract,
    currentTemplateContract,
    editorArtifact,
    currentTemplate,
    hasContractMismatch,
    message,
  };
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
  renderFailedGenerationPanel(metadata);
  if (hasFailedGenerationResult(metadata) || isStaleGeneration(metadata)) {
    elements.generationDiagnosticsDetails.open = false;
  }

  if (!metadata) {
    const presentation = generationPresentation(state, metadata, state.lastValidationReport);
    setStateSummary(
      elements.generationSummary,
      presentation.kind,
      presentation.title,
      presentation.message,
    );
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhuma geração realizada.";
    elements.generationDiagnostics.appendChild(empty);
    return;
  }

  renderGenerationSummary(metadata);

  if (isStaleGeneration(metadata)) {
    const currentProvider = document.createElement("div");
    currentProvider.className = "diagnostic-item";
    const providerLabel = document.createElement("span");
    providerLabel.textContent = "current_provider_selection";
    const providerValue = document.createElement("strong");
    providerValue.textContent = elements.rubricProviderSelect.value || "n/d";
    currentProvider.append(providerLabel, providerValue);

    const currentModel = document.createElement("div");
    currentModel.className = "diagnostic-item";
    const modelLabel = document.createElement("span");
    modelLabel.textContent = "current_model_selection";
    const modelValue = document.createElement("strong");
    modelValue.textContent = elements.rubricModelSelect.value || "n/d";
    currentModel.append(modelLabel, modelValue);

    elements.generationDiagnostics.append(currentProvider, currentModel);
    return;
  }

  const presentation = generationPresentation(state, metadata, state.lastValidationReport);
  if (presentation.severity === "error" && presentation.showTechnicalDetails) {
    if (presentation.state === "provider_mismatch_discarded") {
      elements.generationDiagnostics.classList.add("mismatch");
    }
    const alert = document.createElement("div");
    alert.className = "diagnostic-alert";
    alert.textContent = `${presentation.title}: ${presentation.message}`;
    elements.generationDiagnostics.appendChild(alert);
  }

  const fields = [
    "provider_requested",
    "model_requested",
    "provider_used",
    "model_used",
    "model_to_call",
    "default_model_used",
    "generation_failure_type",
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
  const presentation = generationPresentation(state, state.lastGenerationMetadata, state.lastValidationReport);
  elements.rawModelResponse.textContent = raw || "Nenhuma resposta bruta registrada.";
  if (!raw) {
    elements.rawModelNote.textContent = "Nenhuma resposta bruta registrada.";
    return;
  }
  if (!presentation.showRawResponse) {
    elements.rawModelNote.textContent = "Resposta bruta indisponivel para o estado atual da geracao.";
    return;
  }
  if (presentation.state === "invalid_rubric_response") {
    elements.rawModelDetails.open = false;
    elements.rawModelNote.textContent =
      "Resposta bruta preservada apenas para auditoria. Não foi aplicada como rubrics válidas.";
    return;
  }
  elements.rawModelNote.textContent =
    "Resposta bruta preservada para auditoria. O JSON do editor deve ser revisado separadamente.";
}

function renderGenerationSummary(metadata) {
  const presentation = generationPresentation(state, metadata, state.lastValidationReport);
  if (presentation.state) {
    setStateSummary(
      elements.generationSummary,
      presentation.kind,
      presentation.title,
      presentation.message,
    );
    return;
  }

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

  if (hasFailedGenerationResult(metadata)) {
    setStateSummary(
      elements.generationSummary,
      "offline",
      "Resultado nao aplicado",
      "A chamada ao modelo foi executada, mas a resposta não passou na validação. Nenhuma rubric foi aplicada ao editor.",
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
  if (metadata?.generation_failure_type === "provider_mismatch_discarded") {
    return true;
  }
  const providerMismatch = Boolean(
    metadata?.provider_requested &&
      metadata?.provider_used &&
      metadata.provider_requested !== metadata.provider_used,
  );
  const modelMismatch = Boolean(
    metadata?.model_to_call &&
      metadata?.model_used &&
      metadata.model_to_call !== metadata.model_used,
  );
  return providerMismatch || modelMismatch;
}

function hasFailedGenerationResult(metadata = state.lastGenerationMetadata) {
  return Boolean(
    metadata?.generation_failure_type === "provider_failed" ||
      metadata?.generation_failure_type === "invalid_rubric_response" ||
      metadata?.generation_failure_type === "provider_mismatch_discarded" ||
      metadata?.validation_status === "failed" ||
      metadata?.validation_error,
  );
}

function isStaleGeneration(metadata = state.lastGenerationMetadata) {
  return metadata?.generation_state === "stale" || metadata?.validation_status === "stale";
}

function generationPresentation(
  appState = state,
  metadata = appState.lastGenerationMetadata,
  validationReport = appState.lastValidationReport,
) {
  const qualityStatus = validationReport?.qualityHeuristics?.status;
  const rubricsApplied = editorHasAppliedRubrics();

  if (!metadata) {
    return {
      state: "no_generation_yet",
      title: "Nenhuma geração executada",
      message: "A IA ainda não foi chamada para este caso.",
      severity: "neutral",
      kind: "neutral",
      reason: null,
      nextStep: "Preencha o caso e gere rubrics, ou escreva/copie rubrics manualmente.",
      showTechnicalDetails: false,
      showRawResponse: false,
      showRubricCards: rubricsApplied,
      showQualityWarnings: rubricsApplied,
    };
  }

  if (isStaleGeneration(metadata)) {
    return {
      state: "stale_generation",
      title: "Geração desatualizada",
      message:
        "O caso mudou depois da última geração. Gere novamente para obter uma auditoria válida para a seleção atual.",
      severity: "warning",
      kind: "warning",
      reason: null,
      nextStep: "Gere novamente para obter uma auditoria válida para a seleção atual.",
      showTechnicalDetails: false,
      showRawResponse: false,
      showRubricCards: rubricsApplied,
      showQualityWarnings: false,
    };
  }

  const failureType = metadata.generation_failure_type;
  if (failureType === "provider_failed") {
    return {
      state: failureType,
      title: "Geração falhou",
      message: "A chamada ao provider falhou. Nenhuma rubric foi gerada.",
      severity: "error",
      kind: "offline",
      reason: metadata.raw_error || metadata.validation_error || null,
      nextStep: "Verifique provider/modelo, conexão e configuração antes de gerar novamente.",
      showTechnicalDetails: true,
      showRawResponse: false,
      showRubricCards: false,
      showQualityWarnings: false,
    };
  }
  if (failureType === "invalid_rubric_response") {
    return {
      state: failureType,
      title: "Resultado nao aplicado",
      message:
        "O provider respondeu, mas as rubrics retornadas nao passaram na validacao. Nenhuma rubric foi aplicada ao editor.",
      severity: "error",
      kind: "offline",
      reason: metadata.validation_error || null,
      nextStep: "Revise a resposta bruta para auditoria e gere novamente ou tente outro modelo.",
      showTechnicalDetails: true,
      showRawResponse: true,
      showRubricCards: false,
      showQualityWarnings: false,
    };
  }
  if (failureType === "provider_mismatch_discarded" || hasGenerationMismatch(metadata)) {
    return {
      state: "provider_mismatch_discarded",
      title: "Resultado descartado por seguranca",
      message: "O provider/modelo usado divergiu do solicitado. O resultado foi descartado.",
      severity: "error",
      kind: "offline",
      reason: metadata.blocked_reason || null,
      nextStep: "Selecione provider/modelo novamente e gere outra vez.",
      showTechnicalDetails: true,
      showRawResponse: false,
      showRubricCards: false,
      showQualityWarnings: false,
    };
  }

  if (
    metadata.validation_status === "valid" &&
    qualityStatus === "warning" &&
    rubricsApplied
  ) {
    return {
      state: "valid_rubrics_with_quality_warnings",
      title: "Rubrics geradas com alertas",
      message: "As rubrics passaram na validação técnica, mas precisam de revisão de qualidade.",
      severity: "warning",
      kind: "warning",
      reason: null,
      nextStep: "Revise os alertas de qualidade antes de marcar como reviewed.",
      showTechnicalDetails: true,
      showRawResponse: true,
      showRubricCards: true,
      showQualityWarnings: true,
    };
  }

  if (
    metadata.validation_status === "valid" &&
    qualityStatus === "pass" &&
    rubricsApplied
  ) {
    return {
      state: "valid_rubrics_ready_for_human_review",
      title: "Rubrics geradas",
      message: "As rubrics passaram na validação técnica. Revise antes de marcar como reviewed.",
      severity: "ok",
      kind: "ok",
      reason: null,
      nextStep: "Faça a revisão humana e marque como reviewed quando estiver pronto.",
      showTechnicalDetails: true,
      showRawResponse: true,
      showRubricCards: true,
      showQualityWarnings: true,
    };
  }

  if (failureType === "none" && metadata.generation_executed !== false) {
    return {
      state: "valid_rubrics_ready_for_human_review",
      title: "Rubrics geradas",
      message: "Provider/modelo auditados e resultado aplicado ou aguardando revisao.",
      severity: "ok",
      kind: "ok",
      reason: null,
      nextStep: "Revise as rubrics antes de marcar como reviewed.",
      showTechnicalDetails: true,
      showRawResponse: true,
      showRubricCards: rubricsApplied,
      showQualityWarnings: true,
    };
  }

  if (metadata.raw_error || metadata.validation_error || metadata.blocked_reason) {
    return {
      state: "unknown_failure",
      title: "Geração falhou",
      message: "A geracao nao foi aplicada ao editor.",
      severity: "error",
      kind: "offline",
      reason: metadata.raw_error || metadata.validation_error || metadata.blocked_reason,
      nextStep: "Revise os detalhes técnicos e gere novamente.",
      showTechnicalDetails: true,
      showRawResponse: Boolean(state.lastRawModelResponse),
      showRubricCards: false,
      showQualityWarnings: false,
    };
  }

  return {
    state: "no_generation_yet",
    title: "Nenhuma geração executada",
    message: "A IA ainda não foi chamada para este caso.",
    severity: "neutral",
    kind: "neutral",
    reason: null,
    nextStep: "Preencha o caso e gere rubrics, ou escreva/copie rubrics manualmente.",
    showTechnicalDetails: false,
    showRawResponse: false,
    showRubricCards: rubricsApplied,
    showQualityWarnings: rubricsApplied,
  };
}

function failedGenerationReason(metadata = state.lastGenerationMetadata) {
  const presentation = generationPresentation(state, metadata, state.lastValidationReport);
  if (presentation.reason || presentation.message) {
    return presentation.reason || presentation.message;
  }
  return (
    metadata?.validation_error ||
    metadata?.blocked_reason ||
    metadata?.raw_error ||
    metadata?.workflow_decision?.message ||
    "A resposta do modelo não passou na validação."
  );
}

function renderFailedGenerationPanel(metadata = state.lastGenerationMetadata) {
  const presentation = generationPresentation(state, metadata, state.lastValidationReport);
  if (!hasFailedGenerationResult(metadata)) {
    elements.failedGenerationPanel.hidden = true;
    elements.failedGenerationReason.textContent = "n/d";
    return;
  }
  elements.failedGenerationPanel.hidden = false;
  elements.failedGenerationPanel.querySelector("h3").textContent = presentation.title;
  elements.failedGenerationPanel.querySelector("p").textContent = presentation.message;
  elements.failedGenerationReason.textContent = failedGenerationReason(metadata);
}

function assertGenerationMatch(metadata) {
  const presentation = generationPresentation(state, metadata, state.lastValidationReport);
  if (
    presentation.state === "provider_failed" ||
    presentation.state === "invalid_rubric_response" ||
    presentation.state === "provider_mismatch_discarded"
  ) {
    if (presentation.state === "invalid_rubric_response") {
      throw new Error(
        "O modelo respondeu rubrics, mas a validacao rejeitou o resultado. Nada foi aplicado ao editor.",
      );
    }
    throw new Error(presentation.reason || presentation.message);
  }

  if (metadata?.fallback_applied === true || metadata?.result_discarded === true) {
    throw new Error(
      metadata?.blocked_reason || presentation.message
    );
  }
}

function assertCanUseStatus(status) {
  const contractState = editorContractState();
  if (
    (status === "reviewed" || status === "approved" || status === "exported") &&
    contractState.hasContractMismatch
  ) {
    throw new Error(contractState.message);
  }
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
  state.editorArtifactMetadata = templateSnapshotFromRecord(record);
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
  state.editorArtifactMetadata = null;
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
  const contractState = editorContractState();
  const status = statusOverride || elements.statusSelect.value;
  if (!validation.ok && (status !== "draft" || validation.rubrics === null)) {
    throw new Error("Corrija o JSON de rubrics antes de salvar.");
  }
  assertCanUseStatus(status);
  const caseDataReadyForGeneration = requiredCaseFieldsMissing().length === 0;
  const artifactTemplate = validation.rubrics?.length
    ? contractState.editorArtifact || contractState.currentTemplate
    : contractState.currentTemplate;

  return {
    locale: validation.rubrics?.length && artifactTemplate?.locale
      ? artifactTemplate.locale
      : elements.localeSelect.value,
    category: validation.rubrics?.length && artifactTemplate?.category
      ? artifactTemplate.category
      : elements.categorySelect.value,
    chat_history: parseChatHistory(),
    prompt: elements.prompt.value.trim() || null,
    response_raw: elements.responseRaw.value.trim() || null,
    golden_response: elements.goldenResponse.value.trim() || null,
    evaluator_notes: elements.evaluatorNotes.value.trim() || null,
    template_name:
      artifactTemplate?.template_name ||
      state.currentTemplate?.template_name ||
      `${elements.categorySelect.value.toLowerCase()}_template.json`,
    template_version: artifactTemplate?.template_version || state.currentTemplate?.template_version || "v1",
    rubrics: validation.rubrics || [],
    status,
    tags: parseTags(),
    metadata: {
      source: "localization_rubric_lab",
      case_data_ready_for_generation: caseDataReadyForGeneration,
      rubric_source: validation.rubrics?.length ? "editor_draft" : "empty_draft",
      template_scaffold: artifactTemplate
        ? {
            template_name: artifactTemplate.template_name,
            template_version: artifactTemplate.template_version,
            category: artifactTemplate.category,
            scaffold_slots:
              state.currentTemplate?.template_name === artifactTemplate.template_name
                ? state.currentTemplate.rubrics?.length || 0
                : 0,
          }
        : null,
      current_template_scaffold: state.currentTemplate
        ? {
            template_name: state.currentTemplate.template_name,
            template_version: state.currentTemplate.template_version,
            category: state.currentTemplate.category,
            scaffold_slots: state.currentTemplate.rubrics?.length || 0,
          }
        : null,
      template_contract: validation.rubrics?.length
        ? contractState.editorContract
        : state.currentTemplate?.contract || null,
      current_template_contract: state.currentTemplate?.contract || null,
      contract_mismatch: contractState.hasContractMismatch,
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
  const requestId = ++state.providerModelRequestId;
  state.modelsLoading = true;
  elements.generateRubrics.disabled = true;
  elements.rubricModelSelect.innerHTML = "";
  const loadingOption = document.createElement("option");
  loadingOption.value = "";
  loadingOption.textContent = provider ? "Carregando modelos..." : "Fallback do provider";
  elements.rubricModelSelect.appendChild(loadingOption);
  state.models = [];

  if (!provider) {
    state.modelsLoading = false;
    renderModelSelect();
    elements.generateRubrics.disabled = false;
    return;
  }

  let models = [];
  try {
    const response = await fetchJson(`/api/localization/providers/${provider}/models`);
    models = Array.isArray(response) ? response : [];
  } catch {
    models = [];
  }

  if (
    requestId !== state.providerModelRequestId ||
    elements.rubricProviderSelect.value !== provider
  ) {
    return;
  }

  state.models = models;
  state.modelsLoading = false;
  renderModelSelect();
  elements.generateRubrics.disabled = false;
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
  if (!editorHasAppliedRubrics()) {
    state.editorArtifactMetadata = null;
  }
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

function historyItemPresentation(item) {
  const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
  const generation = metadata.rubric_generation && typeof metadata.rubric_generation === "object"
    ? metadata.rubric_generation
    : {};
  const validationReport = metadata.validation_report && typeof metadata.validation_report === "object"
    ? metadata.validation_report
    : {};
  const rubrics = Array.isArray(item?.rubrics) ? item.rubrics : [];
  const rubricCount = rubrics.length;
  const hasRubrics = rubricCount > 0;
  const category = item?.category || metadata.template_scaffold?.category || "Categoria n/d";
  const templateName = item?.template_name || metadata.template_scaffold?.template_name || "template n/d";
  const rubricLabel = `${rubricCount} ${rubricCount === 1 ? "rubric" : "rubrics"}`;
  const caseSummary = item?.prompt ? item.prompt : "Sem caso preenchido";
  const qualityStatus = validationReport.qualityValidation?.status;
  const generationFailureType = generation.generation_failure_type;
  const hasGenerationFailure =
    generation.validation_status === "failed" ||
    Boolean(generation.raw_error) ||
    (generationFailureType && generationFailureType !== "none");
  const pendingReviewDescription =
    qualityStatus === "pending" || qualityStatus === undefined
      ? "Revisão humana pendente."
      : "Revisão humana pendente.";

  const build = ({
    title,
    subtitle,
    badge,
    severity,
    description,
    isRealRubricArtifact = false,
    canReview = false,
    canApprove = false,
    canExport = false,
  }) => ({
    title,
    subtitle,
    badge,
    severity,
    description,
    caseSummary,
    isRealRubricArtifact,
    canReview,
    canApprove,
    canExport,
  });

  if (item?.status === "exported") {
    return build({
      title: "Rubrics exportadas",
      subtitle: `${category} / ${rubricLabel}`,
      badge: "exported",
      severity: "exported",
      description: "Artefato exportado.",
      isRealRubricArtifact: hasRubrics,
    });
  }

  if (item?.status === "approved") {
    return build({
      title: "Rubrics aprovadas",
      subtitle: `${category} / ${rubricLabel}`,
      badge: "approved",
      severity: "approved",
      description: "Prontas para exportação.",
      isRealRubricArtifact: hasRubrics,
      canExport: hasRubrics,
    });
  }

  if (item?.status === "reviewed" || metadata.human_quality_reviewed === true) {
    return build({
      title: "Rubrics revisadas",
      subtitle: `${category} / ${rubricLabel}`,
      badge: "reviewed",
      severity: "reviewed",
      description: "Revisadas por humano; aprovação pendente.",
      isRealRubricArtifact: hasRubrics,
      canApprove: hasRubrics,
    });
  }

  if (hasGenerationFailure) {
    if (generationFailureType === "provider_failed") {
      return build({
        title: "Geração falhou",
        subtitle: `${category} / provider_failed`,
        badge: "falhou",
        severity: "failed",
        description: "A chamada ao provider falhou. Nenhuma rubric foi aplicada.",
        isRealRubricArtifact: false,
      });
    }

    if (generationFailureType === "provider_mismatch_discarded") {
      return build({
        title: "Resultado descartado por segurança",
        subtitle: `${category} / provider_mismatch_discarded`,
        badge: "falhou",
        severity: "failed",
        description: "Provider/modelo divergiu do solicitado.",
        isRealRubricArtifact: false,
      });
    }

    if (generationFailureType === "invalid_rubric_response") {
      return build({
        title: "Geração descartada",
        subtitle: `${category} / invalid_rubric_response`,
        badge: "falhou",
        severity: "failed",
        description: "O provider respondeu, mas as rubrics não passaram na validação.",
        isRealRubricArtifact: false,
      });
    }

    return build({
      title: "Geração falhou",
      subtitle: `${category} / ${generationFailureType || "resultado descartado"}`,
      badge: "falhou",
      severity: "failed",
      description: "Nenhuma rubric foi aplicada.",
      isRealRubricArtifact: false,
    });
  }

  if (hasRubrics && generation.validation_status === "valid") {
    return build({
      title: "Rubrics geradas por IA",
      subtitle: `${category} / ${rubricLabel}`,
      badge: "IA",
      severity: "ai",
      description: pendingReviewDescription,
      isRealRubricArtifact: true,
      canReview: true,
    });
  }

  if (hasRubrics) {
    return build({
      title: "Draft manual",
      subtitle: `${category} / ${rubricLabel}`,
      badge: "draft",
      severity: "draft",
      description: "Rubrics editadas manualmente; revisão pendente.",
      isRealRubricArtifact: true,
      canReview: true,
    });
  }

  if (metadata.template_scaffold && !hasRubrics) {
    return build({
      title: "Template scaffold",
      subtitle: `${category} / ${templateName}`,
      badge: "scaffold",
      severity: "scaffold",
      description: "Não contém rubrics reais aplicadas.",
      isRealRubricArtifact: false,
    });
  }

  if (!hasRubrics) {
    return build({
      title: "Draft vazio",
      subtitle: `${category} / sem rubrics`,
      badge: "vazio",
      severity: "empty",
      description: "Sem rubrics no editor.",
      isRealRubricArtifact: false,
    });
  }

  return build({
    title: "Artefato desconhecido",
    subtitle: `${category} / ${templateName}`,
    badge: "unknown",
    severity: "unknown",
    description: "Estado do artefato nao identificado.",
    isRealRubricArtifact: false,
  });
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
    const presentation = historyItemPresentation(record);
    const item = document.createElement("button");
    item.type = "button";
    item.className = "history-item";
    item.classList.add(`history-item--${presentation.severity}`);
    item.dataset.realRubricArtifact = presentation.isRealRubricArtifact ? "true" : "false";
    item.dataset.canReview = presentation.canReview ? "true" : "false";
    item.dataset.canApprove = presentation.canApprove ? "true" : "false";
    item.dataset.canExport = presentation.canExport ? "true" : "false";
    if (record.id === state.selectedCaseId) {
      item.classList.add("active");
    }

    const header = document.createElement("div");
    header.className = "history-item-header";

    const title = document.createElement("strong");
    title.textContent = presentation.title;

    const badge = document.createElement("span");
    badge.className = `history-badge history-badge--${presentation.severity}`;
    badge.textContent = presentation.badge;
    header.append(title, badge);

    const subtitle = document.createElement("div");
    subtitle.className = "history-meta";
    subtitle.textContent = presentation.subtitle;

    const description = document.createElement("div");
    description.className = "history-description";
    description.textContent = presentation.description;

    const caseSummary = document.createElement("div");
    caseSummary.className = "history-meta";
    caseSummary.textContent = presentation.caseSummary;

    const updatedAt = document.createElement("div");
    updatedAt.className = "history-meta";
    updatedAt.textContent = formatDate(record.updated_at);

    item.append(header, subtitle, description, caseSummary, updatedAt);
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
  if (state.modelsLoading) {
    throw new Error("Aguarde o carregamento dos modelos do provider selecionado.");
  }

  if (!state.currentTemplate) {
    await loadTemplate();
  }

  const providerRequested = elements.rubricProviderSelect.value || undefined;
  const modelRequested = elements.rubricModelSelect.value || null;
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
        contract: state.currentTemplate?.contract || null,
        provider: providerRequested,
        model: modelRequested,
      }),
    });

    state.lastGenerationMetadata = {
      ...(result.metadata || {}),
      template_used: state.currentTemplate?.template_name || result.metadata?.template_used,
      template_contract: state.currentTemplate?.contract || result.metadata?.template_contract || null,
      category: state.currentTemplate?.category || elements.categorySelect.value,
      locale: state.currentTemplate?.locale || elements.localeSelect.value,
    };
    state.lastRawModelResponse = result.raw_model_response || null;
    state.backendValidationRequestId += 1;
    renderGenerationDiagnostics(state.lastGenerationMetadata);
    renderRawModelResponse(state.lastRawModelResponse);
    renderQualityHeuristics();
    try {
      assertGenerationMatch(state.lastGenerationMetadata);
    } catch (e) {
      elements.aiWarning.textContent = e.message;
      elements.validationOutput.textContent = e.message;
      renderQualityHeuristics();
      return;
    }

    if (!result.success) {
      const presentation = generationPresentation(state, state.lastGenerationMetadata, state.lastValidationReport);
      elements.aiWarning.textContent = result.warning || result.error || presentation.message;
      elements.validationOutput.textContent = result.error || presentation.message;
      renderQualityHeuristics();
      return;
    }

    elements.rubricsEditor.value = JSON.stringify(result.rubrics, null, 2);
    state.editorArtifactMetadata = templateSnapshotFromCurrent();
    elements.statusSelect.value = "draft";
    elements.aiWarning.textContent =
      result.warning || "Rubrics geradas por IA devem ser revisadas antes da aprovação.";
    renderValidation();
  } finally {
    elements.generateRubrics.disabled = false;
    if (state.modelsLoading) {
      elements.generateRubrics.disabled = true;
    }
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

  const contractState = editorContractState();
  const structureValidation = validateStructure(rubrics);
  const formatValidation = validateFormat(rubrics, structureValidation, contractState.editorContract);
  const qualityValidation = validateQuality(structureValidation, formatValidation);
  const approvalReadiness = validateApprovalReadiness(
    structureValidation,
    formatValidation,
    qualityValidation,
    contractState,
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

function validateFormat(rubrics, structureValidation, contract = null) {
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
    } else if (!weightAllowedByContract(weight, contract)) {
      issues.push(`Item ${index + 1}: Rubrics_weight fora da escala do contrato do editor.`);
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

function weightAllowedByContract(weight, contract = null) {
  const policy = contract?.weight_policy || {};
  const negativeMin = policy.negative_min ?? -5;
  const negativeMax = policy.negative_max ?? -1;
  const positiveMin = policy.positive_min ?? 1;
  const positiveMax = policy.positive_max ?? 10;
  return (
    (weight >= negativeMin && weight <= negativeMax) ||
    (weight >= positiveMin && weight <= positiveMax)
  );
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

function validateApprovalReadiness(
  structureValidation,
  formatValidation,
  qualityValidation,
  contractState = editorContractState(),
) {
  if (contractState.hasContractMismatch) {
    return layer("blocked", contractState.message, true, {
      contract_mismatch: true,
    });
  }

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
  const contractState = editorContractState();

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
      contract: contractState.editorContract || state.currentTemplate?.contract || null,
      metadata: {
        human_quality_reviewed: state.humanQualityReviewed,
        template_contract: contractState.editorContract || state.currentTemplate?.contract || null,
        current_template_contract: state.currentTemplate?.contract || null,
        contract_mismatch: contractState.hasContractMismatch,
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
      renderGenerationDiagnostics(state.lastGenerationMetadata);
      elements.nextStep.textContent = generationPresentation(
        state,
        state.lastGenerationMetadata,
        state.lastValidationReport,
      ).nextStep;
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
  const contractState = editorContractState();
  let kind = "neutral";
  let title = "Aguardando rubrics";
  let message = result.message;

  renderContractMismatchWarning(contractState);

  if (contractState.hasContractMismatch) {
    kind = "warning";
    title = "Contrato divergente";
    message = contractState.message;
  } else if (result.rubrics === null) {
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

function renderContractMismatchWarning(contractState = editorContractState()) {
  if (!elements.contractMismatchWarning) {
    return;
  }

  elements.contractMismatchWarning.hidden = !contractState.hasContractMismatch;
  elements.contractMismatchWarning.textContent = contractState.hasContractMismatch
    ? contractState.message
    : "";
}

function getRecommendedNextStep(result, generationMetadata) {
  const report = result.report;
  const contractState = editorContractState();
  if (contractState.hasContractMismatch) {
    return "Contrato divergente: gere novamente para a selecao atual ou limpe o editor antes de revisar/aprovar.";
  }
  const presentation = generationPresentation(state, generationMetadata, state.lastValidationReport);
  if (
    generationMetadata ||
    presentation.state === "no_generation_yet" && report.structureValidation.status === "empty"
  ) {
    return presentation.nextStep;
  }
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
  const presentation = generationPresentation(state, state.lastGenerationMetadata, state.lastValidationReport);
  if (!presentation.showQualityWarnings) {
    elements.qualityHeuristics.classList.remove("pass", "warning", "pending");
    elements.qualityHeuristics.classList.add("pending");
    elements.qualityHeuristicsStatus.className = "badge neutral";
    elements.qualityHeuristicsStatus.textContent = "unavailable";
    elements.qualityHeuristicsMessage.textContent =
      "Alertas de qualidade indisponíveis porque nenhuma rubric válida foi aplicada.";
    elements.qualityHeuristicsMessages.innerHTML = "";
    elements.qualityHeuristicsSignalList.innerHTML = "";
    elements.qualityHeuristicsSignals.hidden = true;
    return;
  }

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
  const hasContractMismatch = editorContractState().hasContractMismatch;
  elements.markReviewed.disabled = !(structureOk && formatOk) || hasContractMismatch;
  elements.markApproved.disabled = !approvalOk || hasContractMismatch;
  elements.exportJsonl.disabled = hasContractMismatch;
  elements.exportCsv.disabled = hasContractMismatch;
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
  if (!editorHasAppliedRubrics()) {
    state.editorArtifactMetadata = null;
  }
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
  invalidateGenerationMetadata();
  loadProviderModels().catch((error) => {
    elements.aiWarning.textContent = error.message;
  });
});

elements.rubricModelSelect.addEventListener("change", () => {
  invalidateGenerationMetadata();
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
