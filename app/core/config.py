from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]

# Load .env file from root
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Second Brain Research Lab"
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    postgres_dsn: str = "postgresql://postgres:postgres@127.0.0.1:5433/second_brain"
    postgres_schema: str = "research"
    ollama_base_url: str = "http://127.0.0.1:11434"
    gemini_api_key: str | None = None
    default_embedding_model: str = "all-MiniLM-L6-v2"
    default_embedding_dimensions: int = 384
    export_dir: Path = ROOT_DIR / "data" / "exports"
    models_dir: Path = ROOT_DIR / "models"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.environ.get("APP_NAME", Settings.app_name),
        app_host=os.environ.get("APP_HOST", Settings.app_host),
        app_port=int(os.environ.get("APP_PORT", Settings.app_port)),
        postgres_dsn=os.environ.get("POSTGRES_DSN", Settings.postgres_dsn),
        postgres_schema=os.environ.get("POSTGRES_SCHEMA", Settings.postgres_schema),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", Settings.ollama_base_url),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
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
    )
