# Service Layer Fix — Claude Code Prompt

## Context

This is a Healthcare RAG System built with FastAPI (Python 3.11+). Three service files need
to be fixed to work correctly with the async DB layer, API gateway, and RAG engine that have
been built. Do not rewrite everything from scratch — fix what is broken, preserve what works,
and wire up what is missing.

### Files to fix:
```
backend/app/services/admin_service.py
backend/app/services/document_service.py
backend/app/services/query_service.py
backend/app/utils/audit.py
```

---

## Fix 1 — `app/utils/audit.py`

### Problem 1: `session.commit()` inside utility function
`create_audit_log` calls `session.commit()` internally. Utility functions must never commit
— that is the caller's responsibility. If the caller wraps operations in a transaction and
the utility commits mid-way, it breaks atomicity.

**Fix:** Remove `session.commit()` from `create_audit_log`. Just `session.add(audit_log)`
and return. Let callers commit.

### Problem 2: `session.query()` is synchronous
All SQLAlchemy calls use the sync API. The DB layer uses `asyncpg` + async SQLAlchemy.

**Fix:** Convert `create_audit_log` to `async def`. Use `await session.execute(...)` pattern
consistent with async SQLAlchemy. Update the signature to accept `AsyncSession` instead of
`Session`.

### Problem 3: `print()` in `safe_log_action`
`print(f"Audit log creation failed: {str(e)}")` is a PHI risk — if `e` contains any query
or user data it gets written to stdout uncontrolled.

**Fix:** Replace with structured logging:
```python
import logging
logger = logging.getLogger("audit")
logger.error("Audit log creation failed", exc_info=True)
# Never log str(e) directly — it may contain sensitive data
```

### Problem 4: `paginate_query` is synchronous
Uses `.count()` and `.all()` — sync SQLAlchemy calls.

**Fix:** Convert to `async def paginate_query`. Use:
```python
total_result = await session.execute(select(func.count()).select_from(query.subquery()))
total = total_result.scalar()
result = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
items = result.scalars().all()
```

---

## Fix 2 — `app/services/admin_service.py`

### Problem 1: SHA-256 password hashing
```python
# CURRENT — BROKEN, do not keep this
@staticmethod
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()
```
SHA-256 without salt is broken for passwords — trivially reversible via rainbow tables.

**Fix:** Replace with `passlib` bcrypt (already in requirements.txt from gateway prompt):
```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@staticmethod
def _hash_password(password: str) -> str:
    return pwd_context.hash(password)

@staticmethod
def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

### Problem 2: All DB calls are synchronous
Every method uses `self.session.query(...)`, `.filter(...)`, `.first()`, `.all()` — these are
sync SQLAlchemy calls that will block the event loop and fail with asyncpg.

**Fix:** Convert the entire `AdminService` class to async:
- Constructor stays sync (no I/O)
- Every method that touches the DB becomes `async def`
- Replace all `self.session.query(Model).filter(...).first()` with:
  ```python
  result = await self.session.execute(select(Model).where(...))
  record = result.scalar_one_or_none()
  ```
- Replace `.all()` with `result.scalars().all()`
- Replace `func.count(...)` queries using `select(func.count()).select_from(...)`
- Replace `session.add()` + `session.flush()` + `session.commit()` with:
  ```python
  self.session.add(record)
  await self.session.flush()
  await self.session.commit()
  ```
- Import `AsyncSession` from `sqlalchemy.ext.asyncio` and update type hints

### Problem 3: `create_audit_log` called with sync session, commits inside
After fixing `audit.py`, update all calls in `admin_service.py` to:
- Use `await create_audit_log(...)` 
- Remove any manual `self.session.commit()` that immediately follows `create_audit_log` since
  the audit log no longer commits — keep a single `await self.session.commit()` at the end of
  each operation

### Problem 4: Analytics queries use raw `func.extract` string grouping
```python
.group_by("hour")  # string-based group_by — fragile and DB-specific
```
**Fix:** Use SQLAlchemy expression:
```python
hour_col = func.extract("hour", QueryAnalyticsModel.created_at).label("hour")
...group_by(hour_col)
```

### Problem 5: `datetime.utcnow()` is deprecated in Python 3.12+
Replace all `datetime.utcnow()` with `datetime.now(UTC)`:
```python
from datetime import datetime, timezone
UTC = timezone.utc
# Replace datetime.utcnow() → datetime.now(UTC)
```

---

## Fix 3 — `app/services/document_service.py`

### Problem 1: In-memory vector store resets on every restart
```python
self.vector_store: List[DocumentChunk] = []  # BROKEN — lost on restart
self.document_index: dict = {}               # BROKEN — lost on restart
```
This means every server restart loses all documents. In a multi-worker deployment, each
worker has its own empty list — searches return nothing.

**Fix:** Replace the in-memory store with the `VectorDBClient` from `app/db/vector_db.py`
(built in the DB layer prompt). Update `DocumentService.__init__` to accept a
`VectorDBClient` dependency:
```python
from app.db.vector_db import VectorDBClient

class DocumentService:
    def __init__(self, vector_db: VectorDBClient):
        self.vector_db = vector_db
        self.storage_dir = Path(__file__).parent.parent / "storage" / "uploads"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
```

Update `process_and_store` to call `await self.vector_db.upsert(vectors)` instead of
appending to the in-memory list.

Update `search` to call `await self.vector_db.query(vector, top_k)` instead of iterating
the in-memory list.

### Problem 2: Mock MD5 embeddings
```python
def _generate_mock_embedding(self, text: str) -> List[float]:
    hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return [(hash_val >> i) % 100 / 100.0 for i in range(384)]
```
These are not real embeddings — all documents will return random similarity scores making
search useless.

**Fix:** Replace with a real embedding call. Use the `sentence-transformers` library
(already in requirements.txt):
```python
from sentence_transformers import SentenceTransformer

# Load once at class level, not per call
_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model

def _generate_embedding(self, text: str) -> List[float]:
    model = _get_embedding_model()
    return model.encode(text).tolist()
```
Add a note: in production this should be replaced with an async embedding API call
(e.g. OpenAI `text-embedding-3-small`) rather than a local model, to avoid blocking
the event loop during encoding.

### Problem 3: `_save_file` writes to local disk synchronously — breaks in cloud/multi-container
```python
with open(file_path, "wb") as f:
    f.write(file_content)
```
Local disk writes don't work across multiple containers and are lost on pod restarts.

**Fix:** Add an `async def _save_file` that writes to AWS S3 if `AWS_ACCESS_KEY_ID` is
configured in settings, falling back to local disk if not (for local dev). Use `aioboto3`
for async S3 writes:
```python
import aioboto3
from app.core.config import settings

async def _save_file(self, filename: str, file_content: bytes) -> str:
    if settings.AWS_ACCESS_KEY_ID:
        # Save to S3
        session = aioboto3.Session()
        async with session.client("s3", region_name=settings.AWS_REGION) as s3:
            key = f"uploads/{uuid.uuid4().hex}/{filename}"
            await s3.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=key,
                Body=file_content,
                ContentType="application/octet-stream",
            )
            return f"s3://{settings.S3_BUCKET_NAME}/{key}"
    else:
        # Local fallback for development
        file_path = self.storage_dir / filename
        if file_path.exists():
            name_parts = filename.rsplit(".", 1)
            if len(name_parts) == 2:
                base, ext = name_parts
                filename = f"{base}_{uuid.uuid4().hex[:8]}.{ext}"
            else:
                filename = f"{filename}_{uuid.uuid4().hex[:8]}"
            file_path = self.storage_dir / filename
        import aiofiles
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)
        return f"storage/uploads/{filename}"
```

### Problem 4: No auth or ownership checks on document operations
Any user can upload, search, or delete any document with no access control.

**Fix:** Add `organization_id: str` and `uploaded_by: str` parameters to
`process_and_store`. Store these in chunk metadata. In `search`, filter by
`organization_id` so users only search their own org's documents. Pass these from the
router via the current user identity from the gateway's `get_current_user` dependency.

### Problem 5: `process_and_store` and `search` are synchronous
Both methods need to be `async def` since they now call async vector DB and file storage.

**Fix:** Convert both to `async def`. Update all callers accordingly.

### Problem 6: Chunk splitting ignores sentence boundaries
Current word-count splitter cuts mid-sentence, which degrades embedding quality.

**Fix:** Split on sentence boundaries first, then group into chunks:
```python
import re

def _split_into_chunks(self, text: str, chunk_size: int = 500) -> List[str]:
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        if current_length + len(sentence) > chunk_size and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_length = len(sentence)
        else:
            current_chunk.append(sentence)
            current_length += len(sentence) + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks if chunks else [text]
```

---

## Fix 4 — `app/services/query_service.py`

### Problem 1: Hardcoded mock answer
```python
def _generate_answer(self, prompt: str) -> str:
    answer = "Based on the provided context, this answer addresses your question..."
    return answer
```
This returns the same string for every question.

**Fix:** Replace with a call to `LLMClient` from `app/rag/llm_client.py` (built in the RAG
engine prompt). Update `QueryService.__init__` to accept an `LLMClient` dependency:
```python
from app.rag.llm_client import LLMClient

class QueryService:
    def __init__(self, document_service: DocumentService, llm_client: LLMClient):
        self.document_service = document_service
        self.llm_client = llm_client

async def _generate_answer(self, system_prompt: str, user_prompt: str) -> str:
    return await self.llm_client.complete(system_prompt, user_prompt)
```

### Problem 2: `_build_prompt` has no medical safety instructions
The current prompt has no disclaimer, no instruction to cite sources, no instruction to
refuse if context is insufficient — all required for a healthcare RAG system.

**Fix:** Replace `_build_prompt` with one that delegates to `PromptBuilder` from
`app/rag/prompt_builder.py`:
```python
from app.rag.prompt_builder import PromptBuilder
from app.rag.models import ParsedQuery, RankedChunk

def _build_prompt(self, question: str, context_chunks: List[dict]) -> tuple[str, str]:
    builder = PromptBuilder()
    parsed_query = ParsedQuery(
        original_query=question,
        expanded_terms=[],
        medical_entities=[],
        intent="general",
        language="en"
    )
    ranked_chunks = [
        RankedChunk(
            chunk_id=c["document_id"],
            content=c["content"],
            source_url=c.get("source_url", ""),
            source_name=c.get("title", ""),
            score=c["similarity_score"],
            metadata={},
            rank=i + 1,
            relevance_score=c["similarity_score"],
        )
        for i, c in enumerate(context_chunks)
    ]
    return builder.build(parsed_query, ranked_chunks)
```

### Problem 3: No user/session tracking on queries
Queries are anonymous — no `user_id` or `session_id` stored. This means analytics,
audit logs, and per-user rate limiting cannot work.

**Fix:** Add `user_id: str` and `session_id: str` to `QueryRequest`:
```python
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    user_id: str
    session_id: str
```
Add `query_id: str` to `QueryResponse` (generate with `uuid4`). Store query + metadata
in `QueryAnalyticsModel` via the DB session after answering.

### Problem 4: `ask_question` is synchronous
**Fix:** Convert to `async def ask_question`. Update `_retrieve_context_chunks` to
`async def` (since `document_service.search` is now async). Update `_generate_answer`
to `async def`.

### Problem 5: No input validation beyond `min_length=1`
A user could submit a 100,000 character "question".

**Fix:** Add `max_length=2000` to the `question` field. Add a check for obviously
non-question inputs (e.g. binary data):
```python
question: str = Field(..., min_length=3, max_length=2000)
```

### Problem 6: Source deduplication only by `document_id` loses chunk-level scoring
When deduping sources, the current code keeps the first chunk's score even if a later
chunk from the same document scored higher.

**Fix:** Keep the highest-scoring chunk per `document_id`:
```python
best_chunks: dict[str, dict] = {}
for chunk in context_chunks:
    doc_id = chunk["document_id"]
    if doc_id not in best_chunks or chunk["similarity_score"] > best_chunks[doc_id]["similarity_score"]:
        best_chunks[doc_id] = chunk

sources = [
    SourceMetadata(
        document_id=doc_id,
        title=c["title"],
        source_url=c.get("source_url"),
        author=c.get("author"),
        similarity_score=c["similarity_score"],
    )
    for doc_id, c in best_chunks.items()
]
```

---

## Dependency Injection — Wire It All Together

Create `backend/app/dependencies.py` with FastAPI dependency providers for all services
so routers get properly injected instances (not manually instantiated):

```python
from functools import lru_cache
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.vector_db import get_vector_db_client
from app.rag.llm_client import LLMClient
from app.services.document_service import DocumentService
from app.services.query_service import QueryService

@lru_cache()
def get_llm_client() -> LLMClient:
    return LLMClient()

async def get_document_service(
    vector_db=Depends(get_vector_db_client),
) -> DocumentService:
    return DocumentService(vector_db=vector_db)

async def get_query_service(
    document_service: DocumentService = Depends(get_document_service),
    llm_client: LLMClient = Depends(get_llm_client),
) -> QueryService:
    return QueryService(
        document_service=document_service,
        llm_client=llm_client,
    )
```

Then in routers, use:
```python
@router.post("/ask")
async def ask(
    request: QueryRequest,
    service: QueryService = Depends(get_query_service),
    current_user: UserIdentity = Depends(get_current_user),
):
    ...
```

---

## New Dependencies to Add to `requirements.txt`

```
aiofiles>=23.2.0       # async local file writes
aioboto3>=12.3.0       # async S3 uploads
```

Note: `passlib[bcrypt]`, `sentence-transformers` already added in previous prompts —
do not duplicate.

---

## Test Updates

Update or add tests in `backend/tests/` for each fixed service:

### `tests/services/test_admin_service.py`
- All DB calls mocked with `AsyncMock`
- Test that `_hash_password` produces bcrypt output (starts with `$2b$`)
- Test that `_verify_password` correctly validates against bcrypt hash
- Test that SHA-256 hash from old code does NOT pass `_verify_password` (regression test)
- Test that `create_audit_log` does NOT call `session.commit()` (assert commit not called)
- Test `get_analytics` returns correct structure with mocked async DB results

### `tests/services/test_document_service.py`
- Mock `VectorDBClient` with `AsyncMock`
- Test `process_and_store` calls `vector_db.upsert()` with correct payload
- Test `search` calls `vector_db.query()` and maps results correctly
- Test `_split_into_chunks` does not split mid-sentence
- Test `_save_file` calls S3 when `AWS_ACCESS_KEY_ID` is set, local disk when not
- Test org isolation: search with `org_A` does not return `org_B` documents

### `tests/services/test_query_service.py`
- Mock `DocumentService` and `LLMClient` with `AsyncMock`
- Test `ask_question` calls `llm_client.complete()` with a prompt containing the medical disclaimer
- Test `ask_question` stores `user_id` and `session_id` in the response `query_id`
- Test source deduplication keeps highest-scoring chunk per document
- Test question over 2000 chars raises `422 Unprocessable Entity`
- Test that `_generate_answer` is never called when no context chunks are found
  (should return "cannot find reliable information" response, not call LLM with empty context)

---

## What NOT to Change

- Do not change the Pydantic model field names on `QueryRequest` / `QueryResponse` /
  `DocumentChunk` / `DocumentMetadata` — only add new fields
- Do not change `mask_sensitive_data` or `extract_before_after` logic in `audit.py` —
  only fix the session/logging issues
- Do not change `check_privilege_escalation` or `is_admin` — these are correct as-is
- Do not touch any router files — only the service and utility layer

---

## Definition of Done

- [ ] `_hash_password` uses bcrypt — SHA-256 removed entirely
- [ ] All DB calls in `admin_service.py` are async (`async def`, `await session.execute`)
- [ ] `create_audit_log` in `audit.py` does NOT call `session.commit()`
- [ ] `audit.py` has zero `print()` calls
- [ ] `document_service.py` uses `VectorDBClient` — no in-memory list
- [ ] `document_service.py` uses real sentence-transformer embeddings — no MD5 mock
- [ ] `document_service.py` `_save_file` uses async file I/O with S3 fallback
- [ ] `query_service.py` calls `LLMClient.complete()` — no hardcoded answer string
- [ ] `query_service.py` uses `PromptBuilder` with medical disclaimer
- [ ] `QueryRequest` has `user_id`, `session_id`; `QueryResponse` has `query_id`
- [ ] All service methods are `async def`
- [ ] `backend/app/dependencies.py` created with all DI providers
- [ ] All existing tests still pass
- [ ] New tests added for each fixed behaviour above
- [ ] `datetime.utcnow()` replaced with `datetime.now(UTC)` everywhere in these files