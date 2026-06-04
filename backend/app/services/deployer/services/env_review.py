"""env_review.py — 环境变量审核相关的 compose 文件读写工具

使用正则替换方式只修改 environment 部分，保留文件原有格式（注释、缩进、引号风格等）。
"""
import os
import re
import yaml
import logging

logger = logging.getLogger(__name__)

# 匹配 environment 段落的正则：
#   ^([ \t]*)environment:[ \t]*\n  — environment 关键字行，捕获基础缩进
#   ((?:\1 .+\n?)*)                — 所有缩进更深的行（\1 + 至少一个空格）
_RE_ENV_SECTION = re.compile(
    r'^([ \t]*)environment:[ \t]*\n'
    r'((?:\1 .+\n?)*)',
    re.MULTILINE,
)


def _parse_env_list(environment: list) -> dict:
    """解析 list 格式环境变量为 dict"""
    result = {}
    for item in environment:
        s = str(item)
        if "=" in s:
            k, v = s.split("=", 1)
            result[k] = v
    return result


def _parse_env_dict(environment: dict) -> dict:
    """解析 dict 格式环境变量为 dict（值统一转字符串）"""
    return {k: str(v) for k, v in environment.items()}


def _parse_raw_env(environment) -> dict:
    """根据类型解析环境变量"""
    if isinstance(environment, list):
        return _parse_env_list(environment)
    elif isinstance(environment, dict):
        return _parse_env_dict(environment)
    return {}


def _quote_value_for_dict(v: str) -> str:
    """对 dict 格式的值进行 YAML 引号保护。

    在 YAML dict 格式中，值是独立的 YAML 标量，以下情况需要加引号：
    - 包含 ': '（冒号+空格会被解析为嵌套 key）
    - 包含 ' #'（空格+井号会被解析为注释）
    - 以特殊字符 {, }, [, ], *, &, -, ?, :, |, >, !, %, @, ` 开头
    """
    if re.search(r': | #', v):
        return f'"{v}"'
    if v and v[0] in '{}[]*&-?:|>!%@`':
        return f'"{v}"'
    return v


def _serialize_list(env_dict: dict, item_indent: str) -> str:
    """将 env_dict 序列化为 YAML list 格式字符串（不含 environment: 前缀）

    list 格式中整个 'KEY=VALUE' 是一个 YAML 纯量，值不需要额外引号。
    YAML 解析器会将其作为普通字符串处理，等号、冒号等都不会被特殊解析。

    Args:
        env_dict: 环境变量字典
        item_indent: 列表项的缩进字符串（如 '      '）
    """
    lines = []
    for k, v in env_dict.items():
        if v is None:
            continue
        lines.append(f"{item_indent}- {k}={v}")
    return "\n".join(lines)


def _serialize_dict(env_dict: dict, item_indent: str) -> str:
    """将 env_dict 序列化为 YAML dict 格式字符串（不含 environment: 前缀）

    dict 格式中值是独立的 YAML 标量，需要对特殊字符进行引号保护。

    Args:
        env_dict: 环境变量字典
        item_indent: 字典项的缩进字符串（如 '      '）
    """
    lines = []
    for k, v in env_dict.items():
        if v is None:
            continue
        v_str = _quote_value_for_dict(str(v))
        lines.append(f"{item_indent}{k}: {v_str}")
    return "\n".join(lines)


def _replace_env_section(content: str, new_env_text: str) -> str:
    """用正则替换 environment 段落，保留文件其他部分的原始格式。

    返回替换后的文件内容。如果未找到 environment 段落，原样返回。
    """
    m = _RE_ENV_SECTION.search(content)
    if not m:
        return content

    # group(1) = environment 关键字前的缩进（如 '    '）
    indent = m.group(1)

    # 构建替换文本：environment: + 换行 + 新的环境变量行
    replacement = f"{indent}environment:\n{new_env_text}\n"

    return content[:m.start()] + replacement + content[m.end():]


def _detect_service_env_section(content: str, service_name: str):
    """在原始文件内容中定位指定服务的 environment 段落。

    返回 (is_list_format, indent) 元组，如果未找到则返回 (None, None)。
    """
    # 先用正则找到所有 environment 段落
    # 然后通过 yaml 解析确定哪个段落属于目标服务
    compose = yaml.safe_load(content)
    if compose is None:
        return None, None

    services = compose.get("services", {})
    if service_name not in services:
        return None, None

    existing = services[service_name].get("environment", {})
    if not existing:
        return None, None

    is_list_format = isinstance(existing, list)

    # 通过正则找到目标服务的 environment 段落缩进
    # 策略：找到所有 environment 段落，按在文件中出现的顺序与服务定义顺序对应
    service_order = list(services.keys())
    try:
        service_idx = service_order.index(service_name)
    except ValueError:
        return None, None

    matches = list(_RE_ENV_SECTION.finditer(content))
    if service_idx >= len(matches):
        return None, None

    return is_list_format, matches[service_idx].group(1)


def read_compose_service_env(repo_dir: str, service_name: str) -> dict:
    """从 docker-compose.yml 读取指定服务的环境变量"""
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        return {}

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    if compose is None:
        return {}

    services = compose.get("services", {})
    service = services.get(service_name, {})
    if not service:
        return {}

    environment = service.get("environment", {})

    raw = _parse_raw_env(environment)
    return {k: {"value": v, "source": "docker-compose.yml"} for k, v in raw.items()}


def update_compose_service_env(repo_dir: str, service_name: str, env_vars: dict) -> bool:
    """更新 docker-compose.yml 中指定服务的环境变量

    使用正则替换只修改 environment 部分，保留文件其他部分的原始格式。
    更新后保持 environment 的原始格式（list 或 dict）。
    """
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        return False

    with open(compose_path, "r") as f:
        content = f.read()

    # 检测原始格式和缩进
    is_list_format, base_indent = _detect_service_env_section(content, service_name)
    if is_list_format is None:
        logger.warning("Service %s not found or has no environment section", service_name)
        return False

    # 用 yaml.safe_load 读取现有环境变量
    compose = yaml.safe_load(content)
    existing = compose["services"][service_name].get("environment", {})
    current = _parse_raw_env(existing)

    # 合并更新
    for k, v in env_vars.items():
        if v.get("value") is not None:
            current[k] = v["value"]

    # 计算条目缩进（base_indent + 2 空格）
    item_indent = base_indent + "  "

    # 按原始格式序列化
    if is_list_format:
        new_env_text = _serialize_list(current, item_indent)
    else:
        new_env_text = _serialize_dict(current, item_indent)

    # 正则替换 environment 段落
    new_content = _replace_env_section(content, new_env_text)

    with open(compose_path, "w") as f:
        f.write(new_content)
    return True


def delete_compose_service_env_var(repo_dir: str, service_name: str, var_name: str) -> bool:
    """删除 docker-compose.yml 中指定服务的指定环境变量

    使用正则替换只修改 environment 部分，保留文件其他部分的原始格式。
    如果变量不存在，返回 False。
    """
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        return False

    with open(compose_path, "r") as f:
        content = f.read()

    # 检测原始格式和缩进
    is_list_format, base_indent = _detect_service_env_section(content, service_name)
    if is_list_format is None:
        return False

    # 用 yaml.safe_load 读取现有环境变量
    compose = yaml.safe_load(content)
    existing = compose["services"][service_name].get("environment", {})
    if not existing:
        return False

    current = _parse_raw_env(existing)

    # 检查变量是否存在
    if var_name not in current:
        return False

    # 删除变量
    del current[var_name]

    # 计算条目缩进（base_indent + 2 空格）
    item_indent = base_indent + "  "

    # 按原始格式序列化
    if is_list_format:
        new_env_text = _serialize_list(current, item_indent)
    else:
        new_env_text = _serialize_dict(current, item_indent)

    # 正则替换 environment 段落
    new_content = _replace_env_section(content, new_env_text)

    with open(compose_path, "w") as f:
        f.write(new_content)
    return True


def read_compose_file(repo_dir: str) -> str:
    """读取 docker-compose.yml 文件内容"""
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    if not os.path.exists(compose_path):
        raise FileNotFoundError("docker-compose.yml not found")
    with open(compose_path, "r") as f:
        return f.read()


def write_compose_file(repo_dir: str, content: str) -> bool:
    """写入 docker-compose.yml 文件内容（含 YAML 验证）"""
    # 验证 YAML 格式
    yaml.safe_load(content)

    # 写入文件
    compose_path = os.path.join(repo_dir, "docker-compose.yml")
    with open(compose_path, "w") as f:
        f.write(content)
    return True
