"""Java 语言检测规则"""
import os
import re
import xml.etree.ElementTree as ET
from typing import Optional

from .base_rule import BaseRule
from .context import ProjectContext


class JavaRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "java"

    @classmethod
    def detect_language(cls, files: list) -> float:
        if "pom.xml" in files or "build.gradle" in files or "build.gradle.kts" in files:
            return 1.0
        if any(f.endswith(".java") for f in files):
            return 0.4
        return 0.0

    @classmethod
    def detect(cls, ctx: ProjectContext) -> Optional[dict]:
        result = {
            "language": "java",
            "framework": "",
            "entry_point": None,
            "package_manager": "maven",
            "build_command": "mvn package -DskipTests",
            "start_command": None,
            "port": 8080,
        }

        has_pom = ctx.exists("pom.xml")
        has_gradle = ctx.exists("build.gradle")

        if not has_pom and not has_gradle:
            return result

        # ---------- 包管理器 ----------
        if has_pom:
            result["package_manager"] = "maven"
            result["build_command"] = "mvn package -DskipTests"
        elif has_gradle:
            result["package_manager"] = "gradle"
            result["build_command"] = "gradle build"

        # ---------- 框架 & 构建信息 ----------
        artifact_id = None
        version = None

        if has_pom:
            pom_content = ctx.read_text("pom.xml")
            if pom_content:
                artifact_id = cls._parse_xml_value(pom_content, "artifactId")
                version = cls._parse_xml_value(pom_content, "version")
                framework = cls._detect_framework_from_pom(pom_content)
                if framework:
                    result["framework"] = framework

                # 多模块项目：根 pom 可能无框架依赖，递归扫描子模块
                if not framework:
                    try:
                        clean = re.sub(r'\sxmlns="[^"]+"', '', pom_content, count=1)
                        root_elem = ET.fromstring(clean)
                        for mod in root_elem.findall(".//module"):
                            mod_name = mod.text.strip() if mod.text else ""
                            mod_content = ctx.read_text(os.path.join(mod_name, "pom.xml"))
                            if mod_content:
                                fw = cls._detect_framework_from_pom(mod_content)
                                if fw:
                                    result["framework"] = fw
                                    break
                    except Exception:
                        pass
        elif has_gradle:
            gradle_content = ctx.read_text("build.gradle")
            if gradle_content:
                framework = cls._detect_framework_from_gradle(gradle_content)
                if framework:
                    result["framework"] = framework

        # ---------- 版本检测 ----------
        if has_pom:
            pom_text = ctx.read_text("pom.xml")
            if pom_text:
                m = re.search(r'<java\.version>([^<]+)</java\.version>', pom_text)
                if m:
                    result["version"] = m.group(1).strip()
                if "version" not in result:
                    m = re.search(r'<maven\.compiler\.source>([^<]+)</maven\.compiler\.source>', pom_text)
                    if m:
                        result["version"] = m.group(1).strip()
                if "version" not in result:
                    m = re.search(r'<maven\.compiler\.target>([^<]+)</maven\.compiler\.target>', pom_text)
                    if m:
                        result["version"] = m.group(1).strip()

        # ---------- 入口点（根目录 + 子模块递归扫描） ----------
        if ctx.is_dir("src/main/java"):
            entry = cls._find_entry_point(ctx, "src/main/java")
            if entry:
                result["entry_point"] = entry

        # 多模块项目：扫描子模块的 src/main/java
        if not result["entry_point"] and has_pom:
            pom_text = ctx.read_text("pom.xml")
            if pom_text:
                try:
                    clean = re.sub(r'\sxmlns="[^"]+"', '', pom_text, count=1)
                    root_elem = ET.fromstring(clean)
                    for mod in root_elem.findall(".//module"):
                        mod_name = mod.text.strip() if mod.text else ""
                        mod_java_dir = os.path.join(mod_name, "src", "main", "java")
                        if ctx.is_dir(mod_java_dir):
                            entry = cls._find_entry_point(ctx, mod_java_dir)
                            if entry:
                                result["entry_point"] = entry
                                break
                except Exception:
                    pass

        # ---------- 启动命令 ----------
        if artifact_id and version:
            result["start_command"] = f"java -jar target/{artifact_id}-{version}.jar"

        # ---------- 端口 ----------
        port = cls._detect_port(ctx)
        if port:
            result["port"] = port

        return result

    @classmethod
    def _parse_xml_value(cls, content: str, tag: str) -> Optional[str]:
        """从 XML 中提取指定标签的内容"""
        try:
            clean_content = re.sub(r'\sxmlns="[^"]+"', '', content, count=1)
            root = ET.fromstring(clean_content)
            elem = root.find(f".//{tag}")
            if elem is not None and elem.text:
                return elem.text.strip()
        except Exception:
            pass
        # fallback: 正则（取第一个匹配）
        pattern = rf"<{tag}>([^<]+)</{tag}>"
        m = re.search(pattern, content)
        if m:
            return m.group(1).strip()
        return None

    @classmethod
    def _detect_framework_from_pom(cls, content: str) -> str:
        """从 pom.xml 内容检测框架"""
        content_lower = content.lower()

        if "mybatis-spring-boot" in content_lower:
            return "mybatis"
        if any(kw in content_lower for kw in [
            "spring-boot-starter", "spring-boot-maven-plugin", "org.springframework.boot"
        ]):
            return "spring-boot"
        if "quarkus" in content_lower:
            return "quarkus"
        if "micronaut" in content_lower:
            return "micronaut"
        if "dropwizard" in content_lower:
            return "dropwizard"
        if "io.vertx" in content_lower:
            return "vertx"
        if "com.typesafe.play" in content_lower:
            return "play"

        return ""

    @classmethod
    def _detect_framework_from_gradle(cls, content: str) -> str:
        """从 build.gradle 内容检测框架"""
        content_lower = content.lower()

        if "mybatis-spring-boot" in content_lower:
            return "mybatis"
        if any(kw in content_lower for kw in [
            "org.springframework.boot", "spring-boot"
        ]):
            return "spring-boot"
        if "quarkus" in content_lower:
            return "quarkus"

        return ""

    @classmethod
    def _find_entry_point(cls, ctx: ProjectContext, java_dir: str) -> Optional[str]:
        """遍历 src/main/java 查找包含 main 方法或 @SpringBootApplication 的类"""
        result_class = None
        result_pkg = None

        go_files = ctx.glob(os.path.join(java_dir, "**/*.java"))
        for filepath in go_files:
            content = ctx.read_text(filepath)
            if not content:
                continue

            has_main = "public static void main" in content
            has_spring_boot = "@SpringBootApplication" in content

            if not has_main and not has_spring_boot:
                continue

            # 获取包名
            pkg = None
            pkg_match = re.search(r"^package\s+([^;]+);", content, re.MULTILINE)
            if pkg_match:
                pkg = pkg_match.group(1).strip()

            # 获取类名
            class_match = re.search(r"public\s+class\s+(\w+)", content)
            if class_match:
                class_name = class_match.group(1).strip()
                result_class = class_name
                result_pkg = pkg
                break

        if result_class:
            if result_pkg:
                return f"{result_pkg}.{result_class}"
            return result_class
        return None

    @classmethod
    def _detect_port(cls, ctx: ProjectContext) -> Optional[int]:
        """从配置文件检测端口（支持子目录、多环境配置）"""
        # 收集所有可能的 resources 目录（多模块项目）
        resources_dirs = []
        if ctx.is_dir("src/main/resources"):
            resources_dirs.append("src/main/resources")

        # 扫描子模块的 resources 目录
        _, dirs = ctx.list_dir(".")
        for d in dirs:
            sub_res = os.path.join(d, "src", "main", "resources")
            if ctx.is_dir(sub_res) and sub_res not in resources_dirs:
                resources_dirs.append(sub_res)

        config_files = [
            "application.properties", "application.yml", "application.yaml",
            "application-dev.properties", "application-dev.yml",
            "bootstrap.properties", "bootstrap.yml",
        ]

        for resources_dir in resources_dirs:
            for cfg_file in config_files:
                cfg_path = os.path.join(resources_dir, cfg_file)
                content = ctx.read_text(cfg_path)
                if not content:
                    continue
                # properties 格式
                m = re.search(r"^server\.port\s*=\s*(\d+)", content, re.MULTILINE)
                if m:
                    return int(m.group(1))
                # yml 格式
                m = re.search(r"port:\s*(\d+)", content)
                if m:
                    return int(m.group(1))

        return None

    @classmethod
    def get_template_name(cls) -> str:
        return "java_template"
