""".NET (C#) 语言检测规则"""
import os
import re
from typing import Optional

from .base_rule import BaseRule
from .context import ProjectContext


class DotnetRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "dotnet"

    @classmethod
    def detect_language(cls, files: list) -> float:
        """根目录文件列表快速检测"""
        for f in files:
            if f.endswith(".csproj") or f.endswith(".sln"):
                return 1.0
        return 0.0

    @classmethod
    def detect(cls, ctx: ProjectContext) -> Optional[dict]:
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

        all_files, _ = ctx.walk()
        for f in all_files:
            if f.endswith(".sln") and not sln_path:
                sln_path = f
            elif f.endswith(".csproj"):
                csproj_files.append(f)

        if not csproj_files and not sln_path:
            return result

        # 2. 选择主 .csproj（优先 Web 项目，其次第一个）
        main_csproj = None
        for csproj in csproj_files:
            content = ctx.read_text(csproj)
            if content and "Microsoft.NET.Sdk.Web" in content:
                main_csproj = csproj
                break
        if not main_csproj and csproj_files:
            main_csproj = csproj_files[0]

        # 3. 框架检测
        if main_csproj:
            result["framework"] = cls._detect_framework(ctx, main_csproj)

        # 4. 版本检测
        for csproj in csproj_files:
            content = ctx.read_text(csproj)
            if content:
                m = re.search(r'<TargetFramework>(?:net|netstandard|netcoreapp)([\d.]+)', content)
                if m:
                    result["version"] = m.group(1)
                    break

        # 5. 入口点检测（查找 Program.cs，优先 Web 项目目录）
        for csproj in csproj_files:
            proj_dir = os.path.dirname(csproj)
            program_cs = os.path.join(proj_dir, "Program.cs") if proj_dir else "Program.cs"
            if ctx.is_file(program_cs):
                result["entry_point"] = program_cs
                # 如果是 Web 项目，优先使用
                content = ctx.read_text(csproj)
                if content and "Microsoft.NET.Sdk.Web" in content:
                    break

        # fallback: 默认入口点
        if not result["entry_point"]:
            result["entry_point"] = "Program.cs"

        # 6. 启动命令（多项目时指定 --project，单项目用默认 dotnet run）
        if main_csproj and len(csproj_files) > 1:
            result["start_command"] = f"dotnet run --project {main_csproj}"

        # 7. 包管理器
        if ctx.exists("paket.lock"):
            result["package_manager"] = "paket"

        return result

    @classmethod
    def _detect_framework(cls, ctx: ProjectContext, csproj_path: str) -> str:
        """从 .csproj 文件内容检测框架"""
        content = ctx.read_text(csproj_path)
        if not content:
            return ""

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

        return ""
