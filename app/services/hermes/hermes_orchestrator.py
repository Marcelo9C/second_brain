from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.schemas.hermes import (
    AutomationManifest,
    HermesRunDetail,
    HermesRunStatus,
    HermesRunSummary,
    PersonaConfig,
)
from app.services.providers.base_provider import BaseProvider, ProviderPrompt

logger = logging.getLogger("hermes")


class HermesOrchestrator:
    """
    Embedded automation engine for sequential dataset generation.

    The current RLHF path is intentionally CPU/RAM friendly: one assistant model,
    two temperature variants, sequential execution, multi-turn conversations, and
    rubric-scored chosen/rejected pairs.
    """

    def __init__(
        self,
        *,
        providers: dict[str, BaseProvider],
        scoring_service: Any,
        localization_service: Any,
        default_provider: str = "ollama",
    ) -> None:
        self.providers = providers
        self.scoring_service = scoring_service
        self.localization_service = localization_service
        self.default_provider = default_provider
        self._runs: dict[str, dict[str, Any]] = {}

    def create_run(self, manifest: AutomationManifest) -> HermesRunDetail:
        active_run = self.active_run()
        if active_run:
            raise ValueError(
                f"Hermes run '{active_run['run_id']}' is already {active_run['status']}."
            )
        run_id = uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        run: dict[str, Any] = {
            "run_id": run_id,
            "status": HermesRunStatus.PENDING,
            "created_at": now,
            "completed_at": None,
            "manifest": manifest,
            "results": [],
            "progress": {
                "stage": "created",
                "current_persona": None,
                "current_conversation": None,
                "current_turn": None,
                "current_model": None,
                "last_update_at": now,
                "context": {},
                "events": [
                    {
                        "at": now,
                        "message": "Run criada e aguardando execucao.",
                    }
                ],
                "personas_done": 0,
                "personas_total": len(manifest.personas),
                "results_total_estimate": (
                    len(manifest.personas)
                    * manifest.num_conversations
                    * manifest.num_turns
                ),
            },
            "error": None,
            "cancel_requested": False,
        }
        self._runs[run_id] = run
        return self._to_detail(run)

    def active_run(self) -> dict[str, Any] | None:
        active_statuses = {HermesRunStatus.PENDING, HermesRunStatus.PROCESSING}
        return next(
            (
                run
                for run in self._runs.values()
                if run.get("status") in active_statuses
            ),
            None,
        )

    def cancel_run(self, run_id: str) -> HermesRunDetail | None:
        run = self._runs.get(run_id)
        if not run:
            return None
        if run.get("status") in {
            HermesRunStatus.SUCCESS,
            HermesRunStatus.FAILED,
            HermesRunStatus.CANCELED,
        }:
            return self._to_detail(run)
        run["cancel_requested"] = True
        run["error"] = "Cancellation requested; stopping after the current model call."
        if run.get("status") == HermesRunStatus.PENDING:
            self._mark_canceled(run)
        return self._to_detail(run)

    def get_run(self, run_id: str) -> HermesRunDetail | None:
        run = self._runs.get(run_id)
        return self._to_detail(run) if run else None

    def list_runs(self) -> list[HermesRunSummary]:
        return [
            HermesRunSummary(
                run_id=r["run_id"],
                status=r["status"],
                created_at=r["created_at"],
                completed_at=r.get("completed_at"),
                persona_count=len(r["manifest"].personas),
                results_count=len(r.get("results", [])),
                error=r.get("error"),
            )
            for r in sorted(
                self._runs.values(),
                key=lambda x: x["created_at"],
                reverse=True,
            )
        ]

    async def execute_automation(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if not run:
            logger.error("Run %s not found.", run_id)
            return

        manifest: AutomationManifest = run["manifest"]
        if self._is_cancel_requested(run):
            self._mark_canceled(run)
            return
        run["status"] = HermesRunStatus.PROCESSING
        self._set_progress(run, stage="starting")
        self._add_event(run, "Execucao iniciada.")
        logger.info(
            "Hermes Run [%s] started: personas=%d stress=%s assistant=%s temps=(%.2f, %.2f)",
            run_id,
            len(manifest.personas),
            manifest.stress_model,
            self._assistant_model(manifest),
            manifest.temperature_low,
            manifest.temperature_high,
        )

        try:
            self._set_progress(run, stage="loading rubrics")
            self._add_event(run, f"Carregando rubricas do case {manifest.rubric_set_id}.")
            rubrics = self._fetch_rubrics(manifest.rubric_set_id)
            if not rubrics:
                raise ValueError(
                    f"Rubric set '{manifest.rubric_set_id}' not found or empty."
                )

            for idx, persona in enumerate(manifest.personas):
                if self._is_cancel_requested(run):
                    self._mark_canceled(run)
                    return
                self._set_progress(
                    run,
                    stage="generating stress prompts",
                    current_persona=persona.name,
                    personas_done=idx,
                )
                self._set_context(
                    run,
                    persona=persona.model_dump(),
                    prompt=(
                        f"Gerar {manifest.num_conversations} primeira(s) mensagem(ns) "
                        f"para {persona.name} no contexto {persona.context}."
                    ),
                    history=[],
                    candidates=[],
                )
                self._add_event(run, f"Persona ativa: {persona.name}.")
                logger.info(
                    "Persona %d/%d: %s (%s)",
                    idx + 1,
                    len(manifest.personas),
                    persona.name,
                    persona.context,
                )

                seeds = await self._generate_stress_prompts(
                    run,
                    persona,
                    manifest.stress_model,
                    manifest.num_conversations,
                )
                if self._is_cancel_requested(run):
                    self._mark_canceled(run)
                    return
                logger.info("Generated %d conversation seeds.", len(seeds))

                for conversation_idx, first_user_message in enumerate(seeds):
                    if self._is_cancel_requested(run):
                        self._mark_canceled(run)
                        return
                    self._set_progress(
                        run,
                        stage="running conversation",
                        current_conversation=conversation_idx + 1,
                    )
                    history: list[dict[str, str]] = []
                    user_message = first_user_message
                    self._set_context(
                        run,
                        prompt=user_message,
                        history=[],
                        candidates=[],
                    )
                    self._add_event(
                        run,
                        f"Conversa {conversation_idx + 1}: seed pronta.",
                    )

                    for turn_idx in range(manifest.num_turns):
                        if self._is_cancel_requested(run):
                            self._mark_canceled(run)
                            return
                        self._set_progress(
                            run,
                            stage="generating candidates",
                            current_turn=turn_idx + 1,
                        )
                        self._set_context(
                            run,
                            prompt=user_message,
                            history=self._history_window(
                                history, manifest.max_history_turns
                            ),
                            candidates=[],
                        )
                        candidates = await self._generate_temperature_candidates(
                            run=run,
                            manifest=manifest,
                            user_message=user_message,
                            history=history,
                        )
                        if self._is_cancel_requested(run):
                            self._mark_canceled(run)
                            return

                        self._set_progress(run, stage="scoring candidates")
                        self._set_context(run, candidates=candidates)
                        self._add_event(run, "Candidatas geradas; iniciando scoring.")
                        scoring = self._score_candidates(
                            user_message,
                            candidates,
                            rubrics,
                            manifest,
                        )
                        preference = scoring.get("preference") or {}
                        chosen_id = preference.get("chosen_candidate_id")
                        rejected_id = preference.get("rejected_candidate_id")
                        chosen_candidate = self._find_candidate(candidates, chosen_id)

                        run["results"].append(
                            {
                                "persona": persona.model_dump(),
                                "conversation_index": conversation_idx,
                                "turn_index": turn_idx,
                                "prompt": user_message,
                                "history_window": self._history_window(
                                    history, manifest.max_history_turns
                                ),
                                "candidates": candidates,
                                "scoring": scoring,
                                "preference_pair": self._preference_pair(
                                    candidates,
                                    chosen_id,
                                    rejected_id,
                                ),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        self._add_event(
                            run,
                            "Resultado salvo"
                            + (
                                f" com preferencia {chosen_id}>{rejected_id}."
                                if chosen_id and rejected_id
                                else " sem par chosen/rejected."
                            ),
                        )

                        assistant_message = (
                            chosen_candidate["response_raw"]
                            if chosen_candidate
                            else candidates[0]["response_raw"]
                        )
                        history.extend(
                            [
                                {"role": "user", "content": user_message},
                                {"role": "assistant", "content": assistant_message},
                            ]
                        )

                        if turn_idx < manifest.num_turns - 1:
                            user_message = await self._generate_followup_prompt(
                                run,
                                persona,
                                manifest.stress_model,
                                history=history,
                                max_history_turns=manifest.max_history_turns,
                            )

            run["progress"]["personas_done"] = len(manifest.personas)
            self._set_progress(
                run,
                stage="completed",
                current_persona=None,
                current_conversation=None,
                current_turn=None,
                current_model=None,
            )
            self._add_event(run, "Run concluida.")
            run["status"] = HermesRunStatus.SUCCESS
            run["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.info("Hermes Run [%s] completed: %d results.", run_id, len(run["results"]))

        except Exception as error:
            run["status"] = HermesRunStatus.FAILED
            run["completed_at"] = datetime.now(timezone.utc).isoformat()
            run["error"] = str(error)
            self._set_progress(run, stage="failed", current_model=None)
            self._add_event(run, f"Falha: {error}")
            logger.error("Hermes Run [%s] failed: %s", run_id, error, exc_info=True)

    async def _generate_temperature_candidates(
        self,
        *,
        run: dict[str, Any],
        manifest: AutomationManifest,
        user_message: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        assistant_model = self._assistant_model(manifest)
        candidates: list[dict[str, Any]] = []
        for variant_id, temperature in (
            ("A", manifest.temperature_low),
            ("B", manifest.temperature_high),
        ):
            if self._is_cancel_requested(run):
                break
            self._set_progress(
                run,
                stage="calling assistant model",
                current_model=f"{assistant_model}@temp={temperature}",
            )
            self._add_event(
                run,
                f"Chamando assistant {assistant_model} com temperature={temperature}.",
            )
            response_raw = await self._get_model_response(
                user_message,
                assistant_model,
                history=history,
                max_history_turns=manifest.max_history_turns,
                temperature=temperature,
            )
            candidates.append(
                {
                    "id": variant_id,
                    "label": f"{assistant_model} temp={temperature}",
                    "model": assistant_model,
                    "temperature": temperature,
                    "response_raw": response_raw,
                }
            )
            if self._is_cancel_requested(run):
                break
            await asyncio.sleep(1)
        return candidates

    def _is_cancel_requested(self, run: dict[str, Any]) -> bool:
        return bool(run.get("cancel_requested"))

    def _mark_canceled(self, run: dict[str, Any]) -> None:
        run["status"] = HermesRunStatus.CANCELED
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        run["error"] = run.get("error") or "Run canceled."
        self._set_progress(
            run,
            stage="canceled",
            current_persona=None,
            current_conversation=None,
            current_turn=None,
            current_model=None,
        )
        self._add_event(run, "Run cancelada.")

    def _set_progress(self, run: dict[str, Any], **updates: Any) -> None:
        run.setdefault("progress", {}).update(updates)
        run["progress"]["last_update_at"] = datetime.now(timezone.utc).isoformat()

    def _set_context(self, run: dict[str, Any], **updates: Any) -> None:
        progress = run.setdefault("progress", {})
        context = progress.setdefault("context", {})
        context.update(updates)
        progress["last_update_at"] = datetime.now(timezone.utc).isoformat()

    def _add_event(self, run: dict[str, Any], message: str) -> None:
        progress = run.setdefault("progress", {})
        events = progress.setdefault("events", [])
        events.append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "message": message,
            }
        )
        del events[:-40]
        progress["last_update_at"] = datetime.now(timezone.utc).isoformat()

    async def _generate_stress_prompts(
        self,
        run: dict[str, Any],
        persona: PersonaConfig,
        stress_model: str,
        count: int,
    ) -> list[str]:
        provider_name, model_name = self._parse_model_ref(stress_model)
        provider = self._get_provider(provider_name)
        system_contract = (
            "You are an adversarial prompt engineer for QA stress testing.\n"
            "Generate realistic, challenging first user messages for independent "
            "multi-turn conversations.\n\n"
            "RULES:\n"
            f"- Generate exactly {count} distinct first messages.\n"
            "- Each item must be a realistic user message, not a meta-instruction.\n"
            "- Include ambiguity, contradictions, emotional language, incomplete "
            "information, or multi-part requests when natural.\n"
            "- Return ONLY a JSON array of strings. No markdown fences.\n"
            "- Write prompts in Portuguese (pt-BR).\n"
        )
        task_payload = (
            f"PERSONA: {persona.name}\n"
            f"CONTEXT: {persona.context}\n"
            f"PROFILE: {persona.profile}\n\n"
            f"Generate {count} independent conversation starters for this persona."
        )
        self._set_progress(
            run,
            stage="calling stress model",
            current_model=f"{stress_model}@temp=0.7",
        )
        self._set_context(run, prompt=task_payload)
        self._add_event(run, f"Chamando stress model {stress_model}.")
        result = await asyncio.to_thread(
            provider.generate,
            prompt=ProviderPrompt(
                system_contract=system_contract,
                task_payload=task_payload,
            ),
            model=model_name,
            temperature=0.7,
        )
        prompts = self._parse_stress_prompts(result.text, count)
        self._add_event(run, f"Stress model retornou {len(prompts)} seed(s).")
        return prompts

    async def _generate_followup_prompt(
        self,
        run: dict[str, Any],
        persona: PersonaConfig,
        stress_model: str,
        *,
        history: list[dict[str, str]],
        max_history_turns: int,
    ) -> str:
        provider_name, model_name = self._parse_model_ref(stress_model)
        provider = self._get_provider(provider_name)
        system_contract = (
            "You are simulating the next user turn in a realistic pt-BR conversation.\n"
            "Stay in persona and continue from the provided recent history.\n\n"
            "RULES:\n"
            "- Return only a JSON object with this shape: {\"message\": \"...\"}.\n"
            "- Do not answer as the assistant.\n"
            "- Do not include labels, markdown, or extra prose.\n"
        )
        task_payload = (
            f"PERSONA: {persona.name}\n"
            f"CONTEXT: {persona.context}\n"
            f"PROFILE: {persona.profile}\n\n"
            "RECENT HISTORY:\n"
            f"{self._format_history(self._history_window(history, max_history_turns))}\n\n"
            "Next user message:"
        )
        self._set_progress(
            run,
            stage="calling stress follow-up model",
            current_model=f"{stress_model}@temp=0.7",
        )
        self._set_context(
            run,
            prompt=task_payload,
            history=self._history_window(history, max_history_turns),
        )
        self._add_event(run, f"Chamando follow-up model {stress_model}.")
        result = await asyncio.to_thread(
            provider.generate,
            prompt=ProviderPrompt(
                system_contract=system_contract,
                task_payload=task_payload,
            ),
            model=model_name,
            temperature=0.7,
        )
        message = self._clean_generated_message(result.text)
        self._add_event(run, "Follow-up de usuario gerado.")
        return message

    async def _get_model_response(
        self,
        prompt: str,
        model: str,
        *,
        history: list[dict[str, str]] | None = None,
        max_history_turns: int = 0,
        temperature: float | None = None,
    ) -> str:
        provider_name, model_name = self._parse_model_ref(model)
        provider = self._get_provider(provider_name)
        history_window = self._history_window(history or [], max_history_turns)
        task_payload = prompt
        if history_window:
            task_payload = (
                "RECENT HISTORY:\n"
                f"{self._format_history(history_window)}\n\n"
                f"CURRENT USER MESSAGE:\n{prompt}"
            )
        result = await asyncio.to_thread(
            provider.generate,
            prompt=ProviderPrompt(
                system_contract=(
                    "You are a helpful AI assistant. Respond naturally and helpfully "
                    "to the user's current message. Respond in Portuguese (pt-BR)."
                ),
                task_payload=task_payload,
            ),
            model=model_name,
            temperature=temperature,
        )
        return result.text

    def _score_candidates(
        self,
        prompt: str,
        candidates: list[dict[str, Any]],
        rubrics: list[dict[str, Any]],
        manifest: AutomationManifest,
    ) -> dict[str, Any]:
        payload = {
            "locale": manifest.locale,
            "category": manifest.category,
            "prompt": prompt,
            "rubrics": rubrics,
            "candidate_responses": candidates,
            "provider": manifest.scoring_provider or self.default_provider,
            "model": manifest.scoring_model,
        }
        try:
            return self.scoring_service.score(payload)
        except Exception as error:
            logger.warning("Scoring failed: %s", error)
            return {
                "success": False,
                "error": str(error),
                "candidate_scores": [],
                "preference": {
                    "chosen_candidate_id": None,
                    "rejected_candidate_id": None,
                    "margin": None,
                    "ranking": [],
                    "warnings": [str(error)],
                },
            }

    def _fetch_rubrics(self, rubric_set_id: str) -> list[dict[str, Any]] | None:
        case = self.localization_service.get_case(rubric_set_id)
        if not case:
            return None
        rubrics = case.get("rubrics")
        if not isinstance(rubrics, list) or not rubrics:
            return None
        return rubrics

    def _assistant_model(self, manifest: AutomationManifest) -> str:
        if manifest.response_models:
            return manifest.response_models[0]
        raise ValueError("Hermes requires an explicit assistant model.")

    def _parse_model_ref(self, model_ref: str) -> tuple[str, str]:
        if "/" in model_ref:
            provider, model = model_ref.split("/", 1)
            return provider, model
        return "ollama", model_ref

    def _get_provider(self, provider_name: str) -> BaseProvider:
        provider = self.providers.get(provider_name)
        if not provider:
            available = ", ".join(sorted(self.providers.keys()))
            raise ValueError(
                f"Provider '{provider_name}' not registered. Available: {available}"
            )
        return provider

    def _parse_stress_prompts(self, raw: str, expected_count: int) -> list[str]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item][:expected_count]
        except json.JSONDecodeError:
            pass

        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if item][:expected_count]
            except json.JSONDecodeError:
                pass

        lines = [
            line.strip().lstrip("0123456789.-) ").strip('"').strip("'")
            for line in raw.strip().split("\n")
            if line.strip() and not line.strip().startswith("{")
        ]
        return [line for line in lines if len(line) > 10][:expected_count]

    def _history_window(
        self,
        history: list[dict[str, str]],
        max_history_turns: int,
    ) -> list[dict[str, str]]:
        if max_history_turns <= 0:
            return []
        return history[-max_history_turns * 2 :]

    def _format_history(self, history: list[dict[str, str]]) -> str:
        return "\n".join(
            f"{message.get('role', 'unknown').upper()}: {message.get('content', '')}"
            for message in history
        )

    def _find_candidate(
        self,
        candidates: list[dict[str, Any]],
        candidate_id: Any,
    ) -> dict[str, Any] | None:
        if not candidate_id:
            return None
        return next(
            (
                candidate
                for candidate in candidates
                if candidate.get("id") == candidate_id
            ),
            None,
        )

    def _preference_pair(
        self,
        candidates: list[dict[str, Any]],
        chosen_id: Any,
        rejected_id: Any,
    ) -> dict[str, Any] | None:
        chosen = self._find_candidate(candidates, chosen_id)
        rejected = self._find_candidate(candidates, rejected_id)
        if not chosen or not rejected:
            return None
        return {
            "chosen_id": chosen_id,
            "rejected_id": rejected_id,
            "chosen": chosen["response_raw"],
            "rejected": rejected["response_raw"],
            "chosen_label": chosen["label"],
            "rejected_label": rejected["label"],
        }

    def _clean_generated_message(self, raw: str) -> str:
        text = raw.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and parsed.get("message"):
                text = str(parsed["message"]).strip()
            elif isinstance(parsed, str):
                text = parsed.strip()
        except json.JSONDecodeError:
            pass
        for prefix in ("USER:", "Usuario:", "Usuário:", "user:"):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
        return text.strip().strip('"').strip("'")

    def _to_detail(self, run: dict[str, Any]) -> HermesRunDetail:
        return HermesRunDetail(
            run_id=run["run_id"],
            status=run["status"],
            created_at=run["created_at"],
            completed_at=run.get("completed_at"),
            persona_count=len(run["manifest"].personas),
            results_count=len(run.get("results", [])),
            error=run.get("error"),
            manifest=run["manifest"],
            results=run.get("results", []),
            progress=run.get("progress", {}),
        )
