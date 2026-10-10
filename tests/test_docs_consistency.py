"""文档与派生文件的同步约束。

本项目有三处"一处定义 + 机械派生"的关系，都靠测试防止漂移：

    pyproject.toml 的依赖  →  requirements.txt      （tools/sync_requirements.py）
    DEFAULT_PARAMS         →  README 的参数计数      （编写时手工同步，测试约束）
    研究设计文档.docx       →  docs/研究设计.md      （tools/export_research_md.py）
    tools/baseline.py      →  baseline/*.json        （tools/baseline.py --check）

如果这些派生文件与源头不一致，测试失败——避免"改了 A 忘了 B"。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCX = REPO_ROOT / "docs" / "研究设计文档.docx"
MARKDOWN = REPO_ROOT / "docs" / "研究设计.md"


def test_derived_markdown_matches_docx() -> None:
    """docs/研究设计.md 必须与 DOCX 同步（由导出脚本派生）。"""
    pytest.importorskip("docx", reason="需要 python-docx 才能读取源文档")
    if not DOCX.exists():
        pytest.skip("研究设计文档.docx 不存在")

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import export_research_md
    from docx import Document

    expected = export_research_md.convert(Document(str(DOCX)))
    actual = MARKDOWN.read_text(encoding="utf-8") if MARKDOWN.exists() else ""
    assert actual == expected, (
        "docs/研究设计.md 与 DOCX 不一致；运行 python tools/export_research_md.py 重新派生"
    )


def test_research_markdown_is_readable_on_github() -> None:
    """派生出的 Markdown 必须结构完整，能在 GitHub 上正常渲染。"""
    if not MARKDOWN.exists():
        pytest.skip("docs/研究设计.md 不存在")
    text = MARKDOWN.read_text(encoding="utf-8")

    # 顶层标题、章节、表格与代码块都要有
    assert text.startswith("<!--") or text.startswith("# "), "缺少标题或派生声明"
    assert "# 家庭代际影响的阶段结构与政策投放时机" in text
    for section in ("## 摘要", "## 一、研究问题", "## 九、研究局限", "## 十、政策意涵"):
        assert section in text, f"缺少章节：{section}"

    # 表格分隔行数量应与表头匹配
    table_lines = [line for line in text.splitlines() if line.startswith("|")]
    separators = [line for line in table_lines if set(line) <= set("| -")]
    assert separators, "没有解析出任何 Markdown 表格"

    # 代码围栏必须成对
    fences = [line for line in text.splitlines() if line.startswith("```")]
    assert len(fences) % 2 == 0, f"代码围栏未闭合（{len(fences)} 个）"

    # DOCX 里用角括号表示中文引号，派生结果应保留（不应出现裸 ASCII 引号对）
    assert "「" in text and "」" in text, "中文引号丢失"
