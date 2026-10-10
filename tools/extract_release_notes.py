"""为 GitHub Release 抽取发布说明正文。

从 CHANGELOG.md 里取出指定版本的段落，去掉文件级抬头与链接定义，
输出可直接粘贴到 Release 表单的内容。

用法：
    python tools/extract_release_notes.py 0.1.0 docs/release-notes-0.1.0.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHANGELOG = REPO / "CHANGELOG.md"

PREAMBLE = """## 研究问题

家庭内部的代际影响强度随子代发展阶段系统性下降。这种变化如何影响子代的长期结果？
含有时变影响系数的家庭动力学，能否被低维方程刻画？

## 验证结果

| 检验 | 结论 |
|---|---|
| E1 易感性阶段结构 | 单调性违例 0 次；阶段边界跳变 2.5×10⁻⁵（连续） |
| E2 效力随阶段递减 | 1.128 → 0.833 → 0.026 → 0.017（学前期 → 成年早期） |
| E3 剂量-反应 | 单调，信噪比 3.7–4.8；**可信强度上限为 4**，超过后状态触界使结论失效 |
| E4 成年后滞后效应 | 仍可分辨（信噪比 3.53），但衰减至童年期的 6.7% |

五条结论在 **25–75 个参数组合下全部成立**；扰动参数只改变适用边界的数值位置
（可信强度上限在 2.0–8.0 之间移动）。

## 已知限制

本工作是**方法性探索，不是政策效果评估**，不提供因果效应估计。

- 影响是**单向下行**的：只实现"年长成员影响年幼成员"，配偶互影响、同伴影响未建模
- 参数部分来自理论解读而非实证测量；定性结论已通过敏感性分析证明稳健，
  但定量门槛依赖参数
- **一个否定的结果**：含有时变影响系数的家庭聚合动力学，无法被单一常系数
  微分方程刻画

完整清单见 [README 的「说明与限制」](https://github.com/C1rcleW/NICHE-sim-Framework#说明与限制)
与 [CHANGELOG](https://github.com/C1rcleW/NICHE-sim-Framework/blob/main/CHANGELOG.md)。

## 安装

```bash
pip install family_abm-0.1.0-py3-none-any.whl
python -m family_abm.web      # 启动仪表板 → http://127.0.0.1:8520
```

要求 Python >= 3.10；MIT 许可。

---

## 完整变更

"""


def extract(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    # 匹配 "## [0.1.0] — ..." 到下一个 "## [" 之前
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"CHANGELOG 中未找到版本 {version}")
    body = match.group(1).strip()
    # 去掉尾部的链接定义（如 [0.1.0]: https://...）
    body = re.sub(r"\n\[[^\]]+\]:\s*\S+\s*$", "", body).strip()
    return PREAMBLE + body + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    version = argv[1]
    notes = extract(version)
    if len(argv) >= 3:
        out = Path(argv[2])
        out.write_text(notes, encoding="utf-8")
        print(f"已写出 {out}（{len(notes.splitlines())} 行）")
    else:
        print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
