"""安装冒烟验证：从构建产物到"能启动 Web 服务"，全链路检查。

这是 P1「非 editable 安装必崩」的回归测试载体：
历史上 setup.py 缺少 package_data / MANIFEST.in，导致 wheel 只含 .py 文件，
安装后 `import family_abm.web` 会因 StaticFiles 目录不存在而抛 RuntimeError。

用法（构建与安装由调用方完成）：

    python tools/verify_install.py --import-only
    python tools/verify_install.py <install-target-dir>

Windows 上建议加 `-X utf8`，避免中文输出被控制台代码页转码：

    python -X utf8 tools/verify_install.py <install-target-dir>

退出码：0 = 全部通过，1 = 失败（失败项会打印原因）
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

FAILURES: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    line = f"[{mark}] {label}"
    if detail:
        line += f"  -> {detail}"
    print(line)
    if not condition:
        FAILURES.append(label)


def find_target_root(base: Path) -> Path:
    """在 --target 安装目录里定位真正的包根（兼容 `--target` 与普通 site-packages 两种布局）。

    `pip install --target` 在旧版本里会跳过 `.data` 重定位，此时包直接落在 base 下；
    新版本可能放进 base/Lib/site-packages。这里把候选位置都查一遍。
    """
    candidates = [base, base / "Lib" / "site-packages"]
    for candidate in candidates:
        if (candidate / "family_abm" / "__init__.py").is_file():
            return candidate
    raise RuntimeError(f"未在 {base} 下找到 family_abm 包（候选：{[str(c) for c in candidates]}）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="family_abm 安装冒烟验证")
    parser.add_argument("target", nargs="?", help="pip install --target 的目标目录")
    parser.add_argument(
        "--import-only",
        action="store_true",
        help="在当前环境验证（用于 editable / 已安装环境）",
    )
    args = parser.parse_args(argv)

    if not args.import_only and not args.target:
        parser.error("需要提供 target 目录，或使用 --import-only")
    if args.import_only and args.target:
        parser.error("--import-only 与 target 不能同时使用")

    if args.target:
        base = Path(args.target).resolve()
        if not base.is_dir():
            print(f"目标目录不存在：{base}")
            return 1
        root = find_target_root(base)
        sys.path.insert(0, str(root))
        label = f"安装目录 {root}"
    else:
        label = "当前环境（editable/开发安装）"

    # 必须在导入 app 之前切换 cwd：避免 cwd 遮蔽已安装的包
    os.chdir(tempfile.gettempdir())

    print(f"== family_abm 安装冒烟验证（{label}）==")

    try:
        import family_abm
    except Exception as exc:  # pragma: no cover - 失败路径由调用方观察
        print(f"[FAIL] import family_abm -> {type(exc).__name__}: {exc}")
        return 1

    # 诚实性检查：`python tools/verify_install.py` 会把 tools/ 的父目录放进
    # sys.path[0]，可能让"仓库副本"冒充"已安装副本"从而给出无意义的绿。
    loaded_from = Path(family_abm.__file__).resolve()
    repo_copy = (Path(__file__).resolve().parent.parent / "family_abm").resolve()
    if not args.target and loaded_from.parent == repo_copy:
        check(
            False,
            "检测到测试的是仓库源码副本而非已安装副本",
            f"{loaded_from.parent}；请改用 `python tools/verify_install.py <install-target>` 或从仓库外的 cwd 以 --import-only 运行",
        )
    print(f"[PASS] import family_abm -> {loaded_from}")

    pkg_dir = Path(family_abm.__file__).resolve().parent
    templates_dir = pkg_dir / "web" / "templates"
    static_dir = pkg_dir / "web" / "static"
    check((templates_dir / "index.html").is_file(), "包内含 web/templates/index.html", str(templates_dir))
    check((static_dir / "css" / "style.css").is_file(), "包内含 web/static/css/style.css", str(static_dir))
    check((static_dir / "js" / "dashboard.js").is_file(), "包内含 web/static/js/dashboard.js", str(static_dir))

    try:
        from family_abm.web.app import app
    except Exception as exc:
        print(f"[FAIL] from family_abm.web.app import app -> {type(exc).__name__}: {exc}")
        return 1
    print("[PASS] from family_abm.web.app import app")

    try:
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/")
        check(response.status_code == 200, "GET / 返回 200", f"实际 {response.status_code}")
        check("Family ABM" in response.text, "GET / 渲染出 index.html 内容")
        css = client.get("/static/css/style.css")
        check(css.status_code == 200, "GET /static/css/style.css 返回 200", f"实际 {css.status_code}")
    except ImportError as exc:
        # 必须视为失败：HTTP 端到端是本脚本的核心检查项。
        # 历史实现把它算作 SKIP 并仍然退出 0，会让"9 passed"变成假绿
        # （httpx 未安装时端到端从未真正执行）。httpx 已列入 [dev] extra。
        check(False, "HTTP 冒烟所需依赖缺失", f"{type(exc).__name__}: {exc}（请安装 .[dev]）")
    except Exception as exc:
        check(False, "HTTP 冒烟", f"{type(exc).__name__}: {exc}")

    print()
    if FAILURES:
        print(f"结果：失败 {len(FAILURES)} 项 -> {FAILURES}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
