from functools import lru_cache

from app.core.config import ROOT_DIR, Settings, get_settings
from app.db import Database
from app.repositories.annotations import AnnotationSxSRepository
from app.repositories.documents import DocumentChunkRepository
from app.repositories.experiments import ExperimentRepository
from app.repositories.localization_repository import LocalizationRubricCaseRepository
from app.repositories.rubric_generation_run_repository import RubricGenerationRunRepository
from app.repositories.retrieval_traces import RetrievalTraceRepository
from app.services.export_service import AnnotationExportService
from app.services.agreement_metrics_service import AgreementMetricsService
from app.services.candidate_recommendation_service import CandidateRecommendationService
from app.services.localization_service import LocalizationService
from app.services.llm_orchestrator import LLMOrchestratorService
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.ollama_provider import OllamaProvider
from app.services.rag_pipeline import RAGPipelineService
from app.services.rubric_candidate_scoring_service import RubricCandidateScoringService
from app.services.rubric_generation_service import RubricGenerationService
from app.services.rubric_validation_service import RubricValidationService
from app.services.smfp_evidence_fusion_service import SmfpEvidenceFusionService
from app.services.smfp_frequency_service import SmfpFrequencyService
from app.services.smfp_health_service import SmfpHealthService
from app.services.smfp_inference_service import SmfpInferenceService
from app.services.smfp_metadata_service import SmfpMetadataService
from app.services.smfp_ml_service import SmfpMlService
from app.services.smfp_origin_service import SmfpOriginService
from app.services.smfp_report_service import SmfpReportService
from app.services.smfp_service import SmfpService


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
def get_rubric_generation_run_repository() -> RubricGenerationRunRepository:
    return RubricGenerationRunRepository(get_db(), get_settings().postgres_schema)


@lru_cache
def get_rubric_validation_service() -> RubricValidationService:
    return RubricValidationService()


@lru_cache
def get_agreement_metrics_service() -> AgreementMetricsService:
    return AgreementMetricsService()


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
def get_smfp_service() -> SmfpService:
    settings = get_settings()
    return SmfpService(
        storage_dir=settings.smfp_dir,
        signing_secret=settings.smfp_signing_secret,
        key_id=settings.smfp_key_id,
        public_key_id=settings.smfp_public_key_id,
        signature_mode=settings.smfp_signature_mode,
        private_key=settings.smfp_private_key,
        private_key_file=settings.smfp_private_key_file,
    )


@lru_cache
def get_smfp_origin_service() -> SmfpOriginService:
    return SmfpOriginService(metadata_service=get_smfp_metadata_service())


@lru_cache
def get_smfp_metadata_service() -> SmfpMetadataService:
    return SmfpMetadataService()


@lru_cache
def get_smfp_frequency_service() -> SmfpFrequencyService:
    return SmfpFrequencyService()


@lru_cache
def get_smfp_evidence_fusion_service() -> SmfpEvidenceFusionService:
    return SmfpEvidenceFusionService()


@lru_cache
def get_smfp_health_service() -> SmfpHealthService:
    settings = get_settings()
    return SmfpHealthService(
        key_registry_path=settings.smfp_dir / "key_registry.json",
        dataset_registry_path=ROOT_DIR / "datasets" / "smfp" / "dataset_registry.json",
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
        model_dir=ROOT_DIR / "models" / "smfp",
    )


@lru_cache
def get_smfp_inference_service() -> SmfpInferenceService:
    return SmfpInferenceService(
        ml_service=get_smfp_ml_service(),
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
        model_dir=ROOT_DIR / "models" / "smfp",
    )


@lru_cache
def get_smfp_report_service() -> SmfpReportService:
    settings = get_settings()
    return SmfpReportService(
        smfp_service=get_smfp_service(),
        public_verify_base_url=f"http://{settings.app_host}:{settings.app_port}",
    )


@lru_cache
def get_smfp_ml_service() -> SmfpMlService:
    return SmfpMlService(
        dataset_registry_path=ROOT_DIR / "datasets" / "smfp" / "dataset_registry.json",
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
    )


@lru_cache
def get_smfp_training_service():
    from app.services.smfp_training_service import SmfpTrainingService

    return SmfpTrainingService(
        dataset_registry_path=ROOT_DIR / "datasets" / "smfp" / "dataset_registry.json",
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
        model_dir=ROOT_DIR / "models" / "smfp",
        snapshot_service=get_smfp_snapshot_service(),
    )


@lru_cache
def get_smfp_review_service():
    from app.services.smfp_review_service import SmfpReviewService

    return SmfpReviewService(
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
        model_dir=ROOT_DIR / "models" / "smfp",
        training_service=get_smfp_training_service(),
        required_approvals=1,
        governance_profile="lab",
        snapshot_service=get_smfp_snapshot_service(),
    )


@lru_cache
def get_smfp_timeline_service():
    from app.services.smfp_timeline_service import SmfpTimelineService

    return SmfpTimelineService(
        dataset_registry_path=ROOT_DIR / "datasets" / "smfp" / "dataset_registry.json",
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
        model_dir=ROOT_DIR / "models" / "smfp",
    )


@lru_cache
def get_smfp_snapshot_service():
    from app.services.smfp_snapshot_service import SmfpSnapshotService

    return SmfpSnapshotService(
        snapshot_dir=ROOT_DIR / "snapshots" / "governance",
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
        dataset_registry_path=ROOT_DIR / "datasets" / "smfp" / "dataset_registry.json",
        model_dir=ROOT_DIR / "models" / "smfp",
        smfp_service=get_smfp_service(),
        timeline_service=get_smfp_timeline_service(),
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


@lru_cache
def get_candidate_recommendation_service() -> CandidateRecommendationService:
    settings = get_settings()
    return CandidateRecommendationService(
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
        debug_trace=settings.localization_debug_recommendation_trace,
    )


@lru_cache
def get_rubric_candidate_scoring_service() -> RubricCandidateScoringService:
    settings = get_settings()
    return RubricCandidateScoringService(
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


@lru_cache
def get_hermes_orchestrator():
    from app.services.hermes.hermes_orchestrator import HermesOrchestrator

    settings = get_settings()
    return HermesOrchestrator(
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
        scoring_service=get_rubric_candidate_scoring_service(),
        localization_service=get_localization_service(),
        default_provider="ollama",
    )


@lru_cache
def get_hermes_advisor():
    from app.services.hermes.hermes_advisor import HermesAdvisor

    return HermesAdvisor()
