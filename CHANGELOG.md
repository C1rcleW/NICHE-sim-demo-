# 变更日志

本项目的所有重要变更都记录在此文件。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。
`0.x` 阶段的次版本号可能包含不兼容改动。

## [0.1.0] — 首个公开版本

首个公开发布。此前仓库内的 `0.2.0` 是开发期版本号，从未对外发布；
`0.1.0` 涵盖全部已完成的工作。

### 新增

**框架核心**

- `Agent` / `Environment` / `Scheduler` / `Simulation` 四层结构，支持顺序、随机与随机激活三种调度
- `StateRecorder` 状态记录，输出宽表 DataFrame；提供 `to_statistics_dataframe()` 分组统计与多级 `to_csv(level=...)`
- 家庭层：`FamilyMember`（成员）、`Household`（家庭）、`Relationship`（关系）、`roles`（角色）
- 小生境层：四维社会空间（经济 / 文化 / 社会 / 情感），支持生境距离与重叠度计算
- ML 接口：状态记录 → 特征提取，输出可直接对接 sklearn / PyTorch

**代际影响机制（`family_abm/family/influence.py`）**

- 影响量 = 影响强度 × 易感性(年龄) × Σ(关系权重 × 来源养育能力 × 来源健康) × 状态差距
- 易感性随埃里克森心理社会发展阶段阶梯下降，阶段边界线性过渡（避免人为的动力学间断）
- 子代跨过成年阈值后由"接受影响"转为"施加影响"，并获得初始养育能力——代际更新内生发生
- 关系权重复用 `Relationship.influence_weight()`（信任 / 权力 / 情感）并扣除冲突
- 来源健康作为能量约束；影响按受影响的未成年成员数分摊

**家庭经济压力**

- `Household.total_income` 从"只写不读"变为共同压力源：人均收入低于基准时产生压力，成员各自读取
- 年幼成员对家庭处境更敏感（对应家庭压力模型的核心预测）

**可复现性**

- `Simulation(seed=...)` 注入独立随机流；默认 `seed=42`，**不传 seed 也可复现**
- 关系变量的随机流按 `(seed, 双方身份, 关系类型)` 派生，关系之间互不干扰、不依赖迭代顺序
- 实测：同一 seed 跨进程逐点一致；全局 `random` 被污染后结果不变

**ODE 拟合**

- 7 种兰彻斯特型社会动力学模型：`square_law`、`linear_law`、`influence`、`wellbeing`、`logistic`、`lotka_volterra`、`resource_competition`
- 多起点鲁棒优化（`fit_robust`）与差分进化全局搜索（`fit_global`）
- 失败路径显式化：哨兵解、参数贴边、R² 为负均有结构化输出与告警

**Web 仪表板**

- FastAPI + Plotly.js，中英双语，覆盖仿真配置 / 运行 / 拟合 / 可视化的全流程
- `GET /api/models` 提供状态列方差报告（可用 / 常量 / 不可验证），避免把常量列当拟合目标
- 页面可调 27 个动力学参数，含两个政策杠杆（`influence_strength`、`income_support`）

**研究实验（`experiments/`）**

- `mechanism_validation.py` 四项可证伪检验：E1 易感性阶段结构、E2 效力随阶段递减、E3 剂量-反应与适用边界、E4 成年后滞后效应
- `sensitivity_analysis.py` 参数敏感性：五条结论在 25–75 个参数组合下全部成立
- `life_stage_reducibility.py` 可约性实验（结果是否定的，见下）

**文档与工程**

- `README.md`（使用指南与限制）、`CONTRIBUTING.md`、`LICENSE`（MIT）
- `docs/研究设计文档.docx` 与派生的 `docs/研究设计.md`：理论框架、检验设计、政策意涵
- GitHub Actions CI：lint、测试（3.10 / 3.12 / 3.13 / Windows）、打包与安装冒烟
- 基线快照 `baseline/default_seed42.json`：默认行为的任何改动都会显式暴露
- 106+ 项自动化检验，含可复现性、数据契约、打包、文档一致性

### 修正

**仿真语义**

- 时间轴由 `[1..n]` 改为 `[0..n]`：在首次步进前记录 t=0 基线，使 ODE 拟合的初值正确（此前整条轨迹相差一步）
- 健康衰减由无下界的线性衰减（40 岁时约 7.8%/年，十余年触底 0.01）改为朝下限渐近并受年龄加速
- 教育对健康的作用此前只乘在年龄项上，对基础衰减无效；现作用于总衰减
- 压力平衡点此前算出 > 1 被钳位饱和，导致神经质人格在高区间完全失效；下调基础值后稳态约 0.31–0.37

**正确性**

- 关系状态此前依赖迭代顺序（排序键是 `uuid4()`），导致同一 seed 不可复现
- `apply_influence` 在 `sigma=0` 时仍调用 `rng.gauss`，无效消耗随机数状态并使关系随机游走错位
- 养育存量衰减曾误乘 `strength`，使强度 ≥2 时衰减因子变负、机制实际未生效
- `income_support` 曾加到"收入基准"上，导致支持越多、测得的压力越大（方向相反）

**错误契约与界面**

- `wellbeing` 等抽象模型的状态名与 ABM 列名无默认对应；改为显式 `state_mapping` 并给出候选提示
- 哨兵解判定移到 `predict` 之前：此前返回 500 `prediction_failed`，现返回 200 + `model_not_applicable`
- 恢复函数级兜底 `except`：此前异常逃逸为 `text/plain`，前端无法解析
- 前端 `|| 0` 把缺失值伪造成 0；改为保留 `null`
- 前端补 `_modelInfoSeq` 竞态防护与切换 agent 时的重新加载

**打包**

- wheel 曾缺少 `web/templates` 与 `web/static`，非 editable 安装后 `import family_abm.web` 抛 `RuntimeError`
- 依赖声明曾分散在 `setup.py` / `requirements.txt` / `pyproject.toml` 三处且不一致；现以 `pyproject.toml` 为唯一真源
- 从索引中移除误纳入的 `__pycache__/*.pyc` 与 `egg-info`

### 已知限制

**方法层面**

- 本研究是方法性探索，**不是政策效果评估**，不提供任何因果效应估计
- 模型行为未与家庭追踪数据比对，输出的绝对水平没有经验意义，只有结构性对比有意义
- 易感性的阶段取值、阶段年龄边界、影响强度均来自理论解读而非实证测量；定性结论已通过敏感性分析证明稳健，但定量门槛依赖参数

**模型层面**

- 影响是**单向下行**的：只实现"年长成员影响年幼成员"；成年子代虽转为施加影响一方，但缺乏作用对象；配偶互影响、同伴影响均未建模
- 高影响强度下机制失效：强度 ≥ 8 时子代幸福有超过一半时间步触及取值边界，剂量-反应关系不再可信（实测可信上限为 4）
- 健康动态缺乏实证标定；家庭结构同质（主要实验为三代同堂的完整家庭）
- 小生境空间维度不完整：`social` 依赖 `social_capital`（仅 `Household` 拥有），`economic` 未归一化
- `FeatureExtractor` 的缺失值处理用 0 填充，用于监督学习前需自行处理

**一个否定的结果**

- 含有时变影响系数的家庭聚合动力学**无法**被单一常系数微分方程刻画。已排除工具问题（拟合器对自生成数据 R²=1.00000），差距来自模型结构与动力学的错配而非机制效应

### 移除

- **Python 3.9 支持**：Pydantic 在类创建时求值注解，`X | None` 需要运行时的 `|` 支持。Python 3.9 已于 2025-10 终止支持，因此最低版本提升至 3.10

### 工程与 CI 修正

首次 CI 运行有 3 个 job 失败，均已修复：

- **静态检查**：ruff 使用了浮动版本且规则集为隐式默认。0.15→0.17 让本项目多出 179 项告警。现钉 `ruff==0.17.0` 并显式声明 `[tool.ruff.lint] select`
- **打包冒烟**：CI 调用 `verify_install.py` 时缺少 `--import-only`，脚本直接退出 2
- **Windows 测试**：平台敏感的构建/安装测试加 `packaging` 标记，由专门的 package job 执行

---

## 版本说明

- `0.1.0` 的 API 尚未稳定，次版本号可能包含不兼容改动
- 报告问题请附操作系统与依赖版本、最小复现脚本（含随机种子）；数值问题请附 `python tools/baseline.py --check` 的差异输出

[0.1.0]: https://github.com/C1rcleW/NICHE-sim-demo-/releases/tag/v0.1.0
