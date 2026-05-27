"""监控服务 — 指标采集、计数器、部署统计。"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


class MonitoringService:
    """系统监控服务，负责指标记录和统计。"""

    def __init__(self) -> None:
        self.metrics: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.counters: dict[str, int] = defaultdict(int)
        self.start_time: datetime = datetime.now(timezone.utc)
        self._deployment_records: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 通用指标
    # ------------------------------------------------------------------

    def record_metric(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """记录一条指标，保留最近 1000 条。"""
        entry = {
            "value": value,
            "tags": tags or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        bucket = self.metrics[name]
        bucket.append(entry)
        # 仅保留最近 1000 条
        if len(bucket) > 1000:
            self.metrics[name] = bucket[-1000:]

    def increment_counter(self, name: str, value: int = 1) -> None:
        """增加计数器。"""
        self.counters[name] += value

    def get_metrics(self, name: str, duration: int = 3600) -> list[dict[str, Any]]:
        """获取指定时间范围内的指标（单位：秒）。"""
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - duration
        results: list[dict[str, Any]] = []
        for entry in self.metrics.get(name, []):
            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if ts >= cutoff:
                results.append(entry)
        return results

    def get_counter(self, name: str) -> int:
        """获取计数器值。"""
        return self.counters.get(name, 0)

    def get_system_status(self) -> dict[str, Any]:
        """返回系统整体状态。"""
        now = datetime.now(timezone.utc)
        uptime = (now - self.start_time).total_seconds()
        metrics_count = sum(len(v) for v in self.metrics.values())
        return {
            "status": "running",
            "uptime": uptime,
            "metrics_count": metrics_count,
            "counters": dict(self.counters),
        }

    # ------------------------------------------------------------------
    # 部署指标
    # ------------------------------------------------------------------

    def record_deployment_start(self, deployment_id: str) -> None:
        """记录部署开始。"""
        self._deployment_records[deployment_id] = {
            "start_time": datetime.now(timezone.utc),
            "success": None,
        }
        self.increment_counter("deployments.running")

    def record_deployment_end(self, deployment_id: str, success: bool) -> None:
        """记录部署结束。"""
        if deployment_id in self._deployment_records:
            self._deployment_records[deployment_id]["success"] = success

        self.increment_counter("deployments.total")
        if success:
            self.increment_counter("deployments.success")
        else:
            self.increment_counter("deployments.failed")

    def record_api_request(self, method: str, path: str, status_code: int, duration: float) -> None:
        """记录一次 API 请求。"""
        self.record_metric("api_request", duration, {"method": method, "path": path, "status_code": str(status_code)})
        self.increment_counter("api_requests.total")

    def get_deployment_stats(self) -> dict[str, Any]:
        """返回部署统计信息（从数据库查询）。"""
        from app.core.database import SessionLocal
        from app.models.deployment import Deployment, DeploymentStatus

        db = SessionLocal()
        try:
            total = db.query(Deployment).count()
            success = db.query(Deployment).filter(Deployment.status == DeploymentStatus.SUCCESS).count()
            failed = db.query(Deployment).filter(Deployment.status == DeploymentStatus.FAILED).count()
            running = db.query(Deployment).filter(Deployment.status == DeploymentStatus.RUNNING).count()
            success_rate = (success / total * 100) if total > 0 else 0.0

            return {
                "total": total,
                "success": success,
                "failed": failed,
                "running": running,
                "success_rate": round(success_rate, 2),
            }
        finally:
            db.close()


# 全局单例
monitoring_service = MonitoringService()
