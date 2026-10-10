"""从研究设计文档（DOCX）导出 Markdown，供 GitHub 在线阅读。

为什么是"导出"而不是"另写一份"
------------------------------
文档内容的唯一真源是 `tools/build_research_doc.py`（生成 DOCX）。
若再手写一份 Markdown，两处会各自漂移——这正是本项目反复避免的模式
（依赖清单、README 参数计数都用了同样的原则：一处定义 + 机械派生 + 测试约束）。

因此这里从 DOCX 的 OOXML 结构**派生** Markdown：读取标题层级、段落、
列表样式与表格，并把加粗 run 还原为 `**` 标记。

用法
----
    python tools/export_research_md.py
    python tools/export_research_md.py --check   # 只校验是否已同步
"""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "docs" / "研究设计文档.docx"
TARGET = REPO_ROOT / "docs" / "研究设计.md"

# 标题中出现的全角空格/尾随空白需要清理
HEADING_CLEAN = re.compile(r"\s+$")


def _iter_blocks(document: Document):
    """按文档顺序产出段落与表格。

    python-docx 的 `document.paragraphs` 与 `document.tables` 是分开的列表，
    直接遍历会丢失两者的相对顺序；这里走 body 的子元素以保证顺序正确。
    """
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, document)
        elif tag == "tbl":
            yield Table(child, document)


def _paragraph_markdown(paragraph: Paragraph) -> str:
    """把段落转成 Markdown 行（保留 ** 加粗标记）。"""
    pieces = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        # 加粗 run 还原为 ** 标记；跳过纯空白加粗避免产生 ** **
        if run.bold and text.strip():
            pieces.append(f"**{text}**")
        else:
            pieces.append(text)
    return "".join(pieces).rstrip()


def _is_mono(paragraph: Paragraph) -> bool:
    """判断是否为等宽（代码）段落。"""
    return any(run.font.name and "Courier" in run.font.name for run in paragraph.runs)


def _table_markdown(table: Table) -> list[str]:
    """把表格转成 GitHub 风格 Markdown 表格。"""
    rows = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        rows.append(cells)
    if not rows:
        return []

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    lines = ["| " + " | ".join(rows[0]) + " |",
             "|" + "|".join([" --- "] * width) + "|"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def convert(document: Document) -> str:
    lines: list[str] = []
    in_code_block = False

    for block in _iter_blocks(document):
        if isinstance(block, Table):
            if in_code_block:
                lines.append("```")
                in_code_block = False
            lines.append("")
            lines.extend(_table_markdown(block))
            lines.append("")
            continue

        style = block.style.name if block.style is not None else ""
        text = _paragraph_markdown(block)

        if style.startswith("Heading") or style == "Title":
            if in_code_block:
                lines.append("```")
                in_code_block = False
            level = {"Title": 1}.get(style)
            if level is None:
                level = int(style.split()[-1]) + 1
            lines.append("")
            lines.append(f"{'#' * min(level, 6)} {text}")
            lines.append("")
            continue

        if not text:
            if not in_code_block:
                lines.append("")
            continue

        if _is_mono(block):
            if not in_code_block:
                lines.append("")
                lines.append("```bash")
                in_code_block = True
            lines.append(text)
            continue

        if in_code_block:
            lines.append("```")
            in_code_block = False

        # 中文引号：DOCX 里是角括号，Markdown 保持原样即可
        if style == "List Bullet":
            lines.append(f"- {text}")
        elif style == "List Number":
            lines.append(f"1. {text}")
        else:
            # 列表后紧跟普通段落时必须留空行，否则 Markdown 会把该段
            # 并入上一个列表项（实测会吞掉段落边界）
            if lines and lines[-1].startswith(("- ", "1. ")):
                lines.append("")
            lines.append(text)
            lines.append("")

    if in_code_block:
        lines.append("```")

    # 压缩连续空行
    output: list[str] = []
    for line in lines:
        if line == "" and output and output[-1] == "":
            continue
        output.append(line)

    header = (
        "<!-- 本文件由 tools/export_research_md.py 从「研究设计文档.docx」派生，请勿手工编辑。 -->\n"
        "<!-- 修改内容请改 tools/build_research_doc.py，然后重新生成两份文件。 -->\n"
    )
    return header + "\n".join(output).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出研究设计文档的 Markdown 版本")
    parser.add_argument("--check", action="store_true", help="只校验是否已同步")
    args = parser.parse_args(argv)

    if not SOURCE.exists():
        print(f"[FAIL] 源文件不存在：{SOURCE}；请先运行 python tools/build_research_doc.py")
        return 1

    with zipfile.ZipFile(SOURCE) as archive:
        archive.testzip()

    content = convert(Document(str(SOURCE)))
    actual = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""

    if content == actual:
        print("[OK] docs/研究设计.md 与 DOCX 已同步")
        return 0

    if args.check:
        print("[FAIL] docs/研究设计.md 与 DOCX 不一致；运行 python tools/export_research_md.py 修复")
        return 1

    TARGET.write_text(content, encoding="utf-8")
    print(f"[OK] 已写入 {TARGET.relative_to(REPO_ROOT)}（{len(content.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
