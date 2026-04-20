# 🧪 Second Brain App: LLM Experimentation Lab

**"From test console to scientific lab"**

An advanced LLM experimentation environment for Supervised Fine-Tuning (SFT), Reinforcement Learning from Human Feedback (RLHF), and Retrieval-Augmented Generation (RAG). 

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
* **Database:** PostgreSQL with `pgvector`
* **Frontend:** Vanilla JS/HTML with KaTeX for mathematical rendering.
* **LLM Orchestration:** Agnostic API layer (Local integration via Ollama, easily extensible).

```text
app/
├── api/          # FastAPI Routes (experiments, annotations, rag)
├── core/         # Configs and environments
├── repositories/ # Database interactions and pgvector semantic search
├── schemas/      # Pydantic models for validation
└── services/     # Business logic (LLM Orchestrator, RAG Pipeline)
```

## 📖 Documentation & Extension

For deep dives into the system design and guides on how to connect your own APIs:

- **[Architecture Guide](ARCHITECTURE.md)**: Logic flow, DDD structure, and RAG mechanics.
- **[Integration Guide](INTEGRATION_GUIDE.md)**: Step-by-Step guide for **Gemini API** and **Supabase** (pgvector).

## 🚀 Como Rodar

1. Garanta que o Ollama esteja ativo em `http://127.0.0.1:11434`
2. Configure o ambiente:
   ```powershell
   cp .env.example .env
   # Ajuste as variáveis se necessário
   ```
3. Suba o PostgreSQL com Docker Compose:
   ```powershell
   docker compose up -d
   ```
4. Inicialize o banco local:
   ```powershell
   python db_init.py
   ```
5. Execute o backend:
   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
   ```
6. Acesse: `http://127.0.0.1:8765`

## 📊 Estrutura do Projeto

- `app/`: backend FastAPI estruturado
- `db_init.py`: bootstrap do banco PostgreSQL
- `docker-compose.yml`: PostgreSQL com `pgvector` em `127.0.0.1:5433`
- `web/`: interface web do laboratório
- `models/`: modelos locais de embeddings
- `scripts/download_sentence_transformer.py`: baixa modelos para uso offline
