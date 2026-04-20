from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class LLMOrchestratorService:
    def __init__(self, ollama_base_url: str, models_dir: Path | None = None) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.models_dir = models_dir
        self._local_models_cache: dict[str, Any] = {}

    def _build_request(self, path: str, payload: dict[str, Any]) -> Request:
        return Request(
            f"{self.ollama_base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def generate_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        generation: dict[str, Any],
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        options = {
            "seed": generation["seed"],
            "temperature": generation["temperature"],
            "top_p": generation["top_p"],
            "top_k": generation["top_k"],
        }
        if generation.get("repeat_penalty") is not None:
            options["repeat_penalty"] = generation["repeat_penalty"]
        if generation.get("max_tokens") is not None:
            options["num_predict"] = generation["max_tokens"]

        payload: dict[str, Any] = {
            "model": generation["model_name"],
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if keep_alive:
            payload["keep_alive"] = keep_alive

        request = self._build_request("/api/chat", payload)
        with urlopen(request, timeout=600) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def list_models(self) -> list[dict[str, Any]]:
        request = Request(f"{self.ollama_base_url}/api/tags", method="GET")
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                return data.get("models", [])
        except Exception:
            return []

    def generate_embeddings(self, model: str, prompt: str) -> list[float]:
        if model.startswith("local:"):
            local_name = model.replace("local:", "")
            return self._generate_local_embedding(local_name, prompt)

        payload = {
            "model": model,
            "prompt": prompt,
        }
        request = self._build_request("/api/embeddings", payload)
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                return data.get("embedding", [])
        except Exception:
            # Fallback for mock if ollama fails or embedding model is not present
            return [0.0] * 384

    def _generate_local_embedding(self, model_name: str, prompt: str) -> list[float]:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return [0.0] * 384

        if model_name not in self._local_models_cache:
            if not self.models_dir:
                return [0.0] * 384
            
            model_path = self.models_dir / model_name
            if not model_path.exists():
                return [0.0] * 384
            
            # Load model and cache it
            self._local_models_cache[model_name] = SentenceTransformer(str(model_path))

        model = self._local_models_cache[model_name]
        embedding = model.encode(prompt)
        return embedding.tolist()

    def health(self) -> dict[str, Any]:
        """
        Check health of Ollama service and verify model availability.
        """
        request = Request(f"{self.ollama_base_url}/api/tags", method="GET")
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                models = data.get("models", [])
                
                # We are only "truly" ok if we can reach the service AND get some models
                has_models = isinstance(models, list) and len(models) > 0
                
                return {
                    "ok": True,
                    "ready": has_models,
                    "url": self.ollama_base_url,
                    "model_count": len(models) if isinstance(models, list) else 0,
                    "models": models if isinstance(models, list) else [],
                    "error": None if has_models else "Service up but 0 models found. Pull a model with 'ollama pull'."
                }
        except URLError as error:
            return {
                "ok": False,
                "ready": False,
                "url": self.ollama_base_url,
                "model_count": 0,
                "models": [],
                "error": f"Ollama unreachable: {str(error.reason) if hasattr(error, 'reason') else str(error)}"
            }
        except Exception as error:
            return {
                "ok": False,
                "ready": False,
                "url": self.ollama_base_url,
                "model_count": 0,
                "models": [],
                "error": f"Unexpected health check error: {str(error)}"
            }
