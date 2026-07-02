"""Aggregate router for all v1 API endpoints."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.classify import router as classify_router
from app.api.v1.documents import router as documents_router
from app.api.v1.query import router as query_router
from app.api.v1.search import router as search_router
from app.api.v1.sessions import router as sessions_router

v1_router = APIRouter()
v1_router.include_router(auth_router)
v1_router.include_router(classify_router)
v1_router.include_router(documents_router)
v1_router.include_router(query_router)
v1_router.include_router(search_router)
v1_router.include_router(sessions_router)

__all__ = ["v1_router"]
