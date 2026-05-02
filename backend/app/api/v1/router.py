from fastapi import APIRouter

from app.api.v1 import auth
from app.api.v1.endpoints import admin, queries

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(queries.router)
api_router.include_router(admin.router)
