# Second Brain App: AI Evaluation And Training Lab

**From test console to scientific lab**

Second Brain is an internal AI evaluation, training, provenance, and governance
lab. It is not an autonomous agentic operating system. Its job is to test,
measure, evaluate, generate datasets, calibrate rubrics, and audit evidence
before any future operational system is allowed to act on that evidence.

The lab supports SFT, RLHF, DPO-style preference data, Side-by-Side (SxS)
evaluation, Retrieval-Augmented Generation (RAG), localization rubric
calibration, synthetic media provenance, and Hermes advisory diagnostics.

## Operating Model

The canonical lab operating model is defined in:

- [Second Brain Lab Operating Model](docs/second_brain_lab_operating_model.md)

That document defines:

- what counts as an experiment;
- what counts as evidence;
- what counts as an approved artifact;
- what may be promoted into a dataset;
- what requires human review;
- what Hermes may consume;
- what remains temporary diagnostics only.

## Core Features

- **Deterministic Parallel Inference:** run two models or prompt variants with
  controlled generation parameters and comparable context.
- **Blind SxS Evaluation:** hide model identity until the evaluation is
  submitted to reduce evaluator bias.
- **Dataset Export:** export reviewed SFT and DPO-style data from human
  annotations and chosen/rejected pairs.
- **Localization Rubric Lab:** create, generate, validate, review, and approve
  rubric cases through explicit quality gates.
- **RAG Pipeline:** retrieve document chunks through `pgvector`, metadata
  filters, deterministic ordering, and retrieval traces.
- **SMFP Provenance:** hash, sign, manifest, revise, and verify synthetic media
  artifacts.
- **Hermes Advise:** deterministic, no-side-effect recommendations for lab
  experiment diagnostics.

## Architecture

Built with a clean, modular architecture separating HTTP routes, schemas,
business logic, and persistence:

- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL with `pgvector`
- **Frontend:** Vanilla JS/HTML
- **LLM Providers:** local Ollama and provider adapters
- **Validation:** Pydantic schemas, service-level tests, contract documents

```text
app/
├── api/          # FastAPI routes
├── core/         # settings and environment configuration
├── repositories/ # database access and pgvector retrieval
├── schemas/      # Pydantic request/response contracts
└── services/     # lab services, orchestration, RAG, Hermes, SMFP
```

## Documentation

- [Architecture Guide](ARCHITECTURE.md)
- [Second Brain Lab Operating Model](docs/second_brain_lab_operating_model.md)
- [Hermes Fallacy ADR](docs/adr_0001_the_hermes_fallacy.md)
- [Hermes Advise Cooldown](docs/hermes_advise_cooldown.md)
- [Localization Rubric Lab Contract](docs/localization_rubric_lab_contract.md)
- [SMFP v1](docs/smfp_v1.md)
- [Integration Guide](INTEGRATION_GUIDE.md)

## Running Locally

### Environment note

The default Python in the shell can point to another virtual environment, such
as `hermes-agent`. For tests, server runs, and project jobs, use:

```powershell
.\.venv\Scripts\python.exe
```

1. Ensure Ollama is running at `http://127.0.0.1:11434`.
2. Configure the environment:

   ```powershell
   cp .env.example .env
   ```

3. Start PostgreSQL:

   ```powershell
   docker compose up -d
   ```

4. Initialize the local database:

   ```powershell
   .\.venv\Scripts\python.exe db_init.py
   ```

5. Run the backend:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
   ```

6. Open `http://127.0.0.1:8765`.

## Hermes Status

Hermes v0 is an archived prototype kept outside main navigation as forensic
evidence of the identity gap described in
[ADR 0001](docs/adr_0001_the_hermes_fallacy.md).

Hermes Advisor is available directly at `/hermes_advise.html` and through
`POST /api/hermes/advise`. It returns deterministic diagnostics and proposed
next actions without executing anything.

Internal version: `hermes-advise-v1.1-stability-green`

Hermes Observe may begin only after the Advise cooldown exits by evidence.
Hermes Act remains out of scope.

## Project Structure

- `app/`: FastAPI backend
- `db_init.py`: PostgreSQL bootstrap
- `docker-compose.yml`: PostgreSQL with `pgvector` on `127.0.0.1:5433`
- `web/`: lab interface
- `models/`: local embedding models
- `scripts/download_sentence_transformer.py`: offline model download helper
