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
            # 从模块配置读取端口/框架
            mod_port = _read_module_port(ctx, name) or 8080
            mod_framework = _read_module_framework(ctx, name) or "spring"
            mod_version = _read_module_version(ctx, name) or None
            services.append({
                "name": name, "dir": name, "type": mtype,
                "port": mod_port, "language": "java", "framework": mod_framework,
            })
        if services:
            return {"type": "multi-module-java", "language": "java",
                    "framework": "spring-cloud", "services": services,
                    "version": mod_version}
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


def detect_microservices(ctx: ProjectContext, base_dir: str = ".") -> Optional[dict]:
    """递归扫描微服务项目：遍历所有子目录，检测有 pom.xml 或 package.json 的服务"""
    import os
    
    skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__",
                 "dist", "build", ".idea", ".vscode", ".settings",
                 "docs", "test", "tests", "sql", "bin", "script",
                 "docker", "deploy", "resource", "resources",
                 "classes", "generated-sources", "generated-test-sources"}
    
    def _scan(dir_path: str) -> list:
        """递归扫描指定目录，返回找到的服务列表"""
        import os
        skip = skip_dirs | {".", ".."}
        try:
            entries = os.listdir(os.path.join(ctx.dir_path, dir_path)) if dir_path != "." else os.listdir(ctx.dir_path)
        except (PermissionError, FileNotFoundError):
            return []
        
        results = []
        for entry in entries:
            if entry.startswith(".") or entry in skip:
                continue
            
            # 处理扫描入口的子目录
            full_rel = os.path.join(dir_path, entry) if dir_path != "." else entry
            full_abs = os.path.join(ctx.dir_path, full_rel)
            if not os.path.isdir(full_abs):
                continue
            
            # 检查该目录下的文件
            try:
                dir_entries = os.listdir(full_abs)
            except (PermissionError, FileNotFoundError):
                continue
            
            has_pom = "pom.xml" in dir_entries
            has_pkg = "package.json" in dir_entries
            has_src = "src" in dir_entries and os.path.isdir(os.path.join(full_abs, "src"))
            
            if (has_pom or has_pkg) and not has_pom and has_pkg:
                # 纯前端模块（有 package.json 无 pom.xml）
                svc = _detect_service(ctx, full_rel, entry)
                if svc:
                    svc["dir"] = full_rel
                    results.append(svc)
            elif has_pom:
                if has_src:
                    # 有 src/ 的可部署服务
                    svc = _detect_service(ctx, full_rel, entry)
                    if svc:
                        svc["dir"] = full_rel
                        results.append(svc)
                else:
                    # 聚合模块（有 pom.xml 无 src/），递归扫描子目录
                    results.extend(_scan(full_rel))
            # 无 pom.xml 也无 package.json → 跳过
        
        return results
    
    services = _scan(base_dir)
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
        # 读取微服务的 bootstrap.yml 或 application.yml 端口
        svc_port = _read_service_port(ctx, dir_path)
        if svc_port:
            svc["port"] = svc_port
        # 通用类型检测（common/service/gateway）
        svc["type"] = _read_module_kind(name)
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


def _read_module_port(ctx: ProjectContext, module_name: str) -> int:
    """从模块的 application.yml 或 application.properties 中读取端口"""
    import re
    res_dir = os.path.join(ctx.dir_path, module_name, "src", "main", "resources")
    # application.yml
    yml_path = os.path.join(res_dir, "application.yml")
    if os.path.exists(yml_path):
        with open(yml_path, errors="ignore") as f:
            content = f.read()
        # YAML: server:
        # YAML format: server:\n  port: N
        m = re.search(r'server:\s*\n(?:\s*#.*\n)*\s*port:\s*(\d+)', content)
        if m:
            return int(m.group(1))
        # server.port=xxx (properties 格式混在 yml 中)
        m = re.search(r'server\.port\s*[:=]\s*(\d+)', content)
        if m:
            return int(m.group(1))
    # application.properties
    props_path = os.path.join(res_dir, "application.properties")
    if os.path.exists(props_path):
        with open(props_path, errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("server.port=") or line.startswith("server.port:"):
                    try:
                        return int(line.split("=")[1].strip())
                    except:
                        pass
    # 如果 application.yml 没找到端口，查 bootstrap.yml（Spring Cloud 微服务）
    for bp_name in ("bootstrap.yml", "bootstrap.yaml"):
        bp_path = os.path.join(res_dir, bp_name)
        if os.path.exists(bp_path):
            with open(bp_path, errors="ignore") as f:
                content = f.read()
            m = re.search(r'server:\s*\n(?:\s*#.*\n)*\s*port:\s*(\d+)', content)
            if m:
                return int(m.group(1))
            # bootstrap.yml 可能用 server: port: XX 格式
            m = re.search(r'server:\s*port:\s*(\d+)', content)
            if m:
                return int(m.group(1))
    return 8080


def _read_module_version(ctx: ProjectContext, module_name: str) -> Optional[str]:
    """从模块的 pom.xml 中读取 Java 版本"""
    import re
    pom_path = os.path.join(ctx.dir_path, module_name, "pom.xml")
    if not os.path.exists(pom_path):
        return None
    with open(pom_path, errors="ignore") as f:
        content = f.read()
    # 先找子模块自己的 java.version
    m = re.search(r'<java\.version>([^<]+)</java\.version>', content)
    if m:
        return m.group(1).strip()
    # 再找 maven.compiler.source
    m = re.search(r'<maven\.compiler\.source>([^<]+)</maven\.compiler\.source>', content)
    if m:
        return m.group(1).strip()
    return None


def _read_module_framework(ctx: ProjectContext, module_name: str) -> str:
    """从模块的 pom.xml 中检测框架"""
    import re
    pom_path = os.path.join(ctx.dir_path, module_name, "pom.xml")
    if not os.path.exists(pom_path):
        return "spring"
    with open(pom_path, errors="ignore") as f:
        content = f.read().lower()
    if "spring-cloud" in content or "spring.cloud" in content:
        return "spring-cloud"
    if "spring-boot-starter" in content or "spring-boot-maven-plugin" in content:
        return "spring-boot"
    if "mybatis-spring-boot" in content:
        return "mybatis"
    if "quarkus" in content:
        return "quarkus"
    return "spring-boot"


def _read_module_kind(module_name: str) -> str:
    """根据模块名判断类型：common/service/gateway/registry/config"""
    nl = module_name.lower()
    if "common" in nl or "util" in nl:
        return "common"
    if "gateway" in nl or "zuul" in nl:
        return "gateway"
    if "eureka" in nl or "registry" in nl:
        return "registry"
    if "config" in nl:
        return "config"
    return "service"


def _read_service_port(ctx: ProjectContext, dir_path: str) -> Optional[int]:
    """读取微服务端口：读 bootstrap.yml 获取 profile，再按优先级扫描各配置文件"""
    import re, os

    active_profile = None
    port = None
    full_path = os.path.join(ctx.dir_path, dir_path)

    # 1. 读 bootstrap.yml 获取 active profile 和 server.port
    for bp_name in ("bootstrap.yml", "bootstrap.yaml"):
        bp_path = os.path.join(full_path, bp_name)
        if not os.path.exists(bp_path):
            continue
        with open(bp_path, errors="ignore") as f:
            content = f.read()
        m = re.search(r'profiles:\s*\n\s+active:\s*(\S+)', content)
        if m:
            active_profile = m.group(1).strip().strip('"').strip("'")
        m = re.search(r'server:\s*\n(?:\s*#.*\n)*\s*port:\s*(\d+)', content)
        if m:
            port = int(m.group(1))

    # 2. 按优先级扫描配置文件
    config_files = ["application.yml", "application.yaml"]
    if active_profile:
        config_files = [
            f"application-{active_profile}.yml",
            f"application-{active_profile}.yaml",
        ] + config_files + [
            f"bootstrap-{active_profile}.yml",
            f"bootstrap-{active_profile}.yaml",
        ]

    for cf in config_files:
        cf_path = os.path.join(full_path, cf)
        if not os.path.exists(cf_path):
            continue
        with open(cf_path, errors="ignore") as f:
            content = f.read()
        m = re.search(r'server:\s*\n(?:\s*#.*\n)*\s*port:\s*(\d+)', content)
        if m:
            return int(m.group(1))

    return port
