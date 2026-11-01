# AI Codebase Architecture & Onboarding Analyzer

> Automated codebase analysis, architecture visualization, and onboarding documentation — powered by AST parsing, local code search, and OpenRouter chat completions.

## Architecture Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Next.js    │────▶│   FastAPI    │────▶│   Celery     │
│   Frontend   │     │   Backend    │     │   Workers    │
│   (Port 3000)│◀────│  (Port 8000) │◀────│              │
└──────────────┘     └──────┬───────┘     └──────┬───────┘
                            │                     │
                    ┌───────┼─────────────────────┤
                    │       │                     │
              ┌─────▼──┐ ┌─▼────────┐  ┌────────▼───┐
              │ Redis  │ │PostgreSQL│  │   Qdrant   │
              │ Broker │ │   (SQL)  │  │ (Vectors)  │
              └────────┘ └──────────┘  └────────────┘
```

## Tech Stack

| Layer       | Technology                                    |
|-------------|-----------------------------------------------|
| Frontend    | Next.js 15, TypeScript, Tailwind CSS, Mermaid |
| Backend     | Python 3.12, FastAPI, Pydantic v2             |
| Workers     | Celery + Redis                                |
| Database    | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic      |
| Vector DB   | Qdrant                                        |
| AST Parsing | Tree-sitter                                   |
| AI          | OpenRouter Gemma chat + local BM25/AST retrieval |

## Quickstart

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose v2
- [Node.js](https://nodejs.org/) >= 20 (for local frontend dev)
- [Python](https://www.python.org/) >= 3.12 (for local backend dev)

### 1. Clone & Configure

```bash
git clone <repository-url>
cd AI\ CODE\ ANALAYSER

# Copy environment template
cp .env.example .env
# Edit .env with your actual values (especially OPENROUTER_API_KEY)
```

### 2. Start Infrastructure

```bash
# Start all services (PostgreSQL, Redis, Qdrant)
docker compose up -d postgres redis qdrant

# Verify services are healthy
docker compose ps
```

### 3. Run Backend (Local Dev)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# Run migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000
```

Create an API key in [OpenRouter](https://openrouter.ai/settings/keys) and set
`OPENROUTER_API_KEY` in the environment used by the backend
(`backend/.env` for local development, or the root `.env` for Docker Compose).
The configured default model is `google/gemma-4-26b-a4b-it:free`; change
`OPENROUTER_MODEL` if you select a different OpenRouter model. Free model availability,
rate limits, and credits are controlled by OpenRouter and may change.
HTTP 429 responses can be caused either by OpenRouter's free-model request caps
or by temporary capacity limits at the model provider. Provider-capacity failures
may not appear as billable activity; check `GET /api/v1/key` and its
`free_model_daily_requests` field for the account's free-model daily quota.
Creating another API key does not bypass shared free-model limits.

Gemma is a chat model, not an embedding model. Code chunks are stored in Qdrant and
retrieved locally using BM25 keyword ranking plus AST-name matching, so indexing does
not make external embedding requests. Chat uses OpenRouter streaming: it tries the
configured model first, then `openrouter/free`, which selects another available free
model if the configured model's providers are rate-limited. No paid fallback is used. The new
`code_chunks_openrouter` Qdrant collection is separate from previous embedding
collections; resubmit repositories to populate it for local retrieval.

### 4. Run Frontend (Local Dev)

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### 5. Run Everything via Docker

```bash
docker compose up --build
```

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── core/          # Config, database, dependencies
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── api/           # Route handlers
│   │   ├── services/      # Business logic
│   │   ├── worker/        # Celery tasks
│   │   └── main.py        # FastAPI application entry point
│   ├── alembic/           # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/           # Next.js App Router pages
│   │   ├── components/    # Reusable React components
│   │   ├── lib/           # Utilities and API client
│   │   └── types/         # TypeScript interfaces
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## License

Private — All rights reserved.
