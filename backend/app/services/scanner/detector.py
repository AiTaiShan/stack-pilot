"""detector -- 检测调度器，协调各规则模块

使用 BaseRule 自动注册机制发现所有语言规则，
通过 ProjectContext 统一文件 IO，避免重复读取。
"""
import os
from .models import ScanResult, ServiceInfo, FrontendInfo, BackendInfo
from .rules.context import ProjectContext
from .rules.base_rule import BaseRule

# 导入所有规则模块，触发自动注册
from .rules import node_rule, python_rule, go_rule, java_rule
from .rules import rust_rule, ruby_rule, php_rule, dotnet_rule
from .rules.structure_rule import (
    detect_project_type, detect_microservices,
    detect_monorepo, detect_multi_module_java,
)

TEMPLATE_CACHE = {}


def _load_template(lang: str):
    if lang in TEMPLATE_CACHE:
        return TEMPLATE_CACHE[lang]
    try:
        mod = __import__(f"app.services.scanner.templates.{lang}_template", fromlist=["generate"])
        TEMPLATE_CACHE[lang] = mod
        return mod
    except ImportError:
        return None


def get_template(lang: str):
    mod = _load_template(lang)
    if mod and hasattr(mod, "generate"):
        return mod.generate
    return None


def _collect_project_structure(ctx: ProjectContext, max_depth: int = 3) -> str:
    """收集项目结构概览（用于 AI 生成 Dockerfile 时参考）"""
    lines = []
    skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__",
                 ".stackpilot", "dist", "build", ".idea", ".vscode"}
    for root, dirs, files in os.walk(ctx.dir_path):
        depth = root.replace(ctx.dir_path, "").count(os.sep)
        if depth > max_depth:
            dirs.clear()
            continue
        dirs[:] = sorted([d for d in dirs if d not in skip_dirs])
        indent = "  " * depth
        basename = os.path.basename(root) if root != ctx.dir_path else os.path.basename(ctx.dir_path) + "/"
        lines.append(f"{indent}{basename}")
        for f in files[:10]:
            lines.append(f"{indent}  {f}")
    return "\n".join(lines[:80])


def _collect_manifest(ctx: ProjectContext) -> str:
    """收集主清单文件内容"""
    manifest_names = ["package.json", "Cargo.toml", "pom.xml", "build.gradle",
                      "build.gradle.kts", "composer.json", "Gemfile"]
    files, _ = ctx.list_dir(".")
    for fname in files:
        if fname in manifest_names or fname.endswith(".csproj") or fname.endswith(".sln"):
            content = ctx.read_text(fname)
            if content:
                return content[:4000]  # 限制长度
    return ""


def _collect_existing_dockerfile(ctx: ProjectContext) -> str:
    """收集已有的 Dockerfile"""
    for df in ["Dockerfile", "Dockerfile.dev", "Dockerfile.prod"]:
        content = ctx.read_text(df)
        if content:
            return content[:2000]
    return ""


def detect(repo_dir: str) -> ScanResult:
    """主检测入口：分析项目目录，返回完整扫描结果"""
    ctx = ProjectContext(repo_dir)

    try:
        root_files, root_dirs = ctx.list_dir(".")
    except Exception:
        return ScanResult(project_type="single", languages=[], key_files={}, dependencies={})

    # ── 结构检测（优先级从高到低） ────────────────────────────────

    # 多模块 Java
    mm = detect_multi_module_java(ctx)
    if mm:
        result = ScanResult(
            project_type="multi-module-java", languages=["java"], language="java",
            framework=mm.get("framework"),
            port=mm.get("services", [{}])[0].get("port", 8080) if mm.get("services") else 8080,
            services=[ServiceInfo(**s) for s in mm.get("services", [])],
            key_files={}, dependencies={},
        )
        result.key_files["structure"] = _collect_project_structure(ctx)
        result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(ctx)
        result.warnings = ctx.warnings
        return result

    # 微服务
    ms = detect_microservices(ctx)
    if ms:
        services = []
        langs = set()
        for s in ms.get("services", []):
            services.append(ServiceInfo(**s))
            if s.get("language"):
                langs.add(s["language"])
        result = ScanResult(
            project_type="microservices", languages=list(langs),
            language=list(langs)[0] if langs else "unknown",
            services=services, key_files={}, dependencies={},
        )
        result.key_files["structure"] = _collect_project_structure(ctx)
        result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(ctx)
        result.warnings = ctx.warnings
        return result

    # monorepo
    mr = detect_monorepo(ctx)
    if mr:
        fe, be = mr.get("frontend", {}), mr.get("backend", {})
        result = ScanResult(
            project_type="monorepo",
            languages=[fe.get("language", "node"), be.get("language", "python")],
            frontend=FrontendInfo(
                dir=fe.get("dir", "frontend"), language=fe.get("language", "node"),
                framework=fe.get("framework"), port=fe.get("port", 3000),
                build_cmd=fe.get("build_command", ""), start_cmd=fe.get("start_command", ""),
            ),
            backend=BackendInfo(
                dir=be.get("dir", "backend"), language=be.get("language", "python"),
                framework=be.get("framework"), port=be.get("port", 8000),
                entry_point=be.get("entry_point"), start_cmd=be.get("start_command"),
            ),
            key_files={}, dependencies={},
        )
        result.key_files["structure"] = _collect_project_structure(ctx)
        result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(ctx)
        result.warnings = ctx.warnings
        return result

    # ── 单语言检测 ────────────────────────────────────────────────

    # 根目录检测
    result = _detect_single(ctx, root_files)
    if result:
        result.key_files["structure"] = _collect_project_structure(ctx)
        result.key_files["manifest"] = _collect_manifest(ctx)
        result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(ctx)
        result.warnings = ctx.warnings
        return result

    # 根目录无匹配时，扫描一级子目录
    for sub in root_dirs:
        if sub.startswith("."):
            continue
        sub_files, _ = ctx.list_dir(sub)
        sub_ctx = ProjectContext(os.path.join(ctx.dir_path, sub))
        result = _detect_single(sub_ctx, sub_files, sub_dir=sub)
        if result:
            result.key_files["structure"] = _collect_project_structure(ctx)
            result.key_files["manifest"] = _collect_manifest(sub_ctx)
            result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(ctx)
            result.warnings = ctx.warnings
            return result

    # 无匹配
    result = ScanResult(project_type="single", languages=[], key_files={}, dependencies={})
    result.key_files["structure"] = _collect_project_structure(ctx)
    result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(ctx)
    result.warnings = ctx.warnings
    return result


def _detect_single(ctx: ProjectContext, files: list, sub_dir: str = "") -> ScanResult | None:
    """在给定目录中尝试所有语言规则，返回第一个匹配的结果"""
    for rule_cls in BaseRule.all_rules():
        confidence = rule_cls.detect_language(files) or 0.0
        if confidence < 0.5:
            continue
        info = rule_cls.detect(ctx)
        if info is None:
            continue
        return ScanResult(
            project_type="single",
            languages=[rule_cls.language_id()],
            language=rule_cls.language_id(),
            framework=info.get("framework"),
            entry_point=info.get("entry_point"),
            package_manager=info.get("package_manager"),
            build_command=info.get("build_command"),
            start_command=info.get("start_command"),
            version=info.get("version"),
            port=info.get("port", 8080),
            key_files={}, dependencies={},
        )
    return None
