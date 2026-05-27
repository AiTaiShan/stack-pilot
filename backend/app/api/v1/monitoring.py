"""监控 API 路由。"""

from fastapi import APIRouter, Query

from app.services.monitoring.monitoring_service import monitoring_service

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/status")
async def get_status():
    """获取系统状态。"""
    return monitoring_service.get_system_status()


@router.get("/metrics/{name}")
async def get_metrics(name: str, duration: int = Query(default=3600, ge=1)):
    """获取指定名称的指标。"""
    return monitoring_service.get_metrics(name, duration)


@router.get("/deployments/stats")
async def get_deployment_stats():
    """获取部署统计信息。"""
    stats = monitoring_service.get_deployment_stats()
    return {"code": 200, "message": "success", "data": stats}
