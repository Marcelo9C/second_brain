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

const CANDIDATE_IDS = ["A", "B", "C", "D"];

const state = {
  templates: [],
  currentTemplate: null,
  cases: [],
  providers: [],
  models: [],
  rubricRuns: [],
  modelsLoading: false,
  providerModelRequestId: 0,
  selectedCaseId: null,
  currentCaseMetadata: {},
  lastGenerationMetadata: null,
  lastRawModelResponse: null,
  editorArtifactMetadata: null,
  humanQualityReviewed: false,
  lastValidationReport: null,
  backendValidationRequestId: 0,
  goldenSource: { mode: "manual", candidate_id: null },
  goldenDraftFromRecommendation: false,
  candidateRecommendation: {
    status: "idle",
    recommendedCandidateId: null,
    recommendedCandidateLabel: null,
    reason: "",
    warnings: [],
    metadata: null,
    appliedToGolden: false,
  },
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
  responseRawLabel: document.querySelector("#response-raw-label"),
  responseModeRadios: Array.from(document.querySelectorAll('input[name="response-mode"]')),
  candidatePanel: document.querySelector("#candidate-response-panel"),
  candidateSelectionStatus: document.querySelector("#candidate-selection-status"),
  candidateSelectionWarning: document.querySelector("#candidate-selection-warning"),
  candidateRecommendationSummary: document.querySelector("#candidate-recommendation-summary"),
  candidateRecommendationAuditSummary: document.querySelector("#candidate-recommendation-audit-summary"),
  candidateRecommendationAuditDetails: document.querySelector("#candidate-recommendation-audit-details"),
  candidateRecommendationDiagnostics: document.querySelector("#candidate-recommendation-diagnostics"),
  candidateRecommendationRawNote: document.querySelector("#candidate-recommendation-raw-note"),
  candidateRecommendationRawResponse: document.querySelector("#candidate-recommendation-raw-response"),
  candidateInputs: Object.fromEntries(
    CANDIDATE_IDS.map((id) => [id, document.querySelector(`#candidate-response-${id}`)]),
  ),
  candidateRadios: Array.from(document.querySelectorAll('input[name="selected-candidate"]')),
  candidateSlots: Array.from(document.querySelectorAll(".candidate-slot")),
  analyzeCandidates: document.querySelector("#analyze-candidates"),
  useSelectedAsGolden: document.querySelector("#use-selected-as-golden"),
  goldenResponse: document.querySelector("#golden-response"),
  evaluatorNotes: document.querySelector("#evaluator-notes"),
  rubricsEditor: document.querySelector("#rubrics-editor"),
  rubricCards: document.querySelector("#rubric-cards"),
  jsonStatus: document.querySelector("#json-status"),
  editorStateSummary: document.querySelector("#editor-state-summary"),
  editorToolbar: document.querySelector("#editor-toolbar"),
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
  showRunHistory: document.querySelector("#show-run-history"),
  copyJson: document.querySelector("#copy-json"),
  aiWarning: document.querySelector("#ai-warning"),
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
    const rawDetail = payload.detail;
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg).join(" | ")
      : typeof payload.detail === "object" && payload.detail !== null
        ? payload.detail.message || JSON.stringify(payload.detail)
        : payload.detail;
    const error = new Error(payload.error || detail || "Falha sem detalhe retornado pelo backend.");
    error.status = response.status;
    error.payload = payload;
    error.detail = rawDetail;
    throw error;
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

function selectedCandidateId() {
  return elements.candidateRadios.find((radio) => radio.checked)?.value || null;
}

function responseMode() {
  return elements.responseModeRadios.find((radio) => radio.checked)?.value || "single";
}

function setResponseMode(mode) {
  const nextMode = mode === "candidates" ? "candidates" : "single";
  for (const radio of elements.responseModeRadios) {
    radio.checked = radio.value === nextMode;
  }
  renderResponseMode();
}

function renderResponseMode() {
  const isCandidateMode = responseMode() === "candidates";
  elements.candidatePanel.hidden = !isCandidateMode;
  elements.responseRaw.readOnly = isCandidateMode;
  elements.responseRawLabel.textContent = isCandidateMode
    ? "Response_raw avaliada"
    : "Response_raw";
  elements.responseRaw.placeholder = isCandidateMode
    ? "Selecione uma candidata para resolver a resposta avaliada."
    : "Resposta bruta do modelo.";
  if (isCandidateMode) {
    elements.responseRaw.value = selectedCandidateText();
  }
  renderCandidateSelectorState();
}

function candidateText(candidateId) {
  return elements.candidateInputs[candidateId]?.value.trim() || "";
}

function selectedCandidateText() {
  const candidateId = selectedCandidateId();
  return candidateId ? candidateText(candidateId) : "";
}

function resetCandidateRecommendation(reason = "candidate_recommendation_reset") {
  const previousRecommendation = state.candidateRecommendation || {};
  if (
    previousRecommendation.recommendedCandidateId &&
    state.goldenSource?.mode === "from_recommended_candidate"
  ) {
    state.goldenSource = {
      ...state.goldenSource,
      recommendation_status: "stale_requires_reanalysis",
      recommendation_stale_reason: reason,
      finalized_by_human: false,
    };
  }
  state.candidateRecommendation = {
    status: "idle",
    recommendedCandidateId: null,
    recommendedCandidateLabel: null,
    reason: "",
    warnings: [],
    metadata: null,
    appliedToGolden: false,
  };
  state.goldenDraftFromRecommendation = false;
}

function goldenRecommendationMetadata() {
  const recommendation = state.candidateRecommendation;
  if (!recommendation?.recommendedCandidateId) {
    return null;
  }
  const metadata = recommendation.metadata || {};
  return {
    recommended_candidate_id: recommendation.recommendedCandidateId,
    recommended_candidate_label: recommendation.recommendedCandidateLabel,
    recommendation_status: recommendation.appliedToGolden
      ? "applied_to_golden_draft"
      : recommendation.status,
    reason: recommendation.reason,
    provider_requested: metadata.provider_requested,
    model_requested: metadata.model_requested,
    provider_used: metadata.provider_used,
    model_used: metadata.model_used,
    candidate_count: metadata.candidate_count,
  };
}

function recommendationAllowsRubricGeneration() {
  if (responseMode() !== "candidates") {
    return true;
  }
  const source = state.goldenSource || {};
  return Boolean(
    elements.goldenResponse.value.trim() &&
      selectedCandidateId() &&
      (
        (state.candidateRecommendation.status === "ready" &&
          state.candidateRecommendation.appliedToGolden &&
          source.mode === "from_recommended_candidate") ||
        source.mode === "from_selected_candidate"
      ),
  );
}

function candidateRubricsContainmentMessage() {
  return "Rubrics ainda não disponíveis. Primeiro analise/selecione uma candidata e prepare a Golden Response.";
}

function candidateRubricsBlocked() {
  return responseMode() === "candidates" && !recommendationAllowsRubricGeneration();
}

function candidateResponsesFromInputs() {
  return CANDIDATE_IDS
    .map((id) => ({
      id,
      label: `Candidate ${id}`,
      response_raw: candidateText(id),
      source: "manual",
    }))
    .filter((candidate) => candidate.response_raw);
}

function candidatePayloadFields() {
  if (responseMode() !== "candidates") {
    return {
      response_raw: elements.responseRaw.value.trim() || null,
      candidate_responses: null,
      selected_candidate_id: null,
      response_raw_resolution: {
        mode: "legacy_response_raw",
        candidate_id: null,
      },
    };
  }

  const candidateResponses = candidateResponsesFromInputs();
  const selectedId = selectedCandidateId();
  if (!candidateResponses.length) {
    return {
      response_raw: null,
      candidate_responses: null,
      selected_candidate_id: null,
      response_raw_resolution: {
        mode: "no_candidate_selected",
        candidate_id: null,
      },
    };
  }

  const selectedResponse = selectedCandidateText();
  return {
    response_raw: selectedResponse || null,
    candidate_responses: candidateResponses,
    selected_candidate_id: selectedId,
    response_raw_resolution: selectedId
      ? {
          mode: "candidate_selected",
          candidate_id: selectedId,
        }
      : {
          mode: "selection_required",
          candidate_id: null,
        },
  };
}

function candidateGenerationBlockReason() {
  if (responseMode() !== "candidates") {
    return null;
  }

  const candidateResponses = candidateResponsesFromInputs();
  const selectedId = selectedCandidateId();
  if (!candidateResponses.length) {
    return "Carregue ao menos uma response_raw candidata antes de gerar rubrics.";
  }
  if (!selectedId) {
    return "Selecione explicitamente qual candidata sera avaliada antes de gerar rubrics.";
  }
  if (!selectedCandidateText()) {
    return `Candidate ${selectedId} esta vazia. Escolha uma candidata preenchida antes de gerar rubrics.`;
  }
  if (!candidateResponses.some((candidate) => candidate.id === selectedId)) {
    return `Candidate ${selectedId} nao esta preenchida. Escolha uma candidata com texto antes de gerar rubrics.`;
  }
  if (!recommendationAllowsRubricGeneration()) {
    return "Analise candidatas com IA ou confirme uma candidata como base da Golden antes de gerar rubrics.";
  }
  return null;
}

function setSelectedCandidate(candidateId) {
  for (const radio of elements.candidateRadios) {
    radio.checked = radio.value === candidateId;
  }
}

function setCandidateResponses(candidates = [], fallbackResponseRaw = "") {
  const byId = new Map(
    (Array.isArray(candidates) ? candidates : [])
      .filter((candidate) => candidate && typeof candidate === "object")
      .map((candidate) => [candidate.id, candidate.response_raw || ""]),
  );

  for (const id of CANDIDATE_IDS) {
    elements.candidateInputs[id].value = byId.get(id) || "";
  }

  if (!byId.size && fallbackResponseRaw) {
    elements.candidateInputs.A.value = fallbackResponseRaw;
  }
}

function syncEvaluatedResponse() {
  if (responseMode() !== "candidates") {
    renderCandidateSelectorState();
    return;
  }
  const selectedId = selectedCandidateId();
  elements.responseRaw.value = selectedId ? selectedCandidateText() : "";
  renderCandidateSelectorState();
}

function renderCandidateSelectorState() {
  if (responseMode() !== "candidates") {
    elements.candidateSelectionWarning.hidden = true;
    elements.candidateSelectionWarning.textContent = "";
    elements.candidateSelectionStatus.classList.remove("ok", "offline", "warning", "neutral");
    elements.candidateSelectionStatus.classList.add("neutral");
    elements.candidateSelectionStatus.textContent = "modo unico";
    if (elements.useSelectedAsGolden) {
      elements.useSelectedAsGolden.disabled = true;
    }
    if (elements.analyzeCandidates) {
      elements.analyzeCandidates.disabled = true;
      elements.analyzeCandidates.textContent = "Analisar candidatas com IA";
      elements.analyzeCandidates.removeAttribute("title");
    }
    for (const slot of elements.candidateSlots) {
      slot.classList.remove("selected", "stale", "candidate-slot--recommended");
      const badge = slot.querySelector(".candidate-slot__ai-badge");
      if (badge) {
        badge.hidden = true;
      }
    }
    elements.candidateRecommendationSummary.hidden = true;
    elements.candidateRecommendationSummary.textContent = "";
    return;
  }

  const selectedId = selectedCandidateId();
  const selectedText = selectedCandidateText();
  const blockReason = candidateGenerationBlockReason();
  const metadata = state.lastGenerationMetadata || {};
  const generationCandidateId = metadata.selected_candidate_id;
  const staleBySelection = Boolean(
    generationCandidateId &&
      selectedId &&
      generationCandidateId !== selectedId,
  );
  const staleMetadata = isStaleGeneration(metadata);

  elements.candidateSelectionStatus.classList.remove("ok", "offline", "warning", "neutral");
  for (const slot of elements.candidateSlots) {
    const slotId = slot.dataset.candidateId;
    const isRecommended = state.candidateRecommendation.recommendedCandidateId === slotId;
    slot.classList.toggle("selected", slotId === selectedId);
    slot.classList.toggle("candidate-slot--recommended", isRecommended);
    slot.classList.toggle("stale", staleBySelection && slotId === selectedId);
    const badge = slot.querySelector(".candidate-slot__ai-badge");
    if (badge) {
      badge.hidden = !isRecommended;
    }
  }

  if (selectedId && selectedText && !staleBySelection && !staleMetadata) {
    elements.candidateSelectionStatus.classList.add("ok");
    elements.candidateSelectionStatus.textContent = `avaliando ${selectedId}`;
  } else if (selectedId && selectedText) {
    elements.candidateSelectionStatus.classList.add("warning");
    elements.candidateSelectionStatus.textContent = `avaliando ${selectedId}`;
  } else {
    elements.candidateSelectionStatus.classList.add("warning");
    elements.candidateSelectionStatus.textContent = "sem selecao";
  }

  const warning = staleBySelection
    ? `A ultima geracao usou Candidate ${generationCandidateId}; a selecao atual e Candidate ${selectedId}. Gere novamente antes de revisar.`
    : staleMetadata
      ? "A geracao atual esta desatualizada para o estado do caso. Gere novamente antes de revisar."
      : blockReason;

  elements.candidateSelectionWarning.hidden = !warning;
  elements.candidateSelectionWarning.textContent = warning || "";
  renderCandidateRecommendationSummary();
  if (elements.useSelectedAsGolden) {
    elements.useSelectedAsGolden.disabled = !(selectedId && selectedText);
  }
  updateAnalyzeCandidatesButtonState();
}

function renderCandidateRecommendationSummary() {
  const recommendation = state.candidateRecommendation;
  renderCandidateRecommendationAudit();
  elements.candidateRecommendationSummary.classList.remove("ready", "running", "warning");
  elements.candidateRecommendationSummary.replaceChildren();
  if (recommendation.status === "running") {
    elements.candidateRecommendationSummary.hidden = false;
    elements.candidateRecommendationSummary.classList.add("running");
    const title = document.createElement("strong");
    title.textContent = "Analisando candidatas";
    const message = document.createElement("span");
    message.textContent = "O modelo esta escolhendo a melhor base para a Golden Response.";
    elements.candidateRecommendationSummary.append(title, message);
    return;
  }
  if (recommendation.status === "failed") {
    elements.candidateRecommendationSummary.hidden = false;
    elements.candidateRecommendationSummary.classList.add("warning");
    const title = document.createElement("strong");
    title.textContent = "Escolha automatica falhou";
    const message = document.createElement("span");
    message.textContent =
      recommendation.warnings?.[0] ||
      "A IA nao retornou uma candidata valida. Tente novamente ou selecione uma candidata manualmente.";
    elements.candidateRecommendationSummary.append(title, message);

    const trace = recommendation.metadata?.recommendation_trace;
    const validationError = trace?.validation_error || recommendation.metadata?.generation_failure_type;
    if (validationError) {
      const detail = document.createElement("span");
      detail.className = "candidate-recommendation-summary__detail";
      detail.textContent = `Diagnostico: ${validationError}`;
      elements.candidateRecommendationSummary.append(detail);
    }
    return;
  }
  if (recommendation.status === "ready") {
    elements.candidateRecommendationSummary.hidden = false;
    elements.candidateRecommendationSummary.classList.add("ready");
    const title = document.createElement("strong");
    title.textContent = `Candidata recomendada: ${recommendation.recommendedCandidateId}`;
    const message = document.createElement("span");
    message.textContent =
      "Golden Response criada como draft editavel a partir da candidata recomendada.";
    elements.candidateRecommendationSummary.append(title, message);
    if (recommendation.reason) {
      const reason = document.createElement("span");
      reason.className = "candidate-recommendation-summary__detail";
      reason.textContent = `Justificativa: ${recommendation.reason}`;
      elements.candidateRecommendationSummary.append(reason);
    }
    return;
  }
  elements.candidateRecommendationSummary.hidden = true;
  elements.candidateRecommendationSummary.textContent = "";
}

function renderCandidateRecommendationAudit() {
  if (
    !elements.candidateRecommendationAuditSummary ||
    !elements.candidateRecommendationDiagnostics ||
    !elements.candidateRecommendationRawNote ||
    !elements.candidateRecommendationRawResponse
  ) {
    return;
  }

  const recommendation = state.candidateRecommendation || {};
  const metadata = recommendation.metadata || null;
  const trace = metadata?.recommendation_trace || null;
  elements.candidateRecommendationDiagnostics.innerHTML = "";

  if (!metadata && recommendation.status !== "running") {
    setStateSummary(
      elements.candidateRecommendationAuditSummary,
      "neutral",
      "Nenhuma analise",
      "A IA ainda nao analisou as candidatas.",
    );
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhuma analise de candidatas executada.";
    elements.candidateRecommendationDiagnostics.appendChild(empty);
    elements.candidateRecommendationRawNote.textContent = "Nenhuma resposta bruta registrada.";
    elements.candidateRecommendationRawResponse.textContent = "Nenhuma resposta bruta registrada.";
    return;
  }

  if (recommendation.status === "running") {
    setStateSummary(
      elements.candidateRecommendationAuditSummary,
      "neutral",
      "Analise em andamento",
      "Aguardando resposta do modelo para escolher a melhor candidata.",
    );
  } else if (recommendation.status === "ready") {
    setStateSummary(
      elements.candidateRecommendationAuditSummary,
      "ok",
      `Recomendada ${recommendation.recommendedCandidateId || "n/d"}`,
      recommendation.reason || "Candidata aplicada como draft da Golden Response.",
    );
  } else if (recommendation.status === "failed") {
    setStateSummary(
      elements.candidateRecommendationAuditSummary,
      "offline",
      "Analise falhou",
      recommendation.warnings?.[0] || "A IA nao retornou uma candidata valida.",
    );
    if (elements.candidateRecommendationAuditDetails) {
      elements.candidateRecommendationAuditDetails.open = true;
    }
  } else {
    setStateSummary(
      elements.candidateRecommendationAuditSummary,
      "neutral",
      "Analise pendente",
      "Clique em Analisar candidatas com IA para executar a recomendacao.",
    );
  }

  const fields = [
    ["status", recommendation.status],
    ["recommended_candidate_id", recommendation.recommendedCandidateId],
    ["recommended_candidate_label", recommendation.recommendedCandidateLabel],
    ["generation_failure_type", metadata?.generation_failure_type],
    ["validation_error", trace?.validation_error],
    ["provider_requested", metadata?.provider_requested],
    ["model_requested", metadata?.model_requested],
    ["provider_used", metadata?.provider_used],
    ["model_used", metadata?.model_used],
    ["candidate_count", metadata?.candidate_count],
    ["model_allowed_by_backend", metadata?.model_allowed_by_backend],
    ["fallback_applied", metadata?.fallback_applied],
    ["result_discarded", metadata?.result_discarded],
    ["blocked_reason", metadata?.blocked_reason],
    ["exact_url_called", metadata?.exact_url_called],
    ["response_status", metadata?.response_status],
    ["generation_duration_ms", metadata?.generation_duration_ms],
    ["response_char_count", metadata?.response_char_count],
    ["approx_prompt_tokens", metadata?.approx_prompt_tokens],
    ["approx_response_tokens", metadata?.approx_response_tokens],
    ["generation_timestamp", metadata?.generation_timestamp],
    ["technical_error", metadata?.technical_error],
    ["raw_error", metadata?.raw_error],
  ];

  for (const [labelText, fieldValue] of fields) {
    const item = document.createElement("div");
    item.className = "diagnostic-item";
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = fieldValue ?? "n/d";
    item.append(label, value);
    elements.candidateRecommendationDiagnostics.appendChild(item);
  }

  const parsedResponse = trace?.parsed_response;
  if (parsedResponse) {
    const item = document.createElement("div");
    item.className = "diagnostic-item";
    const label = document.createElement("span");
    label.textContent = "parsed_response";
    const value = document.createElement("strong");
    value.textContent = JSON.stringify(parsedResponse);
    item.append(label, value);
    elements.candidateRecommendationDiagnostics.appendChild(item);
  }

  if (trace?.raw_provider_response) {
    elements.candidateRecommendationRawNote.textContent =
      "Resposta bruta da recomendacao preservada para auditoria.";
    elements.candidateRecommendationRawResponse.textContent = trace.raw_provider_response;
  } else {
    elements.candidateRecommendationRawNote.textContent =
      "Resposta bruta indisponivel. Reinicie o backend com LOCALIZATION_DEBUG_RECOMMENDATION_TRACE=true para captura-la.";
    elements.candidateRecommendationRawResponse.textContent = "Resposta bruta indisponivel.";
  }
}

function updateAnalyzeCandidatesButtonState() {
  if (!elements.analyzeCandidates) {
    return;
  }
  const isCandidateMode = responseMode() === "candidates";
  const candidateResponses = candidateResponsesFromInputs();
  const missingProviderModel = !elements.rubricProviderSelect.value || !elements.rubricModelSelect.value;
  const recommendationRunning = state.candidateRecommendation.status === "running";
  const blocked = Boolean(!isCandidateMode || state.modelsLoading || recommendationRunning || !candidateResponses.length || missingProviderModel);

  elements.analyzeCandidates.disabled = blocked;
  elements.analyzeCandidates.textContent = recommendationRunning
    ? "Analisando candidatas..."
    : "Analisar candidatas com IA";

  if (!isCandidateMode) {
    elements.analyzeCandidates.title = "Disponivel apenas no modo 4 response_raw candidatas.";
  } else if (state.modelsLoading) {
    elements.analyzeCandidates.title = "Aguarde o carregamento dos modelos.";
  } else if (recommendationRunning) {
    elements.analyzeCandidates.title = "Analise de candidatas em andamento.";
  } else if (!candidateResponses.length) {
    elements.analyzeCandidates.title = "Carregue ao menos uma response_raw candidata.";
  } else if (missingProviderModel) {
    elements.analyzeCandidates.title = "Selecione provider e modelo antes de analisar.";
  } else {
    elements.analyzeCandidates.removeAttribute("title");
  }
}

function markGenerationStale(reason = "case_changed_after_generation", extra = {}) {
  const hadGeneration = Boolean(state.lastGenerationMetadata || state.lastRawModelResponse);
  state.lastGenerationMetadata = null;
  state.lastRawModelResponse = null;
  state.lastValidationReport = null;
  if (hadGeneration) {
    state.lastGenerationMetadata = {
      ...(extra.previous_metadata || {}),
      generation_state: "stale",
      validation_status: "stale",
      generation_executed: false,
      stale: true,
      stale_reason: reason,
      ...extra,
    };
    delete state.lastGenerationMetadata.previous_metadata;
  }
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
    "candidate_count",
    "selected_candidate_id",
    "selected_candidate_label",
    "generation_state",
    "stale",
    "stale_reason",
    "current_selected_candidate_id",
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
      metadata.stale_reason === "selected_candidate_changed_after_generation"
        ? "A selecao de candidata mudou depois da ultima geracao. Gere novamente contra a candidata atual."
        : "O caso foi alterado depois da ultima geracao. Gere novamente ou revise manualmente.",
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
  return Boolean(
    metadata?.generation_state === "stale" ||
      metadata?.generation_state === "stale_generation" ||
      metadata?.validation_status === "stale" ||
      metadata?.stale === true,
  );
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
  state.currentCaseMetadata = record?.metadata && typeof record.metadata === "object"
    ? record.metadata
    : {};
  elements.localeSelect.value = record?.locale || elements.localeSelect.value;
  elements.categorySelect.value = record?.category || elements.categorySelect.value;
  elements.statusSelect.value = record?.status || "draft";
  elements.caseCategory.value = record?.category || elements.categorySelect.value;
  elements.chatHistory.value = record?.chat_history
    ? JSON.stringify(record.chat_history, null, 2)
    : "";
  elements.prompt.value = record?.prompt || "";
  const storedCandidates = record?.metadata?.candidate_responses || [];
  setResponseMode(Array.isArray(storedCandidates) && storedCandidates.length ? "candidates" : "single");
  setCandidateResponses(record?.metadata?.candidate_responses || [], record?.response_raw || "");
  setSelectedCandidate(
    record?.metadata?.selected_candidate_id ||
      record?.metadata?.rubric_generation?.selected_candidate_id ||
      (responseMode() === "candidates" && record?.response_raw ? "A" : null),
  );
  if (responseMode() === "single") {
    elements.responseRaw.value = record?.response_raw || "";
  } else {
    syncEvaluatedResponse();
  }
  elements.goldenResponse.value = record?.golden_response || "";
  state.goldenSource = record?.metadata?.golden_source || { mode: "manual", candidate_id: null };
  const storedRecommendation = record?.metadata?.golden_recommendation || null;
  state.candidateRecommendation = storedRecommendation?.recommended_candidate_id
    ? {
        status: "ready",
        recommendedCandidateId: storedRecommendation.recommended_candidate_id,
        recommendedCandidateLabel: storedRecommendation.recommended_candidate_label,
        reason: storedRecommendation.reason || "",
        warnings: [],
        metadata: storedRecommendation,
        appliedToGolden: state.goldenSource?.mode === "from_recommended_candidate",
      }
    : {
        status: "idle",
        recommendedCandidateId: null,
        recommendedCandidateLabel: null,
        reason: "",
        warnings: [],
        metadata: null,
        appliedToGolden: false,
      };
  state.goldenDraftFromRecommendation = state.goldenSource?.mode === "from_recommended_candidate";
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
  state.currentCaseMetadata = {};
  state.rubricRuns = [];
  elements.statusSelect.value = "draft";
  elements.caseCategory.value = elements.categorySelect.value;
  elements.chatHistory.value = "";
  elements.prompt.value = "";
  setResponseMode("single");
  setCandidateResponses();
  setSelectedCandidate(null);
  elements.responseRaw.value = "";
  elements.goldenResponse.value = "";
  state.goldenSource = { mode: "manual", candidate_id: null };
  resetCandidateRecommendation();
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
  syncEvaluatedResponse();
  const candidatePayload = candidatePayloadFields();
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

  const payload = {
    locale: validation.rubrics?.length && artifactTemplate?.locale
      ? artifactTemplate.locale
      : elements.localeSelect.value,
    category: validation.rubrics?.length && artifactTemplate?.category
      ? artifactTemplate.category
      : elements.categorySelect.value,
    chat_history: parseChatHistory(),
    prompt: elements.prompt.value.trim() || null,
    response_raw: candidatePayload.response_raw,
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
      golden_source: state.goldenSource || { mode: "manual", candidate_id: null },
      golden_recommendation: goldenRecommendationMetadata(),
      validation_report: validation.report,
      rubric_generation: state.lastGenerationMetadata,
      raw_model_response: state.lastRawModelResponse,
    },
  };

  if (candidatePayload.candidate_responses?.length) {
    payload.candidate_responses = candidatePayload.candidate_responses;
    payload.metadata.candidate_responses = candidatePayload.candidate_responses;
    payload.metadata.response_raw_resolution = candidatePayload.response_raw_resolution;
    if (candidatePayload.response_raw) {
      payload.selected_candidate_id = candidatePayload.selected_candidate_id;
      payload.metadata.selected_candidate_id = candidatePayload.selected_candidate_id;
    }
  }

  return payload;
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
    updateGenerateButtonState();
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
  updateGenerateButtonState();
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

async function loadRubricRunsForCurrentCase() {
  let caseId = state.selectedCaseId || state.lastGenerationMetadata?.case_id || null;
  if (!caseId && state.lastGenerationMetadata?.run_id) {
    const run = await fetchJson(`/api/localization/rubrics/runs/${state.lastGenerationMetadata.run_id}`);
    caseId = run?.case_id || null;
  }
  if (!caseId) {
    throw new Error("Este editor ainda nao tem uma run registrada. Gere rubrics com IA ou abra um case salvo.");
  }
  state.selectedCaseId = caseId;
  const runs = await fetchJson(`/api/localization/rubric-cases/${caseId}/runs`);
  state.rubricRuns = Array.isArray(runs) ? runs : [];
  return state.rubricRuns;
}

function runStatusLabel(status) {
  const labels = {
    success: "ok",
    pending: "pendente",
    failed: "falha",
    rejected_by_validation: "rejeitada",
    discarded: "descartada",
  };
  return labels[status] || status || "n/d";
}

function runModelLabel(run) {
  const provider = run.provider_used || run.provider_requested || "provider n/d";
  const model = run.model_used || run.model_requested || "modelo n/d";
  return `${provider} / ${model}`;
}

function runRubricCount(run) {
  return Array.isArray(run?.parsed_rubrics) ? run.parsed_rubrics.length : null;
}

function runDetailRows(run) {
  return [
    ["id", run?.id],
    ["case_id", run?.case_id],
    ["run_number", run?.run_number],
    ["status", run?.status],
    ["provider_requested", run?.provider_requested],
    ["model_requested", run?.model_requested],
    ["provider_used", run?.provider_used],
    ["model_used", run?.model_used],
    ["duration_ms", run?.duration_ms],
    ["response_status", run?.response_status],
    ["approx_prompt_tokens", run?.approx_prompt_tokens],
    ["approx_response_tokens", run?.approx_response_tokens],
    ["exact_url_called", run?.exact_url_called],
    ["error_message", run?.error_message],
    ["created_at", formatDate(run?.created_at)],
  ];
}

function closeRunHistoryModal() {
  const existing = document.querySelector(".run-history-backdrop");
  if (existing) {
    existing.remove();
  }
}

function renderRunHistoryErrorModal(message) {
  closeRunHistoryModal();

  const backdrop = document.createElement("div");
  backdrop.className = "app-modal-backdrop run-history-backdrop";

  const modal = document.createElement("div");
  modal.className = "app-modal run-history-modal";
  modal.setAttribute("role", "alertdialog");
  modal.setAttribute("aria-modal", "true");

  const header = document.createElement("div");
  header.className = "run-history-header";

  const heading = document.createElement("h3");
  heading.className = "app-modal-title";
  heading.textContent = "Histórico de runs indisponível";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "run-history-close";
  closeButton.textContent = "Fechar";
  closeButton.addEventListener("click", closeRunHistoryModal);
  header.append(heading, closeButton);

  const body = document.createElement("div");
  body.className = "run-history-error";
  body.textContent = message;

  modal.append(header, body);
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);
  closeButton.focus();
}

function appendRunDetailBlock(parent, title, value) {
  const details = document.createElement("details");
  details.className = "run-detail-block";
  const summary = document.createElement("summary");
  summary.textContent = title;
  const pre = document.createElement("pre");
  pre.className = "code-block small";
  pre.textContent = typeof value === "string" ? value : JSON.stringify(value ?? null, null, 2);
  details.append(summary, pre);
  parent.appendChild(details);
}

async function showRubricRunDetails(runId) {
  const run = await fetchJson(`/api/localization/rubrics/runs/${runId}`);
  const existing = document.querySelector(".run-detail-panel");
  if (existing) {
    existing.remove();
  }

  const panel = document.createElement("section");
  panel.className = "run-detail-panel";

  const title = document.createElement("h4");
  title.textContent = `Run #${run.run_number || "n/d"} - ${runStatusLabel(run.status)}`;
  panel.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "run-detail-grid";
  for (const [labelText, valueText] of runDetailRows(run)) {
    const item = document.createElement("div");
    item.className = "diagnostic-item";
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText ?? "n/d";
    item.append(label, value);
    grid.appendChild(item);
  }
  panel.appendChild(grid);

  appendRunDetailBlock(panel, "Input snapshot", run.input_snapshot);
  appendRunDetailBlock(panel, "Prompt enviado", run.prompt_text || "n/d");
  appendRunDetailBlock(panel, "Resposta bruta", run.raw_model_response || "n/d");
  appendRunDetailBlock(panel, "Rubrics parseadas", run.parsed_rubrics);
  appendRunDetailBlock(panel, "Validation report", run.validation_report);
  appendRunDetailBlock(panel, "Heuristic report", run.heuristic_report);

  const body = document.querySelector(".run-history-body");
  if (body) {
    body.appendChild(panel);
    panel.scrollIntoView({ block: "nearest" });
  }
}

function renderRunHistoryModal(runs) {
  closeRunHistoryModal();

  const appliedRunId = state.currentCaseMetadata?.applied_run_id || null;
  const backdrop = document.createElement("div");
  backdrop.className = "app-modal-backdrop run-history-backdrop";

  const modal = document.createElement("div");
  modal.className = "app-modal run-history-modal";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "run-history-title");

  const header = document.createElement("div");
  header.className = "run-history-header";

  const heading = document.createElement("h3");
  heading.id = "run-history-title";
  heading.className = "app-modal-title";
  heading.textContent = "Histórico de runs";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "run-history-close";
  closeButton.textContent = "Fechar";
  closeButton.addEventListener("click", closeRunHistoryModal);
  header.append(heading, closeButton);

  const summary = document.createElement("p");
  summary.className = "app-modal-message";
  summary.textContent = state.selectedCaseId
    ? `Case ${state.selectedCaseId}`
    : "Nenhum case selecionado.";

  const body = document.createElement("div");
  body.className = "run-history-body";

  if (!runs.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhuma run registrada para este case.";
    body.appendChild(empty);
  } else {
    const table = document.createElement("table");
    table.className = "run-history-table";

    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const label of ["Run", "Data", "Modelo", "Status", "Rubrics", "Ação"]) {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    }
    head.appendChild(headRow);

    const tableBody = document.createElement("tbody");
    for (const run of runs) {
      const row = document.createElement("tr");
      if (String(run.id) === String(appliedRunId)) {
        row.classList.add("active-run");
      }

      const cells = [
        `#${run.run_number || "n/d"}`,
        formatDate(run.created_at),
        runModelLabel(run),
        runStatusLabel(run.status),
        runRubricCount(run) ?? "-",
      ];

      for (const value of cells) {
        const td = document.createElement("td");
        td.textContent = String(value);
        row.appendChild(td);
      }

      const actionCell = document.createElement("td");
      actionCell.className = "run-action-cell";

      const detailsButton = document.createElement("button");
      detailsButton.type = "button";
      detailsButton.className = "run-apply-button run-detail-button";
      detailsButton.textContent = "Detalhes";
      detailsButton.addEventListener("click", () => {
        showRubricRunDetails(String(run.id)).catch((error) => {
          renderRunHistoryErrorModal(error.message);
        });
      });
      actionCell.appendChild(detailsButton);

      if (String(run.id) === String(appliedRunId)) {
        const badge = document.createElement("span");
        badge.className = "history-badge history-badge--approved";
        badge.textContent = "atual";
        actionCell.appendChild(badge);
      } else if (run.status === "success" && runRubricCount(run)) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "run-apply-button";
        button.textContent = "Aplicar";
        button.addEventListener("click", () => {
          applyRubricRun(String(run.id)).catch((error) => {
            showToast(error.message, "warning");
          });
        });
        actionCell.appendChild(button);
      }
      row.appendChild(actionCell);
      tableBody.appendChild(row);
    }

    table.append(head, tableBody);
    body.appendChild(table);
  }

  modal.append(header, summary, body);
  backdrop.appendChild(modal);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) {
      closeRunHistoryModal();
    }
  });
  document.body.appendChild(backdrop);
  closeButton.focus();
}

async function showRubricRunHistory() {
  const runs = await loadRubricRunsForCurrentCase();
  renderRunHistoryModal(runs);
}

async function applyRubricRun(runId) {
  const result = await fetchJson(`/api/localization/rubrics/runs/${runId}/apply`, {
    method: "POST",
  });
  const record = await fetchJson(`/api/localization/rubric-cases/${result.case_id}`);
  fillCase(record);
  await loadCases();
  const runs = await loadRubricRunsForCurrentCase();
  renderRunHistoryModal(runs);
  showToast(`Run aplicada: ${runId}`, "ok");
}

async function generateRubrics() {
  if (state.modelsLoading) {
    throw new Error("Aguarde o carregamento dos modelos do provider selecionado.");
  }

  syncEvaluatedResponse();
  const blockReason = candidateGenerationBlockReason();
  if (blockReason) {
    renderCandidateSelectorState();
    updateGenerateButtonState();
    throw new Error(blockReason);
  }

  if (!state.currentTemplate) {
    await loadTemplate();
  }

  const providerRequested = elements.rubricProviderSelect.value || undefined;
  const modelRequested = elements.rubricModelSelect.value || null;
  const candidatePayload = candidatePayloadFields();
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
        case_id: state.selectedCaseId,
        locale: elements.localeSelect.value,
        category: elements.categorySelect.value,
        chat_history: parseChatHistory(),
        prompt: elements.prompt.value.trim() || null,
        response_raw: candidatePayload.response_raw,
        golden_response: elements.goldenResponse.value.trim() || null,
        base_template: baseTemplate,
        contract: state.currentTemplate?.contract || null,
        provider: providerRequested,
        model: modelRequested,
        candidate_responses: candidatePayload.candidate_responses,
        selected_candidate_id: candidatePayload.selected_candidate_id,
        metadata: {
          candidate_responses: candidatePayload.candidate_responses,
          selected_candidate_id: candidatePayload.selected_candidate_id,
          response_raw_resolution: candidatePayload.response_raw_resolution,
          golden_source: state.goldenSource || { mode: "manual", candidate_id: null },
          golden_recommendation: goldenRecommendationMetadata(),
        },
      }),
    });

    state.lastGenerationMetadata = {
      ...(result.metadata || {}),
      run_id: result.run_id || result.metadata?.run_id || null,
      run_number: result.run_number || result.metadata?.run_number || null,
      case_id: result.case_id || result.metadata?.case_id || state.selectedCaseId || null,
      template_used: state.currentTemplate?.template_name || result.metadata?.template_used,
      template_contract: state.currentTemplate?.contract || result.metadata?.template_contract || null,
      category: state.currentTemplate?.category || elements.categorySelect.value,
      locale: state.currentTemplate?.locale || elements.localeSelect.value,
    };
    if (result.case_id) {
      state.selectedCaseId = result.case_id;
      state.currentCaseMetadata = {
        ...state.currentCaseMetadata,
        created_for_generation_run: true,
      };
    }
    renderCandidateSelectorState();
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
    updateGenerateButtonState();
  }
}

async function recommendGoldenCandidate() {
  if (state.modelsLoading) {
    throw new Error("Aguarde o carregamento dos modelos do provider selecionado.");
  }
  const candidateResponses = candidateResponsesFromInputs();
  if (!candidateResponses.length) {
    throw new Error("Carregue ao menos uma response_raw candidata antes de analisar.");
  }
  const providerRequested = elements.rubricProviderSelect.value;
  const modelRequested = elements.rubricModelSelect.value;
  if (!providerRequested || !modelRequested) {
    throw new Error("Selecione provider e modelo antes de analisar candidatas.");
  }

  state.candidateRecommendation = {
    status: "running",
    recommendedCandidateId: null,
    recommendedCandidateLabel: null,
    reason: "",
    warnings: [],
    metadata: null,
    appliedToGolden: false,
  };
  renderCandidateSelectorState();
  updateGenerateButtonState();

  elements.analyzeCandidates.disabled = true;
  elements.analyzeCandidates.classList.add("generating");
  elements.analyzeCandidates.setAttribute("aria-busy", "true");
  elements.analyzeCandidates.textContent = "Analisando candidatas...";

  try {
    const result = await fetchJson("/api/localization/candidate-responses/recommend-golden", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        locale: elements.localeSelect.value,
        category: elements.categorySelect.value,
        prompt: elements.prompt.value.trim() || null,
        candidate_responses: candidateResponses,
        provider: providerRequested,
        model: modelRequested,
      }),
    });

    if (!result.success) {
      const technicalWarnings = result.warnings || [];
      const humanWarnings = technicalWarnings.length
        ? technicalWarnings
        : ["A IA nao retornou uma candidata valida. Tente novamente ou selecione uma candidata manualmente."];
      state.candidateRecommendation = {
        status: "failed",
        recommendedCandidateId: null,
        recommendedCandidateLabel: null,
        reason: "",
        warnings: humanWarnings,
        metadata: {
          ...(result.metadata || {}),
          technical_warnings: technicalWarnings,
        },
        appliedToGolden: false,
      };
      elements.aiWarning.textContent = state.candidateRecommendation.warnings[0];
      renderCandidateSelectorState();
      updateGenerateButtonState();
      return;
    }

    const recommendedId = result.recommended_candidate_id;
    const recommendedText = candidateText(recommendedId);
    if (!recommendedId || !recommendedText) {
      throw new Error("A IA recomendou uma candidata vazia ou inexistente.");
    }

    setSelectedCandidate(recommendedId);
    elements.responseRaw.value = recommendedText;
    elements.goldenResponse.value = recommendedText;
    state.candidateRecommendation = {
      status: "ready",
      recommendedCandidateId: recommendedId,
      recommendedCandidateLabel: result.recommended_candidate_label || `Candidate ${recommendedId}`,
      reason: result.reason || "",
      warnings: result.warnings || [],
      metadata: result.metadata || null,
      appliedToGolden: true,
    };
    state.goldenDraftFromRecommendation = true;
    state.goldenSource = {
      mode: "from_recommended_candidate",
      candidate_id: recommendedId,
      human_applied: false,
      human_editable: true,
      human_edited: false,
      finalized_by_human: false,
      recommendation_status: "applied_to_golden_draft",
    };
    invalidateQualityReview();
    invalidateGenerationMetadata("golden_response_created_from_candidate_recommendation", {
      current_selected_candidate_id: recommendedId,
    });
    elements.aiWarning.textContent =
      "Golden Response em draft. Revise/edite antes de gerar rubrics.";
    renderCandidateSelectorState();
  } finally {
    elements.analyzeCandidates.classList.remove("generating");
    elements.analyzeCandidates.removeAttribute("aria-busy");
    updateGenerateButtonState();
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
  if (typeof weight !== "number" || Number.isNaN(weight)) {
    return false;
  }

  const policy = contract?.weight_policy || {};
  const negativeMin = policy.negative_min ?? -5;
  const negativeMax = policy.negative_max ?? -1;
  const positiveMin = policy.positive_min ?? 1;
  const positiveMax = policy.positive_max ?? 10;
  const zeroAllowed = policy.zero_allowed === true;
  const integerOnly = policy.integer_only !== false;

  if (integerOnly && !Number.isInteger(weight)) {
    return false;
  }
  if (weight === 0) {
    return zeroAllowed;
  }

  return (
    (weight >= negativeMin && weight <= negativeMax) ||
    (weight >= positiveMin && weight <= positiveMax)
  );
}

function dimensionAllowedByContract(dimension, contract = null) {
  if (typeof dimension !== "string" || !dimension.trim()) {
    return false;
  }

  if (Array.isArray(contract?.allowed_dimensions) && contract.allowed_dimensions.length) {
    return contract.allowed_dimensions.includes(dimension);
  }

  return ACCEPTED_RUBRIC_DIMENSIONS.has(dimension);
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
  syncEvaluatedResponse();
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
  syncEvaluatedResponse();
  const result = validateRubrics();
  const rubricsBlocked = candidateRubricsBlocked();
  elements.validationOutput.hidden = rubricsBlocked;
  elements.validationOutput.textContent = rubricsBlocked ? "" : result.message;
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
  const candidatePayload = candidatePayloadFields();

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
      response_raw: candidatePayload.response_raw,
      golden_response: elements.goldenResponse.value.trim() || null,
      rubrics: result.rubrics,
      contract: contractState.editorContract || state.currentTemplate?.contract || null,
      metadata: {
        human_quality_reviewed: state.humanQualityReviewed,
        candidate_responses: candidatePayload.candidate_responses || [],
        selected_candidate_id: candidatePayload.selected_candidate_id,
        response_raw_resolution: candidatePayload.response_raw_resolution,
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
  const contractState = editorContractState();

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
    const issues = rubricIssues(rubric, {
      contract: contractState.editorContract,
      suppressContractIssues: contractState.hasContractMismatch,
    });
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
    status.textContent = contractState.hasContractMismatch
      ? "contrato divergente"
      : issues.length
        ? "problemas detectados"
        : "estrutura OK";
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

function rubricIssues(rubric, options = {}) {
  const contract = options.contract || null;
  const suppressContractIssues = options.suppressContractIssues === true;
  const issues = [];
  if (!rubric || typeof rubric !== "object" || Array.isArray(rubric)) {
    return ["Item precisa ser um objeto."];
  }
  const missing = REQUIRED_RUBRIC_FIELDS.filter((field) => !(field in rubric));
  if (missing.length) {
    issues.push(`Campos faltando: ${missing.join(", ")}.`);
  }
  if (!suppressContractIssues && !dimensionAllowedByContract(rubric.Rubric_dimensions, contract)) {
    issues.push("Dimensao nao aceita.");
  }
  if (typeof rubric.Rubric_title !== "string" || !rubric.Rubric_title.trim()) {
    issues.push("Titulo ausente.");
  }
  if (typeof rubric.Rubrics_description !== "string" || rubric.Rubrics_description.trim().length < 20) {
    issues.push("Descricao curta ou ausente.");
  }
  if (!suppressContractIssues && !weightAllowedByContract(rubric.Rubrics_weight, contract)) {
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
    message = "Veja o aviso de contrato do editor antes de revisar/aprovar.";
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
    ["coverage_audit_status", "Coverage audit"],
    ["missing_prompt_requirements", "Missing prompt requirements"],
    ["domain_risk_coverage_gaps", "Domain risk gaps"],
    ["boilerplate_repetition_count", "Boilerplate repetitions"],
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

function updateGenerateButtonState() {
  const isCandidateMode = responseMode() === "candidates";
  const rubricsBlockedForCandidates = candidateRubricsBlocked();
  const blockReason = candidateGenerationBlockReason();
  const missingPrompt = !elements.prompt.value.trim();
  const missingGolden = !elements.goldenResponse.value.trim();
  const missingTemplate = !state.currentTemplate;
  const recommendationRunning = state.candidateRecommendation.status === "running";
  const blocked = Boolean(
    state.modelsLoading ||
      recommendationRunning ||
      rubricsBlockedForCandidates ||
      blockReason ||
      missingPrompt ||
      missingGolden ||
      missingTemplate,
  );

  if (elements.editorToolbar) {
    elements.editorToolbar.hidden = rubricsBlockedForCandidates;
  }
  elements.generateRubrics.disabled = blocked;
  elements.generateRubrics.classList.toggle("candidate-blocked", rubricsBlockedForCandidates);
  elements.generateRubrics.classList.toggle("candidate-ready", isCandidateMode && !blocked);
  elements.generateRubrics.textContent = "Gerar Rubrics com IA";

  if (state.modelsLoading) {
    elements.generateRubrics.title = "Aguarde o carregamento dos modelos.";
  } else if (recommendationRunning) {
    elements.generateRubrics.title = "Analise de candidatas em andamento.";
  } else if (rubricsBlockedForCandidates) {
    elements.generateRubrics.title = candidateRubricsContainmentMessage();
  } else if (blockReason) {
    elements.generateRubrics.title = blockReason;
  } else if (missingPrompt) {
    elements.generateRubrics.title = "Preencha o prompt antes de gerar rubrics.";
  } else if (missingGolden) {
    elements.generateRubrics.title = "Preencha a Golden Response antes de gerar rubrics.";
  } else if (missingTemplate) {
    elements.generateRubrics.title = "Carregue um template antes de gerar rubrics.";
  } else {
    elements.generateRubrics.removeAttribute("title");
  }
  updateAnalyzeCandidatesButtonState();
}

function updateActionStates(report = state.lastValidationReport) {
  const structureOk = report?.structureValidation?.status === "pass";
  const formatOk = report?.formatValidation?.status === "pass";
  const approvalOk = report?.approvalReadiness?.status === "pass";
  const hasContractMismatch = editorContractState().hasContractMismatch;
  elements.showRunHistory.disabled = false;
  elements.markReviewed.disabled = !(structureOk && formatOk) || hasContractMismatch;
  elements.markApproved.disabled = !approvalOk || hasContractMismatch;
  elements.exportJsonl.disabled = hasContractMismatch;
  elements.exportCsv.disabled = hasContractMismatch;
  updateGenerateButtonState();
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

function invalidateGenerationMetadata(reason = "case_changed_after_generation", extra = {}) {
  markGenerationStale(reason, {
    previous_metadata: state.lastGenerationMetadata || {},
    ...extra,
  });
  renderGenerationDiagnostics(state.lastGenerationMetadata);
  renderRawModelResponse();
  renderCandidateSelectorState();
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
for (const radio of elements.responseModeRadios) {
  radio.addEventListener("change", () => {
    if (radio.value === "candidates" && radio.checked) {
      const existingResponse = elements.responseRaw.value.trim();
      if (existingResponse && !candidateResponsesFromInputs().length) {
        elements.candidateInputs.A.value = existingResponse;
        setSelectedCandidate("A");
      }
    }
    renderResponseMode();
    resetCandidateRecommendation("response_mode_changed_after_recommendation");
    invalidateQualityReview();
    invalidateGenerationMetadata("response_mode_changed_after_generation", {
      response_mode: responseMode(),
      current_selected_candidate_id: selectedCandidateId(),
    });
  });
}
elements.responseRaw.addEventListener("input", () => {
  if (responseMode() !== "single") {
    return;
  }
  invalidateQualityReview();
  invalidateGenerationMetadata();
});
for (const radio of elements.candidateRadios) {
  radio.addEventListener("change", () => {
    resetCandidateRecommendation("selected_candidate_changed_after_recommendation");
    syncEvaluatedResponse();
    invalidateQualityReview();
    invalidateGenerationMetadata("selected_candidate_changed_after_generation", {
      current_selected_candidate_id: selectedCandidateId(),
      selected_candidate_id: state.lastGenerationMetadata?.selected_candidate_id || null,
    });
  });
}
for (const [candidateId, textarea] of Object.entries(elements.candidateInputs)) {
  textarea.addEventListener("input", () => {
    resetCandidateRecommendation("candidate_response_changed_after_recommendation");
    syncEvaluatedResponse();
    invalidateQualityReview();
    invalidateGenerationMetadata("candidate_response_changed_after_generation", {
      changed_candidate_id: candidateId,
      current_selected_candidate_id: selectedCandidateId(),
    });
  });
}
elements.useSelectedAsGolden.addEventListener("click", () => {
  const candidateId = selectedCandidateId();
  const response = selectedCandidateText();
  if (!candidateId || !response) {
    showToast("Selecione uma candidata preenchida.", "warning");
    return;
  }
  elements.goldenResponse.value = response;
  state.goldenSource = {
    mode: "from_selected_candidate",
    candidate_id: candidateId,
    human_applied: true,
    human_editable: true,
    human_edited: false,
    finalized_by_human: false,
  };
  state.goldenDraftFromRecommendation = false;
  invalidateQualityReview();
  invalidateGenerationMetadata("golden_response_changed_after_generation", {
    current_selected_candidate_id: candidateId,
  });
});
elements.goldenResponse.addEventListener("input", () => {
  if (state.goldenSource?.mode === "from_recommended_candidate") {
    state.goldenSource = {
      ...state.goldenSource,
      human_applied: true,
      human_editable: true,
      human_edited: true,
      finalized_by_human: false,
    };
  } else if (state.goldenSource?.mode === "from_selected_candidate") {
    state.goldenSource = {
      ...state.goldenSource,
      human_applied: true,
      human_editable: true,
      human_edited: true,
      finalized_by_human: false,
    };
  } else {
    state.goldenSource = { mode: "manual", candidate_id: null };
  }
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
  resetCandidateRecommendation("provider_changed_after_recommendation");
  invalidateGenerationMetadata();
  loadProviderModels().catch((error) => {
    elements.aiWarning.textContent = error.message;
  });
});

elements.rubricModelSelect.addEventListener("change", () => {
  resetCandidateRecommendation("model_changed_after_recommendation");
  invalidateGenerationMetadata();
});

elements.saveCase.addEventListener("click", () => {
  saveCase().catch((error) => {
    elements.validationOutput.textContent = error.message;
  });
});

elements.showRunHistory.addEventListener("click", () => {
  showRubricRunHistory().catch((error) => {
    renderRunHistoryErrorModal(error.message);
  });
});

elements.analyzeCandidates.addEventListener("click", () => {
  recommendGoldenCandidate().catch((error) => {
    state.candidateRecommendation = {
      status: "failed",
      recommendedCandidateId: null,
      recommendedCandidateLabel: null,
      reason: "",
      warnings: ["A IA nao retornou uma candidata valida. Tente novamente ou selecione uma candidata manualmente."],
      metadata: { technical_error: error.message },
      appliedToGolden: false,
    };
    elements.aiWarning.textContent = state.candidateRecommendation.warnings[0];
    renderCandidateSelectorState();
    updateGenerateButtonState();
  });
});

elements.generateRubrics.addEventListener("click", () => {
  generateRubrics().catch((error) => {
    if (error.detail?.run_id || error.detail?.case_id) {
      state.lastGenerationMetadata = {
        ...(state.lastGenerationMetadata || {}),
        run_id: error.detail.run_id || null,
        run_number: error.detail.run_number || null,
        case_id: error.detail.case_id || state.selectedCaseId || null,
        generation_failure_type: "provider_failed",
        raw_error: error.message,
        validation_status: "failed",
        category: state.currentTemplate?.category || elements.categorySelect.value,
        locale: state.currentTemplate?.locale || elements.localeSelect.value,
      };
      if (error.detail.case_id) {
        state.selectedCaseId = error.detail.case_id;
      }
      renderGenerationDiagnostics(state.lastGenerationMetadata);
    }
    elements.aiWarning.textContent = error.message;
    renderCandidateSelectorState();
    updateGenerateButtonState();
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
