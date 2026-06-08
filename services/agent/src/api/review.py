import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from src.review.dockerfile import review_dockerfile
from src.review.compose import review_compose
from src.review.env import review_env

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["审核"])


class ProjectInfo(BaseModel):
    language: str
    framework: str
    version: str
    port: int
    project_type: str


class ReviewDockerfileRequest(BaseModel):
    project_info: ProjectInfo
    dockerfile_content: str


class ReviewComposeRequest(BaseModel):
    project_info: ProjectInfo
    compose_content: str


class ReviewEnvRequest(BaseModel):
    project_info: ProjectInfo
    env_vars: Dict[str, str]


class ReviewIssue(BaseModel):
    category: str
    severity: str
    description: str
    file_path: str
    fix_suggestion: str


class ReviewResponse(BaseModel):
    status: str
    issues: List[ReviewIssue]
    fixed_content: Optional[str]
    suggestions: List[str]


@router.post("/dockerfile", response_model=ReviewResponse)
async def api_review_dockerfile(request: ReviewDockerfileRequest):
    lang = request.project_info.language
    framework = request.project_info.framework
    logger.info("收到 Dockerfile 审核请求: language=%s, framework=%s", lang, framework)
    try:
        result = await review_dockerfile(
            project_info=request.project_info.model_dump(),
            dockerfile_content=request.dockerfile_content
        )
        logger.info("Dockerfile 审核完成: status=%s, issues=%d", result["status"], len(result["issues"]))
        return result
    except Exception as e:
        logger.error("Dockerfile 审核异常: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compose", response_model=ReviewResponse)
async def api_review_compose(request: ReviewComposeRequest):
    lang = request.project_info.language
    framework = request.project_info.framework
    logger.info("收到 Compose 审核请求: language=%s, framework=%s", lang, framework)
    try:
        result = await review_compose(
            project_info=request.project_info.model_dump(),
            compose_content=request.compose_content
        )
        logger.info("Compose 审核完成: status=%s, issues=%d", result["status"], len(result["issues"]))
        return result
    except Exception as e:
        logger.error("Compose 审核异常: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/env", response_model=ReviewResponse)
async def api_review_env(request: ReviewEnvRequest):
    lang = request.project_info.language
    logger.info("收到环境变量审核请求: language=%s, env_var_count=%d", lang, len(request.env_vars))
    try:
        result = await review_env(
            project_info=request.project_info.model_dump(),
            env_vars=request.env_vars
        )
        logger.info("环境变量审核完成: status=%s, issues=%d", result["status"], len(result["issues"]))
        return result
    except Exception as e:
        logger.error("环境变量审核异常: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
