"""项目结构类型识别规则"""
import os
import xml.etree.ElementTree as ET


def detect_project_type(files: list, dirs: list) -> str:
    return "single"


def detect_multi_module_java(repo_dir: str) -> dict | None:
    pom_path = os.path.join(repo_dir, "pom.xml")
    if not os.path.exists(pom_path):
        return None
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        # 兼容有/无 namespace
        modules = root.findall(".//module")
        if not modules:
            modules = root.findall(".//{http://maven.apache.org/POM/4.0.0}module")
        if not modules:
            return None
        services = []
        for mod in modules:
            name = mod.text.strip() if mod.text else ""
            mod_dir = os.path.join(repo_dir, name)
            if not os.path.isdir(mod_dir):
                continue
            has_src = os.path.isdir(os.path.join(mod_dir, "src"))
            has_pom = os.path.exists(os.path.join(mod_dir, "pom.xml"))
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


def detect_microservices(repo_dir: str) -> dict | None:
    service_base_dirs = ["services", "microservices", "apps", "packages", "modules"]
    services = []
    for base in service_base_dirs:
        base_path = os.path.join(repo_dir, base)
        if not os.path.isdir(base_path):
            continue
        for item in sorted(os.listdir(base_path)):
            item_path = os.path.join(base_path, item)
            if not os.path.isdir(item_path):
                continue
            svc = _detect_service(item_path, item)
            if svc:
                svc["dir"] = f"{base}/{item}"
                services.append(svc)
        if services:
            break
    if not services:
        for item in sorted(os.listdir(repo_dir)):
            if item.startswith(".") or item in ["docs", "test", "tests"]:
                continue
            if not item.endswith("-service") and not item.endswith("_service") and not item.endswith("-api"):
                continue
            item_path = os.path.join(repo_dir, item)
            if not os.path.isdir(item_path):
                continue
            svc = _detect_service(item_path, item)
            if svc:
                svc["dir"] = item
                services.append(svc)
    if len(services) >= 2:
        return {"type": "microservices", "services": services}
    return None


def _detect_service(dir_path: str, name: str) -> dict | None:
    files = os.listdir(dir_path)
    svc = {"name": name, "port": 8080, "language": "unknown", "framework": "", "type": "service"}
    if "package.json" in files:
        svc["language"] = "node"; svc["port"] = 3000
    elif "requirements.txt" in files or "setup.py" in files:
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


def detect_monorepo(repo_dir: str) -> dict | None:
    frontend_dirs = ["frontend", "client", "web", "ui", "app"]
    backend_dirs = ["backend", "server", "api", "services"]
    fe_dir = None; be_dir = None
    for d in frontend_dirs:
        path = os.path.join(repo_dir, d)
        if os.path.isdir(path):
            fe_files = os.listdir(path)
            if "package.json" in fe_files or "index.html" in fe_files:
                fe_dir = d; break
    for d in backend_dirs:
        path = os.path.join(repo_dir, d)
        if os.path.isdir(path):
            be_files = os.listdir(path)
            backend_indicators = ["requirements.txt", "pom.xml", "go.mod",
                                  "main.py", "app.py", "package.json", "build.gradle"]
            if any(f in be_files for f in backend_indicators):
                be_dir = d; break
    if fe_dir and be_dir:
        fe_path = os.path.join(repo_dir, fe_dir)
        be_path = os.path.join(repo_dir, be_dir)
        be_files = os.listdir(be_path)
        fe_info = {"language": "node", "port": 3000}
        if os.path.exists(os.path.join(fe_path, "next.config.js")):
            fe_info["framework"] = "next"
        be_info = {}
        if "requirements.txt" in be_files or "setup.py" in be_files:
            be_info = {"language": "python", "port": 8000}
        elif "pom.xml" in be_files or "build.gradle" in be_files:
            be_info = {"language": "java", "port": 8080}
        elif "go.mod" in be_files:
            be_info = {"language": "go", "port": 8080}
        else:
            be_info = {"language": "python", "port": 8000}
        return {"type": "monorepo", "frontend": {"dir": fe_dir, **fe_info},
                "backend": {"dir": be_dir, **be_info}}
    return None
