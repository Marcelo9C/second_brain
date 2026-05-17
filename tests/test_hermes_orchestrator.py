import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from app.schemas.hermes import AutomationManifest, PersonaConfig
from app.services.hermes.hermes_orchestrator import HermesOrchestrator
from app.services.providers.base_provider import BaseProvider, ProviderPrompt, ProviderResult


class FakeHermesProvider(BaseProvider):
    name = "ollama"
    label = "Fake Ollama"
    implemented = True

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def list_models(self) -> list[dict]:
        return [{"name": "assistant-model"}, {"name": "stress-model"}]

    def generate(
        self,
        *,
        prompt: ProviderPrompt | str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> ProviderResult:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "temperature": temperature,
            }
        )
        system_contract = prompt.system_contract if isinstance(prompt, ProviderPrompt) else ""
        task_payload = prompt.task_payload if isinstance(prompt, ProviderPrompt) else str(prompt)
        if "conversation starters" in system_contract:
            text = json.dumps(["Primeira mensagem"])
        elif "next user turn" in system_contract:
            text = "Pode detalhar melhor?"
        else:
            text = f"Resposta temp={temperature} history={'RECENT HISTORY' in task_payload}"
        return ProviderResult(
            text=text,
            provider_used=self.name,
            model_used=model or "assistant-model",
            exact_url_called="http://fake.local",
            response_status=200,
            duration_ms=1,
        )


class FakeLocalizationService:
    def get_case(self, rubric_set_id: str) -> dict:
        return {
            "rubrics": [
                {
                    "Rubric_dimensions": "Helpfulness",
                    "Rubric_title": "Helpful answer",
                    "Rubrics_description": "Rewards helpful responses.",
                    "Rubrics_weight": 10,
                    "is_response_specific": False,
                }
            ]
        }


class FakeScoringService:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def score(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {
            "success": True,
            "candidate_scores": [
                {"candidate_id": "A", "total_score": 1},
                {"candidate_id": "B", "total_score": 2},
            ],
            "preference": {
                "chosen_candidate_id": "B",
                "rejected_candidate_id": "A",
                "margin": 1,
                "ranking": ["B", "A"],
                "warnings": [],
            },
        }


class HermesOrchestratorTest(unittest.TestCase):
    def manifest(self, **overrides) -> AutomationManifest:
        payload = {
            "personas": [
                PersonaConfig(
                    name="Cliente",
                    context="Suporte",
                    profile="Usuario impaciente",
                )
            ],
            "stress_model": "stress-model",
            "response_models": ["assistant-model"],
            "rubric_set_id": "rubric-1",
            "num_conversations": 1,
            "num_turns": 2,
            "max_history_turns": 1,
            "temperature_low": 0.2,
            "temperature_high": 0.8,
            "scoring_model": "judge-model",
        }
        payload.update(overrides)
        return AutomationManifest(**payload)

    def orchestrator(
        self,
        provider: FakeHermesProvider | None = None,
        scoring_service: FakeScoringService | None = None,
    ) -> HermesOrchestrator:
        return HermesOrchestrator(
            providers={"ollama": provider or FakeHermesProvider()},
            scoring_service=scoring_service or FakeScoringService(),
            localization_service=FakeLocalizationService(),
        )

    def test_generates_multiturn_temperature_candidates_with_scored_pair(self) -> None:
        provider = FakeHermesProvider()
        scoring_service = FakeScoringService()
        orchestrator = self.orchestrator(provider, scoring_service)
        manifest = self.manifest()
        run = orchestrator.create_run(manifest)

        with patch(
            "app.services.hermes.hermes_orchestrator.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            asyncio.run(orchestrator.execute_automation(run.run_id))

        completed = orchestrator.get_run(run.run_id)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, "success")
        self.assertEqual(completed.results_count, 2)

        first_result = completed.results[0]
        self.assertEqual(
            [candidate["temperature"] for candidate in first_result["candidates"]],
            [0.2, 0.8],
        )
        self.assertEqual(first_result["preference_pair"]["chosen_id"], "B")
        self.assertIn("temp=0.8", first_result["preference_pair"]["chosen"])

        second_result = completed.results[1]
        self.assertEqual(len(second_result["history_window"]), 2)
        self.assertEqual(second_result["history_window"][1]["role"], "assistant")
        self.assertIn("temp=0.8", second_result["history_window"][1]["content"])

        self.assertEqual(len(scoring_service.payloads), 2)
        self.assertEqual(scoring_service.payloads[0]["model"], "judge-model")
        assistant_temperatures = [
            call["temperature"]
            for call in provider.calls
            if call["model"] == "assistant-model"
        ]
        self.assertEqual(assistant_temperatures, [0.2, 0.8, 0.2, 0.8])

    def test_rejects_new_run_when_another_run_is_active(self) -> None:
        orchestrator = self.orchestrator()
        orchestrator.create_run(self.manifest())

        with self.assertRaisesRegex(ValueError, "already"):
            orchestrator.create_run(self.manifest())

    def test_cancel_pending_run_marks_it_canceled(self) -> None:
        orchestrator = self.orchestrator()
        run = orchestrator.create_run(self.manifest())

        canceled = orchestrator.cancel_run(run.run_id)

        self.assertIsNotNone(canceled)
        self.assertEqual(canceled.status, "canceled")
        self.assertIn("Cancellation requested", canceled.error)


if __name__ == "__main__":
    unittest.main()
