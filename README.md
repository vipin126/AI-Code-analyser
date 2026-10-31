# AI Codebase Architecture & Onboarding Analyzer

> Automated codebase analysis, architecture visualization, and onboarding documentation — powered by AST parsing, vector embeddings, and hybrid RAG synthesis.

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
| AI          | OpenAI Embeddings + Hybrid RAG                |

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
# Edit .env with your actual values (especially OPENAI_API_KEY)
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
