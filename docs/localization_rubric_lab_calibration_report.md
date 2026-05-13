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
