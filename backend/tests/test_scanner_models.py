import pytest
from app.services.scanner.models import ScanResult, ServiceInfo, FrontendInfo, BackendInfo


def test_scan_result_defaults():
    result = ScanResult(
        project_type="single", languages=["python"], language="python", port=8000,
        services=[], key_files={}, dependencies={},
    )
    assert result.project_type == "single"
    assert result.language == "python"
    assert result.port == 8000
    assert result.framework is None


def test_service_info():
    svc = ServiceInfo(name="auth", dir="services/auth", language="go", framework="gin", port=8080, type="service")
    assert svc.name == "auth"
    assert svc.type == "service"
    assert svc.entry_point is None


def test_frontend_info():
    fe = FrontendInfo(dir="frontend", language="javascript", framework="react", port=3000, build_cmd="npm run build", start_cmd="npm start")
    assert fe.framework == "react"
    assert fe.port == 3000


def test_backend_info():
    be = BackendInfo(dir="backend", language="python", framework="fastapi", port=8000, entry_point="main.py", start_cmd="uvicorn main:app")
    assert be.entry_point == "main.py"
