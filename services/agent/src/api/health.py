from fastapi import APIRouter
from src.config import settings

router = APIRouter(tags=["健康检查"])

@router.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}
