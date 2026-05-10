# Healthcare RAG System — Claude Code Context

## Project Overview

A Healthcare RAG (Retrieval-Augmented Generation) system that lets users ask healthcare
questions and get verified, cited answers from official sources (CDC, WHO, NIH, FDA).
Built as a SaaS product — anyone can sign up, admins manage the knowledge base.

---

## Repository Structure

```
healthcare-system/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/             # HTTP routers (auth, queries, documents, admin)
│   │   ├── core/               # Config (Pydantic BaseSettings)
│   │   ├── db/                 # Async SQLAlchemy, Redis, Vector DB clients
│   │   ├── gateway/            # Auth, middleware, security, rate limiting
│   │   ├── models/             # ORM models + enums
│   │   ├── rag/                # RAG pipeline (parser, retriever, reranker, LLM)
│   │   ├── services/           # Business logic (admin, document, query)
│   │   ├── dependencies.py     # FastAPI dependency injection
│   │   └── main.py             # FastAPI entry point
│   ├── alembic/                # Database migrations
│   ├── tests/                  # pytest test suite
│   └── .env                    # Environment variables (never commit)
└── frontend/                   # Next.js 14 frontend
    └── src/
        ├── app/                # Next.js App Router pages
        │   ├── (auth)/         # Login, Register pages
        │   └── (dashboard)/    # Query, Documents, History, Admin pages
        ├── components/         # React components by feature
        │   ├── auth/           # LoginForm, RegisterForm, AuthGuard
        │   ├── layout/         # Navbar, Sidebar, PageWrapper
        │   ├── query/          # QuestionInput, AnswerCard, SourceCard, etc.
        │   ├── documents/      # DocumentUploader, DocumentTable, etc.
        │   └── ui/             # Shared: LoadingSpinner, ErrorBanner, ConfidenceBadge
        ├── hooks/              # useAuth, useQuery, useDocuments, etc.
        ├── lib/                # api.ts (Axios), auth.ts (token storage), helpers
        └── types/              # Shared TypeScript interfaces

```

---

## Tech Stack

### Backend
- **Framework:** FastAPI (Python 3.12)
- **Database:** PostgreSQL + asyncpg + SQLAlchemy 2.0 async
- **Cache:** Redis (rate limiting, token revocation, query cache)
- **Vector DB:** Pinecone (index: `healthcare-rag`, dimensions: 384)
- **Embeddings:** sentence-transformers `all-MiniLM-L6-v2` (384-dim)
- **LLM:** Anthropic Claude (`claude-sonnet-4-20250514`)
- **Auth:** JWT (HS256) via python-jose + passlib bcrypt==4.0.1
- **Migrations:** Alembic
- **Venv:** `/home/samir/Documents/RAG/venv`

### Frontend
- **Framework:** Next.js 14 (App Router, TypeScript)
- **Styling:** Tailwind CSS + shadcn/ui
- **HTTP:** Axios (`src/lib/api.ts`)
- **State:** React Query (@tanstack/react-query)
- **Icons:** lucide-react

---

## Running the Project

### Backend
```bash
cd /home/samir/Documents/RAG/healthcare-system/backend
source /home/samir/Documents/RAG/venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd /home/samir/Documents/RAG/healthcare-system/frontend
npm run dev
```

### Services required
```bash
sudo systemctl start redis-server
sudo systemctl start postgresql
```

### API Docs
```
http://localhost:8000/docs
```

---

## Environment Variables

Backend `.env` is at `backend/.env`. Key variables:

```
# Database
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=healthcare_user
POSTGRES_PASSWORD=healthcare_password
POSTGRES_DB=healthcare_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
SECRET_KEY=...
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# LLM
ANTHROPIC_API_KEY=...
LLM_MODEL=claude-sonnet-4-20250514

# Vector DB
VECTOR_DB_PROVIDER=pinecone
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=healthcare-rag

# Embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

Frontend `.env.local` is at `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## Database

### Run migrations
```bash
cd backend
source /home/samir/Documents/RAG/venv/bin/activate
alembic upgrade head
```

### Create new migration
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Key tables
- `organizations` — multi-tenant orgs
- `users` — with roles: admin, clinician, patient, org_owner
- `documents` — uploaded healthcare PDFs
- `document_chunks` — chunked document pieces (metadata only, vectors in Pinecone)
- `queries` — user questions + RAG answers
- `query_sources` — which chunks were cited in each answer
- `query_feedback` — user ratings on answers
- `audit_logs` — HIPAA-compliant admin action log
- `api_keys` — programmatic access keys
- `rate_limits` — per-user rate limit overrides

---

## Architecture — Key Design Decisions

### Multi-tenancy
Every table has `organization_id` — users only see their org's data.

### RAG Pipeline (`app/rag/`)
```
Query → QueryParser → Retriever (Pinecone) → Reranker → SourceValidator → PromptBuilder → LLMClient → Response
```
- Source validator enforces trusted domains only (CDC, WHO, NIH, FDA, etc.)
- Answers include medical disclaimer always
- Confidence score = mean relevance of top 3 sources

### Auth Flow
- JWT access token (30 min) + refresh token (7 days) stored in Redis
- Token revocation via Redis JTI blacklist
- Roles: admin > org_owner > clinician > patient

### Middleware Stack (in order, outermost first)
1. IPAllowlist (admin routes only)
2. RateLimiter (Redis sliding window)
3. RequestValidator (size, content-type)
4. CORS
5. SecurityHeaders
6. HIPAALogger (audit trail — no PHI in logs)
7. Correlation (X-Request-ID on every request)

---

## Frontend Design System

### Colors
- Primary: `blue-600` (#2563EB)
- Secondary: `teal-500` (#14B8A6)
- Background: `slate-50` (#F8FAFC)
- Surface: `white`
- Border: `slate-200`
- Text primary: `slate-800`
- Text muted: `slate-500`

### Component conventions
- `"use client"` only where hooks/events needed
- All API calls via `src/lib/api.ts` (Axios with JWT interceptor)
- Tokens stored in localStorage via `src/lib/auth.ts`
- No raw `fetch` anywhere
- All loading states show skeletons not blank space
- All errors show `<ErrorBanner>` not console.log

---

## UI Phases Built

- ✅ Phase 1 — Foundation (Navbar, Sidebar, PageWrapper, shared UI components)
- ✅ Phase 2 — Auth (Login, Register, AuthGuard, useAuth hook)
- ✅ Phase 3 — Query interface (QuestionInput, AnswerCard, SourceCard, FeedbackBar)
- ✅ Phase 4 — Documents (DocumentUploader, DocumentTable, drag & drop)
- ⬜ Phase 5 — Admin dashboard (Users, Analytics, Audit logs)
- ⬜ Phase 6 — Wire everything to real API + polish

---

## Known Issues / Watch Out For

- `bcrypt` must be pinned to `==4.0.1` — newer versions break passlib
- Alembic uses `SYNC_DATABASE_URL` (psycopg2), not `DATABASE_URL` (asyncpg)
- Admin routes must NOT include `/api/v1` prefix in router — main.py adds it
- Login uses `application/x-www-form-urlencoded` (OAuth2 form), not JSON
- Swagger docs at `/docs` not `/api/v1/docs`
- Redis must be running or rate limiter logs warnings (fails open — requests still pass)
- `VECTOR_DB_PROVIDER` must be set in `.env` — defaults to pinecone if missing

---

## Common Commands

```bash
# Install new Python package
pip install <package> && pip freeze > requirements.txt

# Run backend tests
cd backend && pytest tests/ -v

# Check all routes registered
python -c "from app.api.v1.router import api_router; print([(r.path, r.methods) for r in api_router.routes])"

# Check DB tables
sudo -u postgres psql -d healthcare_db -c "\dt"

# Check document count
sudo -u postgres psql -d healthcare_db -c "SELECT COUNT(*) FROM documents;"

# Verify Pinecone connection
python -c "from pinecone import Pinecone; import os; from dotenv import load_dotenv; load_dotenv(); pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY')); print(pc.list_indexes().names())"
```