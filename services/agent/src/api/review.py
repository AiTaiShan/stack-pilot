from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from src.review.dockerfile import review_dockerfile
from src.review.compose import review_compose
from src.review.env import review_env

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
    try:
        result = await review_dockerfile(
            project_info=request.project_info.model_dump(),
            dockerfile_content=request.dockerfile_content
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compose", response_model=ReviewResponse)
async def api_review_compose(request: ReviewComposeRequest):
    try:
        result = await review_compose(
            project_info=request.project_info.model_dump(),
            compose_content=request.compose_content
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/env", response_model=ReviewResponse)
async def api_review_env(request: ReviewEnvRequest):
    try:
        result = await review_env(
            project_info=request.project_info.model_dump(),
            env_vars=request.env_vars
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
