"""env_review.py — 环境变量审核相关的 compose 文件读写工具"""
import os
import yaml
import logging

logger = logging.getLogger(__name__)


def read_compose_service_env(repo_dir: str, service_name: str) -> dict:
    """从 docker-compose.yml 读取指定服务的环境变量"""
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        return {}

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    service = services.get(service_name, {})
    environment = service.get("environment", {})

    if isinstance(environment, list):
        result = {}
        for item in environment:
            if "=" in item:
                k, v = item.split("=", 1)
                result[k] = {"value": v, "source": "docker-compose.yml"}
        return result
    elif isinstance(environment, dict):
        return {k: {"value": str(v), "source": "docker-compose.yml"}
                for k, v in environment.items()}
    return {}


def update_compose_service_env(repo_dir: str, service_name: str, env_vars: dict) -> bool:
    """更新 docker-compose.yml 中指定服务的环境变量

    使用 YAML 解析方式读取、修改、写回，避免正则匹配复杂嵌套结构的脆弱性。
    """
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        return False

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    if service_name not in services:
        logger.warning("Service %s not found in docker-compose.yml", service_name)
        return False

    # 读取现有环境变量（保留未在 env_vars 中出现的）
    existing = services[service_name].get("environment", {})
    if isinstance(existing, dict):
        current = {k: str(v) for k, v in existing.items()}
    elif isinstance(existing, list):
        current = {}
        for item in existing:
            if "=" in str(item):
                k, v = str(item).split("=", 1)
                current[k] = v
    else:
        current = {}

    # 合并更新
    for k, v in env_vars.items():
        if v.get("value") is not None:
            current[k] = v["value"]

    # 写回为 list 格式
    compose["services"][service_name]["environment"] = [
        f"{k}={v}" for k, v in current.items()
    ]

    with open(compose_path, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return True


def delete_compose_service_env_var(repo_dir: str, service_name: str, var_name: str) -> bool:
    """删除 docker-compose.yml 中指定服务的指定环境变量

    使用 YAML 解析方式读取、修改、写回，避免正则匹配复杂嵌套结构的脆弱性。
    """
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        return False

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    if service_name not in services:
        return False

    environment = services[service_name].get("environment", {})

    if isinstance(environment, list):
        new_env = []
        for item in environment:
            if "=" in str(item):
                k, _ = str(item).split("=", 1)
                if k != var_name:
                    new_env.append(item)
        compose["services"][service_name]["environment"] = new_env
    elif isinstance(environment, dict):
        if var_name in environment:
            del environment[var_name]
            compose["services"][service_name]["environment"] = environment
        else:
            return False
    else:
        return False

    with open(compose_path, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return True
