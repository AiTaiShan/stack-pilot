import pytest


def test_register_success(client):
    """测试注册成功"""
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "Test1234"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["user"]["username"] == "testuser"


def test_register_duplicate_username(client):
    """测试用户名重复"""
    client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test1@example.com",
        "password": "Test1234"
    })
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test2@example.com",
        "password": "Test1234"
    })
    assert response.status_code == 400
    assert "用户名已被使用" in response.json()["detail"]


def test_login_success(client):
    """测试登录成功"""
    client.post("/api/v1/auth/register", json={
        "username": "logintest",
        "email": "login@example.com",
        "password": "Test1234"
    })
    response = client.post("/api/v1/auth/login", json={
        "username": "logintest",
        "password": "Test1234"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "token" in data["data"]
    assert "refresh_token" in data["data"]


def test_login_wrong_password(client):
    """测试密码错误"""
    response = client.post("/api/v1/auth/login", json={
        "username": "nonexistent",
        "password": "wrongpassword"
    })
    assert response.status_code == 401
    assert "用户名或密码错误" in response.json()["detail"]
