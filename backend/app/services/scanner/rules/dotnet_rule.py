""".NET (C#) 语言检测规则"""
import os
from .base_rule import BaseRule


class DotnetRule(BaseRule):

    @classmethod
    def language_id(cls) -> str:
        return "dotnet"

    @classmethod
    def detect_language(cls, files: list) -> bool:
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

        # Check for .csproj or .sln files
        has_csproj = False
        has_sln = False
        csproj_path = None

        try:
            for entry in os.listdir(dir_path):
                full_path = os.path.join(dir_path, entry)
                if not os.path.isfile(full_path):
                    continue
                if entry.endswith(".csproj"):
                    has_csproj = True
                    csproj_path = full_path
                elif entry.endswith(".sln"):
                    has_sln = True
        except Exception:
            pass

        if not has_csproj and not has_sln:
            return result

        # 入口点：.NET 项目的标准入口点是 Program.cs
        result["entry_point"] = "Program.cs"

        # 框架检测：读取 .csproj 中的 SDK 和 PackageReference
        if csproj_path:
            result["framework"] = cls._detect_framework(csproj_path)

        # 包管理器检测
        if os.path.exists(os.path.join(dir_path, "paket.lock")):
            result["package_manager"] = "paket"

        return result

    @classmethod
    def _detect_framework(cls, csproj_path: str) -> str:
        """从 .csproj 文件内容检测框架"""
        try:
            with open(csproj_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # 检测 Sdk="Microsoft.NET.Sdk.Web"
            if "Microsoft.NET.Sdk.Web" in content:
                return "aspnet"

            # 检测 PackageReference Include="Microsoft.AspNetCore"
            if "Microsoft.AspNetCore" in content:
                return "aspnet"

        except Exception:
            pass

        return ""
