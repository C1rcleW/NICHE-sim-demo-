# 贡献指南

感谢有兴趣参与。本项目是一个研究用的建模框架，欢迎以下类型的贡献：

- **缺陷修复** —— 尤其是可复现性、数值稳定性、平台兼容性问题
- **新机制** —— 请附可证伪的检验（见下文"新增机制的约定"）
- **文档改进** —— 论文引用、术语澄清、示例补充
- **家庭结构扩展** —— 单亲、隔代、重组家庭
- **可视化与交互** —— 仪表板的功能与无障碍改进

## 开发环境

```bash
git clone https://github.com/C1rcleW/NICHE-sim-demo-.git
cd NICHE-sim-demo-
pip install -e ".[dev]"
python -m pytest tests/ -q
```

需要 Python 3.9+。前端行为检查需要 Node.js（可选；缺少时相关测试会跳过）。

## 提交前检查清单

```bash
python -m pytest tests/ -q                              # 全部测试
python -m pytest tests/ -q -m "not packaging"           # 跳过构建/安装测试（环境受限时）
python -m ruff check family_abm tests tools experiments # 静态检查（ruff 0.17.0，见 pyproject）
node tools/check_dashboard_behavior.js                  # 前端行为（可选）

# 若改动影响默认行为，需重跑基线并确认差异符合预期
python tools/baseline.py --check baseline/default_seed42.json

# 若改动了 pyproject.toml 的依赖
python tools/sync_requirements.py
```

> **ruff 版本是钉住的**（`pyproject.toml` 的 `[dev]` 与 CI 都用 `0.17.0`）。
> ruff 的默认规则集会随版本变化，浮动安装会让本地与 CI 结果不一致；规则集本身
> 也在 `[tool.ruff.lint] select` 中显式声明，不依赖默认全集。

## 两条硬性约定

**1. 影响默认行为的改动必须显式暴露差异**

`baseline/default_seed42.json` 是默认配置的行为快照。任何改动模型动力学的
提交都要重跑 `--check`，并在提交信息里说明基线差异的原因与量级。
不允许"顺手调参"而不说明。

**2. 新增机制必须附可证伪的检验**

参照 `experiments/mechanism_validation.py` 的形式：
每项检验先写预期，再报告实测；并给出**适用边界**（在什么参数范围内结论成立）。

如果新机制在某个区间失效，请在测试里如实记录，而不是把参数范围调窄到刚好通过。
本项目的 `README.md`「说明与限制」章节就是按这个原则逐条列出的。

## 关于实验与结果

`experiments/` 下的脚本是研究产出的一部分：

- 结果写入 `experiments/results/`（JSON + PNG），随代码一起提交
- 图表标签一律用英文（图会被单独取出放进幻灯片，不应依赖系统中文字体）
- 报错即结论的一部分：拟合失败或检验不通过时，记录数值而不是跳过

## 提交信息

用中文或英文均可，但请写清：

- **改了什么**（文件与行为）
- **为什么**（动机或对应的问题）
- **验证方式**（跑了哪些检查，基线是否变化）

## 报告问题

请在 issue 中附上：

- 操作系统与 Python / 依赖版本
- 最小复现脚本（含随机种子）
- 实际结果与预期结果

若是数值问题，请附 `tools/baseline.py --check` 的差异输出。

## 许可

贡献即表示同意以 [MIT License](LICENSE) 授权。
