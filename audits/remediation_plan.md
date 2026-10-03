# family_abm 修缮计划（供逐步审计）

> 配套审查证据：[`final_review.md`](final_review.md) · [`core_family.md`](core_family.md) · [`fitting_niche.md`](fitting_niche.md) · [`ml_viz.md`](ml_viz.md) · [`web_packaging.md`](web_packaging.md) · [`verification.md`](verification.md)
>
> **使用方式**：每个 Step 是一条**可独立审计的提交**。审计时只需检查 4 项：① 改动范围是否越界（见"写范围"）；② 验收命令是否真实通过；③ 是否新增/修改了对应回归测试；④ 是否引入了新的硬编码魔法值（这是本次审查反复踩到的坑）。
>
> **全局不可动清单（贯穿所有阶段）**：不要为了"让测试过"而放宽 `_validate_data` 的数据点下限；不要把 `DEFAULT_PARAMS` 的键改名（前端 19 个字段名逐字依赖它）；不要动 `MODEL_REGISTRY`/`MODEL_PARAM_NAMES`/`MODEL_STATE_NAMES` 的对外键名（Web 与 examples 依赖）；任何行为变更都要同步 README（见 P8-2）。

## 阶段总览

| 阶段 | 目标 | 步数 | 预估 | 前置依赖 |
|---|---|---|---|---|
| **P0** | 审计地基：可复现的执行/验证基础设施 | 3 | 1 天 | 无 |
| **P1** | 正确性止血：上报可信、端到端跑得通 | 5 | 2–3 天 | P0 |
| **P2** | 可复现性：种子体系与实验隔离 | 4 | 2 天 | P0 |
| **P3** | 校准与数值健全性：让默认参数下的模型讲得通 | 5 | 3 天 | P1、P2 |
| **P4** | 打包与部署：装得上、扛得住 | 4 | 2 天 | P1 |
| **P5** | 拟合方法论：可辨识、可诊断、可解释 | 5 | 3–4 天 | P1、P2、P3 |
| **P6** | ML 接口契约：标签/特征/导出正确 | 4 | 2 天 | P0 |
| **P7** | 建模深度：niche 与家庭层因果 | 4 | 3 天 | P3、P6 |
| **P8** | 工程化收尾：测试、CI、文档、许可 | 4 | 2 天 | 贯穿 |
| **P9** | 科研增强（可选）：方差/敏感性/基线 | 4 | 3 天 | P2、P5 |

> 建议并行度：P4 与 P2 可并行（写范围不重叠）；P6 可与 P1/P2 并行；P7 必须等 P3 的校准定型（否则 niche 归一化会二次返工）。

---

## P0 — 审计地基（1 天，先做，否则后面每一步都无法客观验收）

### P0-1 建立最小测试骨架
- **改动**：新增 `tests/test_smoke.py`、`tests/conftest.py`（fixture：固定种子的 2 户 5 成员环境）；新增 `pyproject.toml` 的 `[tool.pytest.ini_options]`。
- **审计点**：`pytest -q` 能跑；`conftest` 里**不得**出现裸 `random` 调用（为 P2 预留）。
- **验收**：`python -m pytest -q` → 全绿（此时可能只有 1 个 smoke）。
- **写范围**：`tests/**`, `pyproject.toml`

### P0-2 建立"模型台账"文档（对应"假设没有交代"）
- **改动**：新增 `docs/model_assumptions.md`。**每个** ODE 模型与**每个**智能体状态更新，逐条写：① 方程；② 社会学解释；③ **关键假设及其适用范围**（例如 `q*S*H` 的侵蚀项假设"H 与 S 的接触率成正比"）；④ 已知失效区间（引审查实测：`square_law` 在 α·β 大时发散、`wellbeing` 的 p/income 不可辨识）。
- **审计点**：7 个模型 × 4 项是否齐全；`README` 的模型表格是否指向该文档。
- **验收**：文档中每条"已知失效"都能对应到一条 P3/P5 的 Step（可追溯性）。
- **写范围**：`docs/model_assumptions.md`, `README.md`

### P0-3 建立基线快照脚本（防回归）
- **改动**：新增 `tools/baseline.py`：固定种子跑 120 步 → 输出各状态的 `mean/std/min/max` 到 `baseline/fixture_<hash>.json`。
- **审计点**：脚本**必须**显式接收 seed（P2 前可先 `random.seed(seed)`）；输出不得含绝对路径。
- **验收**：同一 seed 连跑两次 → JSON 逐字节相同；不同 seed → 不同。
- **写范围**：`tools/**`, `baseline/**`

---

## P1 — 正确性止血（2–3 天，最高优先级）

### P1-1 `R²` 与收敛判定不再美化失败
- **问题**：`fitter.py:233` 把负 R² 截断为 0；`:249-254` 的 `converged` 又要求 R²>0 → 失败与"极差"不可区分；选起点用未截断值 `:171`，与上报值不同源。
- **改动**：删除 `max(0.0, ...)`，上报真实值（允许负）；`converged` 改为"优化器成功 **且** R² ≥ 阈值 **且** 无参数贴边 **且** 目标非哨兵"；起点选择与最终上报统一走同一个 `_evaluate()`。
- **审计点**：`summary_json()` 新增 `r_squared_raw`/`n_bound_params`/`hit_sentinel` 字段；**不得**把阈值写成魔法数（走类常量）。
- **验收**：`pytest tests/test_fitter.py::test_negative_r2_reported`（构造极差数据，断言上报值 < 0）；`test_bound_params_flagged`。
- **写范围**：`family_abm/fitting/fitter.py`

### P1-2 失败哨兵改为 `inf` 并设发散闸门
- **问题**：`fitter.py:86-94` 用 `1e12`，而合法发散参数目标函数实测可达 `3.17e44` → 优化被驱向"积分失败平台"（梯度 0，原样返回起点且 `success=True`）。
- **改动**：失败返回 `np.inf`；积分后加有界性检查（`|y|>1e6` 或有 NaN/Inf 即判失败）；`_objective` 不得再用常量哨兵。
- **审计点**：grep `1e12` 应为 0 命中；异常分支不得"吞掉后返回一个有限数"。
- **验收**：`pytest tests/test_fitter.py::test_divergent_params_return_inf`；`test_objective_bounded_gate`。
- **写范围**：`family_abm/fitting/fitter.py`

### P1-3 拟合输入显式化（消灭静默错误映射）
- **问题**：`web/app.py:154-161` 在列名不匹配时把 `R1/R2/O1/O2` 静默映射到任意前 N 个 `state_` 列（实测落到恒为 0 的 `state_savings` 还报 R²=0.878）；`make_fitter('square_law')` 直接 `KeyError`。
- **改动**：`make_fitter`/`compare_models` 支持并**要求**显式 `state_mapping`；映射后校验「语义可比性」（列存在 + 非常量 + 量纲提示）；不匹配时抛带可用列清单的异常，**禁止**自动兜底。
- **审计点**：Web 端不再有 `if f'state_{sn}' not in columns` 的自动猜列分支；错误信息包含可用列。
- **验收**：`pytest tests/test_fitter.py::test_no_silent_mapping`（无映射 + 抽象模型名 → 明确报错）。
- **写范围**：`family_abm/fitting/fitter.py`, `family_abm/web/app.py`

### P1-4 数据契约：NaN 语义显式化（不在 API 层伪造 0）
- **问题**：recorder 对 Household 行没有成员列（实测 5760 个 NaN），`web/app.py:130-134` 用 `fillna(0)` 抹平 → 前端聚合比真实值低 28.6%，与 fitter 的 NaN 跳过均值不是同一序列。
- **改动**：`StateRecorder.to_dataframe(level='agent'|'environment'|'both')`；检索/聚合按 `agent_type` 分表；API 层用 `None` 而非 0 表示缺失（保留 NaN 语义），前端显式渲染为 `—`。
- **审计点**：`fillna(0)` 在 `ml/`、`web/` 中应为 0 命中；`to_dataframe` 的列契约写进 docstring。
- **验收**：`pytest tests/test_recorder.py::test_nan_preserved`；`test_aggregate_basis_per_agent_type`（断言成员列只在成员子集上聚合）。
- **写范围**：`family_abm/ml/recorder.py`, `family_abm/web/app.py`, `family_abm/web/static/js/dashboard.js`

### P1-5 记录 t=0 基线，消除拟合相位差
- **问题**：`simulation.py:30-36` 先 `step()` 后 `record()`，`run(3)` 只记录 [1,2,3]；fitter 的 `y0` 实为走完第一步后的状态（`fitter.py:112,145,199`、`viz/plots.py:287`）。
- **改动**：新增 `Simulation(record_initial=True)`（默认 True），在 `run()` 首次 `step()` 前记录 `time=0`；`reset()` 后同样重新记录基线。
- **审计点**：默认行为变更要在 CHANGELOG/README 标注；`current_step` 与 `env.time` 语义统一（顺带修 `simulation.py:36` 与 `scheduler.py:32` 的错位）。
- **验收**：`pytest tests/test_simulation.py::test_records_t0`（断言时间列从 0 开始且首行等于初始状态）；`test_reset_restores_time_axis`（`run(5)`→reset→`run(3)` 时间列为 [0..3]，**不是** [6,6,7,7,8,8]）。
- **写范围**：`family_abm/core/simulation.py`, `family_abm/core/scheduler.py`

---

## P2 — 可复现性（2 天，一切实验的前提）

### P2-1 引入实例级 RNG 并贯穿仿真链路
- **问题**：全包仿真链路无 seed（实测同输入两次 happiness 0.4151 vs 0.3835）。
- **改动**：`Simulation(seed: int|None)` 创建 `random.Random(seed)` 与 `np.random.default_rng(seed)`；`FamilyMember`、`Relationship`、`Scheduler` 改为接收/继承实例 RNG；**删除**模块级 `random.*` 直调（`family_member.py:48,52-56,86,110,119,130,142,147`；`relationships.py:17-21,32-34`；`scheduler.py:17-23`）。
- **审计点**：`grep -n "random\.\(gauss\|uniform\|shuffle\|randint\|random\)" family_abm/` 应为 0 命中（测试目录除外）；RNG 不得作为可变默认参数。
- **验收**：`pytest tests/test_reproducibility.py::test_same_seed_identical`（同 seed 两次 → 状态序列逐位相同）；`test_different_seed_differs`。
- **写范围**：`family_abm/core/*`, `family_abm/family/*`

### P2-2 实验隔离：改调度不得改变状态轨迹
- **问题**：全局 RNG 耦合让 `random.shuffle` 的消耗平移所有 `random.gauss` 流 → "只改调度方式"也改全部轨迹。
- **改动**：调度用**独立** RNG 流（`seed` 与 `seed+1` 或 `SeedSequence.spawn`）；智能体噪声用各自子流；写进 `docs/model_assumptions.md`。
- **审计点**：调度 RNG 与状态 RNG 不共享实例。
- **验收**：`pytest tests/test_reproducibility.py::test_scheduler_independent_stream`（同 seed 下 `sequential` vs `random`，成员状态差异仅来自顺序语义，噪声项可分离验证）。
- **写范围**：`family_abm/core/scheduler.py`, `family_abm/family/family_member.py`

### P2-3 时间轴与状态回滚语义修正
- **问题**：`reset()` 不重置 `Scheduler.time`（`simulation.py:48-52`）；`Environment.step()` 与 `Scheduler.step()` 双时钟可让时间倒流。
- **改动**：只保留一个时钟（`Environment.time`，Scheduler 不再持有）；`Scheduler.reset()` 或删除；`reset()` 若声称可重跑则必须做状态快照，否则**明确**文档化为"只清记录、不回滚状态"。
- **审计点**：`scheduler.py` 不再有 `self.time` 自增覆盖 `environment.time`。
- **验收**：`pytest tests/test_simulation.py::test_single_clock`（混用 `env.step()` 与 `sim.step()` 后时间单调不减）。
- **写范围**：`family_abm/core/environment.py`, `family_abm/core/scheduler.py`, `family_abm/core/simulation.py`

### P2-4 输入校验层（顺带堵住仪表板 500）
- **问题**：`income_age_spread=0` → ZeroDivisionError（UI `min="0"` + `parseFloat(v)||0`，`dashboard.js:255,266`）；`age=NaN` → API 500；`steps=-5` 静默空跑。
- **改动**：`Environment(params=...)` 做 schema 校验（键白名单 + 类型 + 范围，`income_age_spread>0`、`steps∈[1,5000]`）；前端 `parseFloat(v) ?? default` 且去掉与默认值冲突的 `max="5"`；`/api/run` 包 try/except 返回结构化错误。
- **审计点**：校验规则**不得**复制粘贴到多处（单一真源）。
- **验收**：`pytest tests/test_web_api.py::test_invalid_params_422`（`spread=0`/`age="old"`/`steps=-5` 均返回 4xx 且含字段名）。
- **写范围**：`family_abm/core/environment.py`, `family_abm/web/app.py`, `family_abm/web/static/js/dashboard.js`

---

## P3 — 校准与数值健全性（3 天，需 P1+P2 完成）

### P3-1 健康衰减重新标定
- **问题**：教育只保护"年龄加速项"，基础衰减不受保护；deterministic 下 30 岁 41.7 岁触底 0.01，50 年仿真内健康失去区分度。
- **改动**：`edu_protect` 作用于**总衰减**；下调 `health_decay_age` 或引入下限恢复项；把"触底年龄"作为**显式设计参数**写进文档。
- **审计点**：不得为了好看向上调 `health` 下限（0.01 是当前掩码，掩盖了校准错误）。
- **验收**：`pytest tests/test_calibration.py::test_health_stays_informative`（50 年仿真中位健康 > 0.3，且不同 SES 成员可区分）；P0-3 基线快照更新并评审差异。
- **写范围**：`family_abm/family/family_member.py`, `docs/model_assumptions.md`

### P3-2 压力饱和与 neuroticism 单调性
- **问题**：默认均衡点 ≥1 被 clamp 截断，实测 `neuroticism` 0.75 与 1.0 稳态相同（1.0000，另一组数据 0.7542 vs 0.7908）。
- **改动**：去掉硬 clamp，改用 `tanh`/softplus 饱和或调参使均衡点 < 1；保证 [0,1] 全区间单调有效。
- **验收**：`pytest tests/test_calibration.py::test_stress_monotone_in_neuroticism`（对 neuro ∈ {0,0.25,…,1} 稳态严格递增）。
- **写范围**：`family_abm/family/family_member.py`

### P3-3 角色与年龄解耦修正
- **问题**：构造时 `role` 直接写 `role_name`（默认 adult）不按年龄推导；`role_name="parent"` 首步落兜底乘数 0.2。
- **改动**：构造后立即 `role = _role_at_age(age)`；区分"家庭角色(parent/child)"与"生命阶段(preschool…elder)"两个概念，收入乘数按**生命阶段**查表；`role_mul` 之外的角色不再有兜底 0.2。
- **审计点**：`roles.py` 的 `ROLE_REGISTRY` 要么真正接线（见 P7-4），要么删掉，不得继续导入即弃。
- **验收**：`pytest tests/test_calibration.py::test_infant_income_uses_preschool`（0.2 岁婴儿收入等于 preschool 乘数，不再是 adult 的 1.0）。
- **写范围**：`family_abm/family/family_member.py`, `family_abm/family/roles.py`

### P3-4 `dt` 语义统一
- **问题**：`dt_months` 只作用于教育/健康/年龄，stress/happiness/energy 未乘 dt（energy 甚至完全忽略），`dt=12` 一步 vs `dt=1` 十二步结果不同。
- **改动**：所有状态更新显式乘 `dt`；把 `dt_months` 变成**显式参数**（在 `DEFAULT_PARAMS` 或 `Simulation` 构造参数中），不再是 `_p()` 的隐式 default。
- **审计点**：`energy` 的硬编码 0.92/0.06 改为 dt 缩放 + 明确稳态；初值范围与稳态一致（现在 [0.6,1.0] vs 稳态 0.75 → 前 20 步是初始化漂移）。
- **验收**：`pytest tests/test_calibration.py::test_dt_invariance`（`dt=1,12 步` vs `dt=12,1 步`，结果在容差内一致）。
- **写范围**：`family_abm/family/family_member.py`

### P3-5 `square_law` 结构修正
- **问题**：特征值 ±√(αβ) 是不稳定鞍点、无自限项 → 实测发散到 2.5e13；`eps` 只平移不稳定平衡点。
- **改动**：三选一并写清理由：① 加自限项（如 `-c1*R1`）；② 加饱和/容量项；③ 保留原式但在拟合层禁止发散分支 + 文档标注适用范围。任选都必须把"边界内不保证有界"写进 `docs/model_assumptions.md`。
- **审计点**：不得用"调小默认参数边界"来假装修好（掩盖结构问题）。
- **验收**：`pytest tests/test_ode_models.py::test_square_law_bounded`（在声明边界内 `|y|` 有界，或明确抛出"该参数区间不适用"）。
- **写范围**：`family_abm/fitting/lanchester.py`, `docs/model_assumptions.md`

---

## P4 — 打包与部署（2 天，可与 P2 并行）

### P4-1 依赖单一真源
- **问题**：`setup.py:7` 只有 numpy/pandas，而 `import family_abm` 顶层即拉入 scipy+matplotlib（缺任一 → ModuleNotFoundError）；实际还隐性依赖 pydantic。
- **改动**：新增 `pyproject.toml`（PEP 621 `[project] dependencies` 完整清单 + `requires-python`）；`requirements.txt` 改为 `-e .` 或与之同步；`setup.py` 只留 `setup()` 兼容壳或删除。
- **审计点**：两处依赖清单**逐项一致**（可加个测试断言）。`python_requires>=3.9` 与实际语法一致（见 P4-4）。
- **验收**：`pip install .` 后新 venv 中 `python -c "import family_abm; print(family_abm.__version__)"` 成功。
- **写范围**：`pyproject.toml`, `setup.py`, `requirements.txt`

### P4-2 打包 Web 资源（**本次审查的最强 P1**）
- **问题**：无 `package_data`/`include_package_data`/`MANIFEST.in` → 独立构建 wheel = 27,693 B / 30 entries / **无 templates+static**；sdist 同样缺；安装后 `import family_abm.web` → `RuntimeError: Directory '...\web\static' does not exist`。`pip install -e .` 是唯一掩盖路径。
- **改动**：`pyproject.toml` 加 `[tool.setuptools.package-data] family_abm = ["web/templates/**/*", "web/static/**/*"]` + `include-package-data = true`；新增 `MANIFEST.in` 覆盖 sdist；`web/app.py` 的 `StaticFiles(directory=...)` 改为**缺失时给出可读诊断**而非 starlette 原始报错；`Jinja2Templates` 目录也需校验（只修 static 会暴露第二层 `TemplateNotFound`）。
- **审计点**：`package_data` 路径 glob 必须能匹配到实际文件（审查中已见 SOURCES.txt 过期）。
- **验收**（三条都要过）：① `python -m build` → wheel 含 `web/templates/index.html` 与 `web/static/js/dashboard.js`；② sdist 同样含；③ 干净 venv `pip install <wheel>` → `import family_abm.web` 成功 且 `GET /` = 200。
- **写范围**：`pyproject.toml`, `MANIFEST.in`, `family_abm/web/app.py`

### P4-3 Web 会话化 + 拟合作业化（消灭串台与 155 s 阻塞）
- **问题**：模块级 `_sim_env/_sim_df/_last_fitter` 被所有请求共享（实测 A 的 `/api/data` 返回 B 的数据）；`async def` 内同步跑 CPU 密集拟合（实测阻塞 156.3 s，其他请求延迟 155.33 s）。
- **改动**：`run_id → session` 显式存储（带 TTL/LRU 上限）；端点签名加 `run_id`；拟合改 `run_in_threadpool` 或后台任务 + 状态轮询；加超时与取消；JSON 响应禁 NaN（用 `None`）。
- **审计点**：`grep -n "^_sim" family_abm/web/app.py` 应为 0 命中；不得再用全局可变单例。
- **验收**：`pytest tests/test_web_api.py::test_sessions_isolated`（两个 run_id 交叉请求互不污染）；`test_fit_does_not_block`（拟合进行中 `GET /api/params` P95 < 200 ms）。
- **写范围**：`family_abm/web/app.py`

### P4-4 `examples` 与声明版本对齐
- **问题**：`examples/fitting_viz_demo.py:54,82,134,177` 用 `pd.DataFrame` 注解但**从未 import pandas**、无 `from __future__ import annotations` → 声明支持的 3.9–3.13 上 import 即 `NameError`（3.14 被 PEP 649 掩盖）。
- **改动**：加 `from __future__ import annotations` **或**补 `import pandas as pd`；给三个 examples 加最小回归（至少 import 成功）。
- **审计点**：`requires-python` 与 CI 的测试矩阵一致（建议 3.9 + 3.12 + 3.14）。
- **验收**：`pytest tests/test_examples_import.py`；三项 `python -m py_compile` 通过。
- **写范围**：`examples/*.py`, `tests/test_examples_import.py`

---

## P5 — 拟合方法论（3–4 天，需 P1/P2/P3）

### P5-1 参数可辨识性检查与参数化改造
- **问题**：`wellbeing` 的 `p` 与 `income` 只以 `p*income` 出现 → 乘积不变族目标函数**逐位相同**、残差雅可比 SVD σ_min≈4e-10（秩 4/5）；固定 `income=0.5` 与 `5.0` 得**完全相同**的 R²=0.950314。
- **改动**：`income` 从自由参数改为**输入序列**（由 recorder 提供），或固定其一并只拟合比值；新增通用"可辨识性体检"：拟合后计算残差雅可比 SVD，报告 `σ_min/σ_max` 与秩，低于阈值即在 `summary_json()` 标注 `identifiable: false` + 指明共线参数组。
- **审计点**：不得只在前端隐藏该参数。
- **验收**：`pytest tests/test_identifiability.py::test_p_income_collinear_flagged`（构造乘积不变族断言目标逐位相同）；`test_identifiability_reported`。
- **写范围**：`family_abm/fitting/fitter.py`, `family_abm/fitting/lanchester.py`

### P5-2 按量纲设置参数边界
- **问题**：默认 `(1e-4, 5.0)` 对所有模型所有参数一刀切；对 `K`/`k1`/`k2`/`target1`/`target2` 量纲不合适，`target2=0.0` 根本不可达。
- **改动**：`MODEL_PARAM_BOUNDS`（或每个模型函数暴露 bounds 元数据）按语义给出区间；未提供时**显式报错**而不是回落到魔法默认。
- **验收**：`pytest tests/test_ode_models.py::test_bounds_per_model`（每个模型每个参数都有声明边界，且 `0` 在各参数可达区间内或明确排除的理由）。
- **写范围**：`family_abm/fitting/lanchester.py`, `family_abm/fitting/fitter.py`

### P5-3 `fit_robust` 报告统计而不只是"最佳"
- **问题**：8 个起点只挑最好 → 用户看到的是 best-case；且选起点用未截断 R²（`:171`）而上报用截断值（`:233`），两个 R² 不同源。
- **改动**：上报 `n_starts/n_success/r2_best/r2_median/r2_std/params_std/n_bound_params`；`fit_robust` 暴露 `n_starts`、`seed`；起点采样支持 `latin_hypercube`（默认保持 uniform 以兼容）。
- **验收**：`pytest tests/test_fitter.py::test_robust_reports_dispersion`（断言字段存在且 `r2_median <= r2_best`）。
- **写范围**：`family_abm/fitting/fitter.py`

### P5-4 `fit_global` 参数开放 + 早熟防护
- **问题**：`maxiter=1000`、`tol=1e-8`、`seed=42` 硬编码；只跑一次无法判断早熟；实测 5 参数外推 **45–57 分钟**（单次目标 11 ms / DE 35.7 ms·eval）。
- **改动**：暴露 `maxiter/tol/popsize/seed/mutation/recombination/polish`；默认 `maxiter` 降到 50–100；提供 `n_restarts`（多种子重复）并报告中位数/方差；DE 收敛后在最优解做一次局部 `minimize` 精修。
- **审计点**：不得把长耗时的默认值留成"能跑就行"；Web 端点必须有超时（见 P4-3）。
- **验收**：`pytest tests/test_fitter.py::test_global_multi_seed_dispersion`（`n_restarts=3` 报告方差）；基准测试记录默认配置耗时 < 60 s（`logistic` 2 参数）。
- **写范围**：`family_abm/fitting/fitter.py`

### P5-5 `compare_models` 可用化 + 模型选择准则
- **问题**：7 个模型中 6 个直接因缺映射不可用；不能传 `state_mapping`；无参数个数惩罚。
- **改动**：支持 `state_mapping`/`**fit_kwargs`；输出 AIC/BIC 表（`n*ln(RSS/n) + 2k`），并对"映射语义不匹配"直接报错。
- **验收**：`pytest tests/test_fitter.py::test_compare_models_all_seven`（同名数据下 7 个模型均能出结果或给出明确原因）。
- **写范围**：`family_abm/fitting/fitter.py`

---

## P6 — ML 接口契约（2 天，可与 P2 并行）

### P6-1 标签对齐修正（伪造 0 与行序依赖）
- **问题**：`features.py:36-40` 的 `shift(-lag).fillna(0)` → 实测 485/1680 = **28.9% 标签是伪造 0**（无一为真实 0）；组内位置 shift 依赖行序 → `sample()` 打乱后错位 **99.6%**；`[:len(X)]` 截断是 no-op。
- **改动**：先 `sort_values(["agent_id","time"]).reset_index(drop=True)`；用 `mask = y.notna()` 丢弃无下一步样本（**禁止 fillna(0)**）；删除 no-op 截断；返回 `(X, y, index)` 或直接复用 `build_transition_dataset`。
- **审计点**：`grep -n "fillna(0)" family_abm/ml/features.py` 应为 0 命中。
- **验收**（**必须包含 ground-truth 单测**）：`pytest tests/test_features.py::test_label_alignment_vs_ground_truth`（自建 `(agent_id, time+lag)` 查表逐行断言）、`test_shuffled_input_still_aligned`、`test_no_forged_zero_labels`（伪造 0 计数为 0）。
- **写范围**：`family_abm/ml/features.py`

### P6-2 特征矩阵口径修正
- **问题**：`features.py:31-36` 的 `fillna(0)` 让选定 11 列中 **51.9%** 单元格是伪造 0；默认列还含 `attr_age` 静态属性与 target 自身；Household 专属列与成员列混在一起。
- **改动**：默认特征按 `agent_type` 分表且只取该类型真实存在的 `state_` 列；排除 `attr_*`/`alive`/`target_column`；保留 NaN（交 pipeline）或显式 `SimpleImputer`；docstring 写清列语义。
- **验收**：`pytest tests/test_features.py::test_no_target_leakage`、`test_feature_nan_preserved`。
- **写范围**：`family_abm/ml/features.py`

### P6-3 `StateRecorder` 导出能力与时间轴一致性
- **问题**：`to_dataframe()` 只覆盖 agent 级，环境级 `history` 无导出通道；`record_agents=False` 时返回 (0,0) 无列表；无 parquet。
- **改动**：`to_dataframe(level=...)`、`to_csv/to_parquet(level=...)`；空表也返回列结构；导出前校验时间轴单调。
- **验收**：`pytest tests/test_recorder.py::test_environment_level_export`、`test_empty_shape_has_columns`。
- **写范围**：`family_abm/ml/recorder.py`

### P6-4 可视化默认安全 + 显式后端
- **问题**：`viz/plots.py:8` import 期强制 `matplotlib.use("Agg")` 覆盖调用方后端且 `plt.show()` 失效；`plot_timeseries` 多 agent 拼成一条含重复 t 的折线。
- **改动**：**不再**在 import 期设置后端（改为函数内 `save_path` 时用 Agg，或由环境变量控制）；`plot_timeseries` 按 agent 分组（`groupby('agent_id')`）或加 `agent_id` 必填校验；`plot_aggregate` 按 `agent_type` 过滤；调用方负责 `plt.close`，库内提供 `close_all()`。
- **审计点**：grep `matplotlib.use` 不应出现在模块顶层。
- **验收**：`pytest tests/test_viz.py::test_backend_not_overridden`（import 后 `get_backend()` 不变）、`test_timeseries_one_line_per_agent`。
- **写范围**：`family_abm/viz/plots.py`

---

## P7 — 建模深度（3 天，需 P3 + P6）

### P7-1 niche 维度对齐与距离不变量
- **问题**：`micro_niche.py:22-38` 对维度顺序敏感（位置字典相同的两个 niche，维度顺序不同距离 = 0.447 而非 0）；维度数不同直接 `ValueError`。
- **改动**：`get_position_vector` 按**并集维度名排序**取值（缺失填默认）；`distance_to/overlap` 加 permutation-invariant 测试。
- **验收**：`pytest tests/test_niche.py::test_distance_permutation_invariant`（打乱 dimensions 顺序，距离不变）。
- **写范围**：`family_abm/niche/micro_niche.py`

### P7-2 niche 四维空间去退化
- **问题**：`social_capital` 只有 Household 有 → `min(1.0, nan)=1.0` 使 social **恒为 1.0**；`economic` 直接吃 `income`(≈0.008–0.13) 无归一化 → 实测跨 agent 标准差 [0.055, 0.165, **0.000**, 0.014]，实际约一维。
- **改动**：为 `FamilyMember` 派生 `social_capital`（由关系网络度数/信任合成）与 `cultural_level`（由教育+收入合成）；`economic` 做显式归一化（min-max 或对数）并在文档写明归一化区间；`update_from_agent_state` 对缺失键**报错或显式默认**，不再依赖 `.get(...,0.5)` 静默兜底。
- **验收**：`pytest tests/test_niche.py::test_no_constant_dimension`（任一维度跨 agent 标准差 > ε）；`test_missing_key_explicit`。
- **写范围**：`family_abm/niche/micro_niche.py`, `family_abm/family/family_member.py`, `family_abm/family/relationships.py`

### P7-3 资源守恒与负数防护
- **问题**：`resources.py:12-28` 接受负数（`add(-3)` 使值变负、`remove(-5)` 使值变大）；`transfer_to` 不守恒（1.0→1.0 转 0.5，总量 2.0→**1.5**）；`ResourceBundle.get()` 对未知 key 静默回退 economic。
- **改动**：`add/remove` 拒绝负数并 raise；`transfer_to` 返回未转移量（或改为"要么全转、要么按剩余容量转并报告"）；`get()` 未知 key raise `KeyError`；新增守恒断言工具。
- **验收**：`pytest tests/test_resources.py::test_conservation`（transfer 前后总量不变或差额被显式返回）、`test_negative_rejected`、`test_unknown_key_raises`。
- **写范围**：`family_abm/niche/resources.py`

### P7-4 家庭层因果闭环（或明确降级）
- **问题**：`Relationship` 是纯随机游走（无任何模块读取其状态）；`Household.total_income` 滞后成员一步且无人读取；`roles.py` 四个 Role 类从未实例化；`ROLE_REGISTRY` 导入即弃；`Environment.width/height/x/y` 是死参数。
- **改动**（二选一，必须明确表态并写进文档）：
  - **A. 接线**：让 `Relationship.influence_weight` 对成员 happiness/stress 施加耦合项（如 `Δhappiness += w * (member_happiness - self_happiness)`）；`Role.get_decision_weight` 影响资源分配；`Household` 设定反馈进成员参数。
  - **B. 降级**：删除 `roles.py` 的 Role 类与 `InfluenceRelation`（或标记为实验性并移出 `__all__`），`Household` 明确降级为"只读聚合视图"，删除 `Environment` 的空间参数。
- **审计点**：不得两边都留一半（当前状态正是"看起来有机制、实际不产生因果"）。
- **验收**：若选 A：`pytest tests/test_family_causality.py::test_relationship_affects_member_state`（拔掉关系后成员轨迹显著变化）；若选 B：`grep` 死代码 0 命中 + README 结构树同步。
- **写范围**：`family_abm/family/*`, `family_abm/niche/influence.py`, `family_abm/core/environment.py`, `README.md`

---

## P8 — 工程化收尾（2 天，贯穿全程）

### P8-1 测试覆盖到关键契约
- **改动**：把 P1–P7 各步的验收测试整理为套件，覆盖率门槛按模块设（`fitting`/`ml`/`niche` 高，`viz` 低）。
- **审计点**：测试**不得**依赖网络、不得写仓库内的非 temp 路径、不得依赖执行顺序。
- **验收**：`pytest -q` 全绿；`pytest --cov=family_abm` 报告随 CI 产出。

### P8-2 文档与 README 对齐（修正本次审查发现的全部偏差）
- **必改清单**：① 参数数量 18 → **19**（或把 `randomness` 移出"动力学参数"口径并说明）；② niche"四维空间"改为实际可用的口径；③ 健康衰减描述与实际公式一致；④ 补全局种子用法；⑤ 补 `fit_global` 的耗时警告与 `maxiter` 语义；⑥ 依赖清单与 `pyproject.toml` 一致；⑦ 明确说明 **`pip install -e .` 与普通安装的差异已消除**；⑧ 仓库根**补建 README.md**（当前不存在）。
- **验收**：文档中每条声称都能对应一条测试或一段可执行示例（可追溯性检查）。

### P8-3 CI 与仓库卫生
- **改动**：GitHub Actions：`lint(ruff) + pytest(3.9/3.12/3.14) + build wheel/sdist + 干净 venv 安装冒烟 + examples import 冒烟`；补 `.gitignore`（`__pycache__`、`*.egg-info`、`baseline/`、`examples/output/`）；把仓库纳入 git；补 `LICENSE`（当前无）。
- **验收**：CI 在 wheel 冒烟步骤能**复现**并拦截 P4-2 那类缺陷（即故意移除 `package_data` 时 CI 必须红）。

### P8-4 CHANGELOG 与行为变更标注
- **改动**：`CHANGELOG.md` 记录 t=0 记录、`reset()` 语义、R² 可负、默认 `maxiter` 下调等**破坏性/行为性变更**。
- **验收**：每条行为变更都能在 CHANGELOG 找到条目。

---

## P9 — 科研增强（可选，3 天，需 P2 + P5）

### P9-1 多种子批量实验框架
- **改动**：`family_abm/experiments.py`：`run_batch(config, n_seeds, n_jobs)` → 返回长表（seed × step × agent × state）+ 汇总统计；支持 `to_parquet`。
- **验收**：`pytest tests/test_experiments.py::test_batch_reproducible`（同 config 同 seed 集 → 逐位相同）。

### P9-2 参数敏感性分析
- **改动**：Morris/Sobol（可用 `SALib` 作可选依赖）对 19 个参数做敏感性；输出排序表与 S1/ST；`randomness` 作为一等公民进入分析。
- **验收**：对已知影响大的参数（如 `happiness_stress_penalty`）能复现出高 ST；报告 `randomness` 的作用曲线。

### P9-3 基线对照
- **改动**：定义 2–3 个简单基线（常数幸福、纯均值回归、无压力耦合），与完整模型做同 seed 对比，输出效应量/置信区间。
- **验收**：`pytest tests/test_baselines.py`；产出对比表（复杂机制 vs 基线的 Δ 及其区间）。

### P9-4 不确定性可视化
- **改动**：Web 增加"多种子扇形图（中位数 + 5/95 分位）"，与现有单次轨迹并列。
- **验收**：前端能显示区间带；数据来自 P9-1 的批量结果。

---

## 最小可运行路径（回答"做到 P 几才算跑起来"）

分三层，避免一次性铺开 10 个阶段：

| 层级 | 定义 | 所需阶段 | 关键 Step | 步数 | 预估 |
|---|---|---|---|---|---|
| **L1 能装能跑** | 装得上、能启动、能出图；但结果统计上退化、拟合不可信 | **P0(仅 P0-3) + P1 + P4** | `P0-3` `P1-5` `P1-4` `P1-3` `P4-1` `P4-2` | 6 | 2–3 天 |
| **L2 能跑且结论有意义**（推荐落地线） | 仿真校准合理、可复现、上报诚实；可作为研究工具开始用 | L1 + **P2 + P3** | `P2-1` `P2-2` `P3-1` `P3-2` `P3-3` `P3-4` `P3-5` | 13 | 6–8 天 |
| **L3 五个模块全部可用** | 仿真 / 拟合 / ML / niche / 仪表板 都站得住 | L2 + **P5 + P6 + P7**（+P8 收尾） | `P5-1` `P5-3` `P6-1` `P6-2` `P7-2` `P7-4` | 24 | 2–3 周 |

**停止点判断规则**（按实际要用哪个模块决定）：

- 只用**仿真 + 出图** → 到 **P3** 就必须停；P4 只决定"别人能不能装上"。
- 要用 **`/api/fit` 的 R² 下结论** → 必须补 **P5-1**（否则 `wellbeing` 的 `p`/`income` 无论怎么拟合都不可解释，R² 高只是模型设定巧合）。
- 要用 **ML 接口训练** → 必须补 **P6-1/P6-2**（否则 28.9% 标签是伪造 0，训练集本身是脏的）。
- 要把 **"小生境"当论文卖点** → 必须补 **P7-2**（当前 social 维度恒为 1.0，四维实际退化）。
- **P9**（多种子/敏感性/基线）只在需要"结论具备统计置信度"时做，且依赖 P2，不要提前。

### 能跑 ≠ 结果正常：只做到 L1 时这些坑不会报错

| 现象 | 根因 | 归属 Step |
|---|---|---|
| 长仿真里所有成年人 health 卡在 0.01 | 健康衰减校准错误 | P3-1 |
| `neuroticism` 调到 0.7 以上几乎无效果 | 压力被 clamp 饱和 | P3-2 |
| 每次运行 KPI 都不同，无法比较参数 | 无种子 | P2-1 |
| `dt_months` 改大小结果差很多 | dt 未贯穿全部状态 | P3-4 |
| 拟合 R² 很高但参数毫无意义 | `p`/`income` 不可辨识 | P5-1 |
| ML 标签 28.9% 是伪造 0 | `fillna(0)` | P6-1 |
| 四维 niche 实际是一维 | social 恒 1.0 | P7-2 |

### 建议执行顺序（并行优化后约 1.5–2 周达到 L2）

```
第 1 天      P4-1 + P4-2（打包：最快见效，直接消灭"装不上"）   ┐ 可并行
             P0-3（基线快照，后续所有 diff 的锚点）            ┘
第 2–3 天    P1-5 → P1-1 → P1-2 → P1-3 → P1-4（诚实上报与数据契约）
第 3–4 天    P2-1 → P2-2 → P2-3 → P2-4（可复现；此后才能做敏感性）
第 5–7 天    P3-1 → P3-2 → P3-3 → P3-4 → P3-5（校准；改完必须重跑 P0-3 基线并评审差异）
第 8 天      P8-1/P8-2/P8-3（测试固化 + CI 冒烟 + 文档对齐）→ 宣布 L2 达成
```

> 顺序依赖：**P3 必须在 P2 之后**（没有种子，校准改动无法用多种子验证）；**P5 必须在 P3 之后**（模型结构改了要重新标定）；**P7-2 必须在 P3-1/P3-2 之后**（niche 依赖 income/education/happiness 的分布已稳定）。

## 审计建议顺序

1. **先审 P0/P1/P2**：这三阶段决定"结论可不可信"。重点看：R² 是否还可能被美化、种子是否真的贯穿、t=0 是否落盘。
2. **再审 P4**：装得上、不串台、不阻塞——这三条是可用性硬门槛。
3. **P3/P5 一起审**：校准与拟合方法论互相影响（例如改了 `square_law` 结构就必须重跑 P0-3 基线并评审差异）。
4. **P6/P7 一起审**：ML 契约与 niche 语义都依赖"缺失值语义"的统一（P1-4）。
5. **P8 最后审，但要全程盯**：文档与 CI 是防止本次问题复发的唯一机制。

每个 Step 的审计记录建议固定 5 项：**改动范围 / 验收命令输出 / 新增测试名 / 基线 diff / 是否引入新魔法值**。
