"""集成测试：验证多个 API 端点的端到端流程。"""


def test_full_project_flow(client, auth_headers):
    """完整项目流程：注册(由 auth_headers 完成) → 创建项目 → 列表 → 详情。"""
    # 创建项目
    resp = client.post(
        "/api/v1/projects/",
        json={
            "name": "Integration Project",
            "git_url": "https://github.com/test/integration.git",
            "description": "集成测试项目",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    project_id = data["data"]["id"]

    # 获取项目列表 → 包含新项目
    resp = client.get("/api/v1/projects/", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert any(p["id"] == project_id for p in items)

    # 获取项目详情 → 名称正确
    resp = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()["data"]
    assert detail["name"] == "Integration Project"
    assert detail["id"] == project_id


def test_config_management_flow(client, auth_headers):
    """配置管理流程：创建 → 获取 → 更新 → 删除。"""
    # 创建配置
    resp = client.post(
        "/api/v1/configs/",
        json={
            "key": "test_deploy_timeout",
            "value": 300,
            "value_type": "integer",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["key"] == "test_deploy_timeout"
    assert data["data"]["value"] == 300

    # 获取配置
    resp = client.get("/api/v1/configs/test_deploy_timeout", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["value"] == 300

    # 更新配置
    resp = client.put(
        "/api/v1/configs/test_deploy_timeout",
        json={"value": 600, "value_type": "integer"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["value"] == 600

    # 删除配置
    resp = client.delete("/api/v1/configs/test_deploy_timeout", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 200

    # 验证已删除
    resp = client.get("/api/v1/configs/test_deploy_timeout", headers=auth_headers)
    assert resp.json()["code"] == 404


def test_monitoring_endpoints(client, auth_headers):
    """监控端点：status 和 deployments/stats。"""
    # 系统状态
    resp = client.get("/api/v1/monitoring/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("running", "healthy")

    # 部署统计
    resp = client.get("/api/v1/monitoring/deployments/stats", headers=auth_headers)
    assert resp.status_code == 200
    stats = resp.json()
    assert "total" in stats
    assert "success" in stats
    assert "failed" in stats


def test_health_and_root(client):
    """基础端点：/health 和 /。"""
    # 健康检查
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

    # 根路径
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "name" in body
    assert "version" in body
    assert "status" in body


def test_unauthorized_access(client):
    """未授权访问受保护端点应返回 401 或 403。"""
    resp = client.get("/api/v1/projects/")
    assert resp.status_code in (401, 403)
