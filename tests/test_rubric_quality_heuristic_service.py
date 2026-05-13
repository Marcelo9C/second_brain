import unittest

from app.services.rubric_quality_heuristic_service import RubricQualityHeuristicService


def rubric(
    title: str,
    description: str,
    weight: int,
    *,
    dimension: str = "Natural Language Fluency",
    response_specific: bool = False,
) -> dict:
    return {
        "Rubric_dimensions": dimension,
        "Rubric_title": title,
        "Rubrics_description": description,
        "Rubrics_weight": weight,
        "is_response_specific": response_specific,
    }


def payload(category: str = "Chitchat", rubrics: list[dict] | None = None, **overrides) -> dict:
    base = {
        "locale": "pt-BR",
        "category": category,
        "chat_history": [],
        "prompt": "Synthetic prompt with a named entity cue for Example Project.",
        "response_raw": "Synthetic raw response with limited context.",
        "golden_response": "Synthetic revised response that handles the context more directly.",
        "rubrics": rubrics or [],
        "metadata": {},
    }
    base.update(overrides)
    return base


def passing_layers(rubrics: list[dict]) -> tuple[dict, dict]:
    count = len(rubrics)
    return (
        {"status": "pass", "blocking": False, "count": count},
        {"status": "pass", "blocking": False, "count": count},
    )


class RubricQualityHeuristicServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RubricQualityHeuristicService()

    def evaluate(self, case_payload: dict) -> dict:
        structure, format_result = passing_layers(case_payload["rubrics"])
        return self.service.evaluate(case_payload, structure, format_result)

    def test_pending_when_structure_or_format_has_not_passed(self) -> None:
        report = self.service.evaluate(
            {"rubrics": []},
            {"status": "fail", "count": 0},
            {"status": "pending", "count": 0},
        )

        self.assertEqual(report["status"], "pending")
        self.assertFalse(report["blocking"])

    def test_warns_for_too_few_rubrics(self) -> None:
        rubrics = [
            rubric("Criterion One", "Assesses one useful behavior in the response.", 7),
            rubric("Criterion Two", "Assesses another useful behavior in the response.", 6),
            rubric("Criterion Three", "Assesses a third useful behavior in the response.", 5),
            rubric("Criterion Four", "Assesses a failure mode in the response.", -3),
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="Synthetic prompt with explicit tone and style requirements.",
            )
        )

        self.assertEqual(report["status"], "warning")
        self.assertFalse(report["blocking"])
        self.assertIn("Only 4 rubrics generated", " ".join(report["messages"]))
        self.assertEqual(report["signals"]["rubric_count"], 4)

    def test_warns_for_too_many_rubrics(self) -> None:
        rubrics = [
            rubric(f"Criterion {index}", "Assesses a distinct synthetic evaluation concern.", 5)
            for index in range(16)
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="Synthetic prompt with explicit tone and style requirements.",
            )
        )

        self.assertIn("16 rubrics generated", " ".join(report["messages"]))

    def test_warns_for_concentrated_weights(self) -> None:
        rubrics = [
            rubric("Important Criterion One", "Assesses a central quality concern.", 9),
            rubric("Important Criterion Two", "Assesses another central quality concern.", 9),
            rubric("Important Criterion Three", "Assesses an additional central quality concern.", 9),
            rubric("Important Criterion Four", "Assesses a related quality concern.", 8),
        ]

        report = self.evaluate(payload(rubrics=rubrics))

        self.assertIn("Weight distribution is too concentrated", " ".join(report["messages"]))
        self.assertEqual(report["signals"]["weight_distribution"], [9, 9, 9, 8])

    def test_warns_when_no_negative_rubric_exists(self) -> None:
        rubrics = [
            rubric("Criterion One", "Assesses one desirable behavior.", 7),
            rubric("Criterion Two", "Assesses another desirable behavior.", 6),
            rubric("Criterion Three", "Assesses a third desirable behavior.", 5),
            rubric("Criterion Four", "Assesses another useful behavior.", 4),
            rubric("Criterion Five", "Assesses final useful behavior.", 3),
        ]

        report = self.evaluate(payload(rubrics=rubrics))

        self.assertIn("No negative rubric found", " ".join(report["messages"]))
        self.assertFalse(report["signals"]["has_negative_rubric"])

    def test_warns_for_potential_overlap(self) -> None:
        rubrics = [
            rubric(
                "Natural Conversational Tone",
                "Rewards a natural informal conversational tone that fits the user.",
                7,
            ),
            rubric(
                "Conversational Informal Tone",
                "Rewards natural informal conversational wording that fits the user.",
                6,
            ),
            rubric("Formatting Accuracy", "Assesses whether requested formatting is followed.", 5),
            rubric("Unsupported Detail Penalty", "Penalizes details not grounded in the case.", -3),
            rubric("Relevant Coverage", "Assesses whether the response covers the main need.", 6),
        ]

        report = self.evaluate(payload(rubrics=rubrics))

        self.assertIn("Potential overlap detected", " ".join(report["messages"]))
        self.assertGreaterEqual(report["signals"]["possible_overlap_count"], 1)

    def test_warns_when_contextual_cue_has_no_response_specific_rubric(self) -> None:
        rubrics = [
            rubric("Tone", "Assesses whether the response uses an appropriate tone.", 6),
            rubric("Clarity", "Assesses whether the response is clear and easy to evaluate.", 5),
            rubric("Brevity", "Assesses whether the response is concise enough for the case.", 5),
            rubric("Grounding Penalty", "Penalizes details unsupported by the case data.", -3),
            rubric("Formatting", "Assesses whether requested formatting is preserved.", 5),
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="User refers to a named entity in the prompt and asks for a concise reply.",
            )
        )

        self.assertIn("Contextual cues detected", " ".join(report["messages"]))
        self.assertTrue(report["signals"]["contextual_cue_detected"])
        self.assertFalse(report["signals"]["has_response_specific_rubric"])

    def test_warns_for_unsupported_inference(self) -> None:
        rubrics = [
            rubric(
                "Prior Interaction Claim",
                "Penalizes the response if it fails to acknowledge that the user repeatedly asked before.",
                -3,
            ),
            rubric("Clarity", "Assesses whether the response is clear and useful.", 6),
            rubric("Tone", "Assesses whether the response uses an appropriate tone.", 5),
            rubric("Relevance", "Assesses whether the response stays relevant to the prompt.", 5),
            rubric("Formatting", "Assesses whether requested formatting is followed.", 5),
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="Synthetic single-turn prompt.",
                response_raw="Synthetic response.",
                golden_response="Synthetic revised response.",
            )
        )

        self.assertIn("Potential unsupported inference", " ".join(report["messages"]))
        self.assertEqual(report["signals"]["unsupported_inference_count"], 1)

    def test_warns_for_unsupported_misnaming_inference(self) -> None:
        rubrics = [
            rubric(
                "Repeated Naming Issue",
                "Penalizes repeated misnaming when referring to the user.",
                -3,
            ),
            rubric("Clarity", "Assesses whether the response is clear and useful.", 6),
            rubric("Tone", "Assesses whether the response uses an appropriate tone.", 5),
            rubric("Relevance", "Assesses whether the response stays relevant to the prompt.", 5),
            rubric("Formatting", "Assesses whether requested formatting is followed.", 5),
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="Synthetic single-turn prompt.",
                response_raw="Synthetic response.",
                golden_response="Synthetic revised response.",
            )
        )

        self.assertIn("Potential unsupported inference", " ".join(report["messages"]))
        self.assertEqual(report["signals"]["unsupported_inference_count"], 1)

    def test_warns_when_many_generic_rubrics_ignore_response_difference(self) -> None:
        rubrics = [
            rubric("Clear Reply", "Assesses whether the response is clear and easy to read.", 7),
            rubric("Helpful Tone", "Assesses whether the response has a helpful tone.", 6),
            rubric("Natural Language", "Assesses whether the response sounds natural.", 6),
            rubric("Relevant Content", "Assesses whether the response remains relevant.", 5),
            rubric("Generic Penalty", "Penalizes unsupported or generic content.", -3),
        ]

        report = self.evaluate(
            payload(
                category="Writing",
                rubrics=rubrics,
                prompt="Synthetic writing task with a specific formatting constraint and required style.",
                response_raw="The draft ignores the requested structure and omits the required constraint.",
                golden_response="The revised answer follows the requested structure and includes the required constraint.",
            )
        )

        self.assertIn("Many rubrics appear generic", " ".join(report["messages"]))
        self.assertEqual(report["signals"]["response_comparison_signal"], "weak")
        self.assertGreaterEqual(report["signals"]["generic_rubric_count"], 3)

    def test_universal_rubrics_are_not_automatically_generic_warning(self) -> None:
        rubrics = [
            rubric("Clear Reply", "Assesses whether the response is clear and easy to read.", 7),
            rubric("Helpful Tone", "Assesses whether the response has a helpful tone.", 6),
            rubric("Natural Language", "Assesses whether the response sounds natural.", 6),
            rubric("Relevant Content", "Assesses whether the response remains relevant.", 5),
            rubric("Unsupported Content Penalty", "Penalizes unsupported or generic content.", -3),
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="simple request",
                response_raw="simple answer with matching content",
                golden_response="simple answer with matching content",
            )
        )

        self.assertNotIn("Many rubrics appear generic", " ".join(report["messages"]))
        self.assertEqual(report["signals"]["response_comparison_signal"], "not_applicable")

    def test_missing_useful_penalty_requires_predictable_failure_signal(self) -> None:
        rubrics = [
            rubric("Clear Reply", "Assesses whether the response is clear and easy to read.", 7),
            rubric("Helpful Tone", "Assesses whether the response has a helpful tone.", 6),
            rubric("Natural Language", "Assesses whether the response sounds natural.", 6),
            rubric("Relevant Content", "Assesses whether the response remains relevant.", 5),
            rubric("Correct Style", "Assesses whether the response uses a correct style.", 5),
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="simple request",
                response_raw="simple answer with matching content",
                golden_response="simple answer with matching content",
            )
        )

        self.assertFalse(report["signals"]["missing_useful_penalty"])

    def test_warns_for_dimension_concentration(self) -> None:
        rubrics = [
            rubric("Tone", "Assesses whether the response uses an appropriate tone.", 6),
            rubric("Fluency", "Assesses whether the response reads naturally.", 6),
            rubric("Clarity", "Assesses whether the response is clear and direct.", 5),
            rubric("Brevity", "Assesses whether the response is appropriately concise.", 5),
            rubric("Penalty", "Penalizes unsupported or generic response details.", -3),
        ]

        report = self.evaluate(
            payload(
                rubrics=rubrics,
                prompt="Synthetic prompt with explicit tone and style requirements.",
            )
        )

        self.assertIn("Rubrics are concentrated in one dimension", " ".join(report["messages"]))
        self.assertEqual(report["signals"]["dominant_dimension"], "Natural Language Fluency")
        self.assertEqual(report["signals"]["category_coverage_signal"], "low")

    def test_chitchat_payload_uses_general_quality_signals(self) -> None:
        rubrics = [
            rubric("Social Tone", "Assesses natural social tone for the exchange.", 7),
            rubric("Context Handling", "Assesses whether the response uses the provided context.", 6, response_specific=True),
            rubric("Brevity", "Assesses whether the reply stays concise.", 5),
            rubric("Generic Reply Penalty", "Penalizes generic replies that ignore the context.", -3),
            rubric(
                "Natural Flow",
                "Assesses whether the response flows naturally.",
                5,
                dimension="Cultural Understanding and Application",
            ),
        ]

        report = self.evaluate(payload(category="Chitchat", rubrics=rubrics))

        self.assertIn(report["status"], {"pass", "warning"})
        self.assertEqual(report["signals"]["rubric_count"], 5)

    def test_writing_payload_uses_general_quality_signals(self) -> None:
        rubrics = [
            rubric("Instruction Fit", "Assesses whether explicit writing instructions are followed.", 8),
            rubric("Style Control", "Assesses whether requested style and tone are maintained.", 7),
            rubric("Format Control", "Assesses whether requested structure is preserved.", 6, dimension="Logic and Formatting"),
            rubric("Constraint Handling", "Assesses whether explicit constraints are handled.", 6, response_specific=True),
            rubric("Unsupported Addition Penalty", "Penalizes additions not supported by the prompt.", -3),
        ]

        report = self.evaluate(
            payload(
                category="Writing",
                rubrics=rubrics,
                prompt="Synthetic writing task with explicit style, tone, and formatting requirements.",
            )
        )

        self.assertIn(report["status"], {"pass", "warning"})
        self.assertEqual(report["signals"]["rubric_count"], 5)

    def test_knowledge_payload_uses_general_quality_signals(self) -> None:
        rubrics = [
            rubric("Factual Accuracy", "Assesses whether factual claims are accurate and grounded.", 9, dimension="Local Facts and Awareness"),
            rubric("Relevant Coverage", "Assesses whether the answer covers the requested scope.", 7),
            rubric("Cautious Framing", "Assesses whether uncertain claims are framed carefully.", 6),
            rubric("Case-Specific Detail", "Assesses whether relevant case details are handled.", 6, response_specific=True),
            rubric("Unsupported Claim Penalty", "Penalizes unsupported factual claims.", -4),
        ]

        report = self.evaluate(
            payload(
                category="Knowledge",
                rubrics=rubrics,
                prompt="Synthetic knowledge request involving local facts when applicable.",
            )
        )

        self.assertIn(report["status"], {"pass", "warning"})
        self.assertEqual(report["signals"]["rubric_count"], 5)


if __name__ == "__main__":
    unittest.main()
