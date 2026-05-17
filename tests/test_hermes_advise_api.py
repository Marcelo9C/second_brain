import unittest

from fastapi.testclient import TestClient

from app.main import app


class HermesAdviseApiTest(unittest.TestCase):
    def test_advise_endpoint_returns_deterministic_recommendation(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/hermes/advise",
            json={
                "objective": "generate_dpo_pairs",
                "context": {
                    "current_models": {
                        "generation": "llama3.2:3b",
                        "judge": "llama3.2:3b",
                    }
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "advise")
        self.assertEqual(
            payload["recommendations"][0]["action"],
            "diversify_model_families",
        )
        self.assertEqual(
            payload["recommendations"][0]["reason"],
            "shared_family_may_reduce_judgment_independence",
        )
        self.assertAlmostEqual(payload["recommendations"][0]["confidence"], 0.92)
        self.assertTrue(payload["recommendations"][0]["requires_confirmation"])
        self.assertEqual(
            payload["proposed_plan"][0]["provenance"]["selected_by"],
            "recommendation",
        )

    def test_advise_endpoint_does_not_start_runs(self) -> None:
        client = TestClient(app)

        before = client.get("/api/hermes/runs")
        self.assertEqual(before.status_code, 200)
        before_count = len(before.json())

        response = client.post(
            "/api/hermes/advise",
            json={
                "objective": "generate_dpo_pairs",
                "context": {
                    "rubric": {
                        "criteria_count": 2,
                    }
                },
            },
        )
        self.assertEqual(response.status_code, 200)

        after = client.get("/api/hermes/runs")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(len(after.json()), before_count)


if __name__ == "__main__":
    unittest.main()
