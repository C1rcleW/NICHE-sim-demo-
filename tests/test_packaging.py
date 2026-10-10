"""阶段 A 验收测试：打包必须携带 Web 资源，且安装副本真的能启动。

回归对象：`setup.py` 曾只声明 numpy/pandas 且无 package_data，导致
- `import family_abm` 在缺 scipy/matplotlib 的环境直接 ModuleNotFoundError；
- wheel 不含 web/templates、web/static，安装后 `import family_abm.web` 抛 RuntimeError。

设计约束（来自阶段 A 审计）：
- 构建必须在**源码树拷贝**上进行：`python -m build <repo>` 会在仓库根写 build/ 与
  *.egg-info，污染工作区；--outdir 只重定向 wheel，不能阻止这一点。
- HTTP 冒烟依赖 httpx，必须出现在 [dev] extra，且缺失时算失败而非跳过。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# import family_abm 时真正需要的第三方依赖（源码里实际 import）
REQUIRED_RUNTIME_DEPS = ["numpy", "pandas", "scipy", "matplotlib", "fastapi", "uvicorn", "jinja2", "pydantic"]
# 惰性导入的依赖：只作为 extra 提供
OPTIONAL_DEPS = {"networkx": "viz"}

# 构建 wheel/sdist 所需的文件与目录（相对仓库根）
BUILD_INPUTS = ["family_abm", "pyproject.toml", "setup.py", "README.md"]


def _load_pyproject() -> dict:
    if tomllib is None:
        pytest.skip("缺少 tomllib/tomli，无法解析 pyproject.toml")
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, env=env, timeout=600)


def _stage_sources(destination: Path) -> Path:
    """把构建所需文件拷到临时目录，避免在仓库根产生 build/ 与 *.egg-info。"""
    for name in BUILD_INPUTS:
        source = REPO_ROOT / name
        target = destination / name
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)
    return destination


# ── 元数据契约 ────────────────────────────────────────────────────────────


def test_pyproject_declares_all_runtime_dependencies() -> None:
    """pyproject 必须声明全部运行时依赖，且版本下限非空。"""
    data = _load_pyproject()
    deps = data["project"]["dependencies"]
    declared = {dep.split(">=")[0].strip().lower() for dep in deps}
    missing = [name for name in REQUIRED_RUNTIME_DEPS if name not in declared]
    assert not missing, f"pyproject.toml 缺少运行时依赖：{missing}"
    for dep in deps:
        assert ">=" in dep, f"依赖 {dep!r} 未声明版本下限"


def test_lazily_imported_dependency_is_an_extra_not_required() -> None:
    """只在函数内惰性导入的依赖不应进运行时依赖，但必须作为 extra 提供。"""
    data = _load_pyproject()
    required = {dep.split(">=")[0].strip().lower() for dep in data["project"]["dependencies"]}
    extras = data["project"]["optional-dependencies"]
    for name, extra_name in OPTIONAL_DEPS.items():
        assert name not in required, f"{name} 是惰性依赖，不应出现在运行时依赖中"
        assert extra_name in extras, f"缺少 [{extra_name}] extra"
        assert any(dep.startswith(name) for dep in extras[extra_name]), f"[{extra_name}] 未包含 {name}"


def test_http_smoke_dependency_is_declared_as_dev_extra() -> None:
    """verify_install.py 的 HTTP 端到端依赖 httpx，必须是 [dev] 的一部分。"""
    extras = _load_pyproject()["project"]["optional-dependencies"]
    assert "dev" in extras, "缺少 [dev] extra"
    assert any(dep.startswith("httpx") for dep in extras["dev"]), (
        "[dev] 未包含 httpx：按声明安装会让 HTTP 冒烟退化为跳过（假绿）"
    )


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
    include = _load_pyproject()["tool"]["setuptools"]["packages"]["find"]["include"]
    assert include == ["family_abm*"], f"packages.find.include 应只覆盖 family_abm*，实际 {include}"
    for directory in ("tests", "tools", "baseline"):
        assert not (REPO_ROOT / directory / "__init__.py").exists(), (
            f"{directory}/ 含 __init__.py，会被 find_packages 误认为包；请移除"
        )


def test_web_assets_declared_as_package_data() -> None:
    package_data = _load_pyproject()["tool"]["setuptools"]["package-data"]["family_abm"]
    joined = " ".join(package_data)
    for asset in ("templates", "static"):
        assert asset in joined, f"package-data 未覆盖 web/{asset}"


def test_package_version_matches_pyproject() -> None:
    """`family_abm.__version__` 必须与 pyproject 一致（打包验收命令依赖它）。"""
    import family_abm

    assert hasattr(family_abm, "__version__"), "缺少 family_abm.__version__"
    assert family_abm.__version__ == _load_pyproject()["project"]["version"]


def test_pyproject_does_not_claim_a_license_that_is_missing() -> None:
    """仓库没有 LICENSE 文件时，不得在元数据里声明 license（避免虚假授权声明）。"""
    project = _load_pyproject()["project"]
    has_license_file = any((REPO_ROOT / name).is_file() for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"))
    if not has_license_file:
        assert "license" not in project, "仓库无 LICENSE 文件，却声明了 license 字段"


# ── 构建与安装冒烟 ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """在源码树拷贝上构建 wheel、隔离安装；构建工具缺失则 skip。"""
    preexisting = {name for name in ("build", "dist", "family_abm.egg-info") if (REPO_ROOT / name).exists()}
    stage = _stage_sources(tmp_path_factory.mktemp("src"))
    out_dir = tmp_path_factory.mktemp("dist")
    wheel_result = _run([sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir), str(stage)])
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
    return {"wheel": wheel, "target": target, "stage": stage, "preexisting": preexisting}


def test_build_does_not_pollute_repository(built_dist: dict) -> None:
    """构建必须在临时拷贝里进行，不得在仓库根**新增**构建产物。

    只检测"相对于构建前新增"的产物：``pip install -e .`` 本身就会在仓库根留下
    ``family_abm.egg-info/``（可编辑安装的正常副产物，且已被 .gitignore 覆盖），
    因此不能把预先存在的目录算作本次构建的污染。
    """
    stage = built_dist["stage"]
    assert stage != REPO_ROOT, "构建不应直接以仓库根为源"
    assert (stage / "pyproject.toml").is_file(), "临时拷贝缺少构建输入"

    # 临时拷贝里出现 build/ 是 setuptools 的正常行为，关键是仓库里没有新增
    appeared = [name for name in ("build", "dist", "family_abm.egg-info")
                if (REPO_ROOT / name).exists() and name not in built_dist["preexisting"]]
    assert not appeared, f"本次构建在仓库根新增了产物：{appeared}"

    assert (stage / "build").exists() or (stage / "family_abm.egg-info").exists(), (
        "未在临时拷贝中观察到构建产物，说明构建可能没有真正发生"
    )


def test_wheel_contains_web_assets(built_dist: dict) -> None:
    """wheel 必须包含前端资源——这是历史上被漏掉的那一项。"""
    with zipfile.ZipFile(built_dist["wheel"]) as archive:
        names = archive.namelist()
    for probe in (
        "family_abm/web/templates/index.html",
        "family_abm/web/static/css/style.css",
        "family_abm/web/static/js/dashboard.js",
    ):
        assert probe in names, f"wheel 缺少 {probe}（package-data 未生效）"
    assert not any(name.startswith(("tests/", "tools/", "baseline/")) for name in names), (
        "wheel 不应包含 tests/、tools/ 或 baseline/"
    )


def test_wheel_metadata_declares_dependencies(built_dist: dict) -> None:
    with zipfile.ZipFile(built_dist["wheel"]) as archive:
        metadata_name = next(n for n in archive.namelist() if n.endswith("METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
    for name in REQUIRED_RUNTIME_DEPS:
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
    # 防止"假绿"：HTTP 端到端必须真的执行过，而不是被跳过
    assert "GET / 返回 200" in result.stdout, "HTTP 端到端未执行（疑似被跳过）"
    assert "[SKIP]" not in result.stdout, f"冒烟中存在跳过项：\n{result.stdout}"


def test_verify_install_fails_when_http_dependency_missing(built_dist: dict) -> None:
    """反证：httpx 不可用时，verify_install 必须失败，而不是打印 SKIP 后退出 0。"""
    # 用一个只屏蔽 httpx 的 sitecustomize 注入到 PYTHONPATH。
    # 注意：必须使用 importlib.abc 的现代元路径协议（find_spec）；
    # 旧的 find_module/load_module 在 Python 3.12+ 已被移除，写了也不会生效。
    blocker = built_dist["target"].parent / "httpx_blocker"
    blocker.mkdir(exist_ok=True)
    (blocker / "sitecustomize.py").write_text(
        "import sys\n"
        "from importlib.abc import MetaPathFinder\n"
        "\n"
        "class _HttpxBlocker(MetaPathFinder):\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname == 'httpx' or fullname.startswith('httpx.'):\n"
        "            raise ImportError('httpx blocked for test')\n"
        "        return None\n"
        "\n"
        "sys.meta_path.insert(0, _HttpxBlocker())\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(blocker)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "verify_install.py"), str(built_dist["target"])],
        cwd=str(built_dist["target"]),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert result.returncode == 1, f"httpx 缺失时仍返回 0（假绿）：\n{result.stdout}"
    assert "结果：全部通过" not in result.stdout


# ── 基线 ──────────────────────────────────────────────────────────────────


def _baseline_path() -> Path:
    return REPO_ROOT / "baseline" / "default_seed42.json"


def test_committed_baseline_exists_and_matches_current_behavior(tmp_path: Path) -> None:
    """仓库内必须有可用的基线锚点，且与当前行为一致。

    若本测试失败且改动是有意的，请重新固化：
        python -X utf8 tools/baseline.py --out baseline/default_seed42.json
    并在提交信息中说明行为变化。
    """
    reference = _baseline_path()
    assert reference.is_file(), (
        f"缺少基线锚点 {reference}；生成方式：python -X utf8 tools/baseline.py --out {reference}"
    )
    result = _run([sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "baseline.py"), "--check", str(reference)])
    assert result.returncode == 0, f"当前行为与基线不一致：\n{result.stdout}"


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
    assert (
        _run([sys.executable, str(REPO_ROOT / "tools" / "baseline.py"), "--out", str(reference)], cwd=REPO_ROOT).returncode
        == 0
    )

    same = _run([sys.executable, str(REPO_ROOT / "tools" / "baseline.py"), "--check", str(reference)], cwd=REPO_ROOT)
    assert same.returncode == 0, same.stdout

    tampered = json.loads(reference.read_text(encoding="utf-8"))
    tampered["summary"]["agents"]["FamilyMember"]["columns"]["state_happiness"]["mean"] = 0.123456
    reference.write_text(json.dumps(tampered, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    changed = _run([sys.executable, str(REPO_ROOT / "tools" / "baseline.py"), "--check", str(reference)], cwd=REPO_ROOT)
    assert changed.returncode == 1, "基线对比未能发现被篡改的数值"
