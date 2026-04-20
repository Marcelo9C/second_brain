# 🧪 Second Brain App: LLM Experimentation Lab

From test console to scientific lab: An advanced LLM experimentation environment for Supervised Fine-Tuning (SFT), Reinforcement Learning from Human Feedback (RLHF), and Retrieval-Augmented Generation (RAG). 

This platform allows AI engineers and researchers to run deterministic parallel inferences, evaluate models blindly Side-by-Side (SxS), and generate gold-standard JSONL datasets for local fine-tuning.

## ✨ Core Features

* **Deterministic Parallel Inference:** Run two distinct models (or two distinct prompts) simultaneously against the same parameters and RAG context.
* **Blind SxS Evaluation:** Eliminate human bias with default blind testing. Model identities are only revealed after the evaluation is submitted.
* **Semantic Visual Diffs:** Word-level text diffing (powered by `jsdiff`) to instantly spot hallucinations, omissions, or tone shifts between outputs.
* **Gold-Standard Data Export:** Automatically export human-annotated evaluations (chosen/rejected pairs and rationales) into JSONL format, ready for SFT or Reward Model training.
* **Advanced RAG Pipeline:** Go beyond basic cosine similarity. Features metadata pre-filtering (by section, title, and date) and strict deterministic ordering.

## 🏗️ Architecture (DDD approach)

Built with a clean, modular architecture separating HTTP routes, business logic, and data persistence:

* **Backend:** FastAPI (Python)
* **Database:** PostgreSQL with `pgvector` (Prepared for Supabase migration)
* **Frontend:** Vanilla JS/HTML with KaTeX for mathematical rendering.
* **LLM Orchestration:** Agnostic API layer (Local integration via Ollama, easily extensible).

```text
app/
├── api/          # FastAPI Routes (experiments, annotations, rag)
├── core/         # Configs and environments
├── repositories/ # Database interactions and pgvector semantic search
├── schemas/      # Pydantic models for validation
└── services/     # Business logic (LLM Orchestrator, RAG Pipeline)
