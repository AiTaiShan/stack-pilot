from fastapi import APIRouter
from app.api.v1 import auth, users, projects, members, configs, deployments, monitoring

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(members.router)
api_router.include_router(configs.router)
api_router.include_router(deployments.router)
api_router.include_router(monitoring.router)
