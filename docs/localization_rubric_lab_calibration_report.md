# Localization Rubric Lab Calibration Report

Sprint 5D manual calibration worksheet.

This report uses only synthetic cases. It must not include confidential client guidelines,
OCR output, real customer examples, or manual-test examples copied from screenshots.

## Synthetic Case: Chitchat

Focus:
- Social tone, naturalness, brevity, contextual cue handling, and unsupported inference risk.

Case data:
- Locale: pt-BR
- Category: Chitchat
- Chat history: A prior synthetic turn establishes a friendly, brief social exchange.
- Prompt: The user sends a short greeting that includes a synthetic named entity cue.
- Response_raw: The draft answers warmly but mostly ignores the contextual cue.
- Golden Response: The revised answer keeps the reply brief and handles the cue directly.

Provider/model:
Case data complete: yes
Generation executed: pending manual run
Generation status: pending manual run
Generation failure type: none
Rubrics applied: pending manual run
Rubric count:
Weights:
Negative rubric present:
Response-specific rubric present:
Quality warnings:
Human assessment:
  - pending manual review
Main issue:
Recommended adjustment:

Checks:
- Detect excessive concentration in Natural Language Fluency when present.
- Expect at least one response-specific rubric when the contextual cue matters.
- Warn if rubrics infer repeated behavior or prior relationship not supported by case data.
- Warn if no useful penalty appears when the draft ignores the contextual cue.
- Warn if all weights are high or nearly identical.

## Synthetic Case: Writing

Focus:
- Explicit writing instruction, format, style, tone, constraints, and response_raw vs
  Golden Response comparison.

Case data:
- Locale: pt-BR
- Category: Writing
- Chat history: Empty.
- Prompt: The user requests a short message with a specific tone, fixed structure, and one explicit constraint.
- Response_raw: The draft follows the topic but ignores the structure and constraint.
- Golden Response: The revised answer follows the structure, tone, and constraint.

Provider/model:
Case data complete: yes
Generation executed: pending manual run
Generation status: pending manual run
Generation failure type: none
Rubrics applied: pending manual run
Rubric count:
Weights:
Negative rubric present:
Response-specific rubric present:
Quality warnings:
Human assessment:
  - pending manual review
Main issue:
Recommended adjustment:

Checks:
- Expect rubrics for format and explicit constraints when relevant.
- Warn if the set only rewards generic clarity or tone.
- Warn if no useful penalty appears for ignoring the instruction.
- Warn if response_raw and Golden Response differ materially but the rubrics do not reflect it.

## Synthetic Case: Knowledge

Focus:
- Factual accuracy, coverage, relevance, caution, local facts when applicable, and unsupported inference.

Case data:
- Locale: pt-BR
- Category: Knowledge
- Chat history: Empty.
- Prompt: The user asks for a concise factual explanation with a local-context qualifier.
- Response_raw: The draft includes a broad answer with one unsupported factual claim.
- Golden Response: The revised answer is cautious, scoped, and avoids unsupported claims.

Provider/model:
Case data complete: yes
Generation executed: pending manual run
Generation status: pending manual run
Generation failure type: none
Rubrics applied: pending manual run
Rubric count:
Weights:
Negative rubric present:
Response-specific rubric present:
Quality warnings:
Human assessment:
  - pending manual review
Main issue:
Recommended adjustment:

Checks:
- Expect rubrics for factual accuracy, coverage, relevance, and caution when relevant.
- Expect unsupported factual claims to be penalized.
- Local Facts and Awareness should appear only when local facts are materially relevant.
- Warn if the rubric set invents facts or assumes unavailable context.
- Warn if central and secondary weights are not discriminative.

## Failure Classification

Use these values when recording manual calibration:

- `provider_failed`: the provider call failed before producing a model response, such as HTTP 500,
  timeout, or provider exception. Rubrics are not applied and `raw_error` is preserved.
- `invalid_rubric_response`: the provider returned a response, but the response did not pass
  rubric JSON validation. Rubrics are not applied and `raw_model_response` is preserved for audit.
- `provider_mismatch_discarded`: the provider returned a response using a different provider or
  model than the authorized call. Rubrics are not applied and the result is discarded.
- `none`: generation succeeded with valid rubrics, or generation was not attempted because the
  workflow blocked the call before provider execution.

Do not classify HTTP 200 with invalid rubric JSON as `provider_failed`.
Do not leave any `result_discarded=true` path with `generation_failure_type=none`.

## Calibration Outcome Summary

Chitchat:
- Generation failure type:
- Quality warnings matched human assessment:
- Useful / partially useful / poor:

Writing:
- Generation failure type:
- Quality warnings matched human assessment:
- Useful / partially useful / poor:

Knowledge:
- Generation failure type:
- Quality warnings matched human assessment:
- Useful / partially useful / poor:

## Sprint 5F Category Calibration Against Client Guide Principles

Confidentiality note:
- This section uses only synthetic cases and abstract quality principles.
- It does not include client guide excerpts, screenshots, OCR, proprietary criteria, real customer examples, or close paraphrases of confidential material.

Provider/model used:
- Gemini / gemini-2.5-flash

### Category: Chitchat

Synthetic case used:
- Chat history: Synthetic prior turn where the user asks for a quick and friendly check-in about a fictional project.
- Prompt: Give a short, casual reply that acknowledges the fictional project without adding new facts.
- Response_raw: A cordial but generic reply that does not use the contextual cue.
- Golden Response: A brief, natural reply that acknowledges the contextual cue directly.

Generation state: invalid_rubric_response
Provider/model: gemini / gemini-2.5-flash
Rubrics applied: no
Rubric count: 0
Weights: none applied
Negative rubric present: no applied rubrics
Response-specific rubric present: no applied rubrics
Quality warnings: unavailable because no valid rubrics were applied

Human assessment:
- poor

Guide-alignment assessment:
- not aligned

Abstract issue:
- The provider responded, but generated rubric weights outside the official negative range. Since no rubrics were applied, the set cannot be used by a human evaluator or assessed for guide alignment beyond the invalid output.

Recommended non-confidential adjustment:
- Consider a small abstract generation-prompt adjustment that reinforces the official weight range and states that invalid weights will cause the entire rubric set to be discarded. Do not add examples or guide-derived content.

### Category: Writing

Synthetic case used:
- Chat history: empty.
- Prompt: Write exactly two bullet points in a polite tone; each bullet must be short and include one action item.
- Response_raw: A polite prose reply that ignores the requested bullet format and length constraint.
- Golden Response: Two concise bullet points that satisfy the format and action-item requirements.

Generation state: invalid_rubric_response
Provider/model: gemini / gemini-2.5-flash
Rubrics applied: no
Rubric count: 0
Weights: none applied
Negative rubric present: no applied rubrics
Response-specific rubric present: no applied rubrics
Quality warnings: unavailable because no valid rubrics were applied

Human assessment:
- poor

Guide-alignment assessment:
- not aligned

Abstract issue:
- The provider responded, but generated multiple negative weights outside the official range. This prevented validation and blocked evaluation of whether the rubrics captured explicit writing instructions, format, tone, constraints, or response_raw vs golden_response differences.

Recommended non-confidential adjustment:
- Consider a small abstract generation-prompt adjustment focused on schema-valid weight discipline before any category-specific tuning. Do not add few-shot examples or guide-derived criteria.

### Category: Knowledge

Synthetic case used:
- Chat history: empty.
- Prompt: Explain how local rules can differ from national guidance, without naming specific local rules unless the case provides them.
- Response_raw: A broad answer with an unsupported local obligation.
- Golden Response: A cautious answer that explains the distinction without inventing local facts.

Generation state: invalid_rubric_response
Provider/model: gemini / gemini-2.5-flash
Rubrics applied: no
Rubric count: 0
Weights: none applied
Negative rubric present: no applied rubrics
Response-specific rubric present: no applied rubrics
Quality warnings: unavailable because no valid rubrics were applied

Human assessment:
- poor

Guide-alignment assessment:
- not aligned

Abstract issue:
- The provider responded, but generated a negative weight outside the official range. No rubric list was applied, so the system could not evaluate factual accuracy, coverage, caution, local-fact grounding, or unsupported-claim penalties.

Recommended non-confidential adjustment:
- Consider a small abstract generation-prompt adjustment that explicitly prioritizes valid weights before nuanced category coverage. Keep any future Knowledge calibration synthetic and avoid local facts unless the synthetic case provides them.

### Sprint 5F Interim Conclusion

Across Chitchat, Writing, and Knowledge, the primary blocker was not category-specific guide alignment yet. The blocker was generation validity: Gemini produced rubric objects with negative weights outside the official -5 to -1 penalty range.

Evidence-based recommendation:
- Do not tune category behavior yet.
- First consider a minimal, non-confidential prompt adjustment to reinforce the official weight range and the consequence of invalid weights.
- Re-run the same synthetic category calibration after the validity issue improves.

## Sprint 5G.4 Contract-Based Generation Calibration

Confidentiality note:
- This section uses only synthetic cases and abstract operational checks.
- It does not include client guide excerpts, screenshots, OCR, proprietary criteria, real customer examples, or close paraphrases of confidential material.

Provider/model used:
- Gemini / gemini-2.5-flash

Diagnostic question:
- If generation fails, does it fail by the active contract?
- If generation passes, does it pass by the active contract?

### Backend Contract Boundary Checks

Synthetic validation checks:
- Chitchat accepts `-6` and rejects `-7` with: `negative weight must be between -6 and -1`.
- Writing accepts `-7` and rejects `-8` with: `negative weight must be between -7 and -1`.
- Knowledge accepts `-10` and rejects `-11` with: `negative weight must be between -10 and -1`.

Result:
- Pass. Validation messages reflect the active contract, not the legacy `-5..-1` scale.

### Prompt Contract Projection Checks

For each category, the captured provider prompt included the active negative range and all allowed dimensions from the formal template contract.

Observed:
- Chitchat: prompt included `-6 to -1`; old literal `-5 to -1` absent.
- Writing: prompt included `-7 to -1`; old literal `-5 to -1` absent.
- Knowledge: prompt included `-10 to -1`; old literal `-5 to -1` absent.

Result:
- Pass. Prompt projection now follows the active contract.

### Service Generation Round

This round called the backend generation service with the active server-resolved contract. It did not persist records.

#### Category: Chitchat

Template:
- `chitchat_template.json`

Contract observed:
- Negative range: `-6..-1`
- Allowed dimensions: `Cultural Understanding and Application`, `Natural Language Fluency`

Generation state:
- `valid`

Provider/model:
- `gemini / gemini-2.5-flash`

Rubrics applied:
- yes

Rubric count:
- 3

Weights generated:
- `-6`, `-4`, `5`

Dimensions generated:
- `Cultural Understanding and Application`
- `Natural Language Fluency`

Negative rubric present:
- yes

Response-specific rubric present:
- yes

Quality warnings:
- `Only 3 rubrics generated; expected at least 5 for a complete evaluation set.`

History artifact state:
- Expected from generated item shape: `ai_generated_applied`

Human assessment:
- Partially useful.

Guide-alignment assessment:
- Abstractly aligned on the main synthetic failure modes, but incomplete due low rubric count.

Main issue:
- The generation is valid and contract-compliant, but under-generates compared with the expected Chitchat contract count of 5.

Recommended adjustment:
- Do not adjust contract yet. Consider a later prompt-calibration pass to make expected count more explicit.

Classification:
- `prompt_contract_projection_gap`

#### Category: Writing

Template:
- `writing_template.json`

Contract observed:
- Negative range: `-7..-1`
- Allowed dimensions: `Cultural Understanding and Application`, `Natural Language Fluency`

Generation state:
- `valid`

Provider/model:
- `gemini / gemini-2.5-flash`

Rubrics applied:
- yes

Rubric count:
- 3

Weights generated:
- `-7`, `-7`, `7`

Dimensions generated:
- `Natural Language Fluency`
- `Cultural Understanding and Application`

Negative rubric present:
- yes

Response-specific rubric present:
- yes

Quality warnings:
- `Only 3 rubrics generated; expected at least 5 for a complete evaluation set.`

History artifact state:
- Expected from generated item shape: `ai_generated_applied`

Human assessment:
- Partially useful.

Guide-alignment assessment:
- Abstractly aligned with explicit instruction/format failures, but incomplete due low rubric count.

Main issue:
- The generation is valid and contract-compliant, but under-generates compared with the expected Writing contract count of 6.

Recommended adjustment:
- Do not adjust contract yet. Consider later prompt calibration around expected count and coverage.

Classification:
- `prompt_contract_projection_gap`

#### Category: Knowledge

Template:
- `knowledge_template.json`

Contract observed:
- Negative range: `-10..-1`
- Allowed dimensions: `Cultural Understanding and Application`, `Facts and Local Knowledge`

Generation state:
- `valid`

Provider/model:
- `gemini / gemini-2.5-flash`

Rubrics applied:
- yes

Rubric count:
- 3

Weights generated:
- `-8`, `-7`, `-5`

Dimensions generated:
- `Facts and Local Knowledge`
- `Cultural Understanding and Application`

Negative rubric present:
- yes

Response-specific rubric present:
- yes

Quality warnings:
- `Only 3 rubrics generated; expected at least 5 for a complete evaluation set.`

History artifact state:
- Expected from generated item shape: `ai_generated_applied`

Human assessment:
- Partially useful.

Guide-alignment assessment:
- Abstractly aligned with factual caution and unsupported-claim penalties, but incomplete due low rubric count.

Main issue:
- The generation is valid and contract-compliant, but under-generates compared with the expected Knowledge contract count of 6.

Recommended adjustment:
- Do not adjust contract yet. Consider later prompt calibration around expected count and complete coverage.

Classification:
- `prompt_contract_projection_gap`

### Persistence and History Round

This round saved synthetic calibration records with tag `sprint-5g4-calibration`.

Saved records:
- Chitchat: `71990b44-7b2f-4ed2-8ebe-99072db7ae86`
- Writing: `8e5f3d56-6ccc-4f9b-91e2-7da8fef66068`
- Knowledge: `2ed31780-f60b-4b9b-890c-947c93dc3643`

Observed metadata contract snapshots:
- Chitchat saved `metadata.template_contract.weight_policy.negative_min = -6`.
- Writing saved `metadata.template_contract.weight_policy.negative_min = -7`.
- Knowledge saved `metadata.template_contract.weight_policy.negative_min = -10`.

History state observed from persisted record shape:
- Chitchat: `ai_generated_applied`
- Writing: `empty_draft`
- Knowledge: `ai_generated_applied`

Persistence notes:
- Chitchat persisted with 5 valid rubrics: weights `-6`, `-5`, `7`, `5`, `4`.
- Knowledge persisted with 2 valid rubrics: weights `-7`, `-10`.
- Writing persistence run hit Gemini HTTP 429 quota before valid rubrics were returned.

Writing provider failure metadata:
- `generation_failure_type = provider_failed`
- `generation_executed = true`
- `raw_error` indicates Gemini free-tier quota exceeded.

Issue discovered:
- The persisted Writing record is shown as `empty_draft` by history-state logic because provider failures set `generation_failure_type = provider_failed` but do not set `validation_status = failed`.
- This is not a contract failure and not model noncompliance.

Classification:
- `provider_failure`
- `history_presentation_bug`

Recommended adjustment:
- In a later focused UI/history patch, treat `generation_failure_type != "none"` with no applied rubrics as a failed generation artifact, even when `validation_status` is absent.
- Do not change provider, fallback, retry, repair, or workflow behavior as part of this calibration.

### 5G.4 Interim Conclusion

Answers:
- The active contract used was correct for all three categories.
- The prompt reflected the correct contract for all three categories.
- Backend validation used the correct contract and emitted contract-specific boundary messages.
- Gemini no longer failed because of the legacy `-5..-1` scale in this diagnostic round.
- Generated rubrics were valid but tended to under-generate relative to `expected_rubric_count`.
- Persisted history is honest for successful AI-applied rubrics, but provider failures can still appear as `empty_draft`.

Recommended next step:
- Do not change contract or validator.
- Consider a narrow prompt calibration that communicates `expected_rubric_count` more explicitly.
- Separately consider a narrow history-state fix for provider failures with no applied rubrics.
