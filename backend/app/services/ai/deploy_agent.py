"""部署审核编排 Agent — 使用 LangGraph StateGraph 实现

架构: 审核者(检查+修复) → 调度者(判断循环)

流程:
1. 审核者: 检查 Dockerfile 并直接修复发现的问题
2. 调度者: 判断是否还有问题，循环直到无问题或达到最大轮数
"""
import json
import logging
from typing import Dict, List, Optional, Any, TypedDict, Literal

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


# ========== 状态定义 ==========

class ReviewIssue(TypedDict):
    """审核发现的问题"""
    category: str
    severity: str
    description: str
    file_path: str
    fix_suggestion: str


class DeploymentReviewState(TypedDict):
    """审核状态"""
    repo_dir: str
    project_info: dict
    issues: List[ReviewIssue]
    fixed_files: List[str]
    round: int
    max_rounds: int
    status: str  # reviewing | done | failed


# ========== 审核维度 ==========

REVIEW_DIMENSIONS = {
    "node": ["version_mismatch", "port_mapping", "config_adapt", "pkg_manager"],
    "python": ["version_mismatch", "port_mapping", "config_adapt", "dep_check"],
    "go": ["version_mismatch", "port_mapping", "config_adapt"],
    "java": ["version_mismatch", "port_mapping", "config_adapt", "dep_check"],
    "rust": ["version_mismatch", "port_mapping"],
    "php": ["version_mismatch", "port_mapping"],
    "ruby": ["version_mismatch", "port_mapping"],
    "dotnet": ["version_mismatch", "port_mapping"],
}

FRAMEWORK_DIMENSIONS = {
    "wails": ["frontend_build", "embed_check"],
    "next": ["node_build"],
    "nuxt": ["node_build"],
}


# ========== 节点 ==========

def reviewer_node(state: DeploymentReviewState) -> Dict:
    """审核者: 检查 Dockerfile 并直接修复"""
    import os
    import re

    repo_dir = state["repo_dir"]
    project_info = state["project_info"]
    framework = project_info.get("framework", "")
    language = project_info.get("language", "")
    version = project_info.get("version", "")
    port = project_info.get("port", 8080)
    issues = []
    fixed_files = []

    dockerfile_path = os.path.join(repo_dir, "Dockerfile")

    # 从 go.mod 读取版本（如果 project_info 中没有）
    if language == "go" and not version:
        go_mod_path = os.path.join(repo_dir, "go.mod")
        if os.path.exists(go_mod_path):
            with open(go_mod_path, errors="ignore") as f:
                for line in f:
                    if line.startswith("go "):
                        version = line.strip()[3:].strip()
                        project_info["version"] = version
                        break

    # 如果 Dockerfile 不存在，无法审核
    if not os.path.exists(dockerfile_path):
        issues.append(ReviewIssue(
            category="missing_file", severity="high",
            description="Dockerfile 不存在",
            file_path="Dockerfile", fix_suggestion="生成 Dockerfile"
        ))
        return {"issues": issues, "fixed_files": fixed_files, "round": state["round"] + 1}

    with open(dockerfile_path, errors="ignore") as f:
        df_content = f.read()

    # --- 检查 1: Wails 前端构建 ---
    if framework == "wails":
        has_frontend_build = "npm" in df_content and "build" in df_content
        if not has_frontend_build:
            frontend_dir = os.path.join(repo_dir, "frontend")
            if os.path.isdir(frontend_dir):
                issues.append(ReviewIssue(
                    category="frontend_build", severity="high",
                    description="Wails 项目缺少前端构建步骤",
                    file_path="Dockerfile",
                    fix_suggestion="添加 Node.js 多阶段构建"
                ))
                # 直接修复：重写 Dockerfile（根据 lock 文件选择包管理器）
                go_version = version or "1.24"
                frontend_dir = os.path.join(repo_dir, "frontend")

                # 检测前端包管理器
                if os.path.exists(os.path.join(frontend_dir, "pnpm-lock.yaml")):
                    pkg_mgr = "pnpm"
                    install_cmd = "RUN corepack enable && corepack prepare pnpm@latest --activate\nRUN pnpm install --registry https://registry.npmmirror.com"
                    build_cmd = "RUN pnpm build"
                    copy_lock = "COPY frontend/package.json frontend/pnpm-lock.yaml* frontend/pnpm-workspace.yaml* ./"
                elif os.path.exists(os.path.join(frontend_dir, "yarn.lock")):
                    pkg_mgr = "yarn"
                    install_cmd = "RUN yarn install --registry https://registry.npmmirror.com"
                    build_cmd = "RUN yarn build"
                    copy_lock = "COPY frontend/package.json frontend/yarn.lock* ./"
                else:
                    pkg_mgr = "npm"
                    install_cmd = "RUN npm install --registry https://registry.npmmirror.com --legacy-peer-deps"
                    build_cmd = "RUN npm run build"
                    copy_lock = "COPY frontend/package.json frontend/package-lock.json* ./"

                logger.info("Wails frontend package manager detected: %s", pkg_mgr)

                new_dockerfile = f"""FROM node:lts-alpine AS frontend-builder
WORKDIR /app/frontend
{copy_lock}
{install_cmd}
COPY frontend/ .
{build_cmd}

FROM golang:{go_version}-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
ENV GOPROXY=https://goproxy.cn,direct
RUN go mod download
COPY . .
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
RUN CGO_ENABLED=0 GOOS=linux go build -tags production -o main .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/main .
EXPOSE {port}
CMD ["./main"]
"""
                with open(dockerfile_path, "w") as f:
                    f.write(new_dockerfile)
                fixed_files.append("Dockerfile")
                df_content = new_dockerfile
                logger.info("Wails Dockerfile rewritten with frontend build stage")

    # --- 检查 2: go:embed 前端资源 ---
    if language == "go" and framework != "wails":
        main_go = os.path.join(repo_dir, "main.go")
        if os.path.exists(main_go):
            with open(main_go, errors="ignore") as f:
                main_content = f.read()
            if "//go:embed" in main_content and "frontend" in main_content.lower():
                has_frontend_step = "npm" in df_content or "frontend/dist" in df_content
                if not has_frontend_step:
                    issues.append(ReviewIssue(
                        category="embed_check", severity="high",
                        description="main.go 使用 //go:embed 嵌入前端资源",
                        file_path="Dockerfile", fix_suggestion="添加前端构建阶段"
                    ))

    # --- 检查 3: GOPROXY ---
    if language == "go" and "GOPROXY" not in df_content:
        issues.append(ReviewIssue(
            category="config_adapt", severity="medium",
            description="Go 项目未设置 GOPROXY",
            file_path="Dockerfile", fix_suggestion="添加 ENV GOPROXY"
        ))
        if "go mod download" in df_content:
            df_content = df_content.replace(
                "RUN go mod download",
                "ENV GOPROXY=https://goproxy.cn,direct\nRUN go mod download"
            )
            with open(dockerfile_path, "w") as f:
                f.write(df_content)
            fixed_files.append("Dockerfile")

    # --- 检查 4: 版本匹配 ---
    expected_version = version
    from_matches = re.findall(r"FROM\s+(\S+):(\S+)", df_content)
    for image, tag in from_matches:
        if expected_version and expected_version not in tag and "alpine" not in tag and "lts" not in tag:
            issues.append(ReviewIssue(
                category="version_mismatch", severity="high",
                description=f"基础镜像版本 {tag} 与项目版本 {expected_version} 不匹配",
                file_path="Dockerfile", fix_suggestion=f"改为 {expected_version}"
            ))

    return {
        "issues": issues,
        "fixed_files": list(set(fixed_files)),
        "round": state["round"] + 1,
    }


def dispatcher_node(state: DeploymentReviewState) -> Dict:
    """调度者: 判断是否继续循环"""
    round_num = state["round"]
    max_rounds = state["max_rounds"]
    issues = state.get("issues", [])

    # 没有新问题 → 完成
    if not issues:
        return {"status": "done"}

    # 全部修复了（只有 fixed_files，没有未修复的 high 问题）
    unresolved = [i for i in issues if i.get("severity") == "high" and i["category"] not in ("frontend_build",)]
    if not unresolved:
        return {"status": "done"}

    # 达到最大轮数
    if round_num >= max_rounds:
        logger.warning("达到最大审核轮数 %d", max_rounds)
        return {"status": "failed"}

    return {"status": "reviewing"}


def router_condition(state: DeploymentReviewState) -> Literal["reviewer", "done"]:
    """路由: reviewing → reviewer, 其他 → END"""
    if state["status"] == "reviewing":
        return "reviewer"
    return "done"


# ========== 构建图 ==========

def build_deploy_review_graph() -> StateGraph:
    """构建部署审核 StateGraph"""
    workflow = StateGraph(DeploymentReviewState)

    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("dispatcher", dispatcher_node)

    workflow.set_entry_point("reviewer")

    workflow.add_edge("reviewer", "dispatcher")
    workflow.add_conditional_edges(
        "dispatcher",
        router_condition,
        {"reviewer": "reviewer", "done": END}
    )

    return workflow.compile()


# ========== 便捷接口 ==========

async def run_deploy_review(repo_dir: str, project_info: dict, max_rounds: int = 3) -> Dict[str, Any]:
    """
    运行部署审核流程。

    Args:
        repo_dir: 项目目录
        project_info: 项目检测信息（从 scanner 获得）
        max_rounds: 最大审核轮数

    Returns:
        {"status": "done"|"failed", "issues": [...], "fixed_files": [...], "rounds": int}
    """
    graph = build_deploy_review_graph()

    initial_state: DeploymentReviewState = {
        "repo_dir": repo_dir,
        "project_info": project_info,
        "issues": [],
        "fixed_files": [],
        "round": 0,
        "max_rounds": max_rounds,
        "status": "reviewing",
    }

    result = await graph.ainvoke(initial_state, config={"recursion_limit": max_rounds * 3 + 3})

    return {
        "status": result.get("status", "failed"),
        "issues": result.get("issues", []),
        "fixed_files": result.get("fixed_files", []),
        "rounds": result.get("round", 0),
    }
