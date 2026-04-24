"""
Integration guide for Admin Service with main FastAPI application.
Shows how to wire everything together in app/main.py
"""

# ============ app/main.py INTEGRATION ============

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

from app.models.database import Base
from app.api.v1 import router as api_v1_router
from app.api.v1.endpoints import admin  # Import admin router


# ============ CONFIGURATION ============

# Create SQLAlchemy engine
DATABASE_URL = "postgresql://user:password@localhost:5432/healthcare_db"
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,  # Verify connections before using
    echo=False,  # Set to True for SQL debugging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create database tables
Base.metadata.create_all(bind=engine)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============ FASTAPI APP SETUP ============

app = FastAPI(
    title="Healthcare RAG System",
    description="Production-grade Admin Service for Healthcare RAG",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ DEPENDENCY INJECTION ============

def get_db():
    """Database session dependency for all routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override FastAPI dependency
from fastapi import Depends

app.dependency_overrides[SessionLocal] = get_db


# ============ ROUTE REGISTRATION ============

# Include admin router
app.include_router(admin.router)

# Include other routers
app.include_router(api_v1_router)


# ============ HEALTH CHECK ============

@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "healthcare-rag-admin",
    }


# ============ STARTUP/SHUTDOWN EVENTS ============

@app.on_event("startup")
async def startup_event():
    """App startup hook."""
    logger.info("Healthcare RAG Admin Service starting...")
    # Initialize any resources
    # Connect to external services
    # Load configuration


@app.on_event("shutdown")
async def shutdown_event():
    """App shutdown hook."""
    logger.info("Healthcare RAG Admin Service shutting down...")
    # Clean up resources
    # Close connections


# ============ USAGE EXAMPLE ============

"""
To use this admin service:

1. **Start the FastAPI server:**
   ```
   uvicorn app.main:app --reload
   ```

2. **Access the interactive API docs:**
   ```
   http://localhost:8000/docs
   ```

3. **Example API calls:**

   # Get JWT token (assuming you have auth endpoint)
   POST /api/v1/auth/login
   {
       "email": "admin@example.com",
       "password": "secure_password"
   }
   Response: {"access_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."}

   # Create a new user (admin only)
   POST /api/v1/admin/users
   Headers: Authorization: Bearer {token}
   {
       "email": "newuser@example.com",
       "full_name": "John Doe",
       "organization_id": 1,
       "role": "healthcare_provider",
       "password": "SecurePass123"
   }
   Response: 
   {
       "id": 5,
       "email": "newuser@example.com",
       "full_name": "John Doe",
       "organization_id": 1,
       "role": "healthcare_provider",
       "is_active": true,
       "created_at": "2026-04-24T10:30:00",
       "updated_at": "2026-04-24T10:30:00"
   }

   # Get audit logs with filtering
   GET /api/v1/admin/audit-logs?action=USER_CREATED&start_date=2026-04-01&page=1&page_size=50
   Headers: Authorization: Bearer {token}
   Response:
   {
       "items": [
           {
               "id": 1,
               "user_id": 1,
               "organization_id": 1,
               "action": "USER_CREATED",
               "resource_type": "USER",
               "resource_id": 5,
               "changes": {
                   "email": "newuser@example.com",
                   "role": "healthcare_provider"
               },
               "status": "SUCCESS",
               "created_at": "2026-04-24T10:30:00"
           }
       ],
       "total": 1,
       "page": 1,
       "page_size": 50,
       "total_pages": 1
   }

   # Create API key for user
   POST /api/v1/admin/api-keys/5
   Headers: Authorization: Bearer {token}
   {
       "name": "Mobile App Integration",
       "expires_in_days": 90
   }
   Response:
   {
       "id": "123",
       "key": "api_key_abcd1234efgh5678ijkl9012mnop",
       "name": "Mobile App Integration"
   }
   # NOTE: This is the ONLY time the key is shown in plaintext!

   # View dashboard analytics
   GET /api/v1/admin/analytics?days=30
   Headers: Authorization: Bearer {token}
   Response:
   {
       "metrics": {
           "total_queries": 15000,
           "avg_response_time_ms": 245.5,
           "total_users": 320,
           "queries_last_24h": 1200,
           "avg_feedback_score": 4.5,
           "peak_usage_hour": 14
       },
       "top_users": [
           {
               "user_id": 10,
               "email": "researcher@example.com",
               "total_queries": 2500,
               "avg_response_time_ms": 220.0,
               "last_query_at": "2026-04-24T10:15:00"
           }
       ],
       "usage_trend": [
           {
               "date": "2026-04-24",
               "query_count": 1200,
               "unique_users": 85,
               "avg_response_time_ms": 245.5
           }
       ]
   }

   # Update user role
   PATCH /api/v1/admin/users/5
   Headers: Authorization: Bearer {token}
   {
       "role": "admin"
   }
   Response: (updated user object with new role)

   # Deactivate user (soft delete)
   DELETE /api/v1/admin/users/5
   Headers: Authorization: Bearer {token}
   Response: (user object with is_active: false)

   # Update rate limits
   PATCH /api/v1/admin/rate-limits/5
   Headers: Authorization: Bearer {token}
   {
       "requests_per_minute": 100,
       "requests_per_hour": 5000,
       "requests_per_day": 50000
   }
   Response:
   {
       "user_id": 5,
       "requests_per_minute": 100,
       "requests_per_hour": 5000,
       "requests_per_day": 50000
   }
"""
