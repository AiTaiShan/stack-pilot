"""AI 服务 - 集成大模型进行配置审核和优化"""
import os
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """工具调用结果"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any


class FileTools:
    """文件操作工具 - 提供给大模型使用"""

    @staticmethod
    def read_file(file_path: str) -> Dict[str, Any]:
        """读取文件内容"""
        try:
            if not os.path.exists(file_path):
                return {"success": False, "error": f"File not found: {file_path}"}

            with open(file_path, "r") as f:
                content = f.read()

            # 尝试解析为 JSON
            try:
                data = json.loads(content)
                return {"success": True, "content": content, "data": data, "format": "json"}
            except json.JSONDecodeError:
                return {"success": True, "content": content, "format": "text"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def write_file(file_path: str, content: str) -> Dict[str, Any]:
        """写入文件内容"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write(content)
            return {"success": True, "message": f"File written: {file_path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def edit_json(file_path: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """编辑 JSON 文件 - 合并更新"""
        try:
            if not os.path.exists(file_path):
                return {"success": False, "error": f"File not found: {file_path}"}

            with open(file_path, "r") as f:
                data = json.load(f)

            # 递归合并更新
            def merge_dict(base: dict, update: dict):
                for key, value in update.items():
                    if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                        merge_dict(base[key], value)
                    else:
                        base[key] = value

            merge_dict(data, updates)

            with open(file_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def list_files(directory: str, pattern: str = "*") -> Dict[str, Any]:
        """列出目录文件"""
        try:
            import glob
            full_pattern = os.path.join(directory, pattern)
            files = glob.glob(full_pattern, recursive=True)
            return {"success": True, "files": files}
        except Exception as e:
            return {"success": False, "error": str(e)}


class AIService:
    """AI 服务 - 集成大模型"""

    def __init__(self, api_key: str = None, base_url: str = None):
        from app.core.config import settings
        # 从 settings 读取（已通过 pydantic-settings 加载 .env）
        self.api_key = api_key or settings.LLM_API_KEY or ""
        self.base_url = base_url or settings.LLM_BASE_URL or "https://api.anthropic.com"
        self.model = settings.LLM_MODEL or "claude-sonnet-4-20250514"
        self.provider = settings.LLM_PROVIDER or "openai"
        self.file_tools = FileTools()

    def chat(self, prompt: str, system: str = None) -> Dict[str, Any]:
        """简单对话接口"""
        messages = [{"role": "user", "content": prompt}]
        result = self._call_ai(messages, system=system)
        if "error" in result:
            return {"response": "", "error": result["error"]}
        content = result.get("content", [])
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")
        return {"response": text}

    def _call_ai(self, messages: List[Dict], tools: List[Dict] = None, system: str = None) -> Dict:
        """调用大模型 API - 支持多种提供商"""
        import httpx

        # 快速失败：API key 未配置或是占位符时直接返回错误
        if not self.api_key or self.api_key in ("your-api-key-here", "xxx", "CHANGE_ME", ""):
            return {"error": "LLM API key not configured"}

        # 根据 provider 选择调用方式
        if self.provider == "anthropic":
            return self._call_anthropic(messages, tools, system)
        else:
            # OpenAI 兼容接口（包括 dashscope）
            return self._call_openai_compatible(messages, tools, system)

    def _call_anthropic(self, messages: List[Dict], tools: List[Dict] = None, system: str = None) -> Dict:
        """调用 Anthropic API"""
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages
        }

        if system:
            payload["system"] = system

        if tools:
            payload["tools"] = tools

        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{self.base_url}/v1/messages",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Anthropic API call failed: %s", e)
            return {"error": str(e)}

    def _call_openai_compatible(self, messages: List[Dict], tools: List[Dict] = None, system: str = None) -> Dict:
        """调用 OpenAI 兼容 API（包括 dashscope）"""
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 转换消息格式
        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            openai_messages.append(msg)

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": openai_messages
        }

        # 转换工具格式
        if tools:
            openai_tools = []
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "parameters": tool.get("input_schema")
                    }
                })
            payload["tools"] = openai_tools

        try:
            url = f"{self.base_url}/chat/completions"
            with httpx.Client(timeout=120) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                openai_result = response.json()

            # 转换回 Anthropic 格式
            return self._convert_openai_to_anthropic(openai_result)

        except Exception as e:
            logger.error("OpenAI compatible API call failed: %s", e)
            return {"error": str(e)}

    def _convert_openai_to_anthropic(self, openai_result: Dict) -> Dict:
        """将 OpenAI 格式转换为 Anthropic 格式"""
        choice = openai_result.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = []

        # 处理文本内容
        if message.get("content"):
            content.append({
                "type": "text",
                "text": message["content"]
            })

        # 处理工具调用
        if message.get("tool_calls"):
            for tool_call in message["tool_calls"]:
                func = tool_call.get("function", {})
                content.append({
                    "type": "tool_use",
                    "id": tool_call.get("id", ""),
                    "name": func.get("name"),
                    "input": json.loads(func.get("arguments", "{}"))
                })

        return {
            "content": content,
            "stop_reason": choice.get("finish_reason", "end_turn")
        }

    def review_dockerfile(self, dockerfile_content: str, project_info: Dict) -> Dict[str, Any]:
        """审核 Dockerfile"""
        system_prompt = """你是一个 Docker 和容器化专家。你的任务是审核 Dockerfile 并提供改进建议。

你需要检查：
1. 基础镜像选择是否合适
2. 安全性（是否使用 root 用户、是否有敏感信息泄露）
3. 镜像大小优化（多阶段构建、清理缓存）
4. 层缓存优化（依赖安装顺序）
5. 最佳实践（COPY 顺序、EXPOSE、CMD/ENTRYPOINT）

你可以使用以下工具：
- read_file: 读取文件内容
- write_file: 写入文件内容
- edit_json: 编辑 JSON 文件

如果 Dockerfile 有问题，直接修改文件并返回修改后的内容。
如果没问题，返回 {"approved": true}。"""

        messages = [
            {
                "role": "user",
                "content": f"""请审核以下 Dockerfile：

```dockerfile
{dockerfile_content}
```

项目信息：
- 语言: {project_info.get('language', 'unknown')}
- 框架: {project_info.get('framework', 'unknown')}
- 启动命令: {project_info.get('start_cmd', 'N/A')}

请检查并修改，然后返回审核结果。"""
            }
        ]

        tools = [
            {
                "name": "read_file",
                "description": "读取文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "write_file",
                "description": "写入文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"}
                    },
                    "required": ["file_path", "content"]
                }
            }
        ]

        result = self._call_ai(messages, tools=tools, system=system_prompt)

        if "error" in result:
            return {"approved": None, "skipped": True, "reason": result["error"]}

        # 处理工具调用
        return self._process_tool_calls(result)

    def review_docker_compose(self, compose_content: str, project_info: Dict, deps_info: Dict) -> Dict[str, Any]:
        """审核 docker-compose.yml"""
        system_prompt = """你是 Docker Compose 和微服务架构专家。你的任务是审核 docker-compose.yml 配置。

你需要检查：
1. 服务依赖关系是否正确（depends_on）
2. 网络配置是否合理
3. 数据卷挂载是否正确
4. 环境变量配置是否完整
5. 端口映射是否冲突
6. 健康检查配置
7. 重启策略
8. 资源限制

你可以使用以下工具：
- read_file: 读取文件内容
- write_file: 写入文件内容
- edit_json: 编辑 JSON 文件
- list_files: 列出目录文件

如果配置有问题，直接修改文件并返回修改后的内容。
如果没问题，返回 {"approved": true}。"""

        messages = [
            {
                "role": "user",
                "content": f"""请审核以下 docker-compose.yml：

```yaml
{compose_content}
```

项目信息：
- 类型: {project_info.get('type', 'single')}
- 语言: {project_info.get('language', 'unknown')}
- 框架: {project_info.get('framework', 'unknown')}

外部依赖：
{json.dumps(deps_info.get('external_services', []), indent=2)}

数据库初始化信息：
{json.dumps(deps_info.get('database_init', {}), indent=2)}

请检查并修改，然后返回审核结果。"""
            }
        ]

        tools = [
            {
                "name": "read_file",
                "description": "读取文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "write_file",
                "description": "写入文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"}
                    },
                    "required": ["file_path", "content"]
                }
            },
            {
                "name": "list_files",
                "description": "列出目录文件",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "目录路径"},
                        "pattern": {"type": "string", "description": "文件模式（如 *.yml）", "default": "*"}
                    },
                    "required": ["directory"]
                }
            }
        ]

        result = self._call_ai(messages, tools=tools, system=system_prompt)

        if "error" in result:
            return {"approved": None, "skipped": True, "reason": result["error"]}

        return self._process_tool_calls(result)

    def _process_tool_calls(self, ai_response: Dict) -> Dict[str, Any]:
        """处理 AI 的工具调用"""
        content = ai_response.get("content", [])

        tool_calls = []
        final_text = ""

        for block in content:
            if block.get("type") == "tool_use":
                tool_name = block.get("name")
                tool_input = block.get("input", {})

                # 执行工具调用
                result = self._execute_tool(tool_name, tool_input)
                tool_calls.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "result": result
                })

            elif block.get("type") == "text":
                final_text += block.get("text", "")

        # 检查是否批准
        approved = True
        if "approved" in final_text.lower() or '"approved": true' in final_text:
            approved = True
        elif tool_calls:
            # 如果有文件修改，说明需要修改
            for call in tool_calls:
                if call["tool"] in ("write_file", "edit_json"):
                    if call["result"].get("success"):
                        approved = True  # 已修改，继续执行

        return {
            "approved": approved,
            "response": final_text,
            "tool_calls": tool_calls,
            "modifications": [c for c in tool_calls if c["tool"] in ("write_file", "edit_json")]
        }

    def _execute_tool(self, tool_name: str, tool_input: Dict) -> Dict:
        """执行工具调用"""
        if tool_name == "read_file":
            return self.file_tools.read_file(tool_input.get("file_path", ""))
        elif tool_name == "write_file":
            return self.file_tools.write_file(
                tool_input.get("file_path", ""),
                tool_input.get("content", "")
            )
        elif tool_name == "edit_json":
            return self.file_tools.edit_json(
                tool_input.get("file_path", ""),
                tool_input.get("updates", {})
            )
        elif tool_name == "list_files":
            return self.file_tools.list_files(
                tool_input.get("directory", ""),
                tool_input.get("pattern", "*")
            )
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    def diagnose_error(self, error_log: str, project_info: Dict) -> Dict[str, Any]:
        """诊断部署错误"""
        system_prompt = """你是 DevOps 和容器化专家。分析部署错误日志并提供修复建议。

输出格式：
{
    "root_cause": "错误根因",
    "fix_steps": ["修复步骤1", "修复步骤2"],
    "prevention": "预防措施"
}"""

        messages = [
            {
                "role": "user",
                "content": f"""分析以下部署错误：

```
{error_log}
```

项目信息：{json.dumps(project_info, indent=2)}

请提供诊断结果和修复建议。"""
            }
        ]

        result = self._call_ai(messages, system=system_prompt)

        if "error" in result:
            return {"root_cause": "Unknown", "fix_steps": [], "prevention": ""}

        content = result.get("content", [])
        for block in content:
            if block.get("type") == "text":
                try:
                    return json.loads(block.get("text", "{}"))
                except (json.JSONDecodeError, ValueError):
                    return {"root_cause": block.get("text", ""), "fix_steps": [], "prevention": ""}

        return {"root_cause": "Unknown", "fix_steps": [], "prevention": ""}


# 全局 AI 服务实例
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """获取 AI 服务实例"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
