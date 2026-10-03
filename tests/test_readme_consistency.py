"""README 与代码的一致性测试。

动机：原 README 声称"18 个动力学参数"，而 `/api/params` 实际暴露 19 个；
模型表也漏掉了 `linear_law`。这类"文档与实现漂移"没有测试就必然复发。

这里**只断言可机械核对的事实**（名称/数量/版本/依赖/路由），
不试图校验散文描述——那属于人工复核。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"


@pytest.fixture(scope="module")
def readme_text() -> str:
    assert README.is_file(), "缺少 README.md"
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pyproject() -> dict:
    if tomllib is None:
        pytest.skip("缺少 tomllib/tomli")
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_readme_lists_every_registered_model(readme_text: str) -> None:
    """7 个模型必须全部出现在 README（原版漏了 linear_law）。"""
    from family_abm.fitting import MODEL_REGISTRY

    missing = [name for name in MODEL_REGISTRY if f"`{name}`" not in readme_text]
    assert not missing, f"README 未列出模型：{missing}"


def test_readme_parameter_count_matches_code(readme_text: str) -> None:
    """README 声称的参数个数必须等于 DEFAULT_PARAMS 的真实键数。

    回归：原 README 写"18 个"，实际为 19 个。
    """
    from family_abm.family.family_member import DEFAULT_PARAMS

    match = re.search(r"(\d+)\s*个动力学参数", readme_text)
    assert match, "README 未声明动力学参数个数"
    stated = int(match.group(1))
    assert stated == len(DEFAULT_PARAMS), (
        f"README 声称 {stated} 个参数，实际 DEFAULT_PARAMS 有 {len(DEFAULT_PARAMS)} 个"
    )
    # 分组数字也要自洽
    groups = re.search(r"Education\s*(\d+)\s*／\s*Income\s*(\d+)\s*／\s*Health\s*(\d+)\s*／"
                       r"\s*Stress\s*(\d+)\s*／\s*Happiness\s*(\d+)\s*／\s*Noise\s*(\d+)", readme_text)
    assert groups, "README 未给出参数分组明细"
    assert sum(int(g) for g in groups.groups()) == len(DEFAULT_PARAMS)


def test_readme_version_matches_package(readme_text: str, pyproject: dict) -> None:
    import family_abm

    version = pyproject["project"]["version"]
    assert family_abm.__version__ == version
    assert version in readme_text, f"README 未提及版本号 {version}"


def test_readme_lists_all_runtime_dependencies(readme_text: str, pyproject: dict) -> None:
    """README 的运行时依赖清单必须覆盖 pyproject 的每一项。"""
    names = [dep.split(">=")[0].split("[")[0].strip() for dep in pyproject["project"]["dependencies"]]
    missing = [name for name in names if name not in readme_text]
    assert not missing, f"README 未列出运行时依赖：{missing}"


def test_readme_documents_optional_extras(readme_text: str, pyproject: dict) -> None:
    extras = pyproject["project"]["optional-dependencies"]
    for extra, deps in extras.items():
        assert extra in readme_text, f"README 未提及 [{extra}] extra"
        for dep in deps:
            name = dep.split(">=")[0].strip()
            assert name in readme_text, f"README 未提及 [{extra}] 中的 {name}"


def test_readme_documents_every_api_route(readme_text: str) -> None:
    """README 的 API 表必须与实际路由一致（两个方向都查）。"""
    import importlib

    module = importlib.import_module("family_abm.web.app")
    actual = {route.path for route in module.app.routes if str(route.path).startswith("/api/")}
    assert actual, "未发现 /api 路由"

    undocumented = sorted(p for p in actual if p not in readme_text)
    assert not undocumented, f"README 未记录以下路由：{undocumented}"

    documented = set(re.findall(r"`(/api/[a-z_]+)`", readme_text))
    phantom = sorted(p for p in documented if p not in actual)
    assert not phantom, f"README 记录了不存在的路由：{phantom}"


def test_readme_fit_status_codes_match_implementation(readme_text: str) -> None:
    """README 的 /api/fit 状态码表必须与代码实际返回的 status 值一致。"""
    source = (REPO_ROOT / "family_abm" / "web" / "app.py").read_text(encoding="utf-8")
    actual = set(re.findall(r"'status':\s*'([a-z_]+)'", source))
    actual |= set(re.findall(r"'status':\s*'(ok|model_not_applicable)'", source))
    assert actual, "未在 app.py 中找到 status 返回值"

    documented = set(re.findall(r"\|\s*`([a-z_]+)`\s*\|\s*[0-9]{3}\s*\|", readme_text))
    missing = sorted(actual - documented)
    assert not missing, f"README 状态码表缺少：{missing}"


def test_readme_does_not_claim_a_license_file_that_absent(readme_text: str) -> None:
    """仓库无 LICENSE 时，README 必须如实说明。"""
    has_license = any((REPO_ROOT / name).is_file() for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"))
    if not has_license:
        assert "LICENSE" in readme_text and ("未附带" in readme_text or "没有" in readme_text)


def test_readme_python_api_example_imports_resolve(readme_text: str) -> None:
    """README 示例里 `from family_abm import (...)` 的每个名字都必须真实存在。"""
    import family_abm

    block = re.search(r"from family_abm import \((.*?)\)", readme_text, re.DOTALL)
    assert block, "README 未包含 from family_abm import (...) 示例"
    # 名字可能写成 "Environment, Simulation, Scheduler" 这种逗号分隔形式
    names = [n.strip() for n in re.split(r"[,\n]", block.group(1)) if n.strip()]
    missing = [n for n in names if not hasattr(family_abm, n)]
    assert not missing, f"README 示例导入了不存在的名字：{missing}"
