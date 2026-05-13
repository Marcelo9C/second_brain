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
    _UNSUPPORTED_INFERENCE_TERMS = (
        "repeatedly",
        "always",
        "previously",
        "again",
        "as mentioned earlier",
        "from previous interactions",
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
        unsupported_inference_count = self._unsupported_inference_count(payload, rubric_list)
        contextual_cue_detected = self._has_contextual_cue(payload)
        has_response_specific_rubric = any(
            rubric.get("is_response_specific") is True for rubric in rubric_list
        )
        dominant_dimension = self._dominant_dimension(dimension_distribution)

        rubric_count = len(rubric_list)
        if rubric_count < self.MIN_RECOMMENDED_RUBRICS:
            messages.append(
                f"Only {rubric_count} rubrics generated; expected at least "
                f"{self.MIN_RECOMMENDED_RUBRICS} for a complete evaluation set."
            )
        if rubric_count > self.MAX_RECOMMENDED_RUBRICS:
            messages.append(
                f"{rubric_count} rubrics generated; consider whether the set is too large to remain practical."
            )

        if self._weights_are_concentrated(numeric_weights):
            messages.append(
                "Weight distribution is too concentrated; consider using more discriminative weights."
            )

        has_negative_rubric = any(weight < 0 for weight in numeric_weights)
        if not has_negative_rubric:
            messages.append(
                "No negative rubric found; consider adding a penalty for common failure modes if applicable."
            )

        if possible_overlap_count:
            messages.append(
                f"Potential overlap detected in {possible_overlap_count} rubric pair(s)."
            )

        if contextual_cue_detected and not has_response_specific_rubric:
            messages.append(
                "Contextual cues detected, but no response-specific rubric was found."
            )

        if unsupported_inference_count:
            messages.append("Potential unsupported inference in rubric description.")

        if self._is_dimension_concentrated(rubric_count, dimension_distribution):
            messages.append(
                "Rubrics are concentrated in one dimension; consider broader coverage if relevant."
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
                "possible_overlap_count": possible_overlap_count,
                "unsupported_inference_count": unsupported_inference_count,
                "contextual_cue_detected": contextual_cue_detected,
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
