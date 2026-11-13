from fastapi import APIRouter

from app.api.routes import audit, auth, documents, evidence, exports, matters, workflows

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(matters.router, tags=["matters"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(workflows.router, tags=["workflows"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(exports.router, tags=["exports"])
api_router.include_router(evidence.router, tags=["evidence-review"])
