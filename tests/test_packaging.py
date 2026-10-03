"""阶段 A 验收测试：打包必须携带 Web 资源，且安装副本真的能启动。

回归对象：`setup.py` 曾只声明 numpy/pandas 且无 package_data，导致
- `import family_abm` 在缺 scipy/matplotlib 的环境直接 ModuleNotFoundError；
- wheel 不含 web/templates、web/static，安装后 `import family_abm.web` 抛 RuntimeError。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# import family_abm 时的硬依赖（源码里实际 import 的第三方库）
REQUIRED_RUNTIME_DEPS = ["numpy", "pandas", "scipy", "matplotlib", "networkx", "fastapi", "uvicorn", "jinja2", "pydantic"]


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, env=env, timeout=300)


# ── 元数据契约 ────────────────────────────────────────────────────────────


def test_pyproject_declares_all_runtime_dependencies() -> None:
    """pyproject 必须声明全部运行时依赖，且版本下限非空。"""
    data = _load_pyproject()
    deps = data["project"]["dependencies"]
    declared = {dep.split(">=")[0].split("[")[0].strip().lower() for dep in deps}
    missing = [name for name in REQUIRED_RUNTIME_DEPS if name not in declared]
    assert not missing, f"pyproject.toml 缺少运行时依赖：{missing}"
    for dep in deps:
        assert ">=" in dep, f"依赖 {dep!r} 未声明版本下限"


def test_requirements_matches_pyproject() -> None:
    """requirements.txt 与 pyproject 的依赖清单不得分歧（单一真源）。"""
    data = _load_pyproject()
    pyproject_deps = {d.split(">=")[0].strip().lower(): d.strip() for d in data["project"]["dependencies"]}
    lines = [
        line.strip()
        for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    req_deps = {d.split(">=")[0].strip().lower(): d for d in lines}
    assert set(pyproject_deps) == set(req_deps), (
        f"依赖清单分歧：仅 pyproject 有 {sorted(set(pyproject_deps) - set(req_deps))}，"
        f"仅 requirements 有 {sorted(set(req_deps) - set(pyproject_deps))}"
    )
    for name, spec in pyproject_deps.items():
        assert req_deps[name] == spec, f"{name} 版本不一致：pyproject={spec!r} requirements={req_deps[name]!r}"


def test_package_discovery_excludes_tests_and_tools() -> None:
    """tests/ 与 tools/ 不得被当作可安装包。"""
    data = _load_pyproject()
    include = data["tool"]["setuptools"]["packages"]["find"]["include"]
    assert include == ["family_abm*"], f"packages.find.include 应只覆盖 family_abm*，实际 {include}"
    for directory in ("tests", "tools", "baseline"):
        assert not (REPO_ROOT / directory / "__init__.py").exists(), (
            f"{directory}/ 含 __init__.py，会被 find_packages 误认为包；请移除"
        )


def test_web_assets_declared_as_package_data() -> None:
    data = _load_pyproject()
    package_data = data["tool"]["setuptools"]["package-data"]["family_abm"]
    joined = " ".join(package_data)
    for asset in ("templates", "static"):
        assert asset in joined, f"package-data 未覆盖 web/{asset}"


# ── 构建与安装冒烟 ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """构建 wheel、隔离安装，并返回路径信息；失败则 skip（缺 python -m build 的环境）。"""
    out_dir = tmp_path_factory.mktemp("dist")
    wheel_result = _run([sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir), str(REPO_ROOT)])
    if wheel_result.returncode != 0:
        message = (wheel_result.stderr or wheel_result.stdout or "").strip()
        if "No module named" in message:
            pytest.skip(f"环境缺少构建工具：{message.splitlines()[-1]}")
        pytest.fail(f"wheel 构建失败：\n{message[-2000:]}")

    wheels = sorted(out_dir.glob("*.whl"))
    assert wheels, "构建未产生 wheel"
    wheel = wheels[0]

    target = tmp_path_factory.mktemp("installed")
    install_result = _run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--quiet", "--target", str(target), str(wheel)]
    )
    if install_result.returncode != 0:
        pytest.skip(f"pip install --target 失败（可能是环境限制）：{(install_result.stderr or '')[-500:]}")
    return {"wheel": wheel, "target": target}


def test_wheel_contains_web_assets(built_dist: dict) -> None:
    """wheel 必须包含前端资源——这是历史上被漏掉的那一项。"""
    with zipfile.ZipFile(built_dist["wheel"]) as archive:
        names = archive.namelist()
    for probe in ("family_abm/web/templates/index.html", "family_abm/web/static/css/style.css", "family_abm/web/static/js/dashboard.js"):
        assert probe in names, f"wheel 缺少 {probe}（package-data 未生效）"


def test_wheel_metadata_declares_dependencies(built_dist: dict) -> None:
    with zipfile.ZipFile(built_dist["wheel"]) as archive:
        metadata_name = next(n for n in archive.namelist() if n.endswith("METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
    for name in REQUIRED_RUNTIME_DEPS:
        # METADATA 里形如 "Requires-Dist: numpy>=1.21.0"
        pattern = re.compile(rf"^Requires-Dist: {re.escape(name)}([><=;\s]|$)", re.MULTILINE)
        assert pattern.search(metadata), f"wheel METADATA 未声明 {name}"


def test_installed_copy_starts_web_app(built_dist: dict) -> None:
    """端到端：安装副本上 import family_abm.web 并 GET / = 200。"""
    result = _run(
        # -X utf8 保证子进程中文输出可稳定断言（不依赖控制台代码页）
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "verify_install.py"), str(built_dist["target"])],
        cwd=built_dist["target"],
    )
    assert result.returncode == 0, f"安装冒烟失败：\n{result.stdout}\n{result.stderr}"
    assert "结果：全部通过" in result.stdout, result.stdout


def test_baseline_script_is_deterministic(tmp_path: Path) -> None:
    """同一 seed 两次运行基线脚本，产物必须逐字节相同。"""
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    for out in (first, second):
        result = _run([sys.executable, str(REPO_ROOT / "tools" / "baseline.py"), "--out", str(out)], cwd=REPO_ROOT)
        assert result.returncode == 0, result.stdout + result.stderr
    assert first.read_bytes() == second.read_bytes(), "同一 seed 的基线快照不稳定"

    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["seed"] == 42
    assert payload["steps"] == 120
    assert payload["summary"]["rows"] > 0


def test_baseline_check_detects_change(tmp_path: Path) -> None:
    reference = tmp_path / "ref.json"
    assert _run([sys.executable, str(REPO_ROOT / "tools" / "baseline.py"), "--out", str(reference)], cwd=REPO_ROOT).returncode == 0

    same = _run([sys.executable, str(REPO_ROOT / "tools" / "baseline.py"), "--check", str(reference)], cwd=REPO_ROOT)
    assert same.returncode == 0, same.stdout

    tampered = json.loads(reference.read_text(encoding="utf-8"))
    tampered["summary"]["agents"]["FamilyMember"]["columns"]["state_happiness"]["mean"] = 0.123456
    reference.write_text(json.dumps(tampered, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    changed = _run([sys.executable, str(REPO_ROOT / "tools" / "baseline.py"), "--check", str(reference)], cwd=REPO_ROOT)
    assert changed.returncode == 1, "基线对比未能发现被篡改的数值"
