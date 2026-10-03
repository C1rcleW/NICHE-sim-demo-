# 阶段 B/C 审计报告

- **审计对象**：`47fbdff`（阶段B）与 `f8c7c93`（阶段C，HEAD）
- **仓库**：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`；审计时 `git status --short` 为空
- **环境**：Python 3.14.3 / scipy 1.17.1 / numpy 2.4.3 / pandas 3.0.2 / fastapi 0.136.1（`pyproject.toml` 仅要求 `scipy>=1.7.0`、`requires-python>=3.9`）
- **方法**：只读仓库；在 `%TEMP%\phasebc_audit\` 下建立三份仓库副本做实验：
  - `base/` = HEAD
  - `old/` = `git show 47fbdff^:family_abm/fitting/fitter.py` 覆盖进去的**阶段B之前**版本
  - `noscale/` = HEAD，但用脚本把 `_integration_scale` 改成恒返回 `1.0`
  - 未修改仓库任何源码/测试/配置；唯一写入的仓库文件是本报告

---

## 1. 判定汇总表

| 断言 | 判定 | 我的实测 | 声称 | 差异 |
|---|---|---|---|---|
| **B1** `record_initial=True` 的 t=0 行 = 步进前初始状态，时间轴 [0..n]；`False` 为 [1..n] | **成立** | t=0 行与步进前状态最大差 `0.000e+00`（t=1 差 `3.429e-02`）；`True`→`[0,1,2,3,4,5]`，`False`→`[1..5]`；行数 `(steps+1)*agents` | 同 | 无。附 P3：基线记录发生在 `pre_step` hook **之前** |
| **B2** 三选一映射规则生效；`influence` 报 ValueError 且含可用列；`wellbeing` 默认映射可用；重复映射报错 | **部分成立**（核心规则成立，但存在 4 条绕过路径） | 规则本身全部实测通过（见 §3.2）；但 `compare_models(df,[...],state_mapping=...)`→`TypeError`；映射到非状态列（`time`/`alive`）被接受；df 缺 `time`/`agent_id` 列→`KeyError`（不是"可用列清单"的 ValueError）；常量状态列**不告警** | 同 | 计划 P1-3 要求 `compare_models` 也支持映射、且"列存在 **+ 非常量**"校验未做 |
| **B3(a)** 不缩放时 `steps=120` 必抛 `ValueError: x0 violates bound constraints` | **不成立** | `old`（阶段B前）三条路径全部 `OK success=True`：aggregate `fun=9.559956e-4`、agent `fun=2.467064e-2`、`fit_robust fun=9.559956e-4`（120步、web 默认两户五口场景同样全部 OK）；`noscale`（人为改恒返回 1.0）三条路径同样全部 OK，数值与 `old` 逐位一致 | "实测 steps=120 必崩" | 在声明支持的环境（scipy 1.17.1）**完全不可复现**；`fitter.py:15-18` 的根因表述（"有限差分 eps 是绝对步长→扰动点漂出边界"）与 scipy 实现不符：`_numdiff.py:554` 的 `x0 violates bound constraints` 检查的是 **x0 自身**，且 `_lbfgsb_py.py:410` 已把 x0 clip 进边界 |
| **B3(b)** 修复版不再抛 | **成立但空洞** | base 120 步不抛——但 `old`/`noscale` 也不抛，故不构成修复证据 | 同 | 无信息量 |
| **B3(c)** 缩放前后目标函数值相对差约 `4e-8` | **不成立** | 同一参数向量下 `_objective`：120 步 `rel_diff=1.527e+02`（15270%）；拟合最优点 `fun` 相对差 **1.286**、`R²` 从 `0.9332` 掉到 `0.8473` | "~4e-8" | 差 7 个数量级以上；并且缩放**改变了模型语义**：拟合参数被整体乘上 `~span`（15步 ratio≈15、30步 ratio≈30），120 步时补偿参数超界 → 拟合质量与收敛判定双双退化 |
| **B4** `_r_squared`/`_solve` 抽取与旧实现等价 | **部分成立** | 把 scale 强制为 1.0 时，`_r_squared` 与旧实现（`47fbdff^` 的 `_save_result`，行 214–235）在 4 组参数×2 个跨度上**逐位相同**（如 120 步旧最优 `0.9332156035` = 新(scale=1)）；但**按出厂状态**（scale=span）同参数下旧 `0.9332156035` vs 新 `-9.2618274443` | "等价" | 抽取本身干净；不等价完全来自 `_integration_scale` 的时间膨胀 |
| **C1** `to_dataframe()` 保留 NaN（无 fillna）；`to_statistics_dataframe()` 分组与 n 正确 | **成立** | 宽表 NaN 计数：Household 6 个成员列各 6 个 NaN、成员 8 列各 6 个；`recorder.py` 内无 fillna；统计表 13 行**逐行独立重算** n/mean/std(ddof=0)/min/max → 0 处失配；`n(FamilyMember,state_happiness)=12`（2 agent×6 时点），`n(Household,state_total_income)=6`；`time/agent_id/alive` 与字符串列均未混入 | "t=0..5 每个 agent 应有 6 个样本" | n 是按 agent_type **跨 agent×时间池化**（2 成员=12），不是每 agent 6；`attr_age` 等 `attr_*` 列混入统计表 |
| **C2** `/api/data` 返回 null 而非 0，且响应无 NaN 字面量 | **成立** | steps=20/120：`HTTP 200`，`resp.text` 中 `NaN`/`Infinity`/`-Infinity`/`nan`/`inf` 全部 `False`；用 `json.loads(..., parse_constant=raise)` 严格解析通过；Household 的 `state_happiness` 全为 `None`、无一个 0 | 同 | 无。附 P3：`statistics` 字段把 `attr_*` 与 `state_*` 混在一起，`n` 池化 |
| **C3** 负 R² 能如实上报；测试的极窄边界是否"作弊" | **成立（机制属实），但测试构造人为且非必要** | **合理边界下的反例**：`linear_law` 显式映射到 happiness/stress + 默认边界 `(1e-4,5.0)` → `r2=-3.9756`；仓库自带示例的 influence 拟合（`bounds=[(0,5),(0,5)]`）→ `r2=-3.8115`（旧代码此处上报 `0.0000`）。测试用 `bounds=[(1e-4,1e-3)]^5, p0=[5.0]^5` → `r2=-4.179`，且把 p0 换成界内的 `5e-4` 结果不变 | "窄边界下负 R² 如实上报" | 机制成立；但该测试的"极窄箱"是人为退化场景，不能证明真实设置下的可见性——不过我自己用默认边界复现出了负 R²，故**不判作弊，判"证据偏弱"**（p0=5.0 越界依赖 scipy 内部 clip，也是坏习惯） |
| **C4** `converged` 新定义的副作用 | **部分成立 / 有问题** | 真实数据+默认边界下的**假阴性**：steps=30 influence `r2=0.9729` 但 `gamma` 贴下界 → `converged=False`；steps=120 wellbeing `r2=0.8083` → False；agent 路径 `r2=0.9880` → False；`fitter.py:312-318` 的 tol=1e-8 会把"优化器正常投影到边界"直接判为不可信 | "贴边参数不应判为收敛" | 不是"贴边但合理"的构造问题，而是**语义换名**：`converged` 从"成功且 R²>0"变成了"无贴边"，前端 `dashboard.js:459` 直接把它显示为"Converged 是/否"，R²=0.99 的拟合现在显示"否"；计划要求拆成 `optimizer_ok`/`fit_acceptable` 且 `converged` 含"R² ≥ 阈值"，实现把阈值条件整条丢了 |
| **C5** 是否破坏既有对外契约 | **部分成立** | `to_csv(path)` 默认分支与旧路径**逐字节相同**（`disk == mem` True，含 CRLF）；`summary_json()` 新增 4 个字段是**纯增量**，前端只读 `r_squared`/`converged`/`params`（`dashboard.js:458-462`），示例 `f"{r2:.4f}"` 在 r2=0.798 下正常；**但** `bounds=scipy.optimize.Bounds(...)` 在阶段C后 `TypeError: 'Bounds' object is not iterable`（`old` 上 `fit_from_dataframe`/`fit_global` 均 OK）；且 `FitRequest` 没有 `state_mapping` 字段，6/7 模型永久 400 | "向后兼容" | `to_csv`/`summary_json` 兼容；新增 `list(bounds)`（`fitter.py:218/250/289`）是**新引入的 API 回归** |

### 额外检查

| 项 | 结果 |
|---|---|
| `git status --short` | 空；仓库根仅 `.gitattributes/.gitignore/pyproject.toml/README.md/requirements.txt/setup.py`，无污染 |
| 基线一致性 | `python -X utf8 tools/baseline.py --check baseline/default_seed42.json` → `[OK] 与基线一致`，exit 0 |
| 全量测试 | `python -X utf8 -m pytest tests/ -q -rs` → `39 passed`，本环境无 skip |
| 恒真/过宽断言 | `test_converged_requires_no_bound_parameters` 经突变实验证明**空转**（把 `converged` 硬编码为 True 它仍然 PASSED）；`test_long_horizon_fit_does_not_crash_on_bounds` 只断言"不抛异常且 r_squared 非 None"，退化 128% 的拟合照样通过 |
| 未使用 import | `family_abm/web/app.py:21` 的 `MODEL_STATE_NAMES` 由阶段B**变成死导入**（`47fbdff^` 出现 2 次，HEAD 只剩 import 1 次）；`ROLE_REGISTRY`(:17)、`compare_models`(:20) 在阶段B前就已是死导入（历史责任，非本次引入） |

---

## 2. 逐文件发现

### P1（必须先修）

#### P1-1｜`_integration_scale` 把"数值健壮性修复"做成了模型语义与拟合结果的回归
- **证据**：`family_abm/fitting/fitter.py:19`（`_SCALE_THRESHOLD=2.0`）、`:147-151`（`span if span > 2 else 1.0`）、`:155-156`（`t_scaled=(t-t[0])/scale`，而 `rhs` 仍用**原参数**积分）。
  对自治 ODE 而言，把积分自变量从 `t` 换成 `τ=(t-t0)/span` 等价于把整条模型轨迹按 `span` 压缩：同一参数向量下的预测值不再对应同一物理时间，只有把 `θ→θ·span` 才能复原旧轨迹，而默认边界 `(1e-4, 5.0)`（`fitter.py:217/249/288`）在长窗口下装不下这个补偿。
- **实测**（`b3_fix.py`）：
  - `steps=15`：出厂 `fun=1.500998e-4`（参数 ratio≈15）vs 关闭缩放 `fun=1.502236e-4`；
  - `steps=30`：`1.212653e-4` vs `1.212621e-4`，ratio≈30；
  - `steps=120`（**web 默认 `steps=120`**、示例 `run_simulation(120)`）：出厂 `fun=2.185570e-3, r2=0.847319, converged=False, r 贴上界 5.0` vs 关闭缩放 `fun=9.559956e-4, r2=0.933216, converged=True, 无贴边` → **目标函数恶化 128.6%，R² 下降 0.0859**；
  - 同一参数向量 `_objective`：`rel_diff=1.527e+02`（不是 4e-8）。
- **影响**：所有 `span>2` 的仿真（即全部真实用法）拟合出的**参数物理含义随窗口长度漂移**，与阶段B前的历史结果、与模型方程的时间单位都不可比；长窗口下参数被边界钉死，正是 `converged=False` 的主要来源（P3-2）。所谓"修复崩溃"在被声明支持的环境里既无故障可修，也没有可复现的验证。
- **建议**：撤掉 `_integration_scale`（或改为**显式可选**且默认关闭）；若确实要治有限差分越界，应作用于优化器（例如给 L-BFGS-B 传 `options={'eps': ...}` 或用 `jac` 解析/相对步长），**不得改 ODE 的时间变量**。重做验证：同一参数向量的 `_objective` 对比 + 15/30/120 步的 `fun/r2/params` 对比，并把这些数字写进测试断言。

#### P1-2｜P1-4 只修了一半：前端仍把 null 当 0，用户可见偏差正是提交自己引用的 28.6%
- **证据**：阶段C 文件清单只含 `fitter.py/recorder.py/web/app.py/test_data_contract.py`，**未动** `family_abm/web/static/js/dashboard.js`；而该文件 `:406`（主时序图 `buildTimeSeries`）与 `:483`（拟合图）都是 `byTime[r.time].push(r[col] || 0)`。
- **实测**（TestClient 真实 payload 复算前端公式）：`state_happiness` 渲染序列相对正确成员均值**偏低 28.57%**，每个时点都是 28.57%（`1 - 5/7`；2 户 5 成员 + 2 个 Household 行）——与提交信息里的"低 28.6%"完全同一个数。
- **影响**：API 层契约修好了（C2 成立），但仪表板主图与拟合图显示的聚合序列**仍是旧的被 0 稀释的序列**，P1-4 声称的用户可见效果并未实现。
- **建议**：`dashboard.js:406/483` 改为 `r[col] ?? null` 并在求均值时过滤 null（或按 `agent_type` 分组聚合），与 `fitter` 的 NaN 跳过语义对齐；计划 P1-4 的写范围本就包含 `dashboard.js:78`。

#### P1-3｜`/api/fit` 删掉自动猜列后没有任何传映射的通道，6/7 模型永久 400
- **证据**：`family_abm/web/app.py:162` 只 `make_fitter(req.model_name)`；`FitRequest`（`:52-55`）无 `state_mapping` 字段；`dashboard.js:447-450` 只发 `{model_name, agent_id, robust}`；`index.html:90` 用 `{% for m in models %}` 渲染**全部 7 个模型**。
- **实测**：对前端真实 payload 逐个调用 → `square_law/linear_law/influence/logistic/lotka_volterra/resource_competition` 全部 `400 模型状态 [...] 找不到对应数据列`，仅 `wellbeing` 200。
- **影响**：错误信息让用户"请显式传入 state_mapping"，但 API 没有任何途径可传；相比此前"静默拟错列"，这是**把可用功能变成不可用**（信息更诚实，能力回退）。
- **建议**：`FitRequest` 增加 `state_mapping: Optional[dict[str,str]]`（并在 UI 提供列选择），或在模型为抽象状态时隐藏/禁用下拉项并给出明确提示；`app.py:21` 随之可恢复使用 `MODEL_STATE_NAMES`。

### P2

#### P2-1｜`compare_models` 不支持 `state_mapping`（计划 P1-3 明确要求）
- 证据：`fitter.py:441-456`（无 `state_mapping` 形参，`**fit_kwargs` 会把映射转发给 `fit_robust` → 报错）。
- 实测：`compare_models(df, ["influence"], state_mapping={...})` → `TypeError: ABMFitter.fit_robust() got an unexpected keyword argument 'state_mapping'`。
- 影响：抽象模型的批量对比仍不可用；P1-3 的验收面只覆盖了 `make_fitter`。建议 `compare_models(..., state_mapping=None)` 透传，并对每个模型 try/except 返回错误字段。

#### P2-2｜P1-4 的审计准则"`fillna(0)` 在 `ml/`、`web/` 中应为 0 命中"未达成
- 证据：`family_abm/ml/features.py:36` `X = df[feature_cols].fillna(0).values`、`:39` `...shift(-lag_steps).fillna(0)`（`recorder.py:54` 里刚写下"不是数值 0"的契约，ML 特征矩阵仍在伪造 0）。
- 影响：把 Household 缺失的成员状态喂成 0 会污染训练特征/标签，与 P1-4 的语义修复直接冲突。建议改为丢行/掩码 + 显式 `missing` 指示列，或至少加文档与告警。

#### P2-3｜阶段C 新引入 `scipy.optimize.Bounds` 支持回归
- 证据：`fitter.py:218/250/289` 新增 `self.bounds = list(bounds)`；`Bounds` 不可迭代（`fitter.py:384` 的 `summary_json` 同样假设可迭代）。
- 实测：HEAD `fit_from_dataframe(..., bounds=Bounds([1e-4]*5,[5.0]*5))` → `TypeError: 'Bounds' object is not iterable`；`fit_global` 同样；而 `old`（阶段B前）两者都 OK（`fit_robust` 旧版本就不支持 `Bounds`）。`minimize`/`differential_evolution` 本身接受 `Bounds`。
- 影响：公开方法签名的合法入参被新代码拒绝。建议统一 `_normalize_bounds()`：`getattr(bounds,'lb'/'ub',None)` 或 `zip(*bounds)`，并在三处复用。

#### P2-4｜阶段C 新增的收敛测试是空转的（已用突变实验证明）
- 证据：`tests/test_data_contract.py:165-171` 的断言包在 `if summary["params_at_bounds"]:` 内，而该场景实测 `params_at_bounds == []`（`converged=True, r2=0.9936`），断言体从不执行。
- 实测：`python -X utf8 -m pytest tests/test_data_contract.py -v -p mutate_converged -k "converged or sentinel"`（插件把 `ABMFitter.converged` 替换为恒 `True`）→ `test_converged_requires_no_bound_parameters PASSED`（`test_sentinel_solution_is_flagged FAILED`，说明只有后者是真断言）。
- 建议：构造一个 `params_at_bounds` 非空的确定场景（如 `bounds=[(1e-4,1e-3)]*5`）并无条件断言，或直接单测 `_parameters_at_bounds`。

#### P2-5｜显式映射只校验"列存在/重复"，未做计划要求的"非常量/语义可比性"校验
- 证据：`fitter.py:56-90`（只查存在与重复）；`family_abm/fitting/fitter.py:142` 的方差闸门是 `np.ptp(y, axis=0).max() < 1e-5`（取 **max**，单个常量列不触发）。
- 实测：`state_mapping={"O1":"time","O2":"alive"}` → `resolve_state_columns` 通过（`{'O1':'time','O2':'alive'}`）；"常量 state_a + 变化的 state_b" → `_validate_data` 一条 warning 都不发（`warnings: []`）。
- 影响：P1-3 想要消灭的"拟到无关/恒零列"在**显式路径**上仍可能发生（虽然需要调用方主动写错）。建议逐状态检查 `nunique/ptp` 并对非 `state_` 前缀的映射给出显式警告。

### P3

- **P3-1**｜df 缺 `time`/`agent_id` 列时抛 `KeyError` 而非"带可用列清单的 ValueError"（`fitter.py:116`、`:129`；实测 `df.drop(columns=["time"])` → `KeyError: 'time'`）。`/api/fit` 只把 `ValueError` 映射成 400（`app.py:187`），故库层面直接调用时会得到 500 语义；Web 层因 `/api/run` 自己产表而不受影响。建议在入口统一 `df.columns` 校验。
- **P3-2**｜`converged` 语义换名 + 丢掉了计划要求的 R² 阈值条件（`fitter.py:340-351`）。实测 R²=0.9729/0.9880/0.8083 的拟合均为 `converged=False`（`params_at_bounds` 非空），前端显示"Converged 否"；计划（`audits/remediation_plan.md:54`）要求"成功 且 R² ≥ 阈值 且 无贴边 且 非哨兵"，并要求 `summary_json` 增 `r_squared_raw`/`n_bound_params`（实际只有 `params_at_bounds`）。
- **P3-3**｜死导入：`web/app.py:21` `MODEL_STATE_NAMES` 由阶段B引入为死代码；`ROLE_REGISTRY`(:17)、`compare_models`(:20) 为历史遗留（非本次）。建议连同 P1-3 一并处理。
- **P3-4**｜统计视图语义不清：`attr_age` 等 `attr_*` 与 `state_*` 混排（实测 13 行里含 `attr_age`）；`n` 跨 agent×时间池化（2 成员×6 时点=12），文档只写"按 agent_type 分组"；`std` 用 `ddof=0` 未标注（`recorder.py:91`）。
- **P3-5**｜t=0 基线在 `pre_step` hook **之前**记录（`simulation.py:52-56`）：实测 `pre_step` 里改写 `happiness=0.123456` 后，t=0 行仍是旧值（`0.5231`）。若用户的 hook 承担"t=0 冲击"语义，拟合器 `y0=y_true[0]` 会拿到 hook 之前的状态。建议明确文档或把基线移到 `pre_step` 之后。
- **P3-6**｜`test_long_horizon_fit_does_not_crash_on_bounds`（`tests/test_simulation_and_fitting.py:172-184`）断言过宽：只要求 `result.success` 与 `r_squared is not None`，因此 P1-1 里 R² 掉 0.0859 的退化仍然通过。建议加 `fun` 上界或与"关闭缩放"结果对比的断言。
- **P3-7**｜`examples/fitting_viz_demo.py:54` 用 `df: pd.DataFrame` 注解但**没有** `import pandas`、也没有 `from __future__ import annotations`；本机 3.14 因 PEP 649 惰性注解可导入，但 `requires-python = ">=3.9"` 下 3.9–3.13 会在 import 时 `NameError`（**阶段B/C 之前就存在**，未实测旧版本）。另 `tests/*.py` 用 `pytest.importorskip("fastapi.testclient")`，而 `httpx` 只在 `[dev]` extra（`pyproject.toml:47`），环境缺 httpx 时两个最关键的 API 测试会**静默 skip**。

---

## 3. 反证实验记录

所有命令在仓库根或 `%TEMP%\phasebc_audit` 下执行；副本用 `robocopy <repo> <tmp>\<variant> /E /XD .git __pycache__ .pytest_cache` 生成。

### 3.0 基线与测试
```
$ git log --oneline -5          -> f8c7c93(C) / 47fbdff(B) / ... ; git status --short -> (empty)
$ python -X utf8 -m pytest tests/ -q -rs        -> 39 passed in 37.37s（无 skip）
$ python -X utf8 tools/baseline.py --check baseline/default_seed42.json
  -> [OK] 与基线一致：baseline\default_seed42.json   exit=0
```

### 3.1 B1
```
$ python -X utf8 %TEMP%\phasebc_audit\b1_timeline.py
[1] record_initial=True steps=5 -> times=[0..5] rows=18 (per-agent rows=6)   equals [0..5]: True
[2] record_initial=False -> times=[1,2,3,4,5]
[3] pre-step state: {'health':0.951594,'happiness':0.676809,...}
    max|t0 - prestep| = 0.000e+00 ; max|t1 - prestep| = 3.429e-02
    t0 identical to pre-step: True ; t1 differs from pre-step: True
[5] pre_step hook sets happiness=0.123456 -> t=0 happy=0.523107060698262
[6] rows=18  (steps+1)*agents=18  agents=3
```

### 3.2 B2
```
$ python -X utf8 %TEMP%\phasebc_audit\b2_mapping.py
influence 默认 -> ValueError: 模型状态 ['O1','O2'] 找不到对应数据列。
   has 'state_mapping': True  has 'state_happiness': True  has 'state_O1': True
   | 期望列名：['state_O1','state_O2']
   | 可用状态列：['state_cultural_level',...,'state_total_income']
   | 请显式传入 state_mapping（示意，需按语义核对）：{'O1': 'state_cultural_level','O2':'state_education'}
6 个抽象模型全部 ValueError；wellbeing -> OK fun=1.500998e-4
dup mapping -> ValueError: 状态列存在重复映射：['state_happiness']
partial {'R1':...} -> ValueError: 模型状态 ['R2'] 找不到对应数据列。
extra key ZZ -> OK ; mapping onto time/alive -> OK {'O1':'time','O2':'alive'}
unknown agent_id -> ValueError: ... 可用 agent_id：['1a53e28e-...', ...]
df.drop('agent_id') + agent_id -> KeyError: 'agent_id'
df.drop('time') [aggregate/agent] -> KeyError: 'time'
1 time point -> ValueError: Need at least 10 time points, got 1.
compare_models(..., state_mapping=...) -> TypeError: ABMFitter.fit_robust() got an unexpected keyword argument 'state_mapping'
常量 state_a + 变化的 state_b -> warnings: []        # 方差闸门取 max 不告警
```

### 3.3 B3 / B4（核心反证）
```
$ python -X utf8 %TEMP%\phasebc_audit\b3_crash.py %TEMP%\phasebc_audit\old 120
fitter: ...\old\family_abm\fitting\fitter.py   has _integration_scale: False
-- default p0=[0.5]*5, bounds=(1e-4,5.0) --  aggregate fit_from_dataframe  OK  success=True fun=0.0009559956402388907 r2=0.9332156058352266
-- agent path --                             agent fit_from_dataframe      OK  success=True fun=0.024670637600076165 r2=0.0725122914450348
-- fit_robust --                             aggregate fit_robust          OK  success=True fun=0.000955995639761747 r2=0.933215605868559
```
```
$ python -X utf8 %TEMP%\phasebc_audit\b3_crash.py %TEMP%\phasebc_audit\noscale 120   # 文件级把 _integration_scale 改恒 1.0
scale arange(121) = 1.0
aggregate fit_from_dataframe OK success=True fun=0.0009559956402388907 r2=0.9332156058352266 conv=True at_bounds=[]
agent / fit_robust 同样 OK（fun 与 old 逐位一致）
```
```
$ python -X utf8 %TEMP%\phasebc_audit\b3_web_default.py %TEMP%\phasebc_audit\old   # 2 户 5 口 steps=120
aggregate robust OK success=True fun=0.00041264676 r2=0.9700187670596782 (81.5s)
agent robust     OK success=True fun=0.00099557452 r2=0.9604673298391317 (87.5s)
aggregate single OK success=True fun=0.0019500637  r2=0.8583163143890553 (4.3s)
```
```
$ python -X utf8 %TEMP%\phasebc_audit\b3_fix.py %TEMP%\phasebc_audit\base
### steps=15 span=15 ###  as-shipped fun=1.500998e-4 r2=0.9710933719 conv=False at_bounds=['s']
                          scale=1.0   fun=1.502236e-4 r2=0.9710695253 conv=False at_bounds=['p','s','income']
                          ratio=[66.7 14.99 14.98 1 66.7]
### steps=30 span=30 ###  as-shipped fun=1.212653e-4 r2=0.9878989840 conv=True  at_bounds=[]
                          scale=1.0   fun=1.212621e-4 r2=0.9878993072 conv=False at_bounds=['p','income']
### steps=120 span=120 #  as-shipped fun=2.185570e-3 r2=0.8473194430 conv=False at_bounds=['r'] params=[0.001415,1.477,5.0,0.0519,0.001415]
                          scale=1.0   fun=9.559956e-4 r2=0.9332156058 conv=True  at_bounds=[]
                          => fun rel_diff = 1.286e+00 ; r2 delta = 8.590e-02
```
```
$ python -X utf8 %TEMP%\phasebc_audit\b4_r2.py %TEMP%\phasebc_audit\base
steps=120  old optimum:  old(raw)=0.9332156035  new(scale=1)=0.9332156035  new(scale=120)=-9.2618274443
steps=120  p0=[0.5]*5:   old(raw)=-14.8563754503 new(scale=1)=-14.8563754503 new(scale=120)=-9.8780000209
（同一向量下 obj: unscaled=9.55996004724e-4 vs scaled=0.146894290684, rel_diff=1.527e+02）
```
```
scipy 侧证据：C:\...\scipy\optimize\_numdiff.py:554 `if np.any((x0 < lb) | (x0 > ub)): raise ValueError("`x0` violates bound constraints.")`
              C:\...\scipy\optimize\_lbfgsb_py.py:408-410 `# initial vector must lie within the bounds ... x0 = np.clip(x0, bounds[0], bounds[1])`
p0 恰好贴界的独立测试（span 120 与 span 1 两套）：p0=1e-4/5.0/0.5 全部 OK，无该异常。
```

### 3.4 C1 / C2
```
$ python -X utf8 %TEMP%\phasebc_audit\c1_recorder.py
household state_happiness all NaN: True ; member state_total_income all NaN: True ; any ==0: False
statistics columns ['agent_type','column','n','mean','std','min','max'] ; NaN anywhere: False
forbidden columns present (agent_id/time/alive/str): []
FamilyMember/state_happiness n = 12 (2 members x 6 time points) ; Household/state_total_income n = 6
empty recorder -> columns preserved ; to_csv(path) 默认 == to_dataframe().to_csv(index=False): True（见 final 复测）
level=bogus -> ValueError 未知 level='bogus'，可选：agent / statistics / environment
$ python -X utf8 %TEMP%\phasebc_audit\final_checks.py
rows checked: 13 ; mismatches: 0        # 独立重算 n/mean/std(ddof=0)/min/max
```
```
$ python -X utf8 %TEMP%\phasebc_audit\c2_api.py
POST /api/run steps=20 -> 200 ; GET /api/data -> 200 len(text)=73412
literal 'NaN'/'Infinity'/'-Infinity'/'nan'/'inf' in resp.text: False (all)
strict json.loads (parse_constant raises): OK
Household.state_happiness all null: True ; any 0: False ; Member.state_total_income all null: True
steps=120 同样：len(text)=411084，全部字面量为 False，严格解析 OK
== /api/fit per model ==  square_law 400 / linear_law 400 / influence 400 / wellbeing 200 r2=0.997355 /
   logistic 400 / lotka_volterra 400 / resource_competition 400
```

### 3.5 C3 / C4 / C5
```
$ python -X utf8 %TEMP%\phasebc_audit\c34_diag.py
linear_law mapped to happiness/stress   r2=-3.975634  conv=False at_bounds=['beta']      # 默认边界下的负 R²
wellbeing bounds=(1e-4,1e-3)^5, p0=5.0^5  r2=-4.179674 conv=False
wellbeing bounds=(1e-4,1e-3)^5, p0=5e-4^5 r2=-4.179674 conv=False  # 与 p0 是否越界无关
steps=30  influence r2=0.972875 new_conv=False legacy_conv=True  at_bounds=['gamma']
steps=120 wellbeing r2=0.808294 new_conv=False legacy_conv=True  at_bounds=['p','r','income']
steps=120 influence r2=0.864920 new_conv=False legacy_conv=True  at_bounds=['gamma','delta']
$ python -X utf8 %TEMP%\phasebc_audit\c34b.py
bounds=Bounds(...) [scipy object] -> TypeError: 'Bounds' object is not iterable
params_at_bounds = [] -> test's inner assertion runs: False
$ python -X utf8 %TEMP%\phasebc_audit\hygiene.py %TEMP%\phasebc_audit\old
bounds=Bounds(...) -> OK r2=0.993598219968742 ; fit_global -> OK      # 阶段C前可用的证据
$ python -X utf8 -m pytest tests/test_data_contract.py -v -p mutate_converged -k "converged or sentinel"
test_converged_requires_no_bound_parameters PASSED   test_sentinel_solution_is_flagged FAILED   # 前者空转
$ python -B -X utf8 %TEMP%\phasebc_audit\c5_examples.py "<repo>"        # 只调用导入+拟合，不画图、不写 PNG
import examples/fitting_viz_demo.py -> OK ; run_simulation(120) rows=847
wellbeing  params={p:0.18904, q:1.31102, r:4.68962, s:0.0, income:0.78453} r_squared=0.7980 params_at_bounds=['s']
influence  params={gamma:5.0, delta:0.0} r_squared=-3.8115 params_at_bounds=['gamma','delta']
$ python -B -X utf8 c5_examples.py "<tmp>\old"     -> wellbeing r_squared=0.7855 ; influence r_squared=0.0000（旧版被 max(0,·) 截断）
前端 null→0 偏差复算（TestClient payload，按 dashboard.js:406/483 的公式）:
  state_happiness 渲染序列相对正确成员均值偏低 28.57%（每时点均 28.57%）；state_stress 同为 28.57%
```

---

## 4. 未复现/存疑项

1. **B3(a) 的崩溃**：在 scipy 1.17.1 下用阶段B前代码、缩放关闭代码、以及 web 默认场景（两户五口/120 步，含 `fit_robust`）**均未复现** `ValueError: x0 violates bound constraints`。我不排除它在别的 scipy 版本（`pyproject` 只要求 `>=1.7.0`）或别的数据下存在，但**当前环境下"必崩"不成立**，且代码注释给出的机理与 scipy 源码不符（该异常检查的是 x0 自身，而 `_lbfgsb_py.py:410` 已 clip）。若维护者能在某版本上给出可复现脚本，请附 scipy 版本与完整参数。
2. **`converged=True` 且 `R² ≤ 0` 的真实反例**：在 3 种窗口 × 2 类数据 × 5 个模型的网格里没有找到（因此"阈值条件被删"目前只有计划一致性风险，未观察到实际误导输出）。测试里 `test_sentinel_solution_is_flagged` 的 `fun=0.01 + r_squared=None` 是人工构造。
3. **`examples/fitting_viz_demo.py` 的 `pd` NameError**：本机只有 Python 3.14（PEP 649 惰性注解）故导入通过；对 3.9–3.13 的失败是**代码阅读推断**，未在旧解释器实测。
4. **`_SCALE_THRESHOLD=2.0` 的取值本身**：没有任何测试或文档证明 2.0 是安全阈值；实测 15/30 步也已被缩放（ratios≈15/30），即阈值实际上对几乎所有真实运行都生效。

---

## 5. 放行结论

**不放行（必须先修 3 项 P1）。**

阶段C 的方向性改进是真实的、可验证的：NaN 契约（C1）、`/api/data` 的 null 与无非法字面量（C2）、负 R² 不再被抹平（C3）我都独立复现通过，基线快照与全量测试也没被打破。但阶段B 引入的时间轴缩放属于**改了模型语义却当作数值微调**的改动，并且它的两条验证声明（必崩 / 4e-8）我都无法复现、其中一条明确为假；叠加"前端仍把 null 当 0"与"抽象模型在 API 上无路可走"，当前 HEAD 的对外可见行为比阶段B之前更差。

**放行前必须先修：**
1. **撤销或重构 `_integration_scale`**（`fitter.py:19,147-151,155-156`）。禁止通过改 ODE 时间变量来"修"有限差分；补齐 15/30/120 步下"同参数 `_objective` 对比 + 同数据 `fun/r2/params` 对比"的测试断言，用真实数字替代 `4e-8`/`必崩` 的说法。
2. **修前端 null→0**（`dashboard.js:406`、`:483`）——提交自己引用的 28.6% 偏差就来自这条未改的路径；改完补一个"渲染序列 == 成员子集均值"的断言。
3. **给 `/api/fit` 一条传 `state_mapping` 的路**（`app.py:52-55,162`）或按可映射性收敛模型下拉，否则 6/7 模型在下拉里永远是 400。

**建议同批修（P2）**：`compare_models` 透传 `state_mapping`；恢复 `scipy.optimize.Bounds` 入参支持（`fitter.py:218/250/289`）；把 `test_converged_requires_no_bound_parameters` 改成非空断言场景；`ml/features.py:36,39` 的 `fillna(0)` 按新契约重新设计；清理 `web/app.py:21` 的死导入。
