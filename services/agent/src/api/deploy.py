import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from src.agent.deploy_graph import deploy_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deploy", tags=["部署诊断"])


class DeployDiagnoseRequest(BaseModel):
    """部署诊断请求"""
    deployment_id: str
    failed_step: str
    project_type: str
    language: str
    framework: str
    dockerfile_content: Optional[str] = None
    compose_content: Optional[str] = None
    logs: List[str]
    retry_count: int = 0
    max_retries: int = 3


class DeployDiagnoseResponse(BaseModel):
    """部署诊断响应"""
    diagnosis: str
    suggestions: List[str]
    failure_category: str
    fixable_by_agent: bool
    fixed_content: Optional[str]
    fixed_file_type: Optional[str]
    retry_count: int


@router.post("/diagnose", response_model=DeployDiagnoseResponse)
async def api_deploy_diagnose(request: DeployDiagnoseRequest):
    """部署失败诊断（编排流程）"""
    logger.info("收到部署诊断请求: id=%s, step=%s, language=%s, retry=%d/%d",
                request.deployment_id, request.failed_step,
                request.language, request.retry_count, request.max_retries)

    try:
        # 构建初始状态
        initial_state = {
            "deployment_id": request.deployment_id,
            "failed_step": request.failed_step,
            "project_type": request.project_type,
            "language": request.language,
            "framework": request.framework,
            "dockerfile_content": request.dockerfile_content,
            "compose_content": request.compose_content,
            "logs": request.logs,
            "retry_count": request.retry_count,
            "max_retries": request.max_retries,
            # 输出字段初始化
            "diagnosis": "",
            "suggestions": [],
            "failure_category": "infra_error",
            "fixable_by_agent": False,
            "fixed_content": None,
            "fixed_file_type": None,
            "_next": "end"
        }

        # 运行 deploy_graph
        result = await deploy_graph.ainvoke(initial_state)

        logger.info("诊断完成: category=%s, fixable=%s",
                     result.get("failure_category"), result.get("fixable_by_agent"))

        return DeployDiagnoseResponse(
            diagnosis=result.get("diagnosis", "诊断失败"),
            suggestions=result.get("suggestions", []),
            failure_category=result.get("failure_category", "infra_error"),
            fixable_by_agent=result.get("fixable_by_agent", False),
            fixed_content=result.get("fixed_content"),
            fixed_file_type=result.get("fixed_file_type"),
            retry_count=request.retry_count + 1
        )
    except Exception as e:
        logger.error("诊断流程异常: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"诊断失败: {str(e)}")
