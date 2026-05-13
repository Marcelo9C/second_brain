from __future__ import annotations

import re
import string
from collections import Counter
from typing import Any


class RubricQualityHeuristicService:
    MIN_RECOMMENDED_RUBRICS = 5
    MAX_RECOMMENDED_RUBRICS = 15
    OVERLAP_THRESHOLD = 0.6
    DIMENSION_CONCENTRATION_THRESHOLD = 0.8

    _STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    }
    _GENERIC_ANCHOR_TOKENS = {
        "appropriate",
        "clear",
        "correct",
        "good",
        "natural",
        "prompt",
        "quality",
        "relevant",
        "response",
        "user",
    }
    _UNSUPPORTED_INFERENCE_TERMS = (
        "repeatedly",
        "always",
        "previously",
        "again",
        "as mentioned earlier",
        "from previous interactions",
        "misnaming",
        "called the user",
        "prior preference",
    )
    _CONTEXT_CUE_TERMS = (
        "named entity",
        "specific entity",
        "prior turn",
        "previous message",
        "chat history",
        "slang",
        "cultural reference",
        "formatting requirement",
        "must",
        "do not",
        "avoid",
        "include",
        "keep",
        "use exactly",
        "bullet",
        "tone",
        "style",
    )

    def evaluate(
        self,
        payload: dict[str, Any],
        structure: dict[str, Any],
        format_result: dict[str, Any],
    ) -> dict[str, Any]:
        rubrics = payload.get("rubrics")
        if structure["status"] != "pass" or format_result["status"] != "pass":
            return {
                "status": "pending",
                "blocking": False,
                "messages": ["Quality heuristics pending until structure and format pass."],
                "signals": {
                    "rubric_count": len(rubrics) if isinstance(rubrics, list) else 0,
                },
            }

        rubric_list = rubrics if isinstance(rubrics, list) else []
        rubric_count = len(rubric_list)
        messages: list[str] = []
        weights = [rubric.get("Rubrics_weight") for rubric in rubric_list]
        numeric_weights = [
            weight
            for weight in weights
            if isinstance(weight, (int, float)) and not isinstance(weight, bool)
        ]
        dimensions = [
            rubric.get("Rubric_dimensions")
            for rubric in rubric_list
            if isinstance(rubric.get("Rubric_dimensions"), str)
        ]
        dimension_distribution = dict(Counter(dimensions))
        possible_overlap_count = self._possible_overlap_count(rubric_list)
        generic_rubric_count = self._generic_rubric_count(payload, rubric_list)
        unsupported_inference_count = self._unsupported_inference_count(payload, rubric_list)
        contextual_cue_detected = self._has_contextual_cue(payload)
        response_pair_differs = self._response_pair_has_meaningful_difference(payload)
        has_response_specific_rubric = any(
            rubric.get("is_response_specific") is True for rubric in rubric_list
        )
        dominant_dimension = self._dominant_dimension(dimension_distribution)
        high_weight_concentration = self._weights_are_concentrated(numeric_weights)
        response_comparison_signal = self._response_comparison_signal(
            response_pair_differs=response_pair_differs,
            has_response_specific_rubric=has_response_specific_rubric,
            generic_rubric_count=generic_rubric_count,
            rubric_count=rubric_count,
        )
        category_coverage_signal = self._category_coverage_signal(
            payload,
            rubric_count,
            dimension_distribution,
            dominant_dimension,
        )
        has_negative_rubric = any(weight < 0 for weight in numeric_weights)
        missing_useful_penalty = self._missing_useful_penalty(
            has_negative_rubric=has_negative_rubric,
            response_pair_differs=response_pair_differs,
            contextual_cue_detected=contextual_cue_detected,
            category_coverage_signal=category_coverage_signal,
        )
        if rubric_count < self.MIN_RECOMMENDED_RUBRICS:
            messages.append(
                f"Only {rubric_count} rubrics generated; expected at least "
                f"{self.MIN_RECOMMENDED_RUBRICS} for a complete evaluation set."
            )
        if rubric_count > self.MAX_RECOMMENDED_RUBRICS:
            messages.append(
                f"{rubric_count} rubrics generated; consider whether the set is too large to remain practical."
            )

        if high_weight_concentration:
            messages.append(
                "Weight distribution is too concentrated; consider using more discriminative weights."
            )

        if not has_negative_rubric:
            messages.append(
                "No negative rubric found; consider adding a penalty for common failure modes if applicable."
            )

        if possible_overlap_count:
            messages.append(
                f"Potential overlap detected in {possible_overlap_count} rubric pair(s)."
            )

        if self._genericity_warning_applies(
            rubric_count=rubric_count,
            generic_rubric_count=generic_rubric_count,
            has_response_specific_rubric=has_response_specific_rubric,
            response_pair_differs=response_pair_differs,
            contextual_cue_detected=contextual_cue_detected,
        ):
            messages.append(
                "Many rubrics appear generic for a case with contextual or response-specific signals."
            )

        if contextual_cue_detected and not has_response_specific_rubric:
            messages.append(
                "Contextual cues detected, but no response-specific rubric was found."
            )

        if response_comparison_signal == "weak":
            messages.append(
                "Response comparison appears weak; consider rubrics that reflect meaningful differences between response_raw and golden_response."
            )

        if unsupported_inference_count:
            messages.append("Potential unsupported inference in rubric description.")

        if self._is_dimension_concentrated(rubric_count, dimension_distribution):
            messages.append(
                "Rubrics are concentrated in one dimension; consider broader coverage if relevant."
            )

        if category_coverage_signal == "low":
            messages.append(
                "Category coverage appears narrow for the case; consider broader coverage if relevant."
            )

        return {
            "status": "warning" if messages else "pass",
            "blocking": False,
            "messages": messages,
            "signals": {
                "rubric_count": rubric_count,
                "has_negative_rubric": has_negative_rubric,
                "has_response_specific_rubric": has_response_specific_rubric,
                "weight_distribution": numeric_weights,
                "high_weight_concentration": high_weight_concentration,
                "missing_useful_penalty": missing_useful_penalty,
                "possible_overlap_count": possible_overlap_count,
                "redundant_pair_count": possible_overlap_count,
                "generic_rubric_count": generic_rubric_count,
                "unsupported_inference_count": unsupported_inference_count,
                "contextual_cue_detected": contextual_cue_detected,
                "response_pair_differs": response_pair_differs,
                "response_comparison_signal": response_comparison_signal,
                "category_coverage_signal": category_coverage_signal,
                "dominant_dimension": dominant_dimension,
                "dimension_distribution": dimension_distribution,
            },
        }

    def _weights_are_concentrated(self, weights: list[int | float]) -> bool:
        if len(weights) < 3:
            return False
        if all(weight >= 8 for weight in weights):
            return True
        return max(weights) - min(weights) <= 1

    def _possible_overlap_count(self, rubrics: list[dict[str, Any]]) -> int:
        count = 0
        token_sets = [
            self._tokens(
                f"{rubric.get('Rubric_title', '')} {rubric.get('Rubrics_description', '')}"
            )
            for rubric in rubrics
        ]
        for left_index, left_tokens in enumerate(token_sets):
            if not left_tokens:
                continue
            for right_tokens in token_sets[left_index + 1 :]:
                if not right_tokens:
                    continue
                shared = left_tokens & right_tokens
                smaller = min(len(left_tokens), len(right_tokens))
                if smaller and len(shared) / smaller >= self.OVERLAP_THRESHOLD:
                    count += 1
        return count

    def _generic_rubric_count(
        self,
        payload: dict[str, Any],
        rubrics: list[dict[str, Any]],
    ) -> int:
        case_tokens = self._specific_tokens(self._case_text(payload))
        count = 0
        for rubric in rubrics:
            text = f"{rubric.get('Rubric_title', '')} {rubric.get('Rubrics_description', '')}"
            rubric_tokens = self._specific_tokens(text)
            anchored_tokens = rubric_tokens & case_tokens
            if rubric.get("is_response_specific") is not True and len(anchored_tokens) <= 1:
                count += 1
        return count

    def _genericity_warning_applies(
        self,
        *,
        rubric_count: int,
        generic_rubric_count: int,
        has_response_specific_rubric: bool,
        response_pair_differs: bool,
        contextual_cue_detected: bool,
    ) -> bool:
        if rubric_count < 3:
            return False
        many_generic = generic_rubric_count / rubric_count >= 0.6
        needs_case_anchor = response_pair_differs or contextual_cue_detected
        return many_generic and needs_case_anchor and not has_response_specific_rubric

    def _unsupported_inference_count(
        self,
        payload: dict[str, Any],
        rubrics: list[dict[str, Any]],
    ) -> int:
        case_text = self._case_text(payload).lower()
        count = 0
        for rubric in rubrics:
            rubric_text = (
                f"{rubric.get('Rubric_title', '')} {rubric.get('Rubrics_description', '')}".lower()
            )
            for term in self._UNSUPPORTED_INFERENCE_TERMS:
                if term in rubric_text and term not in case_text:
                    count += 1
                    break
        return count

    def _has_contextual_cue(self, payload: dict[str, Any]) -> bool:
        case_text = self._case_text(payload)
        lowered = case_text.lower()
        if any(term in lowered for term in self._CONTEXT_CUE_TERMS):
            return True
        if self._chat_history_has_content(payload.get("chat_history")):
            return True
        if self._has_named_entity_phrase(case_text):
            return True
        return self._response_pair_has_meaningful_difference(payload)

    def _response_comparison_signal(
        self,
        *,
        response_pair_differs: bool,
        has_response_specific_rubric: bool,
        generic_rubric_count: int,
        rubric_count: int,
    ) -> str:
        if not response_pair_differs:
            return "not_applicable"
        if has_response_specific_rubric:
            return "present"
        if rubric_count and generic_rubric_count / rubric_count >= 0.5:
            return "weak"
        return "partial"

    def _category_coverage_signal(
        self,
        payload: dict[str, Any],
        rubric_count: int,
        dimension_distribution: dict[str, int],
        dominant_dimension: str | None,
    ) -> str:
        if rubric_count < 4 or not dominant_dimension:
            return "not_applicable"
        concentration = dimension_distribution[dominant_dimension] / rubric_count
        case_text = self._case_text(payload).lower()
        relevant_case_complexity = any(
            term in case_text
            for term in (
                "format",
                "constraint",
                "fact",
                "local",
                "style",
                "tone",
                "instruction",
                "culture",
                "slang",
                "chat history",
            )
        )
        if concentration >= self.DIMENSION_CONCENTRATION_THRESHOLD and relevant_case_complexity:
            return "low"
        return "adequate"

    def _missing_useful_penalty(
        self,
        *,
        has_negative_rubric: bool,
        response_pair_differs: bool,
        contextual_cue_detected: bool,
        category_coverage_signal: str,
    ) -> bool:
        if has_negative_rubric:
            return False
        return response_pair_differs or contextual_cue_detected or category_coverage_signal == "low"

    def _chat_history_has_content(self, chat_history: Any) -> bool:
        if isinstance(chat_history, list):
            return any(bool(str(item).strip()) for item in chat_history)
        return isinstance(chat_history, str) and bool(chat_history.strip())

    def _has_named_entity_phrase(self, text: str) -> bool:
        return bool(re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text))

    def _response_pair_has_meaningful_difference(self, payload: dict[str, Any]) -> bool:
        raw_tokens = self._tokens(payload.get("response_raw"))
        golden_tokens = self._tokens(payload.get("golden_response"))
        if len(raw_tokens) < 4 or len(golden_tokens) < 4:
            return False
        overlap = len(raw_tokens & golden_tokens) / max(1, len(raw_tokens | golden_tokens))
        return overlap < 0.55

    def _is_dimension_concentrated(
        self,
        rubric_count: int,
        dimension_distribution: dict[str, int],
    ) -> bool:
        if rubric_count < 4 or not dimension_distribution:
            return False
        return max(dimension_distribution.values()) / rubric_count >= self.DIMENSION_CONCENTRATION_THRESHOLD

    def _dominant_dimension(self, dimension_distribution: dict[str, int]) -> str | None:
        if not dimension_distribution:
            return None
        return max(dimension_distribution, key=dimension_distribution.get)

    def _case_text(self, payload: dict[str, Any]) -> str:
        parts = [
            payload.get("locale"),
            payload.get("category"),
            payload.get("prompt"),
            payload.get("response_raw"),
            payload.get("golden_response"),
            payload.get("chat_history"),
        ]
        return " ".join(self._stringify(part) for part in parts if part is not None)

    def _stringify(self, value: Any) -> str:
        if isinstance(value, list):
            return " ".join(self._stringify(item) for item in value)
        if isinstance(value, dict):
            return " ".join(self._stringify(item) for item in value.values())
        return str(value)

    def _tokens(self, value: Any) -> set[str]:
        text = self._stringify(value).lower()
        translation = str.maketrans(string.punctuation, " " * len(string.punctuation))
        normalized = text.translate(translation)
        return {
            token
            for token in normalized.split()
            if len(token) > 2 and token not in self._STOPWORDS
        }

    def _specific_tokens(self, value: Any) -> set[str]:
        return {
            token
            for token in self._tokens(value)
            if token not in self._GENERIC_ANCHOR_TOKENS
        }
