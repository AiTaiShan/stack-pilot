"""AI 服务 - 集成大模型进行配置审核和优化"""
import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from json_repair import repair_json as json_repair

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

        # 记录 AI 请求到文件日志（截取避免日志过大）
        req_preview = {
            "model": self.model,
            "provider": self.provider,
            "system_len": len(system) if system else 0,
            "messages_count": len(messages),
            "tools_count": len(tools) if tools else 0,
            "first_message_snippet": (messages[0].get("content", "")[:200] if messages else ""),
        }
        logger.info("AI call request: %s", json.dumps(req_preview, ensure_ascii=False, default=str))

        ai_start = datetime.now(timezone.utc)

        # 根据 provider 选择调用方式
        if self.provider == "anthropic":
            result = self._call_anthropic(messages, tools, system)
        else:
            result = self._call_openai_compatible(messages, tools, system)

        ai_end = datetime.now(timezone.utc)
        ai_duration_ms = int((ai_end - ai_start).total_seconds() * 1000)

        # 记录 AI 响应到文件日志
        has_error = "error" in result
        resp_preview = {
            "duration_ms": ai_duration_ms,
            "has_error": has_error,
            "error": result.get("error") if has_error else None,
            "content_blocks": len(result.get("content", [])),
            "stop_reason": result.get("stop_reason"),
        }
        if not has_error:
            for block in result.get("content", []):
                if block.get("type") == "text":
                    resp_preview["response_snippet"] = block.get("text", "")[:300]
                    break
        logger.info("AI call response (%dms): %s", ai_duration_ms,
                     json.dumps(resp_preview, ensure_ascii=False, default=str))

        return result

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

    def review_project(self, repo_dir: str, scan_data: Dict) -> Dict[str, Any]:
        """
        全面审核项目 — 一次性提供完整扫描上下文，AI 自行决定：
        1. 哪些模块可执行 → 需要 Dockerfile
        2. 基础镜像选什么
        3. 是否需要修改配置文件
        4. 是否需要 docker-compose.yml（含外部依赖）

        Args:
            repo_dir: 项目根目录（用作文件工具的 base_path）
            scan_data: 完整扫描结果，包含：
                - project_structure: 目录结构树
                - config_files: 所有关键配置文件内容
                - detected: 检测结果（type, language, framework, services, dependencies）
        """
        system_prompt = f"""你是一个 DevOps 和容器化专家，正在为一个项目做部署前的准备。

## 你的任务
1. 审核当前的项目结构，判断哪些模块是**可执行服务**（有 main 方法的 Spring Boot / Quarkus / 普通 Java 应用）
2. 只给可执行模块生成/优化 Dockerfile，依赖库模块跳过
3. 必要时修改项目的配置文件（application.yml 等）以适应 Docker 部署
4. 如果项目有外部依赖（MySQL、Redis 等），生成 docker-compose.yml

## 你可以使用的工具
- `read_file(<file_path>)` — 读取文件内容
- `write_file(<file_path>, <content>)` — 写入/修改文件
- `list_files(<directory>)` — 列出目录内容

所有文件路径是相对于项目根目录「{repo_dir}」的绝对路径。

## 判断可执行模块的标准（满足任一即可）
1. pom.xml 中有 spring-boot-maven-plugin 打包配置
2. pom.xml 的 packaging 为 jar/war（非 pom）
3. 有 @SpringBootApplication 注解的 main 类
4. 构建产物（target/*.jar）是 fat JAR（有 BOOT-INF 目录）
5. 有独立的 main 方法

## 项目根目录
{repo_dir}

## 输出要求
完成所有文件修改后，返回 JSON：
{{
  "executable_services": ["service1", "service2"],
  "modified_files": ["path/to/Dockerfile", "path/to/application.yml"],
  "compose_generated": true/false,
  "summary": "做了什么，为什么"
}}
"""

        # 构建完整的用户消息 —— 包含所有扫描数据
        structure = scan_data.get("project_structure", "")
        config_files = scan_data.get("config_files", {})
        detected = scan_data.get("detected", {})
        deps = detected.get("dependencies", {})

        config_content = "\n\n".join([
            f"=== {{path}} ===\n{{content}}"
            for path, content in config_files.items()
        ])

        messages = [
            {
                "role": "user",
                "content": f"""请审核以下项目，完成部署准备。

## 项目目录结构
```
{structure[:3000]}
```

## 检测结果
```json
{json.dumps(detected, indent=2, ensure_ascii=False)[:2000]}
```

## 外部依赖
```json
{json.dumps(deps.get('external_services', []), indent=2, ensure_ascii=False)}
```

## 关键配置文件
```
{config_content[:4000]}
```

## 操作要求
1. 使用 list_files 探索项目结构
2. 使用 read_file 读取 pom.xml 等关键文件，判断哪些模块可执行
3. 为可执行模块生成/优化 Dockerfile（使用 write_file）
4. 如果依赖 MySQL/Redis 等外部服务，生成 docker-compose.yml
5. 修改配置文件中的连接地址（localhost → Docker 服务名）

完成后返回 JSON 格式的结果。"""
            }
        ]

        tools = [
            {
                "name": "read_file",
                "description": "读取文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件绝对路径"}
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
                        "file_path": {"type": "string", "description": "文件绝对路径"},
                        "content": {"type": "string", "description": "文件内容"}
                    },
                    "required": ["file_path", "content"]
                }
            },
            {
                "name": "list_files",
                "description": "列出目录中的文件",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "目录绝对路径"}
                    },
                    "required": ["directory"]
                }
            }
        ]

        # 先尝试带工具的 AI 调用
        result = self._call_ai(messages, tools=tools, system=system_prompt)

        # 如果工具调用模式失败（dashscope 可能不支持工具调用），回退到纯文本模式
        if "error" in result:
            error_str = str(result["error"])
            if "400" not in error_str and "Bad Request" not in error_str:
                # 非工具调用错误（如 API key 无效），直接返回
                return {"skipped": True, "reason": result["error"], "executable_services": []}
            # 工具调用模式不支持，回退到纯文本模式（不传 tools）
            result = self._call_ai(messages, system=system_prompt)
            if "error" in result:
                return {"skipped": True, "reason": result["error"], "executable_services": []}

        # 处理 AI 回复：收集文本 + 执行工具调用
        final_text = ""
        tool_calls_made = []
        ai_content = result.get("content", [])
        for block in ai_content:
            if block.get("type") == "text":
                final_text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_result = self._execute_tool(block["name"], block.get("input", {}))
                tool_calls_made.append({"tool": block["name"], "result": tool_result})

        if tool_calls_made:
            messages.append({"role": "assistant", "content": result.get("content", [])})
            for tc in tool_calls_made:
                messages.append({"role": "user", "content": json.dumps(tc["result"], default=str)[:500]})
            result2 = self._call_ai(messages, tools=tools, system=system_prompt)
            if "error" not in result2:
                for block in result2.get("content", []):
                    if block.get("type") == "text":
                        final_text += block.get("text", "")

        from json_repair import repair_json
        parsed = repair_json(final_text)
        if isinstance(parsed, dict):
            return parsed
        return {"executable_services": [], "modified_files": [], "compose_generated": False, "summary": final_text[:500]}

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
