"""Java 语言检测规则"""
import os
import re
from .base_rule import BaseRule


class JavaRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "java"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        return "pom.xml" in files or "build.gradle" in files

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "java",
            "framework": "",
            "entry_point": None,
            "package_manager": "maven",
            "build_command": "mvn package -DskipTests",
            "start_command": None,
            "port": 8080,
        }

        has_pom = os.path.exists(os.path.join(dir_path, "pom.xml"))
        has_gradle = os.path.exists(os.path.join(dir_path, "build.gradle"))

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
            try:
                pom_content = cls._read_file(os.path.join(dir_path, "pom.xml"))
                artifact_id = cls._parse_xml_value(pom_content, "artifactId")
                version = cls._parse_xml_value(pom_content, "version")
                framework = cls._detect_framework_from_pom(pom_content)
                if framework:
                    result["framework"] = framework
            except Exception:
                pass
        elif has_gradle:
            try:
                gradle_content = cls._read_file(os.path.join(dir_path, "build.gradle"))
                framework = cls._detect_framework_from_gradle(gradle_content)
                if framework:
                    result["framework"] = framework
            except Exception:
                pass

        # ---------- 入口点 ----------
        java_dir = os.path.join(dir_path, "src", "main", "java")
        if os.path.isdir(java_dir):
            entry = cls._find_entry_point(java_dir, dir_path)
            if entry:
                result["entry_point"] = entry

        # ---------- 启动命令 ----------
        if artifact_id and version:
            result["start_command"] = f"java -jar target/{artifact_id}-{version}.jar"

        # ---------- 端口 ----------
        port = cls._detect_port(dir_path)
        if port:
            result["port"] = port

        return result

    @classmethod
    def _read_file(cls, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    @classmethod
    def _parse_xml_value(cls, content: str, tag: str) -> str:
        """从 XML 中提取指定标签的内容"""
        # 跳过 project 和 dependencies 层级
        # 查找第一个顶级标签的值
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
        if "spring-boot-starter" in content_lower or "spring-boot-maven-plugin" in content_lower:
            return "spring-boot"
        if "quarkus" in content_lower:
            return "quarkus"

        return ""

    @classmethod
    def _detect_framework_from_gradle(cls, content: str) -> str:
        """从 build.gradle 内容检测框架"""
        content_lower = content.lower()

        if "mybatis-spring-boot" in content_lower:
            return "mybatis"
        if "org.springframework.boot" in content_lower:
            return "spring-boot"
        if "quarkus" in content_lower:
            return "quarkus"

        return ""

    @classmethod
    def _find_entry_point(cls, java_dir: str, project_dir: str) -> str:
        """遍历 src/main/java 查找包含 main 方法或 @SpringBootApplication 的类"""
        result_class = None
        result_pkg = None

        for root, dirs, files in os.walk(java_dir):
            for f in files:
                if not f.endswith(".java"):
                    continue
                filepath = os.path.join(root, f)
                try:
                    content = cls._read_file(filepath)
                except Exception:
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
                break

        if result_class:
            if result_pkg:
                return f"{result_pkg}.{result_class}"
            return result_class
        return None

    @classmethod
    def _detect_port(cls, dir_path: str) -> int:
        """从 application.properties 或 application.yml 检测端口"""
        resources_dir = os.path.join(dir_path, "src", "main", "resources")
        if not os.path.isdir(resources_dir):
            return None

        # 尝试 application.properties
        prop_path = os.path.join(resources_dir, "application.properties")
        if os.path.isfile(prop_path):
            try:
                content = cls._read_file(prop_path)
                m = re.search(r"^server\.port\s*=\s*(\d+)", content, re.MULTILINE)
                if m:
                    return int(m.group(1))
            except Exception:
                pass

        # 尝试 application.yml
        yml_path = os.path.join(resources_dir, "application.yml")
        if os.path.isfile(yml_path):
            try:
                content = cls._read_file(yml_path)
                m = re.search(r"port:\s*(\d+)", content)
                if m:
                    return int(m.group(1))
            except Exception:
                pass

        return None

    @classmethod
    def get_template_name(cls) -> str:
        return "java_template"
