"""README 与代码的一致性测试。

动机：原 README 声称"18 个动力学参数"，而 `/api/params` 实际暴露 19 个；
模型表也漏掉了 `linear_law`。这类"文档与实现漂移"没有测试就必然复发。

测试范围刻意收窄到 **README 应当承载的事实**：特性清单里的模型名、参数个数、
依赖库名、API 路径、以及授权声明是否属实。
不要求 README 充当完整 API 参考（版本号、错误码表、dev 依赖明细等由代码与
包元数据负责），以免为了过测试而把 README 写成工程文档。
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


def test_readme_lists_runtime_dependencies(readme_text: str, pyproject: dict) -> None:
    """README 的依赖清单必须覆盖 pyproject 的运行时依赖。"""
    names = [dep.split(">=")[0].split("[")[0].strip() for dep in pyproject["project"]["dependencies"]]
    missing = [name for name in names if name not in readme_text]
    assert not missing, f"README 未列出运行时依赖：{missing}"


def test_documented_extras_actually_exist(readme_text: str, pyproject: dict) -> None:
    """README 里提到的 extra 必须真实存在（例如写了 [viz] 就得有 viz extra）。"""
    extras = set(pyproject["project"]["optional-dependencies"])
    mentioned = set(re.findall(r"\[([a-z]+)\]", readme_text)) & (extras | {"dev", "viz", "docs", "test"})
    phantom = sorted(name for name in mentioned if name not in extras)
    assert not phantom, f"README 提到了不存在的 extra：{phantom}"


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


def test_readme_license_statement_is_truthful(readme_text: str) -> None:
    """README 的授权说明必须与仓库实际是否附带 LICENSE 一致。"""
    has_license = any((REPO_ROOT / name).is_file() for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"))
    if has_license:
        assert "LICENSE" in readme_text
    else:
        assert "LICENSE" in readme_text and ("未附带" in readme_text or "没有" in readme_text or "确认授权" in readme_text), (
            "仓库无 LICENSE 文件时，README 必须如实说明"
        )


def test_readme_python_api_example_imports_resolve(readme_text: str) -> None:
    """README 示例里 `from family_abm import (...)` 的每个名字都必须真实存在。"""
    import family_abm

    block = re.search(r"from family_abm import \((.*?)\)", readme_text, re.DOTALL)
    assert block, "README 未包含 from family_abm import (...) 示例"
    # 名字可能写成 "Environment, Simulation, Scheduler" 这种逗号分隔形式
    names = [n.strip() for n in re.split(r"[,\n]", block.group(1)) if n.strip()]
    missing = [n for n in names if not hasattr(family_abm, n)]
    assert not missing, f"README 示例导入了不存在的名字：{missing}"


def test_readme_python_api_example_runs() -> None:
    """README 的 Python 示例必须真能跑通（防止文档里的 API 用法失效）。"""
    import random

    import numpy as np

    from family_abm import (
        Environment,
        FamilyMember,
        Household,
        Scheduler,
        Simulation,
        StateRecorder,
        make_fitter,
    )

    random.seed(7)
    np.random.seed(7)

    env = Environment()
    hh = Household(name="张")
    env.add_agent(hh)
    hh.add_member(FamilyMember(name="父亲", age=35, role_name="parent"))
    hh.add_member(FamilyMember(name="儿子", age=8, role_name="child"))

    recorder = StateRecorder(record_agents=True)
    sim = Simulation(env, scheduler=Scheduler("sequential"))
    sim.add_recorder(recorder)
    sim.run(60)

    df = recorder.to_dataframe()
    assert not df.empty

    fitter = make_fitter("wellbeing")
    fitter.fit_robust(df)
    assert "R^2:" in fitter.summary()

