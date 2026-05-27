import pytest


def test_create_project_success(client, auth_headers):
    """测试创建项目成功"""
    response = client.post(
        "/api/v1/projects/",
        json={"name": "Test Project", "git_url": "https://github.com/test/test.git", "description": "Test description"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["name"] == "Test Project"


def test_create_project_invalid_git_url(client, auth_headers):
    """测试无效Git地址"""
    response = client.post(
        "/api/v1/projects/",
        json={"name": "Test Project", "git_url": "invalid-url"},
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "Git地址格式不正确" in response.json()["detail"]


def test_list_projects(client, auth_headers):
    """测试获取项目列表"""
    client.post(
        "/api/v1/projects/",
        json={"name": "List Test Project", "git_url": "https://github.com/test/list.git"},
        headers=auth_headers
    )
    response = client.get("/api/v1/projects/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["items"]) > 0
