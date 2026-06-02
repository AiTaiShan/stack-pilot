"""项目结构类型识别规则"""
import os
import re
import xml.etree.ElementTree as ET
from typing import Optional

from .context import ProjectContext


def detect_project_type(ctx: ProjectContext) -> str:
    """检测项目结构类型（优先级从高到低）：
    1. 现代 monorepo 工具（turbo/nx/pnpm-workspace）— 避免 apps/ 被误判为微服务
    2. 微服务
    3. Java 多模块
    4. 传统 monorepo（前后端分离）
    5. 单体
    """
    # 1. 现代 monorepo 工具检测（最高优先级）
    mono_modern = detect_monorepo_modern(ctx)
    if mono_modern:
        return "monorepo"

    # 2. 微服务检测
    micro = detect_microservices(ctx)
    if micro and len(micro.get("services", [])) >= 2:
        return "microservices"

    # 3. Java 多模块检测（Maven）
    multi = detect_multi_module_java(ctx)
    if multi:
        return "multi-module-java"

    # 3b. Java 多模块检测（Gradle）
    gradle_multi = detect_multi_module_gradle(ctx)
    if gradle_multi:
        return "multi-module-java"

    # 4. 传统 monorepo 检测（前后端分离）
    mono = detect_monorepo(ctx)
    if mono:
        return "monorepo"

    return "single"


def detect_multi_module_java(ctx: ProjectContext) -> Optional[dict]:
    root = ctx.read_xml("pom.xml")
    if root is None:
        return None
    try:
        modules = root.findall(".//module")
        if not modules:
            modules = root.findall(".//{http://maven.apache.org/POM/4.0.0}module")
        if not modules:
            return None
        services = []
        for mod in modules:
            name = mod.text.strip() if mod.text else ""
            if not ctx.is_dir(name):
                continue
            has_src = ctx.is_dir(os.path.join(name, "src"))
            has_pom = ctx.exists(os.path.join(name, "pom.xml"))
            if not (has_src and has_pom):
                continue
            mtype = "service"
            nl = name.lower()
            if "common" in nl or "util" in nl:
                mtype = "common"
            elif "gateway" in nl or "zuul" in nl:
                mtype = "gateway"
            elif "eureka" in nl or "registry" in nl:
                mtype = "registry"
            elif "config" in nl:
                mtype = "config"
            services.append({
                "name": name, "dir": name, "type": mtype,
                "port": 8080, "language": "java", "framework": "spring",
            })
        if services:
            return {"type": "multi-module-java", "language": "java",
                    "framework": "spring-cloud", "services": services}
    except Exception:
        pass
    return None


def detect_multi_module_gradle(ctx: ProjectContext) -> Optional[dict]:
    """检测 Gradle 多模块项目"""
    for settings_file in ["settings.gradle", "settings.gradle.kts"]:
        content = ctx.read_text(settings_file)
        if content is None:
            continue
        try:
            includes = re.findall(r'''include\s*[\(]?\s*['"]([^'"]+)['"]''', content)
            if len(includes) >= 2:
                services = []
                for inc in includes:
                    mod_name = inc.strip(":").replace(":", "/")
                    if ctx.is_dir(mod_name):
                        services.append({
                            "name": mod_name.split("/")[-1], "dir": mod_name,
                            "type": "service", "port": 8080,
                            "language": "java", "framework": "",
                        })
                if services:
                    return {"type": "multi-module-java", "language": "java",
                            "framework": "", "services": services}
        except Exception:
            pass
    return None


def detect_microservices(ctx: ProjectContext) -> Optional[dict]:
    # 注意：不含 apps/（Turborepo/Nx 等 monorepo 常用 apps/）
    # 含 app/（go-zero/Dubbo-go 微服务常用）
    service_base_dirs = ["services", "microservices", "packages", "modules",
                         "app", "api", "server", "backend", "workers", "components"]
    services = []
    for base in service_base_dirs:
        if not ctx.is_dir(base):
            continue
        files, sub_dirs = ctx.list_dir(base)
        for item in sub_dirs:
            svc = _detect_service(ctx, os.path.join(base, item), item)
            if svc:
                svc["dir"] = f"{base}/{item}"
                services.append(svc)
        if services:
            break

    # 二级目录扫描（如 ruoyi-modules/ruoyi-system、pkg/api-gateway）
    if not services:
        _, root_dirs = ctx.list_dir(".")
        for parent in root_dirs:
            parent_lower = parent.lower()
            if not any(kw in parent_lower for kw in ["module", "service", "component", "pkg"]):
                continue
            _, sub_dirs = ctx.list_dir(parent)
            for item in sub_dirs:
                svc = _detect_service(ctx, os.path.join(parent, item), item)
                if svc:
                    svc["dir"] = f"{parent}/{item}"
                    services.append(svc)
            if len(services) >= 2:
                break

    # 也检测根目录下 xxx-service / xxx_api 模式
    if not services:
        _, root_dirs = ctx.list_dir(".")
        for item in root_dirs:
            if item.startswith(".") or item in ["docs", "test", "tests", "frontend", "web", "ui"]:
                continue
            if not (item.endswith("-service") or item.endswith("_service") or
                    item.endswith("-api") or item.endswith("_api")):
                continue
            svc = _detect_service(ctx, item, item)
            if svc:
                svc["dir"] = item
                services.append(svc)
    if len(services) >= 2:
        return {"type": "microservices", "services": services}
    return None


def _detect_service(ctx: ProjectContext, dir_path: str, name: str) -> Optional[dict]:
    files, _ = ctx.list_dir(dir_path)
    svc = {"name": name, "port": 8080, "language": "unknown", "framework": "", "type": "service"}
    if "package.json" in files:
        svc["language"] = "node"; svc["port"] = 3000
    elif "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files:
        svc["language"] = "python"; svc["port"] = 8000
    elif "go.mod" in files:
        svc["language"] = "go"
    elif "pom.xml" in files or "build.gradle" in files:
        svc["language"] = "java"
    elif "Cargo.toml" in files:
        svc["language"] = "rust"
    elif "composer.json" in files:
        svc["language"] = "php"; svc["port"] = 80
    elif "Gemfile" in files:
        svc["language"] = "ruby"; svc["port"] = 3000
    elif any(f.endswith(".csproj") for f in files):
        svc["language"] = "dotnet"; svc["port"] = 5000
    else:
        return None
    return svc


def detect_monorepo(ctx: ProjectContext) -> Optional[dict]:
    frontend_dirs = ["frontend", "client", "web", "ui", "app", "apps",
                     "packages/web", "packages/client", "src/web"]
    backend_dirs = ["backend", "server", "api", "services", "apps/api",
                    "packages/api", "packages/server", "src/api", "src/server"]
    fe_dir = None
    be_dir = None
    for d in frontend_dirs:
        if ctx.is_dir(d):
            fe_files, _ = ctx.list_dir(d)
            if "package.json" in fe_files or "index.html" in fe_files:
                fe_dir = d
                break
    for d in backend_dirs:
        if ctx.is_dir(d):
            be_files, _ = ctx.list_dir(d)
            backend_indicators = ["requirements.txt", "pom.xml", "go.mod",
                                  "main.py", "app.py", "package.json", "build.gradle",
                                  "pyproject.toml", "Cargo.toml"]
            if any(f in be_files for f in backend_indicators):
                be_dir = d
                break
    if fe_dir and be_dir:
        be_files, _ = ctx.list_dir(be_dir)
        fe_info = {"language": "node", "port": 3000}
        # 前端框架检测
        for cfg, fw in [("next.config.js", "next"), ("next.config.ts", "next"),
                        ("next.config.mjs", "next"), ("nuxt.config.ts", "nuxt"),
                        ("nuxt.config.js", "nuxt"), ("vue.config.js", "vue"),
                        ("vite.config.ts", "vite"), ("vite.config.js", "vite")]:
            if ctx.exists(os.path.join(fe_dir, cfg)):
                fe_info["framework"] = fw
                break
        be_info = {}
        if "requirements.txt" in be_files or "setup.py" in be_files or "pyproject.toml" in be_files:
            be_info = {"language": "python", "port": 8000}
        elif "pom.xml" in be_files or "build.gradle" in be_files:
            be_info = {"language": "java", "port": 8080}
        elif "go.mod" in be_files:
            be_info = {"language": "go", "port": 8080}
        elif "Cargo.toml" in be_files:
            be_info = {"language": "rust", "port": 8080}
        else:
            be_info = {"language": "python", "port": 8000}
        return {"type": "monorepo", "frontend": {"dir": fe_dir, **fe_info},
                "backend": {"dir": be_dir, **be_info}}
    return None


def detect_monorepo_modern(ctx: ProjectContext) -> Optional[dict]:
    """检测现代 monorepo 工具链"""
    modern_tools = {
        "pnpm-workspace.yaml": "pnpm",
        "lerna.json": "lerna",
        "nx.json": "nx",
        "turbo.json": "turborepo",
    }
    for file, tool in modern_tools.items():
        if ctx.exists(file):
            return {"type": "monorepo", "tool": tool}
    return None
