from functools import lru_cache

from app.core.config import Settings, get_settings
from app.db import Database
from app.repositories.annotations import AnnotationSxSRepository
from app.repositories.documents import DocumentChunkRepository
from app.repositories.experiments import ExperimentRepository
from app.repositories.retrieval_traces import RetrievalTraceRepository
from app.services.export_service import AnnotationExportService
from app.services.llm_orchestrator import LLMOrchestratorService
from app.services.rag_pipeline import RAGPipelineService


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
def get_llm_service() -> LLMOrchestratorService:
    settings: Settings = get_settings()
    return LLMOrchestratorService(settings.ollama_base_url)


@lru_cache
def get_rag_service() -> RAGPipelineService:
    return RAGPipelineService(
        document_repository=get_document_chunk_repository(),
        retrieval_trace_repository=get_retrieval_trace_repository(),
        llm_service=get_llm_service(),
    )


@lru_cache
def get_annotation_export_service() -> AnnotationExportService:
    settings = get_settings()
    return AnnotationExportService(
        annotation_repository=get_annotation_repository(),
        export_dir=settings.export_dir,
    )
