"""detector -- 检测调度器，协调各规则模块"""
import os
from .models import ScanResult, ServiceInfo, FrontendInfo, BackendInfo

from .rules.structure_rule import detect_project_type, detect_microservices, detect_monorepo, detect_multi_module_java
from .rules.node_rule import NodeRule
from .rules.python_rule import PythonRule
from .rules.go_rule import GoRule
from .rules.java_rule import JavaRule
from .rules.rust_rule import RustRule
from .rules.php_rule import PhpRule
from .rules.ruby_rule import RubyRule
from .rules.dotnet_rule import DotnetRule

ALL_RULES = [NodeRule, PythonRule, GoRule, JavaRule, RustRule, PhpRule, RubyRule, DotnetRule]

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


def _collect_project_structure(repo_dir: str, max_depth: int = 3) -> str:
    lines = []
    skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__",
                 ".stackpilot", "dist", "build", ".idea", ".vscode"}
    for root, dirs, files in os.walk(repo_dir):
        depth = root.replace(repo_dir, "").count(os.sep)
        if depth > max_depth:
            dirs.clear(); continue
        dirs[:] = sorted([d for d in dirs if d not in skip_dirs])
        indent = "  " * depth
        basename = os.path.basename(root) if root != repo_dir else os.path.basename(repo_dir) + "/"
        lines.append(f"{indent}{basename}")
        for f in files[:10]:
            lines.append(f"{indent}  {f}")
    return "\n".join(lines[:80])


def _collect_manifest(dir_path: str) -> str:
    manifest_names = ["package.json", "Cargo.toml", "pom.xml", "build.gradle",
                      "build.gradle.kts", "composer.json", "Gemfile"]
    for fname in os.listdir(dir_path):
        if fname in manifest_names or fname.endswith(".csproj") or fname.endswith(".sln"):
            try:
                with open(os.path.join(dir_path, fname), errors="ignore") as f:
                    return "".join(f.readlines(100))
            except Exception:
                pass
    return ""


def _collect_existing_dockerfile(dir_path: str) -> str:
    for df in ["Dockerfile", "Dockerfile.dev", "Dockerfile.prod"]:
        df_path = os.path.join(dir_path, df)
        if os.path.exists(df_path):
            try:
                with open(df_path, errors="ignore") as f:
                    return "".join(f.readlines(50))
            except Exception:
                pass
    return ""


def detect(repo_dir: str) -> ScanResult:
    try:
        root_files = os.listdir(repo_dir)
    except Exception:
        return ScanResult(project_type="single", languages=[], key_files={}, dependencies={})
    root_dirs = [d for d in root_files if os.path.isdir(os.path.join(repo_dir, d))]

    # 多模块 Java
    mm = detect_multi_module_java(repo_dir)
    if mm:
        result = ScanResult(project_type="multi-module-java", languages=["java"], language="java",
                            framework=mm.get("framework"), port=mm.get("services", [{}])[0].get("port", 8080) if mm.get("services") else 8080,
                            services=[ServiceInfo(**s) for s in mm.get("services", [])],
                            key_files={}, dependencies={})
        result.key_files["structure"] = _collect_project_structure(repo_dir)
        result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(repo_dir)
        return result

    # 微服务
    ms = detect_microservices(repo_dir)
    if ms:
        services = []; langs = set()
        for s in ms.get("services", []):
            services.append(ServiceInfo(**s))
            if s.get("language"): langs.add(s["language"])
        result = ScanResult(project_type="microservices", languages=list(langs),
                            language=list(langs)[0] if langs else "unknown",
                            services=services, key_files={}, dependencies={})
        result.key_files["structure"] = _collect_project_structure(repo_dir)
        result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(repo_dir)
        return result

    # monorepo
    mr = detect_monorepo(repo_dir)
    if mr:
        fe, be = mr.get("frontend", {}), mr.get("backend", {})
        result = ScanResult(project_type="monorepo",
                            languages=[fe.get("language", "node"), be.get("language", "python")],
                            frontend=FrontendInfo(dir=fe.get("dir", "frontend"), language=fe.get("language", "node"),
                                                  framework=fe.get("framework"), port=fe.get("port", 3000),
                                                  build_cmd=fe.get("build_command", ""), start_cmd=fe.get("start_command", "")),
                            backend=BackendInfo(dir=be.get("dir", "backend"), language=be.get("language", "python"),
                                                framework=be.get("framework"), port=be.get("port", 8000),
                                                entry_point=be.get("entry_point"), start_cmd=be.get("start_command")),
                            key_files={}, dependencies={})
        result.key_files["structure"] = _collect_project_structure(repo_dir)
        result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(repo_dir)
        return result

    # 单体 + 根目录无匹配
    for rule_cls in ALL_RULES:
        if rule_cls.detect_language(root_files):
            info = rule_cls.detect(repo_dir)
            result = ScanResult(project_type="single", languages=[rule_cls.language_id()],
                                language=rule_cls.language_id(), framework=info.get("framework"),
                                entry_point=info.get("entry_point"),
                                package_manager=info.get("package_manager"),
                                build_command=info.get("build_command"),
                                start_command=info.get("start_command"),
                                version=info.get("version"),
                                port=info.get("port", 8080),
                                key_files={}, dependencies={})
            result.key_files["structure"] = _collect_project_structure(repo_dir)
            result.key_files["manifest"] = _collect_manifest(repo_dir)
            result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(repo_dir)
            return result

    # 根目录无匹配时，扫描一级子目录（如 src/*.csproj、backend/package.json）
    for sub in sorted(root_files):
        sub_path = os.path.join(repo_dir, sub)
        if not os.path.isdir(sub_path) or sub.startswith("."):
            continue
        try:
            sub_files = os.listdir(sub_path)
        except Exception:
            continue
        for rule_cls in ALL_RULES:
            if rule_cls.detect_language(sub_files):
                info = rule_cls.detect(sub_path)
                result = ScanResult(project_type="single", languages=[rule_cls.language_id()],
                                    language=rule_cls.language_id(), framework=info.get("framework"),
                                    entry_point=info.get("entry_point"),
                                    package_manager=info.get("package_manager"),
                                    build_command=info.get("build_command"),
                                    start_command=info.get("start_command"),
                                    version=info.get("version"),
                                    port=info.get("port", 8080),
                                    key_files={}, dependencies={})
                result.key_files["structure"] = _collect_project_structure(repo_dir)
                result.key_files["manifest"] = _collect_manifest(sub_path)
                result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(repo_dir)
                return result

    result = ScanResult(project_type="single", languages=[], key_files={}, dependencies={})
    result.key_files["structure"] = _collect_project_structure(repo_dir)
    result.key_files["existing_dockerfile"] = _collect_existing_dockerfile(repo_dir)
    return result
