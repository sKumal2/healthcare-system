# Healthcare System

FastAPI-based backend (with placeholders for frontend and infrastructure) for a healthcare platform. The backend exposes a versioned API and is configured via environment variables.

## Repository layout

```
healthcare-system/
├── backend/            # FastAPI backend
│   ├── app/            # Application code
│   ├── requirements.txt
│   └── .env.example    # Sample environment config
├── frontend/           # Placeholder for web app
├── infrastructure/     # Docker/K8s/Terraform placeholders
├── docs/               # Architecture and API docs
└── main.py             # Sample FastAPI stub (root)
```

Key config: [backend/app/core/config.py](backend/app/core/config.py) (reads .env) and [backend/.env.example](backend/.env.example).

## Prerequisites

- Python 3.11+ recommended
- pip
- (Optional) Redis, Postgres, AWS credentials depending on features you use

## Setup (backend)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in secrets in `.env` (DB, SMTP, AWS, Redis). Defaults target local Postgres and Redis.

## Run the API (dev)

From `backend/` with the virtualenv active:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Open API docs: http://localhost:8000/api/v1/docs
- Health check: http://localhost:8000/health

## Testing

From `backend/`:

```bash
pytest
```

## Frontend

`frontend/` is scaffold space; no build configured yet. Add your framework of choice and wire to the API origins configured in CORS.

## Infrastructure

`infrastructure/` includes placeholders for Docker, Kubernetes, and Terraform. Populate with environment-specific manifests as needed.

## Git hygiene

Add a `.gitignore` to exclude `__pycache__`, virtualenvs, and other build artifacts before further commits.
