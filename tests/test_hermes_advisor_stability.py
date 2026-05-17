import hashlib
import json
import time
import unittest
from pathlib import Path

from app.schemas.hermes_advise import HermesAdviseRequest
from app.services.hermes.hermes_advisor import HermesAdvisor


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hermes_advise"
LATENCY_BUDGET_SECONDS = 0.05


class HermesAdvisorStabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.advisor = HermesAdvisor()

    def test_golden_fixtures_match_snapshots(self) -> None:
        for path in sorted(FIXTURE_DIR.glob("*.json")):
            with self.subTest(fixture=path.name):
                fixture = self._read_fixture(path)
                response = self.advisor.advise(
                    HermesAdviseRequest(**fixture["request"])
                )
                payload = response.model_dump(mode="json")
                snapshot = fixture["snapshot"]

                self.assertEqual(
                    [item["action"] for item in payload["recommendations"]],
                    snapshot["actions"],
                )
                self.assertEqual(
                    {
                        item["action"]: item["confidence"]
                        for item in payload["recommendations"]
                    },
                    snapshot["confidences"],
                )
                self.assertEqual(
                    payload["advisor_trace"]["rules_triggered"],
                    snapshot["rules_triggered"],
                )
                self.assertEqual(
                    payload["advisor_trace"]["response_hash"],
                    snapshot["response_hash"],
                )

    def test_same_payload_has_same_response_hash_for_100_calls(self) -> None:
        fixture = self._read_fixture(FIXTURE_DIR / "missing_provenance.json")
        request = HermesAdviseRequest(**fixture["request"])

        hashes = {
            self.advisor.advise(request).advisor_trace.response_hash
            for _ in range(100)
        }

        self.assertEqual(hashes, {fixture["snapshot"]["response_hash"]})

    def test_response_payload_hash_is_stable_for_100_calls(self) -> None:
        fixture = self._read_fixture(FIXTURE_DIR / "same_family_models.json")
        request = HermesAdviseRequest(**fixture["request"])

        hashes = {
            self._hash_response_payload(self.advisor.advise(request).model_dump(mode="json"))
            for _ in range(100)
        }

        self.assertEqual(len(hashes), 1)

    def test_local_latency_budget_under_50ms(self) -> None:
        fixture = self._read_fixture(FIXTURE_DIR / "local_model_conflict.json")
        request = HermesAdviseRequest(**fixture["request"])

        started = time.perf_counter()
        for _ in range(100):
            self.advisor.advise(request)
        duration = time.perf_counter() - started

        self.assertLess(duration / 100, LATENCY_BUDGET_SECONDS)

    def test_advisor_trace_contract(self) -> None:
        fixture = self._read_fixture(FIXTURE_DIR / "low_margin.json")
        response = self.advisor.advise(HermesAdviseRequest(**fixture["request"]))

        trace = response.advisor_trace
        self.assertIsNotNone(trace)
        self.assertEqual(len(trace.request_id), 64)
        self.assertEqual(len(trace.response_hash), 64)
        self.assertIn("preference_margin", trace.rules_evaluated)
        self.assertEqual(trace.rules_triggered, ["preference_margin"])

    def _read_fixture(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _hash_response_payload(self, payload: dict) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    unittest.main()
