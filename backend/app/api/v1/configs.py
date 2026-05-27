from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.schemas.config import ConfigCreate, ConfigUpdate
from app.services.config.config_service import ConfigService

router = APIRouter(prefix="/configs", tags=["配置"])


def _ok(data=None, message="success"):
    return {"code": 200, "message": message, "data": data}


@router.get("/")
async def list_configs(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConfigService(db)
    items = service.get_all_configs()
    return _ok({"items": items})


@router.get("/{key}")
async def get_config(
    key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConfigService(db)
    config = service.get_config(key)
    if config is None:
        return {"code": 404, "message": f"配置 '{key}' 不存在", "data": None}
    return _ok(config)


@router.post("/")
async def create_config(
    config_data: ConfigCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConfigService(db)
    result = service.set_config(
        key=config_data.key,
        value=config_data.value,
        value_type=config_data.value_type,
        description=config_data.description,
        is_sensitive=config_data.is_sensitive,
    )
    return _ok(result)


@router.put("/{key}")
async def update_config(
    key: str,
    config_data: ConfigUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConfigService(db)
    result = service.set_config(
        key=key,
        value=config_data.value,
        value_type=config_data.value_type,
        description=config_data.description,
    )
    return _ok(result)


@router.delete("/{key}")
async def delete_config(
    key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConfigService(db)
    deleted = service.delete_config(key)
    if not deleted:
        return {"code": 404, "message": f"配置 '{key}' 不存在", "data": None}
    return _ok(message="删除成功")
