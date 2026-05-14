from __future__ import annotations

import re
import string
from collections import Counter
from typing import Any

from app.schemas.rubric_contract import RubricContract


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
    _PROMPT_REQUIREMENT_PATTERNS = {
        "subject line": (
            "assunto",
            "subject",
            "subject line",
        ),
        "greeting": (
            "saudacao",
            "saudação",
            "cumprimento",
            "greeting",
            "salutation",
        ),
        "signature": (
            "assinatura",
            "signature",
            "sign-off",
            "closing",
        ),
        "brevity": (
            "curto",
            "curta",
            "breve",
            "conciso",
            "concisa",
            "concise",
            "short",
        ),
        "empathy": (
            "empatico",
            "empática",
            "empático",
            "empathy",
            "empathetic",
        ),
        "tone": (
            "tom",
            "tone",
            "formal",
            "profissional",
            "professional",
            "motivacional",
            "motivational",
        ),
        "format": (
            "formato",
            "estrutura",
            "format",
            "structure",
        ),
    }
    _DOMAIN_RISK_PATTERNS = {
        "customer_support_grounding": {
            "case_terms": (
                "cliente",
                "customer",
                "suporte",
                "support",
                "pedido",
                "order",
                "entrega",
                "delivery",
                "atraso",
                "delay",
                "reclamou",
                "complaint",
            ),
            "coverage_terms": (
                "accurate",
                "accuracy",
                "unsupported",
                "invent",
                "invented",
                "fabricated",
                "hallucinated",
                "promise",
                "deadline",
                "refund",
                "compensation",
                "prazo",
                "reembolso",
                "compensacao",
                "compensação",
            ),
        },
    }

    def evaluate(
        self,
        payload: dict[str, Any],
        structure: dict[str, Any],
        format_result: dict[str, Any],
        *,
        contract: RubricContract | None = None,
    ) -> dict[str, Any]:
        rubrics = payload.get("rubrics")
        if structure["status"] != "pass" or format_result["status"] != "pass":
            return {
                "status": "pending",
                "blocking": False,
                "messages": ["Quality heuristics pending until structure and format pass."],
                "signals": {
                    "rubric_count": len(rubrics) if isinstance(rubrics, list) else 0,
                    **self.analyze_contract_coverage([], contract, payload)["signals"],
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
        contract_coverage = self.analyze_contract_coverage(rubric_list, contract, payload)
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
        coverage_audit = self._coverage_audit(payload, rubric_list)
        has_negative_rubric = any(weight < 0 for weight in numeric_weights)
        missing_useful_penalty = self._missing_useful_penalty(
            has_negative_rubric=has_negative_rubric,
            response_pair_differs=response_pair_differs,
            contextual_cue_detected=contextual_cue_detected,
            category_coverage_signal=category_coverage_signal,
        )
        messages.extend(contract_coverage["messages"])

        if not contract and rubric_count < self.MIN_RECOMMENDED_RUBRICS:
            messages.append(
                f"Only {rubric_count} rubrics generated; expected at least "
                f"{self.MIN_RECOMMENDED_RUBRICS} for a complete evaluation set."
            )
        if not contract and rubric_count > self.MAX_RECOMMENDED_RUBRICS:
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

        if coverage_audit["missing_prompt_requirements"]:
            missing = ", ".join(coverage_audit["missing_prompt_requirements"])
            messages.append(
                f"Coverage audit: explicit prompt requirements not clearly represented in rubrics: {missing}."
            )

        if coverage_audit["domain_risk_coverage_gaps"]:
            gaps = ", ".join(coverage_audit["domain_risk_coverage_gaps"])
            messages.append(
                f"Coverage audit: domain risk may need rubric coverage: {gaps}."
            )

        if coverage_audit["boilerplate_repetition_count"]:
            messages.append("Repeated boilerplate detected in rubric descriptions.")

        return {
            "status": "warning" if messages else "pass",
            "blocking": False,
            "messages": messages,
            "signals": {
                "rubric_count": rubric_count,
                **contract_coverage["signals"],
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
                "coverage_audit_status": coverage_audit["status"],
                "missing_prompt_requirements": coverage_audit["missing_prompt_requirements"],
                "domain_risk_coverage_gaps": coverage_audit["domain_risk_coverage_gaps"],
                "boilerplate_repetition_count": coverage_audit["boilerplate_repetition_count"],
                "dominant_dimension": dominant_dimension,
                "dimension_distribution": dimension_distribution,
            },
        }

    def analyze_contract_coverage(
        self,
        rubrics: list[dict[str, Any]],
        contract: RubricContract | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        del payload
        actual_rubric_count = len(rubrics)
        dimensions = [
            rubric.get("Rubric_dimensions")
            for rubric in rubrics
            if isinstance(rubric.get("Rubric_dimensions"), str)
        ]
        dimension_distribution = dict(Counter(dimensions))
        used_dimensions = sorted(dimension_distribution)
        numeric_weights = [
            rubric.get("Rubrics_weight")
            for rubric in rubrics
            if isinstance(rubric.get("Rubrics_weight"), (int, float))
            and not isinstance(rubric.get("Rubrics_weight"), bool)
        ]
        response_specific_count = sum(
            1 for rubric in rubrics if rubric.get("is_response_specific") is True
        )
        universal_count = sum(
            1 for rubric in rubrics if rubric.get("is_response_specific") is False
        )
        overrepresented_dimensions = [
            dimension
            for dimension, count in dimension_distribution.items()
            if actual_rubric_count
            and count / actual_rubric_count >= self.DIMENSION_CONCENTRATION_THRESHOLD
        ]

        if not contract:
            return {
                "messages": [],
                "signals": {
                    "expected_rubric_count": None,
                    "actual_rubric_count": actual_rubric_count,
                    "rubric_count_delta": None,
                    "count_coverage_status": "not_applicable",
                    "allowed_dimensions": [],
                    "used_dimensions": used_dimensions,
                    "missing_dimensions": [],
                    "overrepresented_dimensions": sorted(overrepresented_dimensions),
                    "dimension_coverage_ratio": None,
                    "contract_weight_distribution": numeric_weights,
                    "response_specific_count": response_specific_count,
                    "universal_count": universal_count,
                },
            }

        allowed_dimensions = list(contract.allowed_dimensions)
        allowed_dimension_set = set(allowed_dimensions)
        used_allowed_dimensions = [dimension for dimension in used_dimensions if dimension in allowed_dimension_set]
        missing_dimensions = [
            dimension for dimension in allowed_dimensions if dimension not in dimension_distribution
        ]
        dimension_coverage_ratio = (
            len(used_allowed_dimensions) / len(allowed_dimensions)
            if allowed_dimensions
            else None
        )
        expected_rubric_count = contract.expected_rubric_count
        rubric_count_delta = actual_rubric_count - expected_rubric_count
        if actual_rubric_count < expected_rubric_count:
            count_coverage_status = "under_generated"
        elif actual_rubric_count > expected_rubric_count:
            count_coverage_status = "over_generated"
        else:
            count_coverage_status = "matches_expected"

        messages: list[str] = []
        if count_coverage_status == "under_generated":
            messages.append(
                "Generated fewer rubrics than the active contract expects; coverage may be incomplete."
            )
        elif count_coverage_status == "over_generated":
            messages.append(
                "Generated more rubrics than the active contract expects; review whether the set remains practical."
            )

        if overrepresented_dimensions:
            messages.append("Rubrics are concentrated in one dimension; coverage may be narrow.")

        if missing_dimensions:
            messages.append(
                "Some allowed dimensions from the active contract are not represented in the generated rubrics."
            )

        return {
            "messages": messages,
            "signals": {
                "expected_rubric_count": expected_rubric_count,
                "actual_rubric_count": actual_rubric_count,
                "rubric_count_delta": rubric_count_delta,
                "count_coverage_status": count_coverage_status,
                "allowed_dimensions": allowed_dimensions,
                "used_dimensions": used_dimensions,
                "missing_dimensions": missing_dimensions,
                "overrepresented_dimensions": sorted(overrepresented_dimensions),
                "dimension_coverage_ratio": dimension_coverage_ratio,
                "contract_weight_distribution": numeric_weights,
                "response_specific_count": response_specific_count,
                "universal_count": universal_count,
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

    def _coverage_audit(
        self,
        payload: dict[str, Any],
        rubrics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        prompt_text = self._normalize_text(
            " ".join(
                self._stringify(value)
                for value in (payload.get("prompt"), payload.get("chat_history"))
                if value is not None
            )
        )
        case_text = self._normalize_text(self._case_text(payload))
        rubric_text = self._normalize_text(
            " ".join(
                f"{rubric.get('Rubric_title', '')} {rubric.get('Rubrics_description', '')}"
                for rubric in rubrics
            )
        )

        detected_requirements = [
            name
            for name, aliases in self._PROMPT_REQUIREMENT_PATTERNS.items()
            if self._contains_any(prompt_text, aliases)
        ]
        missing_prompt_requirements = [
            name
            for name in detected_requirements
            if not self._requirement_is_covered(name, rubric_text)
        ]

        domain_risk_coverage_gaps = [
            risk_name
            for risk_name, pattern in self._DOMAIN_RISK_PATTERNS.items()
            if self._contains_any(case_text, pattern["case_terms"])
            and not self._contains_any(rubric_text, pattern["coverage_terms"])
        ]
        boilerplate_repetition_count = self._boilerplate_repetition_count(rubrics)
        status = (
            "warning"
            if missing_prompt_requirements
            or domain_risk_coverage_gaps
            or boilerplate_repetition_count
            else "pass"
        )
        return {
            "status": status,
            "missing_prompt_requirements": missing_prompt_requirements,
            "domain_risk_coverage_gaps": domain_risk_coverage_gaps,
            "boilerplate_repetition_count": boilerplate_repetition_count,
        }

    def _requirement_is_covered(self, requirement: str, rubric_text: str) -> bool:
        aliases = self._PROMPT_REQUIREMENT_PATTERNS[requirement]
        if self._contains_any(rubric_text, aliases):
            return True
        if requirement in {"subject line", "greeting", "signature"}:
            return self._contains_any(
                rubric_text,
                (
                    "email structure",
                    "complete email",
                    "required components",
                    "required elements",
                    "missing required elements",
                ),
            )
        if requirement == "brevity":
            return self._contains_any(rubric_text, ("conciseness", "concise", "brevity", "short"))
        if requirement == "empathy":
            return self._contains_any(rubric_text, ("empathy", "empathetic", "empathetic tone"))
        if requirement == "tone":
            return self._contains_any(rubric_text, ("tone", "register", "style"))
        return False

    def _boilerplate_repetition_count(self, rubrics: list[dict[str, Any]]) -> int:
        repeated_count = 0
        for rubric in rubrics:
            description = self._normalize_text(rubric.get("Rubrics_description"))
            words = description.split()
            seen: set[tuple[str, ...]] = set()
            repeated: set[tuple[str, ...]] = set()
            for index in range(0, max(0, len(words) - 3)):
                phrase = tuple(words[index : index + 4])
                if phrase in seen:
                    repeated.add(phrase)
                seen.add(phrase)
            if repeated:
                repeated_count += 1
        return repeated_count

    def _contains_any(self, text: str, terms: tuple[str, ...]) -> bool:
        return any(self._normalize_text(term) in text for term in terms)

    def _normalize_text(self, value: Any) -> str:
        text = self._stringify(value).lower()
        normalized = (
            text.replace("á", "a")
            .replace("à", "a")
            .replace("â", "a")
            .replace("ã", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("õ", "o")
            .replace("ú", "u")
            .replace("ç", "c")
        )
        return re.sub(r"\s+", " ", normalized).strip()

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
