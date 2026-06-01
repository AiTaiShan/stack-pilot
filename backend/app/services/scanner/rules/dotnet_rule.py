""".NET (C#) 语言检测规则"""
import os
import re
from .base_rule import BaseRule


class DotnetRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "dotnet"

    @classmethod
    def detect_language(cls, files: list) -> bool:
        """根目录文件列表快速检测"""
        for f in files:
            if f.endswith(".csproj") or f.endswith(".sln"):
                return True
        return False

    @classmethod
    def detect(cls, dir_path: str) -> dict:
        result = {
            "language": "dotnet",
            "framework": "",
            "entry_point": None,
            "package_manager": "nuget",
            "build_command": "dotnet build",
            "start_command": "dotnet run",
            "port": 5000,
        }

        # 1. 搜索 .sln 和 .csproj（支持子目录，深度 3）
        sln_path = None
        csproj_files = []

        for root, dirs, files in os.walk(dir_path):
            depth = root.replace(dir_path, "").count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "bin", "obj", "packages"}]
            for f in files:
                full = os.path.join(root, f)
                if f.endswith(".sln") and not sln_path:
                    sln_path = full
                elif f.endswith(".csproj"):
                    csproj_files.append(full)

        if not csproj_files and not sln_path:
            return result

        # 2. 选择主 .csproj（优先 Web 项目，其次第一个）
        main_csproj = None
        for csproj in csproj_files:
            try:
                with open(csproj, errors="ignore") as f:
                    content = f.read()
                if "Microsoft.NET.Sdk.Web" in content:
                    main_csproj = csproj
                    break
            except Exception:
                pass
        if not main_csproj and csproj_files:
            main_csproj = csproj_files[0]

        # 3. 框架检测
        if main_csproj:
            result["framework"] = cls._detect_framework(main_csproj)

        # 4. 版本检测
        for csproj in csproj_files:
            try:
                with open(csproj, errors="ignore") as f:
                    content = f.read()
                m = re.search(r'<TargetFramework>(?:net|netstandard|netcoreapp)([\d.]+)', content)
                if m:
                    result["version"] = m.group(1)
                    break
            except Exception:
                pass

        # 5. 入口点检测（查找 Program.cs，优先 Web 项目目录）
        for csproj in csproj_files:
            proj_dir = os.path.dirname(csproj)
            program_cs = os.path.join(proj_dir, "Program.cs")
            if os.path.isfile(program_cs):
                rel = os.path.relpath(program_cs, dir_path)
                result["entry_point"] = rel
                # 如果是 Web 项目，优先使用
                try:
                    with open(csproj, errors="ignore") as f:
                        if "Microsoft.NET.Sdk.Web" in f.read():
                            break
                except Exception:
                    pass

        # fallback: 默认入口点
        if not result["entry_point"]:
            result["entry_point"] = "Program.cs"

        # 6. 启动命令（多项目时指定 --project，单项目用默认 dotnet run）
        if main_csproj and len(csproj_files) > 1:
            rel_csproj = os.path.relpath(main_csproj, dir_path)
            result["start_command"] = f"dotnet run --project {rel_csproj}"

        # 7. 包管理器
        if os.path.exists(os.path.join(dir_path, "paket.lock")):
            result["package_manager"] = "paket"

        return result

    @classmethod
    def _detect_framework(cls, csproj_path: str) -> str:
        """从 .csproj 文件内容检测框架"""
        try:
            with open(csproj_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            framework_map = {
                "Microsoft.NET.Sdk.Web": "aspnet",
                "Microsoft.NET.Sdk.BlazorWebAssembly": "blazor",
                "Microsoft.NET.Sdk.WindowsDesktop": "wpf",
                "Microsoft.Maui.Controls": "maui",
            }
            for sdk, fw in framework_map.items():
                if sdk in content:
                    return fw

            if "Microsoft.AspNetCore" in content:
                return "aspnet"
            if "UseWPF" in content:
                return "wpf"
            if "UseWindowsForms" in content:
                return "winforms"

        except Exception:
            pass

        return ""
