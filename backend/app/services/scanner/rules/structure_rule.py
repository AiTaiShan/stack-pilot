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
        # 检查是否有前端目录（Java Spring Cloud 项目可能包含前端）
        fe_dir = _find_frontend_directory(ctx)
        if fe_dir:
            return "microservices-with-frontend"
        return "microservices"

    # 3. Java 多模块检测（Maven）
    multi = detect_multi_module_java(ctx)
    if multi:
        # 检查是否有前端目录（Java Spring Cloud 项目可能包含前端）
        fe_dir = _find_frontend_directory(ctx)
        if fe_dir:
            return "multi-module-java-with-frontend"
        return "multi-module-java"

    # 3b. Java 多模块检测（Gradle）
    gradle_multi = detect_multi_module_gradle(ctx)
    if gradle_multi:
        # 检查是否有前端目录
        fe_dir = _find_frontend_directory(ctx)
        if fe_dir:
            return "multi-module-java-with-frontend"
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
    """检测前后端分离的 monorepo 项目（动态扫描所有子目录）"""
    # 动态扫描所有子目录，查找前端项目
    fe_dir = _find_frontend_directory(ctx)

    # 动态扫描所有子目录，查找后端项目
    be_dir = _find_backend_directory(ctx)

    if fe_dir and be_dir:
        be_files, _ = ctx.list_dir(be_dir)
        fe_info = _detect_frontend_info(ctx, fe_dir)

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


def _find_frontend_directory(ctx: ProjectContext) -> Optional[str]:
    """动态扫描所有子目录，查找前端项目"""
    skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__",
                 ".idea", ".vscode", ".stackpilot", "sql", "docs", "doc",
                 "test", "tests", "scripts", "deploy", "docker"}

    files, dirs = ctx.list_dir(".")

    for d in dirs:
        # 跳过隐藏目录和常见的非项目目录
        if d.startswith(".") or d.lower() in skip_dirs:
            continue

        # 检查子目录是否是前端项目
        if _is_frontend_directory(ctx, d):
            return d

    return None


def _is_frontend_directory(ctx: ProjectContext, dir_name: str) -> bool:
    """判断一个目录是否是前端项目"""
    if not ctx.is_dir(dir_name):
        return False

    files, _ = ctx.list_dir(dir_name)

    # 必须有 package.json
    if "package.json" not in files:
        return False

    # 检查 package.json 中是否有前端框架依赖
    pkg = ctx.read_json(os.path.join(dir_name, "package.json"))
    if pkg is None:
        return False

    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    # 后端框架列表（如果检测到这些，就不是前端）
    backend_frameworks = {
        "express", "fastify", "koa", "hapi", "nest", "@nestjs/core",
        "fastify", "hono", "elysia", "trpc", "@trpc/server",
        "sequelize", "typeorm", "prisma", "drizzle-orm",
        "mongoose", "mongodb", "pg", "mysql2", "sqlite3",
        "jsonwebtoken", "bcrypt", "passport",
        "socket.io", "ws",
    }

    # 如果有后端框架依赖，不是前端
    has_backend_dep = any(dep in deps for dep in backend_frameworks)
    if has_backend_dep:
        return False

    # 前端框架列表（必须是明确的前端框架）
    frontend_frameworks = {
        "react", "react-dom", "vue", "vue-router", "pinia", "vuex",
        "@angular/core", "svelte", "solid-js", "preact",
        "next", "nuxt", "gatsby", "remix",
        "element-ui", "element-plus", "antd", "ant-design-vue",
        "vant", "naive-ui", "arco-design",
        "@emotion/react", "@emotion/styled", "styled-components",
        "tailwindcss", "postcss", "sass", "less",
    }

    # 检查是否有前端框架依赖
    has_frontend_dep = any(dep in deps for dep in frontend_frameworks)

    # 或者检查是否有前端配置文件（更严格的检查）
    frontend_configs = [
        "vite.config.ts", "vite.config.js", "vite.config.mjs",
        "next.config.js", "next.config.ts", "next.config.mjs",
        "nuxt.config.ts", "nuxt.config.js",
        "vue.config.js", "angular.json",
        "svelte.config.js", "svelte.config.mjs",
    ]
    has_frontend_config = any(ctx.exists(os.path.join(dir_name, cfg)) for cfg in frontend_configs)

    # 或者检查是否有 index.html（必须在根目录或 public 目录）
    has_index_html = "index.html" in files or ctx.exists(os.path.join(dir_name, "public", "index.html"))

    # 检查 src 目录下是否有前端文件（更严格的检查）
    src_dir = os.path.join(dir_name, "src")
    has_src = ctx.is_dir(src_dir)
    has_frontend_files = False
    if has_src:
        src_files, _ = ctx.list_dir(src_dir)
        # 只检查明确的前端文件扩展名
        frontend_extensions = {".jsx", ".tsx", ".vue", ".svelte"}
        has_frontend_files = any(
            any(f.endswith(ext) for ext in frontend_extensions)
            for f in src_files
        )

    # 组合判断：必须有明确的前端特征
    return has_frontend_dep or has_frontend_config or (has_index_html and has_frontend_files)


def _find_backend_directory(ctx: ProjectContext) -> Optional[str]:
    """动态扫描所有子目录，查找后端项目"""
    skip_dirs = {".git", "node_modules", "target", ".mvn", "__pycache__",
                 ".idea", ".vscode", ".stackpilot", "sql", "docs", "doc",
                 "test", "tests", "scripts", "deploy", "docker"}

    files, dirs = ctx.list_dir(".")

    # 后端项目特征文件
    backend_indicators = [
        "pom.xml", "build.gradle",  # Java
        "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",  # Python
        "go.mod",  # Go
        "Cargo.toml",  # Rust
        "composer.json",  # PHP
        "Gemfile",  # Ruby
        "*.csproj",  # .NET
    ]

    for d in dirs:
        # 跳过隐藏目录和常见的非项目目录
        if d.startswith(".") or d.lower() in skip_dirs:
            continue

        # 跳过前端目录（避免误判）
        if _is_frontend_directory(ctx, d):
            continue

        # 检查子目录是否是后端项目
        if _is_backend_directory(ctx, d):
            return d

    return None


def _is_backend_directory(ctx: ProjectContext, dir_name: str) -> bool:
    """判断一个目录是否是后端项目"""
    if not ctx.is_dir(dir_name):
        return False

    files, _ = ctx.list_dir(dir_name)

    # 后端项目特征文件
    backend_indicators = [
        "pom.xml", "build.gradle",  # Java
        "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",  # Python
        "go.mod",  # Go
        "Cargo.toml",  # Rust
        "composer.json",  # PHP
        "Gemfile",  # Ruby
    ]

    # 检查是否有后端特征文件
    if any(f in files for f in backend_indicators):
        return True

    # 检查是否有 src/main 目录结构（Java 项目）
    if ctx.is_dir(os.path.join(dir_name, "src", "main")):
        return True

    # 检查是否有 app.py、main.py 等入口文件
    entry_files = ["app.py", "main.py", "manage.py", "server.py", "index.py"]
    if any(f in files for f in entry_files):
        return True

    return False


def _detect_frontend_info(ctx: ProjectContext, fe_dir: str) -> dict:
    """检测前端项目的详细信息"""
    fe_info = {"language": "node", "port": 3000}

    # 前端框架检测
    for cfg, fw in [("next.config.js", "next"), ("next.config.ts", "next"),
                    ("next.config.mjs", "next"), ("nuxt.config.ts", "nuxt"),
                    ("nuxt.config.js", "nuxt"), ("vue.config.js", "vue"),
                    ("vite.config.ts", "vite"), ("vite.config.js", "vite"),
                    ("angular.json", "angular"), ("svelte.config.js", "svelte")]:
        if ctx.exists(os.path.join(fe_dir, cfg)):
            fe_info["framework"] = fw
            break

    # 端口检测（从 vite.config、package.json scripts 等）
    pkg = ctx.read_json(os.path.join(fe_dir, "package.json"))
    if pkg:
        scripts = pkg.get("scripts", {})
        dev_script = scripts.get("dev", "") or scripts.get("start", "")
        # 从 dev 脚本中提取端口
        import re
        port_match = re.search(r'--port\s+(\d+)', dev_script)
        if port_match:
            fe_info["port"] = int(port_match.group(1))

    return fe_info


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
