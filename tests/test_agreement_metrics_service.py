import unittest

from app.services.agreement_metrics_service import AgreementMetricsService


class AgreementMetricsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgreementMetricsService()

    def test_computes_perfect_pairwise_kappa(self) -> None:
        result = self.service.compute(
            [
                {"item_id": "1", "rater_id": "human", "label": "A"},
                {"item_id": "1", "rater_id": "judge", "label": "A"},
                {"item_id": "2", "rater_id": "human", "label": "B"},
                {"item_id": "2", "rater_id": "judge", "label": "B"},
            ],
            primary_rater_id="human",
            secondary_rater_id="judge",
        )

        self.assertEqual(result["cohens_kappa"]["value"], 1.0)
        self.assertEqual(result["cohens_kappa"]["observed_agreement"], 1.0)
        self.assertEqual(result["krippendorff_alpha"]["value"], 1.0)

    def test_computes_partial_pairwise_kappa(self) -> None:
        result = self.service.compute(
            [
                {"item_id": "1", "rater_id": "human", "label": "A"},
                {"item_id": "1", "rater_id": "judge", "label": "A"},
                {"item_id": "2", "rater_id": "human", "label": "A"},
                {"item_id": "2", "rater_id": "judge", "label": "B"},
                {"item_id": "3", "rater_id": "human", "label": "B"},
                {"item_id": "3", "rater_id": "judge", "label": "B"},
                {"item_id": "4", "rater_id": "human", "label": "B"},
                {"item_id": "4", "rater_id": "judge", "label": "A"},
            ],
            primary_rater_id="human",
            secondary_rater_id="judge",
        )

        self.assertEqual(result["cohens_kappa"]["overlap_count"], 4)
        self.assertEqual(result["cohens_kappa"]["observed_agreement"], 0.5)
        self.assertEqual(result["cohens_kappa"]["value"], 0.0)

    def test_alpha_handles_three_raters(self) -> None:
        result = self.service.compute(
            [
                {"item_id": "1", "rater_id": "human", "label": "chosen_A"},
                {"item_id": "1", "rater_id": "gemini", "label": "chosen_A"},
                {"item_id": "1", "rater_id": "ollama", "label": "chosen_B"},
                {"item_id": "2", "rater_id": "human", "label": "chosen_B"},
                {"item_id": "2", "rater_id": "gemini", "label": "chosen_B"},
                {"item_id": "2", "rater_id": "ollama", "label": "chosen_B"},
            ]
        )

        self.assertIsNone(result["cohens_kappa"])
        self.assertEqual(result["metadata"]["rater_count"], 3)
        self.assertEqual(result["krippendorff_alpha"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
