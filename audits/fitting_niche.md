# fitting + niche 审查报告

审查对象：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`（Python 包 `family_abm`）
审查范围：`family_abm/fitting/{lanchester.py, fitter.py, __init__.py}`、`family_abm/niche/{micro_niche.py, resources.py, influence.py, __init__.py}`
方式：只读代码审查 + 实测数值实验（Python 3.14.3 / numpy 2.4.3 / scipy 1.17.1 / pandas 3.0.2；实验中未修改仓库任何文件）
严重度：P1 = 正确性错误/结论错误；P2 = 设计或健壮性缺陷；P3 = 可读性与小优化

## 0. 前置事实（影响全文核对口径）

- **仓库中不存在 README.md**。`glob **/*.md` 返回空；根目录只有 `examples/`、`family_abm/`、`family_abm.egg-info/`、`requirements.txt`、`setup.py`；`family_abm.egg-info/PKG-INFO` 无 `Description` 字段（PKG-INFO:1-8）。因此本次审查中所有「README 声称」只能对**任务书转述的参数表/API 声称**与**代码 docstring、Web UI（`web/app.py`、`templates/index.html`、`static/js/dashboard.js`）、examples** 进行交叉核对。文档缺失本身记为 **P2（见 P12）**，凡无法在仓库内证实的声称均标注「疑似」。
- 基准数据：120 步 ABM 仿真（2 Household × 5 FamilyMember），`StateRecorder.to_dataframe()` 得 840 行 × 20 列；`time` 取值 1..120（非 0 起），无重复 `(agent_id,time)`。
- 关键数据事实（决定 niche 与拟合结论）：
  - FamilyMember 状态列：`state_health, state_happiness, state_stress, state_energy, state_education, state_income`；**没有** `state_social_capital`（该状态只在 `Household.__init__` 中设置：household.py:20）。
  - 两类 agent 的状态列完全不重叠，各自在对方行上为 NaN（实测 `state_happiness` 非空 600 行且全部是 FamilyMember；`state_total_income/social_capital/savings` 非空 240 行且全部是 Household）。
  - 实测 `state_income` 范围 **0.0 – 0.132**（FamilyMember），`state_stress` 0.257–1.0（饱和），`state_happiness` 0.177–0.654。

## 1. 结论摘要（最关键问题）

1. **P1｜`square_law` 在拟合器默认参数边界内必然指数爆炸，且无任何防护。** 系数矩阵 `[[0,-α],[-β,0]]` 特征值为 `±√(αβ)`，是**不稳定鞍点**；`fit_from_dataframe/fit_robust/fit_global` 的默认边界 `(1e-4, 5.0)` 迫使 `eps1,eps2 ≥ 1e-4 > 0`，只会把不稳定平衡点平移，不会带来自限。实测 `y0=[1.0,0.8], params=[0.3,0.25,0.5,0.4]` → `R1=2.487e13, R2=-2.271e13`；**该拟合仍返回 `success=True`、`fun=602.97`、`R²=0.0`，无任何报错或拒绝**（lanchester.py:9-17, 102；fitter.py:118/149/203）。
2. **P1｜`wellbeing` 的 `p` 与 `income` 严格不可辨识。** 目标函数中两者只以乘积 `p*income` 出现（lanchester.py:52）。实测有限差分雅可比最小奇异值 = **0**（5 参数秩 4），且沿乘积不变方向 `(p,I) = (0.01,100)…(100,0.01)` 目标函数**逐位相同** `9.091023496560e-01`、预测轨迹完全相同。因此 `summary()`/`/api/fit` 展示的 `p`、`income` 数值没有统计意义；R²=0.863 的"好拟合"实际只用 4 个有效自由度。
3. **P1｜失败哨兵 `1e12` 不是目标函数的上界，优化被驱向"积分失败"平台。** 实测合法参数 `alpha=0.3,beta=0.7,eps=0` 的目标函数为 **3.17e44 ≫ 1e12**，因此"求解失败"（1e12）反而优于真实的爆炸解；同时 1e12 平台梯度恒为 0，L-BFGS-B 会原样返回起点并报 `success=True`（fitter.py:86-94）。实测把时间轴加入重复点后：`success=True, fun=1e12, R²=None`（静默错误结论）。
4. **P2｜R² 的定义、选择、报告三者不一致，且无任何过拟合防护。** `_save_result` 用 `max(0.0, 1-ss_res/ss_total)` 截断负 R²（fitter.py:233，实测原始值 **-3.5175 → 报告 0.0**），而 `fit_robust` 用**未截断**的 `r2` 选起点（fitter.py:171），`converged` 又要求 `r_squared > 0.0`（fitter.py:249-254）→ "拟合失败"与"拟合很差"不可区分；R² 为跨状态合并（pooled）而非按状态，全程 in-sample，无参数计数/正则/留出校验。
5. **P2｜默认边界一刀切 + 性能失控。** 所有模型所有参数共用 `(1e-4, 5.0)`（fitter.py:118/149/203），对容量类参数（`K`、`k1/k2`）、目标水平类参数（`target1/target2`）、收入（`income`）量纲全错，并使 `social_influence` 的文档默认 `target2=0.0` **不可达**。性能实测：单次 5 参数 `fit_robust` **44.3 s**（8 起点，120 点、单 agent）；`fit_global` 2 参数 17.2 s，按 DE 实测单次评估 36–46 ms 外推 5 参数、`maxiter=1000` **约 45–57 分钟**（`differential_evolution` 无 `popsize`/`workers`/超时/`maxiter` 暴露，fitter.py:205-208），而 `/api/fit` 是 `async def` 内同步调用（web/app.py:144-165），会阻塞事件循环。
6. **P1/P2｜niche 四维空间实测只有 2 维有效变异，且距离/重叠度公式在合法调用下会算错。** `social` 维度恒为 **1.0**（FamilyMember 无 `social_capital`，NaN 经 `max(0.0,min(1.0,NaN))` 被静默饱和为 1.0，micro_niche.py:17），`economic` 被 `income`(0.001–0.132) 压在低端；跨 5 个 agent 的最终位置标准差 `[0.0555, 0.0552, 0.0000, 0.0272]`，10 组成对 `overlap` 全部落在 **0.900–0.982**（几乎无区分度）。另有：`dimensions` 顺序不同的两个 niche（位置字典完全相同）距离实测 **0.8 而非 0**；维度数不同直接抛 `ValueError`（`(4,)` vs `(2,)` 广播失败）；`Resource.transfer_to` 违反守恒（满容量目标下 1.0+1.0 → 1.5，凭空丢失 0.5）。

## 2. 逐模型数学核对表

| 模型 | 实现方程（含行号） | 声称（任务书转述/仓库内 docstring） | 判定 | 问题 |
|---|---|---|---|---|
| `competition_square_law` / `square_law` | `dR1/dt = -α·R2 + eps1`；`dR2/dt = -β·R1 + eps2`（lanchester.py:16-17） | `dR1/dt=-α·R2, dR2/dt=-β·R1` 类（Lanchester 平方律） | **公式与原版平方律一致（无缺项）；模型不可用于拟合** | 鞍点：`eig=±√(αβ)`（实测 `α=0.3,β=0.25 → ±0.2739`）。`eps>0` 只把不稳定平衡点移到 `(eps2/β, eps1/α)`，不改变不稳定性质；`eps=0` 时实测 `R1: 0.858→1.148e23`、`R2→-1.754e23`，`α=β` 时两分量反向发散到 `±3.19e14`。无正性/上界保护，无 `y≥0` 事件截断。**修复**：加饱和项（如 `-c·R1²` 或 logistic 自限）、或把 `eps` 下界设为 0 并加"轨迹离开 [0,1] 即判无效"的惩罚；否则应从 `MODEL_REGISTRY` 拟合可用集合中移除。 |
| `competition_linear_law` / `linear_law` | `dR1/dt = -α·R1·R2`；`dR2/dt = -β·R1·R2`（lanchester.py:26-27） | "交互驱动竞争"（Lanchester 线性律：损耗 ∝ 双方乘积） | **正确** | 不变式 `R1-(α/β)R2` 实测守恒（漂移 2.2e-16）；但两状态单调衰减到 0（实测 `R2: 0.8→5.3e-5`），**无法表达"竞争胜负"**（无自增长项、无平衡点）。属语义/适用性问题（与 P1-1 同源）。 |
| `social_influence` / `influence` | `dO1/dt = -γ(O1-O2) + δ(target1-O1)`；`dO2/dt = -γ(O2-O1) + δ(target2-O2)`（lanchester.py:38-41） | `dO1/dt = γ(O2-O1)+T1` 类 | **等价改写，但参数语义与声称不同** | `-γ(O1-O2) ≡ γ(O2-O1)` 符号一致；但 `T1` 在实现中不是常数激励，而是松弛项 `δ(target1-O1)`，`target1/target2` 是被拟合的"目标水平"参数而非外生常量。实测 `δ=0` 时均值守恒（漂移 2.2e-16）、`γ=0,δ=0` 时恒定；`γ=0.4,δ=0.2,t=(0.7,0.3)` 终值 `[0.54,0.46]` 与解析平衡解完全一致 → 动力学实现正确。**问题**：4 参数对 2 状态线性系统可辨识（短时雅可比满秩），但**共享单一 γ 是对 ABM 的误配**（happiness 是均值回复、stress 是常数激励+饱和，二者动态不对称），且模型只能单向收敛到唯一稳定平衡 → 无法表达共识/极化双稳态（与 Lead 线索 7 一致）。 |
| `wellbeing_balance` / `wellbeing` | `dH/dt = p·income - q·S·H`；`dS/dt = r·H·(1-S) - s·S`（lanchester.py:52） | 参数表 `p,q,r,s,I`，H/S 两状态 | **参数个数口径一致（第 5 个命名为 `income` 而非 `I`）；数学上有两处硬伤** | (a) **`p` 与 `income` 严格不可辨识**（雅可比第 5 奇异值=0；乘积不变族目标函数逐位相同，见 P2）；(b) **无界**：H 无自限，实测 `[2.0,0.1,5.0,0.01,5.0] → H→100.00`，`[5.0,0.01,5.0,1e-4,5.0] → H→2161.7`，Lead 给 `[1.0,0.2,3.0,0.3,0.8] → H_max=4.0976`（数据 H 上界 0.6537）；H 还可低至 0.038/0（实测 `income=0` 时 H→0）。ABM 侧 H、S 均被 `max(0.0,min(1.0,·))` 硬夹（family_member.py:131/143），模型侧却不夹 → 模型-数据结构性不匹配。 |
| `logistic_growth` / `logistic` | `dP/dt = r·P·(1-P/K)`（lanchester.py:60-61） | 标准 logistic | **正确** | 公式与标准式一致；`K` 是容量却与速率共用 `(1e-4,5.0)` 边界（量纲错配，P7）。`MODEL_STATE_NAMES['logistic']=['population']`（lanchester.py:116）在 ABM 列中不存在（实测 `KeyError: state_population`），只有 Web 自动映射才能跑（且映射错列，见 P10）。 |
| `lotka_volterra` / `lotka_volterra` | `dP/dt = a·P - b·P·Q`；`dQ/dt = c·P·Q - d·Q`（lanchester.py:71-72） | 参数 `a,b,c,d`；社会类比"工作 vs 家庭时间" | **函数形式正确（标准捕食者-被捕食者）；与文档的社会语义脱节** | 参数名与个数与声称一致。但无容量上限：实测 `a=2,b=0.5,c=1.5,d=0.8` 时 `P∈(0.0098,3.0746)`、`Q∈(0.4995,13.7641)`，远超数据 [0,1]；`MODEL_STATE_NAMES` 用 `prey/predator`（lanchester.py:117），"工作 vs 家庭时间"只存在于 docstring，无任何代码/映射体现。 |
| `resource_competition` | `dR1/dt = r1·R1(1-R1/k1) - α·R2`；`dR2/dt = r2·R2(1-R2/k2) - β·R1`（lanchester.py:83-86） | 参数 `r1,k1,r2,k2,α,β` | **与声称一致（含自限项），但交叉项无正性保护** | 参数名/个数与声称完全一致。交叉项 `-α·R2` 未乘 `R1`，是**与自身密度无关的常数抽血**：`R1→0` 时 `dR1/dt = -α·R2 < 0`，实测 `[0.05,0.01,0.05,0.01,2.0,2.0]` 与 `[1e-4,…,5.0,5.0]` 均出现 `R1,R2 = -0.0000`（数值下探为负）。建议改为 `-α·R1·R2`，或在 RHS 加 `max(0,·)`/正性事件。 |
| 求解器 `solve_model` / `_objective` | `solve_ivp(..., method='RK45', rtol=1e-6, atol=1e-8)`（lanchester.py:128-129）；拟合时额外 `max_step=np.diff(t).mean()`（fitter.py:83-85） | 使用 scipy 积分，`t_eval` 与数据时间轴对齐 | **对齐正确；无刚性/发散/负值/重复时间轴处理** | `t_eval=t` 与数据轴逐点对齐（实测 `t=1..120, n=120`），初值取 `y_true[0]`（fitter.py:112/145/199）正确。但：(a) `max_step=mean(diff(t))=1.0` 强制 ≥120 步 → 单次目标函数 11 ms，是 `fit_global` 数十分钟的直接原因；(b) 无 `LSODA/BDF` 回退，爆炸/刚性问题只落到 `success=False`；(c) `t_eval` 不查重，重复时间戳使 `solve_ivp` 抛 `ValueError: Values in t_eval are not properly sorted`，被 `except Exception` 吞掉（见 P4）；(d) 不检查 `sol.y.shape[1]==len(t_eval)`（`solve_model` 只在 `success` 为假时抛错）。 |

## 3. 拟合器发现（ABMFitter）

### P1｜`square_law` 拟合必然发散且被报为成功的参数
- 证据：`lanchester.py:9-17`（方程）、`lanchester.py:102`（默认边界下 eps 恒 > 0）、`fitter.py:118/149/203`（`bounds=[(1e-4,5.0)]*n`）。
- 实测：`solve_model(competition_square_law, [1.0,0.8], t=0..119, [0.3,0.25,0.5,0.4])` → `R1 max=2.4872e13, R2 min=-2.2705e13`；`fit_from_dataframe` 结果 `success=True, fun=602.966, R²=0.0`，参数 `alpha=0.0999, beta=0.0858, eps1=2.5739, eps2=2.4170`（全部贴边）。
- 为什么是问题：`compare_models` / `/api/fit` 会把该结果与正常模型一起返回，调用方若只看 `result.success`（或直接读 `summary()` 的 Params 行）会得到完全错误的结论；模型在数学上是鞍点，对任何正 α、β 都不存在吸引平衡点（除非 y0 恰在稳定流形上）。
- 修复建议：(1) 把 `eps1/eps2` 下界设为 0，并给 RHS 加自限/饱和项；(2) 在目标函数中加入"轨迹有效性"约束——预测状态离开数据合理范围 `[lo,hi]`（可由数据 min/max 外扩得到）即判无效并给**大于任何有限目标函数**的惩罚；(3) 从拟合可选模型集合中移除 `square_law`，改为文档化的"示意用"模型。

### P2｜`wellbeing` 的 `p` 与 `income` 严格不可辨识（报告值无意义）
- 证据：`lanchester.py:52`（`p * income` 只以乘积出现）、`fitter.py:105`（`p0=[0.5]*5`，`n_params=5`）、`fitter.py:302-333`（`make_fitter` 把 `income` 作为自由参数）。
- 实测（Child agent，120 点）：
  - 有限差分雅可比 SVD（在 `[0.3,0.5,0.4,0.2,0.5]`）：`[21.248, 12.846, 0.5817, 0.1795, 0.]` → **σ_min=0，秩 4/5**；在 `[1.0,0.5,0.4,0.2,0.5]` 同样 `σ_min=0`。
  - 乘积不变族（`q,r,s` 固定）：`(p,I)=(0.01,100),(0.1,10),(1,1),(10,0.1),(100,0.01)` → 目标函数**逐位相同** `9.091023496560e-01`，且预测 `H` 范围完全相同 `0.6537..2.7449`。
  - `fit_robust` 的 8 个起点中最优解：`p` 在 `0.0327–4.5679` 间跳变、`income` 在 `0.0317–4.4383` 间跳变，而乘积稳定在 `0.1449`（`q=0.6507, r=0.0515, s=1e-4`），目标函数 3.163e-3。
- 为什么是问题：用户看到的是"拟合出的收入效应参数"，但该数字可由优化器任意选择（乘积才是被识别的量）；`summary_json()`（fitter.py:256-284）与 Web UI 直接展示 `params`，无任何不可辨识性警告。
- 修复建议：(1) 立即：对 `wellbeing` 固定 `income=1.0`（或把 `income` 从 `MODEL_PARAM_NAMES` 移到"外生输入"），只拟合 `p`，并在 docstring/UI 说明 `p` 的含义是"单位收入增益"；(2) 中期：加入可辨识性诊断（数值雅可比 SVD/条件数、相关系数矩阵），当 `σ_min/σ_max < 1e-6` 时在 `summary()` 打警告；(3) 报告参数时给出 profile-likelihood 区间，而不是单点值。

### P3｜失败哨兵 `1e12` 不是上界：优化器被驱向"求解失败"区域
- 证据：`fitter.py:86-87`（`if not sol.success: return 1e12`）、`fitter.py:91-92`（MSE）、`fitter.py:93-94`（`except Exception: return 1e12`）。
- 实测：`_objective([0.3,0.7,0,0]) = 3.1722906133830547e+44 > 1e12`，附近扰动同样量级（3.229e44, 3.287e44）。因此对 `square_law` 这类会爆炸的模型，**求解失败比真实参数"更好"**，优化会被主动推向失败平台；而该平台对参数完全平坦，L-BFGS-B 的有限差分梯度为 0，直接返回起点并报 `success=True`。
- 为什么是问题：产生"成功但无意义"的结果（实测 `success=True, fun=1e12` 的案例），且 `except Exception` 吞掉所有编程错误（含 `t_eval` 重复导致的 `ValueError`）→ 任何 bug 都表现为"拟合成功但参数不变"。
- 修复建议：(1) 把目标函数改为归一化形式（如按各状态方差归一化的 RMSE），使惩罚可设为一个真正上界（如 `1e3`）；(2) 失败时返回 `np.inf`（DE 可处理；L-BFGS-B 需配合 `maxiter` 早停或改用 `scipy.optimize.least_squares` 的 `residual` 接口返回大幅值残差）；(3) **不要**裸 `except Exception`——至少只捕获 `ValueError/RuntimeError` 并把异常信息记入 `fit_result.message`；对时间轴先做 `np.unique` 去重与单调性检查。

### P4｜时间轴重复 → 全部目标函数=1e12，但报 success=True、R²=None
- 证据：`fitter.py:83-85`（`t_eval=t` 未去重）、`fitter.py:93-94`（吞异常）、`fitter.py:48`（`sort_values('time')` 不去重）、`fitter.py:214-237`（`_save_result` 不校验失败）。
- 实测：给单 agent 数据插入一个重复时间戳后，`max_step=mean(diff)=0.9917`（`min diff=0`），`fit_from_dataframe` 返回 `success=True, fun=1.0e12, R²=None`；直接复现根因：`solve_ivp(..., t_eval=<含重复值>)` 抛 `ValueError: Values in t_eval are not properly sorted.`。
- 为什么是问题：静默产出"成功但等于初值"的拟合（负 R² 被截断为 0.0 的同类问题），且 `_validate_data` 只查 NaN/方差，不查时间轴单调唯一。
- 修复建议：在 `_validate_data`/`_extract_*_series` 内 `t = np.unique(t)` 并对 `y` 同步去重（或直接用 `groupby('time').mean()`），同时断言 `np.all(np.diff(t) > 0)` 且 `len(t) >= n_states+1`。

### P5｜R² 截断 + 选择/报告不一致 + 无过拟合防护
- 证据：`fitter.py:233`（`self.r_squared = max(0.0, 1.0 - ss_res/ss_total)`）、`fitter.py:249-254`（`converged` 要求 `r_squared > 0.0`）、`fitter.py:171`（起点选择用未截断 `r2`）、`fitter.py:219-220`（pooled `ss_total`）。
- 实测：故意极差的固定参数拟合 → `fun=0.10446`，报告 `r_squared=0.0`、`converged=False`，而**真实值 `1-ss_res/ss_total = -3.5175`**。另一个用例：`square_law` 的 `fun=602.97 → R²=0.0`，与"恰好等于均值"的模型无法区分。
- 为什么是问题：(a) 负 R² 是有信息量的诊断（模型比均值还差），被抹掉后无法区分"拟合失败/发散"与"拟合等于均值"；(b) `fit_robust` 的择优准则（未截断 R²）与最终报告值不一致，可能出现"报告的 R²=0 但内部按 R²=-5 选中"的情形；(c) `ss_total` 是跨状态合并的 pooled 值，不同量纲状态相互掩盖（实测 happiness 单状态 R²=0.8801、stress=0.8593 尚接近，但这只是巧合——`income`(σ=0.058) 与 `stress`(σ=0.174) 同池时会由大方差状态主导）；(d) 全程 in-sample，5 参数拟 2 状态 × 120 点无任何留出验证或参数计数约束。
- 修复建议：(1) 去掉 `max(0.0, ·)`，直接报告原始 R²，并同时提供 `r2_per_state`、`rmse_per_state`、`aic/bic`；(2) 用**同一个**指标做起点选择与报告（建议用目标函数值，而不是 R²）；(3) 增加 `train_frac`/留出段预测 R²；(4) `converged` 拆分语义：`optimizer_ok`（收敛）与 `fit_acceptable`（如 `r2 > 0.5` 且轨迹有效）。
- 附注（P3）：`ss_total`/`y_mean` 与参数无关，却在 `fit_robust` 的 8 次循环内重复计算（fitter.py:160-161），可移到循环外。

### P6｜一刀切默认边界 `(1e-4, 5.0)` 造成量纲错配与不可达默认值
- 证据：`fitter.py:118`、`fitter.py:149`、`fitter.py:203`；`lanchester.py:101-109`（参数名表）；`lanchester.py:30-31`（`target2` 默认 0.0）。
- 实测/推算：`logistic` 的 `K`（容量，数据量级 0.1–0.3）、`resource_competition` 的 `k1/k2`、`influence` 的 `target1/target2`（水平，而非速率）与 `wellbeing` 的 `income`（ABM 实测 0–0.132）全部被塞进同一 `(1e-4,5.0)`；`social_influence` 文档默认 `target2=0.0` 落在边界外 → 默认行为无法在拟合中重现（实测 influence 拟合给出 `target2=1.2019 > 1.0`，与 ABM stress 上界 1.0 冲突）。examples 里不得不手工覆盖边界（fitting_viz_demo.py:146）。
- 修复建议：把默认边界改为"按参数角色"的表驱动（速率 `(1e-6,10)`、容量 `(eps, 10*max|y|)`、目标水平 `(min(y)-δ, max(y)+δ)`、外生输入固定）；`make_fitter(model, bounds=...)` 暴露显式接口；对 `target2=0.0` 这类默认值提供"可含 0"的边界。

### P7｜`fit_global` 无预算控制、运行时间不可预期；`/api/fit` 阻塞
- 证据：`fitter.py:205-208`（`differential_evolution(..., seed=42, maxiter=1000, tol=1e-8, polish=True)`，无 `popsize`/`workers`/`maxiter` 参数暴露），`fitter.py:83-85`（固定 `max_step`），`web/app.py:144-165`（`async def api_fit` 内同步调用 `fit_robust`）。
- 实测：单次目标函数 11.0 ms（wellbeing，120 点）；`fit_from_dataframe(wellbeing, demo bounds)` 1.60 s（27 迭代）；**`fit_robust(wellbeing, 8 起点, 默认边界)` 44.3 s**（单 agent 120 点；Lead 在 3 成员聚合数据上实测 74.2 s、`/api/fit` 44.9 s，量级一致）；`fit_global(logistic, 2 参数)` 17.2 s（`nfev=1572`，靠 `tol=1e-8` 提前收敛）；用 `maxiter=3, popsize=15, n=5` 实测 `nfev=300, 10.7 s`（35.7 ms/eval）→ 若 DE 不提前收敛，`maxiter=1000` 需 `15×5×1001 = 75075` 次评估 ≈ **2680–3440 s（45–57 分钟）**。
- 为什么是问题：Web 端点 `async def` 里跑 45 s 纯 CPU 循环会阻塞 ASGI 事件循环，期间任何并发请求（包括前端"运行→取数→画图"链路）全部挂起；`fit_global` 则可能占用数十分钟且无法取消/限量。
- 修复建议：(1) 把 `maxiter`/`popsize`/`workers`/`tol` 作为 `fit_global` 参数并设保守默认（如 `popsize=8, maxiter=100, tol=1e-6`）；(2) 搜索阶段用 `rtol=1e-3`、只在最终 polish 用 1e-8（能把单次评估成本降 3–5 倍）；(3) `max_step` 改为 `None` 或仅在检测到数据稀疏时设置；(4) Web 端用 `run_in_threadpool`/`ProcessPoolExecutor`（`await anyio.to_thread.run_sync(...)`）避免阻塞，并加超时与进度反馈；(5) 缓存同一 `(model,t,y0)` 的目标函数调用（DE 会重复评估同一点）。

### P8｜`compare_models` 对 7 个模型中的 6 个不可用（且无法传 `state_mapping`）
- 证据：`fitter.py:336-351`（`make_fitter(name)` 未接收 `state_mapping`；`**fit_kwargs` 被转发给 `fit_robust`/`fit_from_dataframe`）。`fitter.py:302-333`（`state_mapping` 只能进 `make_fitter`）。
- 实测：`make_fitter(name)` 期望的列名——`wellbeing` 命中；`influence→state_O1/state_O2`、`logistic→state_population`、`square_law/linear_law/resource_competition→state_R1/state_R2`、`lotka_volterra→state_prey/state_predator` **全部不存在**。`compare_models(df, ['wellbeing','influence'])` → `KeyError: Column "state_O1" not found`；尝试转发映射 → `TypeError: ABMFitter.fit_from_dataframe() got an unexpected keyword argument 'state_mapping'`。
- 为什么是问题：对外声称的"多模型比较"功能实际只能比较 `wellbeing` 一个模型；且一个模型的异常会中断整批比较（无 per-model 隔离）。
- 修复建议：`compare_models(..., state_mapping=None)` 显式透传给 `make_fitter`；每个模型 `try/except` 记录失败原因并返回带 `error` 字段的结果；返回按 AIC/R² 排序的表。

### P9｜隐式 DataFrame 列名耦合：Web 自动映射会把模型拟合到错误的列
- 证据：`web/app.py:154-161`（`state_cols = [c for c in _sim_df.columns if c.startswith('state_')]`，按位置补映射）；`fitter.py:41-44`（`state_{name}` 约定）；`fitter.py:55-66`（聚合路径）。
- 实测：`logistic` 在 Web 路径被映射到 `state_total_income`（列序第一，Household 变量），**在全体 agent 的聚合数据上"成功"收敛：R²=0.0、r=1.8728、K=4.7536（K 是数据最大值 0.26 的 18 倍）**；`influence` 在 Web 路径被映射到 `{'O1':'state_total_income', 'O2':'state_savings'}`，其中 `state_savings` 方差恒为 **0**，拟合返回 `success=True, R²=0.8778, gamma=1e-4, target2=1e-4`，且 `_validate_data` 的近零方差警告**没有触发**（因 `np.ptp(y,axis=0).max()` 取的是两状态中的最大值）。
- 为什么是问题：UI 会展示一个看起来 R²=0.878 的"好拟合"，而被拟合的量其实是"家庭总收入 vs 储蓄=0"；默认路径无任何列语义校验。另外 6/7 个模型在非 `wellbeing` 场景下的默认行为是 `KeyError: 'state_population'` 这种对用户不友好但至少显式的失败。
- 修复建议：(1) 移除按列位置自动补映射，改为要求显式 `state_mapping`，或在 UI 提供下拉选择；(2) 拟合前校验每个状态列：非全 NaN、方差 > 阈值、agent 类型一致，并在响应中回显"实际使用的列名"；(3) 把 `_validate_data` 的方差检查从 `max(...)` 改为逐状态检查（`np.any`）并为低方差状态单独告警。

### P10｜聚合路径把不同 agent 群体混在一起（Lead 线索 6 的精确化）
- 证据：`fitter.py:55-66`（`df.groupby('time')` 后逐列 `.mean()`）。
- 实测：`state_happiness` 非空 600 行全为 FamilyMember；`state_total_income/social_capital/savings` 非空 240 行全为 Household。pandas `.mean()` 默认跳过 NaN，所以**并不是"把 Household 的 NaN 算进均值"**（这一点对 Lead 线索 6 的措辞是**证伪**）；真实缺陷是：`happiness+stress` 的"population"是 5 个 FamilyMember，而 `social_capital+total_income` 的"population"是 2 个 Household——同一个函数返回的"总体均值"在不同状态上对应不同群体，且当某状态列全为 NaN（或只由单一 agent 类型填充而不想混）时无任何提示；若某状态列在全部行上都缺失，则 `mean` 为 NaN → `_validate_data` 抛 `ValueError: Data contains NaN values.`（实测：用 Household 的 `agent_id` 走 `wellbeing` 即触发），错误信息指向 NaN 而非"该状态列不属于该类 agent"。
- 修复建议：显式区分 `aggregate='population'`（限定 agent 类型/角色）与 `aggregate='household'`；在 `_extract_aggregate_series` 中先筛 `agent_type`，并统计每个状态的实际贡献者数量；错误信息列出缺失列与可用列（`_extract_agent_series` 目前完全没有列校验，`fitter.py:46-53`，只有 `_extract_aggregate_series` 有友好提示，fitter.py:57-59）。

### P11｜`make_fitter(param_fix=...)` 静默忽略拼错的参数名；0 自由参数无保护
- 证据：`fitter.py:309-311`（`for k in param_fix: if k in all_params: all_params.remove(k)`——不在表里的名字被静默保留在 `fixed` 但永不被 `_FixedModel` 使用），`fitter.py:315-329`。
- 实测：`make_fitter('wellbeing', target1=0.5)` → 返回 `param_names=['p','q','r','s','income']`，`target1=0.5` 被静默丢弃（用户以为固定了某参数，实际没有）；当所有参数都被固定时 `n_params=0`，`fit_*` 仍会走到 `minimize`/数据提取阶段（实测在该路径上先撞到 `KeyError`，行为不确定）。
- 修复建议：未知参数名直接 `raise KeyError(f'{k} is not a parameter of {model_name}')`；把 `target1` 这类"输入"与"速率"分类管理；`n_params == 0` 时改为"只评估一次并返回评估结果"的显式分支。

### P12（P2）｜仓库内不存在 README.md，但多处声称以它为文档口径
- 证据：`glob **/*.md` 为空；`family_abm.egg-info/PKG-INFO:1-8` 无 `Description`/`long_description` 字段；`setup.py` 未打包任何文档。
- 为什么是问题：本任务书列出的"7 种模型、参数表 `p,q,r,s,I` / `a,b,c,d` / `r1,k1,r2,k2,α,β`、`fit_robust/fit_global`、四维小生境"等声称在仓库内**无书面来源**，只有代码 docstring 与 Web UI 可作依据；用户/后续维护者按 README 使用时无参照，也无法判断 `income`（第 5 参数）应被当作"待拟合参数"还是"外生输入"（与 P2 直接相关）。
- 修复建议：补一份 README，逐模型给出方程、参数含义与单位、默认/建议边界、`MODEL_STATE_NAMES` 与 ABM 列名的对应表，并显式标注"当前不建议用于拟合的模型"（如 `square_law`）。

### P13（P3）｜其他
- `_extract_agent_series`（fitter.py:46-53）不做列存在性检查，错误信息是 pandas 的 `KeyError`，与聚合路径的友好提示不一致。
- `predict`（fitter.py:241-245）不校验 `t` 单调/`len(t)>=2`，也不校验 `y0` 长度；Web 端还直接访问私有 `_t/_y0`（web/app.py:169-171），私有属性成为事实 API。
- `compare_models` 无结果排序、无失败隔离（见 P8）。
- `summary()`（fitter.py:286-293）不显示参数边界、是否贴边（实测多个最优解落在 `1e-4`/`5.0` 边界上，如 `s=0.0001`、`q=5.0000`），用户无法察觉参数被边界截断；`summary_json()` 也不含 `bounds`、`nit`、`nfev`。
- `fitter.py` 顶部 `import warnings` 的 `warnings.warn`（fitter.py:73-74）是唯一的告警通道，但拟合结束时不汇总任何警告（实测多个发散/贴边拟合 `warnings: []`）。

## 4. niche 发现

### N1（P1）｜`distance_to`/`overlap` 在 `dimensions` 顺序不同或长度不同时给出错误结果/崩溃
- 证据：`micro_niche.py:19-20`（按各自 `self.dimensions` 顺序取向量）、`micro_niche.py:22-34`（`np.linalg.norm(v1-v2)`）、`micro_niche.py:36-38`（`1.0 - dist/np.sqrt(len(self.dimensions))`）。
- 实测：(a) `a=MicroNiche('a',['economic','cultural','social','emotional'])` 与 `c=MicroNiche('c',['emotional','social','cultural','economic'])`，把 `c` 的位置字典设成与 `a` **完全相同** → `a.distance_to(c) = 0.8`（应为 0）、`overlap = 0.6`（应为 1.0）；(b) 4 维 niche 与 2 维 niche → `ValueError: operands could not be broadcast together with shapes (4,) (2,)`；(c) `overlap` 只用 `len(self.dimensions)` 归一，方向性依赖 `self`（长度不同时先崩，长度相同但维度名不同时算错）。
- 为什么是问题：`MicroNiche(dimensions=[...])` 是公开参数，`examples/fitting_viz_demo.py:88-89` 就显式传了 4 维列表；只要两个对象的维度列表不同，距离/重叠度（进而 `resource_exchange_efficiency`、聚类、可视化）就是错的，且不报错。
- 修复建议：在 `distance_to` 开头校验 `self.dimensions == other.dimensions`（顺序敏感可接受，但必须显式报错），或改为按**维度名取交集并按固定排序**构造向量；`overlap` 用 `len(shared_dims)` 或直接改用"每个维度独立的相似度再平均"；`cosine` 返回的是**距离**（`1-cos`），建议更名 `cosine_distance` 或让 `overlap` 显式处理该分支。

### N2（P1）｜`Resource.transfer_to` 违反守恒（目标容量不足时资源凭空消失）
- 证据：`resources.py:12-18`（`add` 受 `capacity` 截断，返回实际加入量但 `transfer_to` 忽略）、`resources.py:20-23`（`remove` 先执行）、`resources.py:25-28`（`removed = self.remove(amount); other.add(removed); return removed`）。
- 实测：`a=EmotionalCapital(1.0)`（容量 1.0，已满）→ `b=EmotionalCapital(1.0)`（已满），`a.transfer_to(b, 0.5)` 返回 0.5，但 `a=0.5, b=1.0`，**总量 1.5，凭空丢失 0.5**（原为 2.0）；`a=0.5 → b=0.9`（容量 1.0）转 0.4：`a=0.1, b=0.9`，总量 1.0（原 1.4），丢失 0.4，返回值 0.4 高估了实际转移量（实际 0.0）。
- 为什么是问题：`transfer_to` 是唯一与"资源分配守恒"相关的原语，其语义（返回 transferred）与行为不符；若后续把它接进 MicroNiche 的资源交换，账目会系统性丢失资源。（当前影响面小：`ResourceBundle`/`transfer_to` 在仓库内**无任何调用方**——`MicroNiche.resources` 恒为 0，见 N4。）
- 修复建议：先算可接收量再扣减，或先 `add` 后按实际加入量 `remove`：
  ```python
  def transfer_to(self, other, amount):
      amount = max(0.0, amount)
      accepted = other.add(amount)      # 目标实际接收
      moved = self.remove(accepted)     # 源实际扣减（应等于 accepted）
      if moved != accepted: other.remove(accepted - moved)  # 回滚差额
      return moved
  ```
  并在 `add/remove` 中拒绝负数量（见 N5）。

### N3（P1/P2）｜`overlap` 公式在"有效维度退化"时失去区分度
- 证据：`micro_niche.py:36-38`（`max(0, 1 - dist/sqrt(len(dimensions)))`）、`micro_niche.py:45-54`（默认映射）、`household.py:20`（`social_capital` 只在 Household 上）。
- 实测（5 个 FamilyMember 的最终位置）：`social` 恒为 **1.0**（FamilyMember 无 `social_capital`，`None/NaN` 经 `min(1.0,NaN)=1.0` 被饱和，`micro_niche.py:17`）、`economic` 仅在 0.0012–0.1194、`cultural` 0.4847–0.6399、`emotional` 0.2075–0.2891；跨 agent 标准差 `[0.0555, 0.0552, 0.0000, 0.0272]`；10 组成对距离 `d∈[0.0366,0.1989]`、`overlap∈[0.9005,0.9817]`，而公式的可用区间是 `[1-√2/2, 1] = [0.293,1]`（真实最大距离只有 √2，因为 2 个维度不参与）。
- 为什么是问题：`overlap` 名义取值 [0,1]，实测恒 >0.90 → 无法区分"高度重叠"与"完全不重叠"，任何基于重叠度的机制（资源交换、聚类、图表）都失去意义；`economic` 与 `social` 两维实为常量，四维空间名义上只有二维信息。
- 修复建议：(1) `update_from_agent_state` 对缺失键显式报错或回退到文档化的默认值（而不是让 NaN 在 `set_position` 里饱和成 1.0）——`set_position` 应先 `if not np.isfinite(value): raise/warn`；(2) 维度归一化改为按**实际方差 > 0 的维度**计算，或先做 min-max/分位数标准化，使 `income`(0–0.13) 与 `happiness`(0–0.65) 可比；(3) 让 FamilyMember 也维护 `social_capital`（或把该维度映射到 `relationship.affection` 的聚合量），否则从 4 维降为 3 维并在文档中标注。

### N4（P1/P2）｜资源模型从不进入 MicroNiche；`resources`/`boundary_permeability` 是死状态
- 证据：`micro_niche.py:12-13`（初始化 `ResourceBundle()` 与全 0.5 的渗透率）、`micro_niche.py:45-54`（`update_from_agent_state` 只改 `position`）、`micro_niche.py:40-43`（`resource_exchange_efficiency` 在仓库内无调用方）。
- 实测：`MicroNiche('x')` 的 `resources.to_dict() == {'economic':0,'cultural':0,'social':0,'emotional':0}`，任意次 `update_from_agent_state` 后仍全 0；`boundary_permeability` 恒为 0.5；`grep` 显示 `resource_exchange_efficiency`/`boundary_permeability` 在 `family_abm/` 与 `examples/` 中除定义/序列化外无调用。
- 为什么是问题："四维社会空间 + 资源分配 + 渗透率"的模型框架只实现了坐标映射，`ResourceBundle`（含 `capacity`）与 `InfluenceRelation` 都没有接进 `MicroNiche`/`Agent`/`Simulation`；Lead 线索 8 的"资源模型从不下发到 MicroNiche"**证实**。
- 修复建议：要么把资源交换接进调度器（`MicroNiche.resource_exchange_efficiency` → `ResourceBundle` 转移 → 回写 agent 状态，并用 N2 修复后的守恒原语），要么删除死代码并在文档中明确 MicroNiche 当前仅为"坐标容器"。

### N5（P2）｜`Resource.add/remove` 接受负数量，破坏非负性与容量约束；`ResourceBundle.get` 静默回退
- 证据：`resources.py:12-18`、`resources.py:20-23`、`resources.py:34-51`（`Cultural/Social/EmotionalCapital` 容量 1.0）、`resources.py:61-68`（`mapping.get(resource_type, self.economic)`）。
- 实测：`EconomicCapital(1.0).add(-5.0) → -4.0`（容量 `inf`，无下界）；`SocialCapital(1.0).remove(-3.0) → 4.0`（容量 1.0 被突破，`remove(-x)` 等价于无上限加）；`CulturalCapital(0.0).add(10.0) → 1.0`（正常封顶）；`ResourceBundle().get('bogus') → economic_capital`（拼错资源类型会静默把操作作用到经济资本上）。
- 为什么是问题：负数量使 `value` 越界（可为负或超容量），会让任何后续守恒/容量推理失效；`get` 的静默回退会把拼写错误变成"改错了资源"。
- 修复建议：`add/remove` 对负数量 `raise ValueError`（或显式提供 `subtract`）；`add` 在 `capacity=inf` 时也保证 `value>=0`；`ResourceBundle.get` 对未知类型 `raise KeyError`（或提供 `get(..., default=None)`）。

### N6（P2/P3）｜`InfluenceRelation` 语义与接口缺陷
- 证据：`influence.py:6-17`（`method` 只在 `__init__` 内硬编码为 `"linear"`，构造函数不暴露）、`influence.py:19-30`（`apply` 内魔数 `0.2`、`0.5`；未识别 `method` 时静默返回副本；`strength` 无界；只改变 target 不改变 source）。
- 实测：`strength=0.5` 线性：`happiness 0.3→0.6`、`stress 0.9→0.5`（同时向源靠拢，但因两状态方向相反，二者被一起拉向"更接近源的中间值"，与 ABM 中 stress 的常数激励+饱和逻辑不一致）；`strength=3.0` 时 `0.1→1.0`（越过源值 0.9 后被 clamp）；`strength=-1 → 0.0`（负强度=排斥，文档未提）；`method='unknown'` → 原样返回；`domain` 字段从未参与计算（`influence.py:11/35`）。
- 为什么是问题：无 `t`/`dt`/双向作用，`apply` 是一次性快照而非动力学（"关系动力学"名不副实）；`method`/阈值/半衰系数不可配置，用户只能改私有属性；`strength` 无界会直接撞到 clamp。
- 修复建议：构造函数暴露 `method`、`threshold`、`rate`；`method` 非法值抛错；`strength` 限制在 `[0,1]` 或显式支持负值并在 docstring 说明；补上互惠项（source 也按比例变化）与 `domain` 过滤；考虑给出与 `social_influence` ODE 一致的离散更新（`Δx = rate*dt*(x_src - x_tgt)`）。

### N7（P3）｜`set_position` 静默夹取 + NaN 饱和
- 证据：`micro_niche.py:15-17`。
- 实测：`max(0.0, min(1.0, float('nan'))) == 1.0`（Python 的 `min(1.0, nan)` 因 `nan < 1.0` 为 False 而返回 1.0）→ NaN 被**静默变成上界 1.0**；`update_from_agent_state({'income':5.0,'education':-3.0,'happiness':nan})` → `{'economic':1.0,'cultural':0.0,'social':0.5,'emotional':1.0}`，无任何告警。
- 为什么是问题：Web/examples 路径（`web/app.py:202-208`、`examples/fitting_viz_demo.py:92-98`、`examples/ml_ready.py:41/80`）正是拿 `state_social_capital`（FamilyMember 行为 NaN）调用它 → `social` 维恒为 1.0（N3 的根因）。
- 修复建议：`if not np.isfinite(value): raise ValueError / warnings.warn` 后再夹取；维度未知时不要静默忽略（当前 `if dimension in self.dimensions` 静默丢弃拼错的维度名）。

## 5. 数值实验记录

环境：`python 3.14.3`（numpy 2.4.3 / scipy 1.17.1 / pandas 3.0.2）；所有脚本写在系统临时目录，**未改动仓库任何文件**（唯一写入是本报告）。

数据构造：2 个 `Household`（Zhang: 3 成员；Li: 2 成员），`Simulation(scheduler=Scheduler('sequential'))` 跑 120 步，`StateRecorder(record_agents=True).to_dataframe()` → 840×20；`time ∈ 1..120`，无重复 `(agent_id,time)`。

| 实验 | 命令/脚本要点 | 关键结果 |
|---|---|---|
| E1 数据 | ABM 120 步 + 列/范围统计 | 840×20；状态列 12 个；`state_income` FM 范围 0–0.132；`social_capital` 只有 Household 有（FM 行全 NaN） |
| E2 数学 | 逐模型积分 + 不变式 | square_law `[0.3,0.7,0,0]`：`R1→1.148e23`、`R2→-1.754e23`（鞍点 `±0.2739`）；linear_law 不变式漂移 2.2e-16，两状态→0；influence 均值守恒、平衡解与解析一致；wellbeing `[2,0.1,5,0.01,5]→H=100.002`、`[5,0.01,5,1e-4,5]→H=2161.7`；resource_competition 出现 `-0.0000` |
| E3 拟合 | `fit_from_dataframe(wellbeing, demo p0/bounds)` | **1.60 s**，`nit=27`，`success=True`，`R²=0.8654`，`fun=3.113e-3`，`warnings=[]`，预测 H∈0.247–0.695（数据 0.177–0.654） |
| E4 多起点 | `fit_robust(wellbeing, 默认边界, 8 起点, seed=42)` | **44.3 s**，`R²=0.8632`，`fun=3.163e-3`，最优解 `p=0.0327, q=0.6507, r=0.0515, s=1.0e-4(贴边), income=4.4383`；8 个起点中 `p∈[0.0327,4.5679]`、`income∈[0.0317,4.4383]` 而乘积稳定在 0.1449；最差/最好目标函数比 2.62 |
| E4c 不可辨识 | 固定乘积改 `(p,income)` | `(0.5,1.0)/(1.0,0.5)/(5.0,0.1)/(0.1,5.0)` → 目标函数**完全相同** 5.494915e-01 |
| E5 性能 | 单次目标函数 + `fit_global` | 单次 11.0 ms；`fit_global(logistic,2)` **17.2 s**（`nfev=1572`，`R²=0.9648`）；DE `maxiter=3,n=5,popsize=15` → `nfev=300, 10.7 s`（35.7 ms/eval）→ `maxiter=1000` 外推 **2683–3442 s（45–57 min）** |
| E6 R² | 好/坏拟合对比 | 好拟合 pooled 0.8654（happiness 0.8801 / stress 0.8593）；坏拟合原始 `1-ss_res/ss_tot=-3.5175` → 报告 **0.0**、`converged=False` |
| E7 哨兵/发散 | `square_law` 目标函数与拟合 | `_objective([0.3,0.7,0,0])=3.172e44 ≫ 1e12`；拟合 `success=True, fun=602.966, R²=0.0`（无告警） |
| E8 耦合 | 缺列/错 agent | `logistic` 默认 → `KeyError: state_population`；`wellbeing` 用 Household id → `ValueError: Data contains NaN values.`；Web 自动映射 `logistic→state_total_income`：`R²=0.0, r=1.8728, K=4.7536`；`influence→{O1:total_income, O2:savings}`：`success=True, R²=0.8778`（savings 方差 0，无警告） |
| E9 时间轴 | 插入重复时间戳 | `success=True, fun=1.0e12, R²=None`；根因 `solve_ivp` → `ValueError: Values in t_eval are not properly sorted.` |
| E10 param_fix | 拼错/全固定 | `make_fitter('wellbeing', target1=0.5)` 静默忽略；`n_params=0` 无专门分支 |
| N1 niche NaN | 真实 5 agent 映射 | `social` 恒 1.0；`economic` 0.0012–0.1194 |
| N2 overlap | 10 组两两 | `d∈[0.0366,0.1989]`、`overlap∈[0.9005,0.9817]`；对称性成立 |
| N3 维度 | 置换/不同长度 | 位置字典相同但维度顺序不同 → `d=0.8`（应 0）；4 维 vs 2 维 → `ValueError`；未知 metric 静默回退 euclidean |
| N4 资源 | `transfer_to` | 满→满转 0.5：总量 2.0→1.5（丢 0.5）；`add(-5)→-4.0`；`remove(-3)→4.0`（超容量）；`get('bogus')→economic` |
| N5 influence | `apply` 行为 | `method='unknown'` 原样返回；`strength=3` → clamp 到 1.0；`strength=-1` → 0.0；target 未被就地修改 |
| N6 耦合 | `MicroNiche` 字段 | `resources` 恒 0、`boundary_permeability` 恒 0.5、`resource_exchange_efficiency` 无调用方 |

### 5.1 Lead 线索逐条核验（证实/证伪）

| # | Lead 线索 | 结论 | 证据与实测 |
|---|---|---|---|
| 1 | `square_law` 在 `[1e-4,5]` 内数值爆炸；`params=[0.3,0.25,0.5,0.4], y0=[1.0,0.8]` → R1=2.49e13、R2=-2.27e13；eps 常激励且无自限/无下界；核对 eps 可辨识性 | **证实（数值逐位复现）**；eps 可辨识性：**形式满秩但实用上不可用** | 复现 `R1=2.4872e13, R2=-2.2705e13`。机理：`lanchester.py:16-17` 的系数矩阵 `[[0,-α],[-β,0]]` 特征值 `±√(αβ)=±0.2739`（不稳定鞍点）；`eps1/eps2`（:17）只把平衡点平移到 `(eps2/β, eps1/α)`，不改变不稳定性质，且拟合边界（fitter.py:118/149/203）把 eps 下界钉在 `1e-4>0`。可辨识性实测：`[α,β,eps1,eps2]` 雅可比 SVD 在 `[0.3,0.25,0,0]` 为 `[246.8,27.7,7.35,1.67]`（σ_min/σ_max=6.75e-3，满秩）、在 `[0.3,0.25,0.5,0.4]` 为 `[58.0,20.1,1.22,0.23]`（3.95e-3）→ **秩为 4，不存在严格零空间**，但条件数 10²–10³、且爆炸后残差完全由增长模主导，拟合出的 eps 无可解释性。判定：不可辨识性不是主要问题，**模型结构性发散**才是。 |
| 2 | `wellbeing` 的 `p`、`income` 只以乘积出现；实测 `p=income=0.0001`（下界）也能给 R²=0.984；单/多起点 `(p,income)` 分别 (0.1274,0.1274)/(0.0302,0.5381)，乘积相近 | **机制证实（严格）**；`R²=0.984` 的具体数值**未复现**（属数据/设置相关），但"不同 `(p,income)` 给出近似相同拟合质量"在新数据上成立 | `lanchester.py:52` 只出现 `p*income`。雅可比 SVD（5 参数）最小奇异值 = **0**（两个测试点均如此，σ_min/σ_max≈1e-10/1.6e-17）= 严格秩亏；乘积不变族 `(0.01,100)…(100,0.01)` 目标函数**逐位相同** `9.091023496560e-01`。我个人数据上：把 `p=income=1e-4`（乘积 1e-8）固定、只拟合 `q,r,s` → `R²=0.7770`（vs 拟合乘积 0.145 时的 0.8632）；`(p,I)=(0.1274,0.1274)` 与 `(0.0302,0.5381)` 目标函数 1.6589e-1 / 1.6582e-1（差 0.05%）。 |
| 3 | `:233` 把负 R² 截断为 0，而 `converged` 要求 R²>0（:249-254）；`fit_robust` 用未截断 r2 选起点（:171），与报告不一致 | **证实** | 代码行号准确：fitter.py:233、249-254、171。实测原始 R² `-3.5175` → 报告 `0.0`、`converged=False`；`fit_robust` 内 `r2`（:171）不截断而 `_save_result`（:233）截断 → 二者不是同一指标。 |
| 4 | 无界 ODE：`wellbeing [1.0,0.2,3.0,0.3,0.8]` → H=4.098，可低至 0.038；所有模型无非负/上界约束 | **证实** | 实测 `H_max=4.0976, H_min=0.6537`（与 4.098 一致），数据 H 上界 0.6537；另测 `[2,0.1,5,0.01,5]→H=100.002`、`[5,0.01,5,1e-4,5]→H=2161.7`。`lanchester.py` 全部 RHS 无非负/上界夹取，`fitter.py` 无轨迹范围校验；ABM 侧却夹取（family_member.py:131/143）。 |
| 5 | 默认边界 `(1e-4,5.0)` 一刀切，对 K、k1/k2、target1/target2 量纲不合适 | **证实** | fitter.py:118/149/203；参数角色见 lanchester.py:101-109。实测后果：`logistic` 拟合出 `K=4.7536`（数据最大 0.26）；`influence` 拟合出 `target2=1.2019>1.0`，而文档默认 `target2=0.0`（lanchester.py:31）落在边界外不可达。 |
| 6 | 默认走全体 agent 时间均值（fitter.py:55-66），"会把 Household 的 NaN 状态算进均值"；性能 74.2 s / 6.8 s / 44.9 s | **性能证实；"NaN 进均值"证伪（措辞需修正）**，真实缺陷是群体混合 | pandas `.mean()` 默认 `skipna=True`：`state_happiness` 非空 600 行全为 FamilyMember、`state_total_income/social_capital` 非空 240 行全为 Household，故 NaN 不会进入均值；实际是"每个状态列的总体 = 拥有该列的 agent 子集"，`happiness+stress` 的总体是 5 个 FamilyMember，`social_capital+total_income` 的总体是 2 个 Household（实测该路径返回 social=0.5 恒定、total_income 0→0.26）。我方实测 `fit_robust(wellbeing,8 起点)=44.3 s`、单起点 1.60 s，与 Lead 的 44.9 s/74.2 s 同量级（差异来自数据规模/机器）。 |
| 7 | `linear_law`/`square_law` 无自增长项，实测单调衰减到 ~0；`social_influence` 恒收敛到固定 target，无法表现共识/极化 | **`linear_law` 证实；`square_law` 证伪（是发散而非衰减）；`social_influence` 证实** | linear_law：`R2: 0.8→5.31e-5`、不变式守恒 → 确实只能单调衰减。square_law：`eps=0,α=0.3,β=0.7` 时 `R1: 0.858→1.148e23`、`R2→-1.754e23`；`α=β=0.3` 时 `R1→3.19e14, R2→-3.19e14` → **并非衰减到 0，而是鞍点发散**（其中一侧穿过 0 后反向增长）。influence：实测平衡 `[0.54,0.46]` 与解析解完全一致，线性系统只有唯一稳定平衡 → 无共识/极化双稳态。 |
| 8 | niche 维度退化：`social` 恒 1.0、`economic` 被 income(≈0.008–0.13) 压缩、跨 agent 标准差 `[0.054,0.165,0.000,0.014]`；资源从不下发（resources 恒 0） | **证实**（标准差数值不同：我的数据为 `[0.0555,0.0552,0.0000,0.0272]`，语义一致） | `social` 恒 1.0（`household.py:20` 只有 Household 有该状态 → FM 行为 NaN → `micro_niche.py:17` 的 `min(1.0,NaN)=1.0`）；`economic` 实测 0.0012–0.1194；位置均值 `[0.0734,0.5687,1.0,0.2543]`、标准差 `[0.0555,0.0552,0.0000,0.0272]`；`MicroNiche.resources` 恒全 0、`boundary_permeability` 恒 0.5、`resource_exchange_efficiency` 无调用方。 |
| 9 | `resources.py:12-23` 接受负数量（`add(-3)` 变负、`remove(-5)` 变大）；`ResourceBundle.get()` 对未知 key 静默回退 economic | **证实** | `resources.py:12-18/20-23`；实测 `add(-5.0)→-4.0`、`remove(-3.0)→4.0`（容量 1.0 被突破）、`ResourceBundle().get('bogus')→economic_capital`；附加发现 `transfer_to`（:25-28）不守恒（满→满丢 0.5/2.0）。 |

## 6. 建议改进（按收益排序）

1. **给 ODE 目标函数加"轨迹有效性"约束与统一次优惩罚（收益最高，一次性修掉 P1-3/P3）**：在 `_objective`（fitter.py:78-94）中先检查 `np.all(np.isfinite(y_pred))` 与 `y_pred` 是否落在数据可行域 `[lo-δ, hi+δ]`（`lo/hi` 由 `y_true` 的 min/max 外扩），越界即返回**可证明大于任何有限目标的上界**（改成按方差归一化的 RMSE 后取 `1e3`），并删掉裸 `except Exception`（改为捕获 `ValueError/RuntimeError` 并记录原因）。这同时消除"1e12 被 3e44 击败"和"失败平台梯度为 0"两个静默错误。
2. **修掉 `square_law` 的结构性发散（P1-1）**：`eps1/eps2` 下界改 0；给 RHS 加自限项或正性事件；若不做，则把该模型从拟合可用集合中移除，并在 `MODEL_REGISTRY` 旁标注"仅示意"。
3. **消除 `wellbeing` 的 `p*income` 不可辨识（P1-2）**：把 `income` 从可拟合参数改为固定外生输入（`p` 表示单位收入增益），或对 `p*income` 做重参数化；在 `summary_json()` 加入数值雅可比 SVD/条件数，秩亏时明确警告；报告参数时附 profile 区间。
4. **修正 R² 体系（P2-5）**：去掉 `max(0.0, ·)`（fitter.py:233），补 `r2_per_state`/`rmse_per_state`/AIC/BIC 与留出段 R²；起点选择改用目标函数值；把 `converged` 拆成 `optimizer_ok` 与 `fit_acceptable`；把 `ss_total` 移出 8 次循环。
5. **重做默认边界与模型-列映射（P2-6/P9/P10）**：按参数角色给默认边界（速率/容量/目标水平/外生输入）；`compare_models` 透传 `state_mapping` 并做 per-model 隔离；移除 Web 端"按列位置自动补映射"，改为显式选择 + 拟合前逐状态列校验（非全 NaN、方差阈值、agent 类型一致），并把实际使用的列名回显给用户。
6. **修 niche 的距离/重叠与维度语义（P1-N1/N3）**：`distance_to` 校验 `dimensions` 一致或按名取交集；`overlap` 用实际有效维度归一并在维度标准化后计算；`set_position` 对非有限值报错而非饱和；补上 FamilyMember 的 `social_capital`（或把 `social` 维改为关系网络的聚合量）；把 `economic` 做尺度归一（income 0–0.13 → 分位数映射到 [0,1]）。
7. **修资源守恒与输入校验（P1-N2、P2-N5）**：按"先看目标能接收多少、再扣源"的顺序实现 `transfer_to`（或失败回滚），`add/remove` 拒绝负数量，`ResourceBundle.get` 对未知 key 报错；随后决定是否把资源交换真正接进调度器，否则删除 `resource_exchange_efficiency`/`boundary_permeability` 等死代码。
8. **控制运行时间与解耦 Web（P2-P7）**：`fit_global` 暴露 `popsize/maxiter/tol/workers` 并设保守默认；搜索阶段放宽容差（rtol 1e-3）仅在 polish 收紧；Web 端把拟合放到线程池并加超时；`_objective` 增加同点缓存。
9. **补齐文档（P2-P12）**：仓库内没有 README；建议补一份 `README.md`，写明每个模型的方程、参数含义/单位/默认边界、`MODEL_STATE_NAMES` 与 ABM 列的对应关系、以及"哪些模型当前不建议用于拟合"。
10. **清理 P3 项**：`make_fitter` 未知参数名报错；`_extract_agent_series` 列校验与友好错误；`InfluenceRelation` 暴露 `method/threshold/rate` 并校验取值；`distance_to` 未知 metric 报错；`summary()` 显示边界与贴边状态、`nit/nfev`。

---
审查者：`fit-niche-auditor`（只读审查；唯一写入文件为本报告）。所有结论均可由第 5 节列出的实测命令/脚本复现。
