from functools import lru_cache

from app.core.config import ROOT_DIR, Settings, get_settings
from app.db import Database
from app.repositories.annotations import AnnotationSxSRepository
from app.repositories.documents import DocumentChunkRepository
from app.repositories.experiments import ExperimentRepository
from app.repositories.localization_repository import LocalizationRubricCaseRepository
from app.repositories.retrieval_traces import RetrievalTraceRepository
from app.services.export_service import AnnotationExportService
from app.services.localization_service import LocalizationService
from app.services.llm_orchestrator import LLMOrchestratorService
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.ollama_provider import OllamaProvider
from app.services.rag_pipeline import RAGPipelineService
from app.services.rubric_generation_service import RubricGenerationService
from app.services.rubric_validation_service import RubricValidationService


@lru_cache
def get_db() -> Database:
    settings = get_settings()
    return Database(settings.postgres_dsn)


@lru_cache
def get_experiment_repository() -> ExperimentRepository:
    return ExperimentRepository(get_db(), get_settings().postgres_schema)


@lru_cache
def get_retrieval_trace_repository() -> RetrievalTraceRepository:
    return RetrievalTraceRepository(get_db(), get_settings().postgres_schema)


@lru_cache
def get_document_chunk_repository() -> DocumentChunkRepository:
    return DocumentChunkRepository(get_db(), get_settings().postgres_schema)


@lru_cache
def get_annotation_repository() -> AnnotationSxSRepository:
    return AnnotationSxSRepository(get_db(), get_settings().postgres_schema)


@lru_cache
def get_localization_repository() -> LocalizationRubricCaseRepository:
    return LocalizationRubricCaseRepository(get_db(), get_settings().postgres_schema)


@lru_cache
def get_rubric_validation_service() -> RubricValidationService:
    return RubricValidationService()


@lru_cache
def get_llm_service() -> LLMOrchestratorService:
    settings: Settings = get_settings()
    return LLMOrchestratorService(settings.ollama_base_url, settings.models_dir)


@lru_cache
def get_rag_service() -> RAGPipelineService:
    settings = get_settings()
    return RAGPipelineService(
        document_repository=get_document_chunk_repository(),
        retrieval_trace_repository=get_retrieval_trace_repository(),
        llm_service=get_llm_service(),
        models_dir=settings.models_dir,
    )


@lru_cache
def get_annotation_export_service() -> AnnotationExportService:
    settings = get_settings()
    return AnnotationExportService(
        annotation_repository=get_annotation_repository(),
        export_dir=settings.export_dir,
    )


@lru_cache
def get_localization_service() -> LocalizationService:
    localization_dir = ROOT_DIR / "LOCALIZATION"
    if not localization_dir.exists():
        localization_dir = ROOT_DIR / "Localization"

    return LocalizationService(
        repository=get_localization_repository(),
        localization_dir=localization_dir,
        validation_service=get_rubric_validation_service(),
    )


@lru_cache
def get_rubric_generation_service() -> RubricGenerationService:
    settings = get_settings()
    return RubricGenerationService(
        providers={
            "ollama": OllamaProvider(
                base_url=settings.ollama_base_url,
                fallback_model=settings.localization_rubric_model,
            ),
            "gemini": GeminiProvider(
                api_key=settings.gemini_api_key,
                base_url=settings.gemini_base_url,
                default_model=settings.gemini_default_model,
                models=settings.gemini_models,
            ),
        },
        default_provider="ollama",
    )
