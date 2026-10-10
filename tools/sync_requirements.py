"""把 pyproject.toml 的运行时依赖同步到 requirements.txt。

为什么需要
----------
`pyproject.toml` 是依赖的**唯一真源**（`tests/test_packaging.py` 会强制两者一致）。
但 `requirements.txt` 仍有存在价值：在 GitHub 上渲染为纯文本、便于
`pip install -r` 与依赖机器人读取。

两者必须保持一致，否则测试失败。本脚本提供机械同步，避免手工改两处。

用法
----
    python tools/sync_requirements.py            # 写入
    python tools/sync_requirements.py --check     # 只校验，不写入（CI 可用）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"

HEADER = """# 本文件由 tools/sync_requirements.py 从 pyproject.toml 生成，请勿手工编辑。
# 依赖的唯一真源是 pyproject.toml 的 [project] dependencies 与 optional-dependencies。
# 修改依赖请改 pyproject.toml，然后运行：python tools/sync_requirements.py
"""


def render(pyproject: dict) -> str:
    """按 pyproject 生成 requirements.txt 内容。"""
    project = pyproject["project"]
    lines = [HEADER, "# ── 运行时依赖 ──"]
    lines.extend(project["dependencies"])

    extras = project.get("optional-dependencies", {})
    for name, deps in extras.items():
        lines.append("")
        lines.append(f"# ── 可选依赖 [{name}]：pip install \"family_abm[{name}]\" ──")
        lines.extend(deps)

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步 requirements.txt")
    parser.add_argument("--check", action="store_true", help="只校验是否已同步")
    args = parser.parse_args(argv)

    with PYPROJECT.open("rb") as handle:
        pyproject = tomllib.load(handle)

    expected = render(pyproject)
    actual = REQUIREMENTS.read_text(encoding="utf-8") if REQUIREMENTS.exists() else ""

    if expected == actual:
        print("[OK] requirements.txt 与 pyproject.toml 已同步")
        return 0

    if args.check:
        print("[FAIL] requirements.txt 与 pyproject.toml 不一致；"
              "运行 python tools/sync_requirements.py 修复")
        return 1

    REQUIREMENTS.write_text(expected, encoding="utf-8")
    print(f"[OK] 已写入 {REQUIREMENTS.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
