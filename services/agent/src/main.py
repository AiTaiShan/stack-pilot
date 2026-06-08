from fastapi import FastAPI
from src.config import settings
from src.utils.logger import setup_logging
from src.api.health import router as health_router
from src.api.review import router as review_router
from src.api.deploy import router as deploy_router

setup_logging(log_level=settings.LOG_LEVEL, log_dir=settings.LOG_DIR)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="StackPilot AI 审核服务"
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(deploy_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION}
