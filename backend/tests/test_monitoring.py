"""监控和日志功能测试。"""

from datetime import datetime, timezone

from app.services.monitoring.monitoring_service import MonitoringService


def test_record_metric():
    """记录指标后能通过 get_metrics 获取。"""
    svc = MonitoringService()
    svc.record_metric("cpu_usage", 72.5, {"host": "web-01"})

    results = svc.get_metrics("cpu_usage")
    assert len(results) == 1
    assert results[0]["value"] == 72.5
    assert results[0]["tags"] == {"host": "web-01"}


def test_increment_counter():
    """增加计数器后能正确读取。"""
    svc = MonitoringService()
    svc.increment_counter("requests")
    svc.increment_counter("requests", 5)

    assert svc.get_counter("requests") == 6
    # 不存在的计数器返回 0
    assert svc.get_counter("nonexistent") == 0


def test_get_system_status():
    """系统状态包含 status 和 uptime。"""
    svc = MonitoringService()
    status = svc.get_system_status()

    assert "status" in status
    assert status["status"] == "running"
    assert "uptime" in status
    assert status["uptime"] >= 0
    assert "metrics_count" in status
    assert "counters" in status


def test_deployment_stats(db):
    """部署统计信息正确。"""
    svc = MonitoringService()
    svc.record_deployment_start("d-001")
    svc.record_deployment_end("d-001", success=True)

    svc.record_deployment_start("d-002")
    svc.record_deployment_end("d-002", success=False)

    stats = svc.get_deployment_stats()
    assert stats["total"] >= 2
    assert stats["success"] >= 1
    assert stats["failed"] >= 1
    assert stats["success_rate"] >= 0


def test_record_api_request():
    """API 请求记录后能正确统计。"""
    svc = MonitoringService()
    svc.record_api_request("GET", "/api/v1/users", 200, 0.12)
    svc.record_api_request("POST", "/api/v1/auth/login", 200, 0.34)

    assert svc.get_counter("api_requests.total") == 2

    metrics = svc.get_metrics("api_request")
    assert len(metrics) == 2
