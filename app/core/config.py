from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]

# Load .env file from root
load_dotenv(ROOT_DIR / ".env", override=True)


@dataclass(frozen=True)
class Settings:
    app_name: str = "Second Brain Research Lab"
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    postgres_dsn: str = "postgresql://postgres:postgres@127.0.0.1:5433/second_brain"
    postgres_schema: str = "research"
    ollama_base_url: str = "http://127.0.0.1:11434"
    localization_rubric_model: str = "llama3.2:3b"
    default_advisor_model: str = "hermes:latest"
    default_stress_model: str = "openhermes:latest"
    default_judge_model: str = "hermes:latest"
    default_scoring_model: str = "llama3.2:3b"
    default_rubric_model: str = "llama3.2:3b"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_default_model: str = "gemma-4-26b-a4b-it"
    gemini_models: tuple[str, ...] = (
        "gemma-4-26b-a4b-it",
        "gemini-flash-latest",
    )
    openai_api_key: str | None = None
    default_embedding_model: str = "all-MiniLM-L6-v2"
    default_embedding_dimensions: int = 384
    export_dir: Path = ROOT_DIR / "data" / "exports"
    smfp_dir: Path = ROOT_DIR / "data" / "smfp"
    smfp_signing_secret: str = "dashem-smfp-dev-secret"
    smfp_key_id: str = "dashem-ed25519-dev-01"
    smfp_public_key_id: str = "dashem-ed25519-dev-01"
    smfp_signature_mode: str = "PUBLIC_ED25519"
    smfp_private_key: str | None = None
    smfp_private_key_file: Path | None = None
    models_dir: Path = ROOT_DIR / "models"
    localization_debug_recommendation_trace: bool = False


@lru_cache
def get_settings() -> Settings:
    gemini_models = tuple(
        model.strip()
        for model in os.environ.get(
            "GEMINI_MODELS",
            ",".join(Settings.gemini_models),
        ).split(",")
        if model.strip()
    )

    return Settings(
        app_name=os.environ.get("APP_NAME", Settings.app_name),
        app_host=os.environ.get("APP_HOST", Settings.app_host),
        app_port=int(os.environ.get("APP_PORT", Settings.app_port)),
        postgres_dsn=os.environ.get("POSTGRES_DSN", Settings.postgres_dsn),
        postgres_schema=os.environ.get("POSTGRES_SCHEMA", Settings.postgres_schema),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", Settings.ollama_base_url),
        localization_rubric_model=os.environ.get(
            "LOCALIZATION_RUBRIC_MODEL",
            Settings.localization_rubric_model,
        ),
        default_advisor_model=os.environ.get(
            "DEFAULT_ADVISOR_MODEL",
            Settings.default_advisor_model,
        ),
        default_stress_model=os.environ.get(
            "DEFAULT_STRESS_MODEL",
            Settings.default_stress_model,
        ),
        default_judge_model=os.environ.get(
            "DEFAULT_JUDGE_MODEL",
            Settings.default_judge_model,
        ),
        default_scoring_model=os.environ.get(
            "DEFAULT_SCORING_MODEL",
            Settings.default_scoring_model,
        ),
        default_rubric_model=os.environ.get(
            "DEFAULT_RUBRIC_MODEL",
            Settings.default_rubric_model,
        ),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        gemini_base_url=os.environ.get("GEMINI_BASE_URL", Settings.gemini_base_url),
        gemini_default_model=os.environ.get(
            "GEMINI_DEFAULT_MODEL",
            Settings.gemini_default_model,
        ),
        gemini_models=gemini_models or Settings.gemini_models,
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        default_embedding_model=os.environ.get(
            "DEFAULT_EMBEDDING_MODEL",
            Settings.default_embedding_model,
        ),
        default_embedding_dimensions=int(
            os.environ.get(
                "DEFAULT_EMBEDDING_DIMENSIONS",
                Settings.default_embedding_dimensions,
            )
        ),
        export_dir=Path(os.environ.get("EXPORT_DIR", str(Settings.export_dir))),
        smfp_dir=Path(os.environ.get("SMFP_DIR", str(Settings.smfp_dir))),
        smfp_signing_secret=os.environ.get(
            "SMFP_SIGNING_SECRET",
            Settings.smfp_signing_secret,
        ),
        smfp_key_id=os.environ.get("SMFP_KEY_ID", Settings.smfp_key_id),
        smfp_public_key_id=os.environ.get(
            "SMFP_PUBLIC_KEY_ID",
            os.environ.get("SMFP_KEY_ID", Settings.smfp_public_key_id),
        ),
        smfp_signature_mode=os.environ.get(
            "SMFP_SIGNATURE_MODE",
            Settings.smfp_signature_mode,
        ),
        smfp_private_key=os.environ.get("SMFP_PRIVATE_KEY"),
        smfp_private_key_file=(
            Path(os.environ["SMFP_PRIVATE_KEY_FILE"])
            if os.environ.get("SMFP_PRIVATE_KEY_FILE")
            else None
        ),
        localization_debug_recommendation_trace=_env_bool(
            "LOCALIZATION_DEBUG_RECOMMENDATION_TRACE",
            Settings.localization_debug_recommendation_trace,
        ),
    )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
