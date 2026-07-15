"""Aggregate router for all v1 API endpoints."""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.classify import router as classify_router
from app.api.v1.documents import router as documents_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.it_query import router as it_query_router
from app.api.v1.orchestrator import router as orchestrator_router
from app.api.v1.leave import router as leave_router
from app.api.v1.query import router as query_router
from app.api.v1.search import router as search_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.tickets import router as tickets_router

v1_router = APIRouter()
v1_router.include_router(admin_router)
v1_router.include_router(auth_router)
v1_router.include_router(classify_router)
v1_router.include_router(documents_router)
v1_router.include_router(feedback_router)
v1_router.include_router(it_query_router)
v1_router.include_router(leave_router)
v1_router.include_router(orchestrator_router)
v1_router.include_router(query_router)
v1_router.include_router(search_router)
v1_router.include_router(sessions_router)
v1_router.include_router(tickets_router)

__all__ = ["v1_router"]
