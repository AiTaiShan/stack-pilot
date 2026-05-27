# StackPilot API 文档

## 概述

StackPilot API 是一个 RESTful API，用于管理智能部署 Agent 的各项功能。所有 API 端点都需要 JWT 认证（除登录和注册外）。

**基础路径**: `/api/v1`

**认证方式**: Bearer Token（JWT）

---

## 认证模块 /api/v1/auth

### POST /api/v1/auth/register — 用户注册

创建新用户账户。

**请求参数**:
```json
{
  "username": "string",  // 用户名，3-50个字符
  "email": "string",     // 邮箱地址
  "password": "string"   // 密码，最少8个字符
}
```

**响应格式**:
```json
{
  "id": "integer",
  "username": "string",
  "email": "string",
  "created_at": "datetime"
}
```

**认证要求**: 无需认证

---

### POST /api/v1/auth/login — 用户登录

用户登录并获取访问令牌。

**请求参数**:
```json
{
  "username": "string",
  "password": "string"
}
```

**响应格式**:
```json
{
  "token": "string",         // JWT 访问令牌
  "refresh_token": "string", // 刷新令牌
  "user": {
    "id": "integer",
    "username": "string",
    "email": "string"
  }
}
```

**认证要求**: 无需认证

---

## 用户模块 /api/v1/users

### GET /api/v1/users/me — 获取当前用户信息

获取当前已认证用户的详细信息。

**请求参数**: 无

**响应格式**:
```json
{
  "id": "integer",
  "username": "string",
  "email": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### PUT /api/v1/users/me — 更新用户信息

更新当前已认证用户的信息。

**请求参数**:
```json
{
  "email": "string",     // 可选
  "password": "string"   // 可选
}
```

**响应格式**:
```json
{
  "id": "integer",
  "username": "string",
  "email": "string",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

## 项目模块 /api/v1/projects

### GET /api/v1/projects — 获取项目列表

获取当前用户的所有项目。

**请求参数**:
- `page` (query, 可选): 页码，默认 1
- `per_page` (query, 可选): 每页数量，默认 20

**响应格式**:
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "git_url": "string",
      "description": "string",
      "created_at": "datetime",
      "updated_at": "datetime"
    }
  ],
  "total": "integer",
  "page": "integer",
  "per_page": "integer"
}
```

**认证要求**: 需要 JWT 认证

---

### POST /api/v1/projects — 创建项目

创建新的部署项目。

**请求参数**:
```json
{
  "name": "string",          // 项目名称
  "git_url": "string",       // Git 仓库地址
  "description": "string"    // 项目描述（可选）
}
```

**响应格式**:
```json
{
  "id": "integer",
  "name": "string",
  "git_url": "string",
  "description": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### GET /api/v1/projects/{id} — 获取项目详情

获取指定项目的详细信息。

**路径参数**:
- `id` (integer): 项目 ID

**响应格式**:
```json
{
  "id": "integer",
  "name": "string",
  "git_url": "string",
  "description": "string",
  "created_at": "datetime",
  "updated_at": "datetime",
  "deployments": [
    {
      "id": "integer",
      "status": "string",
      "created_at": "datetime"
    }
  ]
}
```

**认证要求**: 需要 JWT 认证

---

## 成员模块 /api/v1/members

### GET /api/v1/members — 获取成员列表

获取项目的所有成员。

**请求参数**:
- `project_id` (query, 必需): 项目 ID

**响应格式**:
```json
{
  "items": [
    {
      "id": "integer",
      "user_id": "integer",
      "username": "string",
      "email": "string",
      "role": "string",  // owner, admin, member
      "joined_at": "datetime"
    }
  ]
}
```

**认证要求**: 需要 JWT 认证

---

### POST /api/v1/members — 添加成员

向项目添加新成员。

**请求参数**:
```json
{
  "project_id": "integer",
  "user_id": "integer",
  "role": "string"  // admin, member
}
```

**响应格式**:
```json
{
  "id": "integer",
  "user_id": "integer",
  "project_id": "integer",
  "role": "string",
  "joined_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证（项目 owner 或 admin）

---

### PUT /api/v1/members/{id} — 更新成员角色

更新项目成员的角色。

**路径参数**:
- `id` (integer): 成员记录 ID

**请求参数**:
```json
{
  "role": "string"  // admin, member
}
```

**响应格式**:
```json
{
  "id": "integer",
  "user_id": "integer",
  "project_id": "integer",
  "role": "string",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证（项目 owner）

---

### DELETE /api/v1/members/{id} — 移除成员

从项目中移除成员。

**路径参数**:
- `id` (integer): 成员记录 ID

**响应格式**:
```json
{
  "message": "成员已移除"
}
```

**认证要求**: 需要 JWT 认证（项目 owner 或 admin）

---

## 配置模块 /api/v1/configs

### GET /api/v1/configs — 获取所有配置

获取项目的所有配置项。

**请求参数**:
- `project_id` (query, 必需): 项目 ID

**响应格式**:
```json
{
  "items": [
    {
      "key": "string",
      "value": "string",
      "description": "string",
      "created_at": "datetime",
      "updated_at": "datetime"
    }
  ]
}
```

**认证要求**: 需要 JWT 认证

---

### GET /api/v1/configs/{key} — 获取配置

获取指定配置项。

**路径参数**:
- `key` (string): 配置键名

**请求参数**:
- `project_id` (query, 必需): 项目 ID

**响应格式**:
```json
{
  "key": "string",
  "value": "string",
  "description": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### POST /api/v1/configs — 创建配置

创建新的配置项。

**请求参数**:
```json
{
  "project_id": "integer",
  "key": "string",
  "value": "string",
  "description": "string"  // 可选
}
```

**响应格式**:
```json
{
  "key": "string",
  "value": "string",
  "description": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### PUT /api/v1/configs/{key} — 更新配置

更新指定配置项。

**路径参数**:
- `key` (string): 配置键名

**请求参数**:
```json
{
  "project_id": "integer",
  "value": "string",
  "description": "string"  // 可选
}
```

**响应格式**:
```json
{
  "key": "string",
  "value": "string",
  "description": "string",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### DELETE /api/v1/configs/{key} — 删除配置

删除指定配置项。

**路径参数**:
- `key` (string): 配置键名

**请求参数**:
- `project_id` (query, 必需): 项目 ID

**响应格式**:
```json
{
  "message": "配置已删除"
}
```

**认证要求**: 需要 JWT 认证

---

## 部署模块 /api/v1/deployments

### POST /api/v1/deployments — 创建部署

为项目创建新的部署任务。

**请求参数**:
```json
{
  "project_id": "integer",
  "branch": "string",      // 部署分支，默认 main
  "commit_hash": "string", // 可选，指定 commit
  "environment": "string"  // 环境：staging, production
}
```

**响应格式**:
```json
{
  "id": "integer",
  "project_id": "integer",
  "status": "pending",
  "branch": "string",
  "commit_hash": "string",
  "environment": "string",
  "created_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### GET /api/v1/deployments/{id}/status — 获取部署状态

获取部署任务的当前状态。

**路径参数**:
- `id` (integer): 部署 ID

**响应格式**:
```json
{
  "id": "integer",
  "status": "string",  // pending, building, deploying, success, failed, cancelled
  "progress": "integer",  // 0-100
  "message": "string",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### GET /api/v1/deployments/{id}/logs — 获取部署日志

获取部署过程的日志输出。

**路径参数**:
- `id` (integer): 部署 ID

**请求参数**:
- `offset` (query, 可选): 日志偏移量
- `limit` (query, 可选): 返回日志行数，默认 100

**响应格式**:
```json
{
  "logs": [
    {
      "timestamp": "datetime",
      "level": "string",  // info, warn, error
      "message": "string"
    }
  ],
  "total": "integer"
}
```

**认证要求**: 需要 JWT 认证

---

### POST /api/v1/deployments/{id}/cancel — 取消部署

取消正在执行的部署任务。

**路径参数**:
- `id` (integer): 部署 ID

**响应格式**:
```json
{
  "id": "integer",
  "status": "cancelled",
  "message": "部署已取消",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### POST /api/v1/deployments/{id}/pause — 暂停部署

暂停正在执行的部署任务。

**路径参数**:
- `id` (integer): 部署 ID

**响应格式**:
```json
{
  "id": "integer",
  "status": "paused",
  "message": "部署已暂停",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### POST /api/v1/deployments/{id}/resume — 恢复部署

恢复已暂停的部署任务。

**路径参数**:
- `id` (integer): 部署 ID

**响应格式**:
```json
{
  "id": "integer",
  "status": "deploying",
  "message": "部署已恢复",
  "updated_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

### POST /api/v1/deployments/{id}/rollback — 回滚部署

回滚到上一个成功的部署版本。

**路径参数**:
- `id` (integer): 部署 ID

**响应格式**:
```json
{
  "id": "integer",
  "status": "rolling_back",
  "message": "正在回滚...",
  "created_at": "datetime"
}
```

**认证要求**: 需要 JWT 认证

---

## 监控模块 /api/v1/monitoring

### GET /api/v1/monitoring/status — 系统状态

获取系统整体运行状态。

**请求参数**: 无

**响应格式**:
```json
{
  "status": "healthy",  // healthy, degraded, unhealthy
  "version": "string",
  "uptime": "integer",  // 秒
  "services": {
    "database": "connected",
    "redis": "connected",
    "llm_api": "available"
  }
}
```

**认证要求**: 需要 JWT 认证

---

### GET /api/v1/monitoring/metrics/{name} — 获取指标

获取指定监控指标。

**路径参数**:
- `name` (string): 指标名称（deployments_total, success_rate, avg_duration 等）

**请求参数**:
- `start_time` (query, 可选): 开始时间
- `end_time` (query, 可选): 结束时间
- `interval` (query, 可选): 聚合间隔（1h, 6h, 1d, 7d）

**响应格式**:
```json
{
  "name": "string",
  "data_points": [
    {
      "timestamp": "datetime",
      "value": "number"
    }
  ]
}
```

**认证要求**: 需要 JWT 认证

---

### GET /api/v1/monitoring/deployments/stats — 部署统计

获取部署统计数据。

**请求参数**:
- `project_id` (query, 可选): 项目 ID
- `period` (query, 可选): 统计周期（7d, 30d, 90d），默认 30d

**响应格式**:
```json
{
  "total": "integer",
  "successful": "integer",
  "failed": "integer",
  "success_rate": "number",
  "avg_duration": "number",  // 秒
  "by_status": {
    "pending": "integer",
    "building": "integer",
    "deploying": "integer",
    "success": "integer",
    "failed": "integer",
    "cancelled": "integer"
  }
}
```

**认证要求**: 需要 JWT 认证

---

## 错误响应格式

所有 API 错误响应遵循以下格式：

```json
{
  "detail": "错误描述信息"
}
```

**常见 HTTP 状态码**:
- `200`: 成功
- `201`: 创建成功
- `400`: 请求参数错误
- `401`: 未认证
- `403`: 无权限
- `404`: 资源不存在
- `422`: 请求参数验证失败
- `500`: 服务器内部错误
