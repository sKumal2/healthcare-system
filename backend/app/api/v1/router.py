from fastapi import APIRouter
from app.api.v1.endpoints import queries, admin

api_router = APIRouter()
api_router.include_router(queries.router)
api_router.include_router(admin.router)
