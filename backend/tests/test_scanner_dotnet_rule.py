""".NET (C#) 语言检测规则测试"""
import os
from app.services.scanner.rules.dotnet_rule import DotnetRule


def test_language_id():
    assert DotnetRule.language_id() == "dotnet"


def test_get_template_name():
    assert DotnetRule.get_template_name() == "dotnet_template"


def test_detect_language_with_csproj():
    assert DotnetRule.detect_language(["MyApp.csproj"]) == True


def test_detect_language_with_sln():
    assert DotnetRule.detect_language(["MyApp.sln"]) == True


def test_detect_language_without_dotnet_files():
    assert DotnetRule.detect_language(["package.json"]) == False
    assert DotnetRule.detect_language(["requirements.txt"]) == False
    assert DotnetRule.detect_language(["main.py"]) == False


def test_detect_basic_dotnet_app(tmpdir):
    csproj_path = os.path.join(str(tmpdir), "MyApp.csproj")
    with open(csproj_path, "w") as f:
        f.write('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>''')
    result = DotnetRule.detect(str(tmpdir))
    assert result["language"] == "dotnet"
    assert result["framework"] == ""
    assert result["entry_point"] == "Program.cs"
    assert result["package_manager"] == "nuget"
    assert result["build_command"] == "dotnet build"
    assert result["start_command"] == "dotnet run"
    assert result["port"] == 5000


def test_detect_aspnet_framework(tmpdir):
    csproj_path = os.path.join(str(tmpdir), "MyApp.csproj")
    with open(csproj_path, "w") as f:
        f.write('''<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.App" />
  </ItemGroup>
</Project>''')
    result = DotnetRule.detect(str(tmpdir))
    assert result["framework"] == "aspnet"


def test_detect_paket_package_manager(tmpdir):
    csproj_path = os.path.join(str(tmpdir), "MyApp.csproj")
    with open(csproj_path, "w") as f:
        f.write('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>''')
    paket_path = os.path.join(str(tmpdir), "paket.lock")
    with open(paket_path, "w") as f:
        f.write('''NUGET
  remote: https://www.nuget.org
  FSharp.Core (7.0.0)''')
    result = DotnetRule.detect(str(tmpdir))
    assert result["package_manager"] == "paket"


def test_detect_with_sln_only(tmpdir):
    sln_path = os.path.join(str(tmpdir), "MyApp.sln")
    with open(sln_path, "w") as f:
        f.write('''
Microsoft Visual Studio Solution File
Project("...") = "MyApp", "MyApp.csproj"
''')
    result = DotnetRule.detect(str(tmpdir))
    assert result["language"] == "dotnet"
    assert result["framework"] == ""
    assert result["entry_point"] == "Program.cs"
    assert result["package_manager"] == "nuget"
    assert result["build_command"] == "dotnet build"
    assert result["start_command"] == "dotnet run"
    assert result["port"] == 5000


def test_detect_no_dotnet_files_returns_minimal(tmpdir):
    """当目录中没有 .csproj 或 .sln 文件时，返回最小默认值"""
    result = DotnetRule.detect(str(tmpdir))
    assert result["language"] == "dotnet"
    assert result["framework"] == ""
    assert result["entry_point"] is None
    assert result["package_manager"] == "nuget"
    assert result["build_command"] == "dotnet build"
    assert result["start_command"] == "dotnet run"
    assert result["port"] == 5000
