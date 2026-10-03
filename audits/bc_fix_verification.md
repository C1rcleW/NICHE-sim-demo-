# 阶段 B/C 修复验证报告

- **验证对象**：`15a8294` `fix(fitting,web): 落实阶段B/C审计意见——撤销错误的时间轴缩放等 3 项 P1`（HEAD）
- **仓库**：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`（验证期间 `git status --short` 为空，仓库零改动）
- **环境**：Python 3.14.3 / numpy 2.4.3 / scipy 1.17.1 / pandas 3.0.2 / fastapi 0.136.1 / httpx 0.28.1 / Node v24.14.0
- **方法**：只读仓库；全部实验在 `%TEMP%\bcfix_verify\` 下的仓库副本中进行（`base/`＝HEAD；`mut_scale/`＝把缩放机制按阶段B原样加回；`mut_js/`＝把 `r[col] || 0` 加回；`baselinechk/`＝基线快照检查）。**未运行 examples 绘图路径，未在仓库根做 build。**
- **默认立场**：先假设修复为假/不完整，逐项做突变与反证实验。

---

## 1. 判定汇总表

| 项 | 判定 | 我的实测 | 原审计要求 | 差异 |
|---|---|---|---|---|
| **F1 时间轴缩放已撤销且未复活** | **已修复** | `fitter.py` 全文无 `_integration_scale`/`_SCALE_THRESHOLD`（`:144-160` 的 `_solve` 直接 `solve_ivp(rhs,[t[0],t[-1]],y0,t_eval=t,..., max_step=mean(diff(t)))`，与"原样 t 积分"**逐位相等**）；合成 logistic(r=.35,K=1.2,t=0..119) 恢复 **r=0.349999、K=1.200000、R²=1.000000**；把缩放按阶段B原机制加回后 120 步恢复 **r=5.0（贴上界）、R²=-5.3405**，提交自带判别测试 `test_long_horizon_fit_recovers_known_parameters` 在突变体上 **FAILED**、在 HEAD 上 PASSED | 撤销 `_integration_scale`/`_SCALE_THRESHOLD`；t_eval/max_step 用原始 t；r 恢复接近真值；缩放加回则退化 | 承诺兑现。唯一差异：我**复现不出**提交信息里"120 步 R² 0.9661→0.7065、240 步 0.9390→-0.1377"的精确数字。我在真实 ABM 数据（seed=0、两户五口、n_starts=8）上实测是 **0.9714→0.8172（聚合）/ 0.9756→0.5615（agent）**；合成 logistic 上退化幅度是 **1.0000→-5.3405**。**退化本身确凿存在，幅度/数字与提交不一致** |
| **F2 前端零填充已消除且不会复活** | **已修复** | `dashboard.js` 时序图 `:439-444`、拟合图 `:535-539` 均为 null 检查+跳过；正则扫描全文件仅 `:270`（参数输入）与 `:470-471`（niche 坐标兜底）命中 `\|\| 0`，都不是缺失值语义。真实 payload（两户五口、steps=40、287 行）在 **Node 里逐字复刻新旧两套逻辑**：旧逻辑对成员列（5 成员/7 行）**每时点偏低 28.5714%**（Household 列 2/7 偏低 71.4286%），新逻辑与"仅拥有该列的 agent 子集均值"**逐点完全一致**（12/12 列）；把 `|| 0` 加回后 `test_frontend_does_not_coerce_null_to_zero` **FAILED**，HEAD 上 PASSED | 消除 `r[col]\|\|0`；旧逻辑约 -28.6%、新逻辑 == 成员子集均值；扫描测试必须真的能失败 | 承诺兑现，无差异。补注：`state_income`/`state_total_income` 因参考序列起点为 0 而无法用相对差表示，我按其原始定义用绝对差核对过，新逻辑仍逐点一致 |
| **F3 抽象模型在 Web 上确实可用** | **部分修复** | 机制全部就位（`app.py:52-59` `FitRequest.state_mapping`、`:156-182` `/api/models` 返回 `directly_fittable`+`suggested_mapping`、`dashboard.js:390-395/500` 会发 `state_mapping`）。**逐模型实测：7 个中用 suggested_mapping 有 6 个返回 200，`resource_competition` 返回 500 `RuntimeError: All fitting attempts failed.`**（`robust=False` 时 `fun=1e12`、`hit_sentinel=True`；同一数据换成 `fit_global`（differential_evolution）则 R²=0.9695 —— 是 L-BFGS-B 路径整体失败，与选哪两列无关） | 7 个模型用 suggested_mapping 都返回 200（不再永久 400）；R² 合理；下拉与映射无冲突 | **未达"7/7 都 200"**。另：`suggested_mapping` 是把模型状态**按字母序**映射到前 N 个 `state_` 列，第一列 `state_cultural_level` 是 **Household 专属常量列（ptp=0）**，导致多数抽象模型被喂到常量/无意义列：`logistic` 得 **R²=0.0 且 converged=True**（前端显示"Converged 是"），`square_law`/`linear_law` 得 R²=-2.3e5/-4.4。**这正是 `fitter.py:61-62` 注释声称已消灭的"拟到方差为 0 的列上"**，只是从"静默猜列"换成了"API 建议的路" |
| **额外：`converged` 新语义** | **已修复（但 UI 未同步）** | 6 个 seed × wellbeing 聚合 fit_robust：R²=0.96421、`converged=True`、`at_bounds=[]`，**无一例高 R² 被误判未收敛**；`params_at_bounds`/`hit_sentinel` 只在 `summary_json`/`summary()` 里作为告警出现。**但 `dashboard.js` 全文没有 `params_at_bounds`/`hit_sentinel`（出现 0 次），`fitKPIs` 只渲染 R² 和 Converged** → 用户会看到"R²=-227526.5905 / Converged 是"而没有任何告警 | 高 R² 不得误判；贴边只作告警出现在 summary/UI | summary 侧达成、**UI 侧未达成**；且"converged"现在纯粹是"优化器自报成功"，与"拟合可用"脱钩（见 §3-3） |
| **额外：`scipy.optimize.Bounds` 入参** | **已修复** | `fit_from_dataframe`/`fit_robust`/`fit_global` 三处均可传 `Bounds(lb=...,ub=...)`，标量 `Bounds` 亦可用，`summary_json()['bounds']` 正常输出；错长 `Bounds(3)` 报 `ValueError`（由 scipy 抛出，文字可读） | 恢复 Bounds 支持 | 承诺兑现。小缺口：标量 `Bounds` 与错长 `Bounds` 无专门单测 |
| **额外：`compare_models.state_mappings`** | **部分修复** | 正常使用可用（`{wellbeing:0.96421, square_law:-55206.5}`，`_resolved_columns` 正确落地）；未请求的模型 → `ValueError: state_mappings 含有未请求的模型`；缺映射/部分映射 → 带可用列与建议的 `ValueError`；旧式 `state_mapping=` → `TypeError`。**但一个模型拟合失败会直接抛异常终止整批**（`fitter.py:497-503` 无 try/except），未实现审计建议的"逐模型返回错误字段" | 支持映射 + 错误处理合理 | "支持"达成，"错误处理"未达：`compare_models(df,[...,'resource_competition'],robust=True,...)` 会因 `RuntimeError` 整批失败 |
| **额外：测试与卫生** | **通过** | `python -X utf8 -m pytest tests/ -q -rs` → **44 passed in 122.95s，0 skip**（httpx 已装，两个 `importorskip` API 测试真的执行了）；`tools/baseline.py --check` → `[OK] 与基线一致`，exit 0；`node --check dashboard.js` → exit 0；`git status --short` → 空（本报告写入前） | 全绿、无 skip、无空转测试 | 2 个关键测试做了突变实验：F1 判别测试 **真会失败**；F2 扫描测试 **真会失败**。但 `test_converged_is_false_when_parameters_are_pinned_at_bounds` 两半里有一半是弱断言（见 §4-3） |

### 结论一句话

**三项 P1 的"删除/改写"动作都是真的、且都有突变实验证明不会悄悄复活（F1、F2 判定已修复）；F3 的机制是通了，但 `resource_competition` 仍然 500、`suggested_mapping` 会把模型指向常量列并给出"Converged 是 / R²=0.0"的误导性结论，因此 F3 只算部分修复。**

---

## 2. 反证实验记录

### 2.1 F1：缩放删除 + 语义验证 + 缩放加回

**命令与输出（HEAD 副本）**
```
$ python -X utf8 %TEMP%\bcfix_verify\f1_semantics.py %TEMP%\bcfix_verify\base
== _integration_scale 存在: False
== _SCALE_THRESHOLD 存在: False
== _solve 源码中的缩放痕迹: 'scale'->False  'span'->False  '/ '->False  't_scaled'->False
真值      r=0.35  K=1.2
恢复值    r=0.349999  K=1.200000
r 相对误差 = 0.000%      K 相对误差 = 0.000%
R^2 = 1.0000000000   converged=True  at_bounds=[]
>>> [通过] 恢复 r 在真值 15% 内（时间轴未被缩放）
```
```
$ python -X utf8 %TEMP%\bcfix_verify\f1_logistic_grid.py <base>
steps= 120 span=  119  r=0.349999 K=1.200000 fun=5.725118e-13 R2=1.000000 conv=True at_bounds=[]
steps= 240 span=  239  r=0.350000 K=1.199998 fun=2.746400e-12 R2=1.000000 conv=True at_bounds=[]
```

**逐位等价（`_solve` vs 独立实现的"原样 t 积分"）**
```
$ python -X utf8 %TEMP%\bcfix_verify\final_checks.py %TEMP%\bcfix_verify\base
_solve 与"原样 t + max_step=mean(diff(t))"逐位相等: True
时间轴被压缩到 [0,1] 会得到: True      # 说明两者确实不同，不是退化比较
```
（注：`_solve` 的 `step = mean(diff(t))` 在缩放与不缩放两种写法里都是同一个公式，因此**缩放阈值与 `max_step` 的交互不能靠"步长补偿"抵消**——我据此论证"缩放不可能被 max_step 悄悄中和"。）

**缩放加回（阶段B原机制：`_SCALE_THRESHOLD=2.0` + `_integration_scale` + `t_scaled`）**
```
$ python -X utf8 %TEMP%\bcfix_verify\f1_semantics.py %TEMP%\bcfix_verify\mut_scale
恢复值    r=5.000000  K=5.000000
r 相对误差 = 1328.571%      K 相对误差 = 316.667%
R^2 = -5.3405449168   converged=True  at_bounds=['r', 'K']
>>> [失败] 恢复 r 在真值 15% 内（时间轴未被缩放）
```
```
$ python -X utf8 %TEMP%\bcfix_verify\f1_logistic_grid.py <mut_scale>
steps= 120 span=  119  r=5.000000 K=5.000000 fun=1.088904e+00 R2=-5.340545 conv=True at_bounds=['r','K']
steps= 240 span=  239  r=5.000000 K=5.000000 fun=1.230570e+00 R2=-11.733596 conv=True at_bounds=['r','K']
```
**提交自带判别测试在突变体上的行为（这是"修复不会复活"的最强证据）**
```
$ pytest mut_scale/tests/test_simulation_and_fitting.py::test_long_horizon_fit_recovers_known_parameters -q
E       AssertionError: 恢复的 r=5.0 与真值 0.35 偏差过大——时间轴可能被缩放
E       assert np.float64(5.0) == 0.35 ± 0.0525
1 failed in 4.37s
$ pytest base/tests/...::test_long_horizon_fit_recovers_known_parameters -q
1 passed in 3.57s
```

**真实 ABM 数据（Web 默认两户五口、steps=120、seed=0、n_starts=8、seed=42）**
```
$ python -X utf8 %TEMP%\bcfix_verify\f1_abm_regression.py <base> 120
  aggregate fit_robust  : success=True fun=3.6533573576e-04 R2=0.9713510429 conv=True at_bounds=[]
  agent     fit_robust  : success=True fun=4.8928035028e-04 R2=0.9755643964 conv=True at_bounds=[]
  aggregate single-start: success=True fun=3.6533573568e-04 R2=0.9713510430 conv=True at_bounds=[]

$ python -X utf8 %TEMP%\bcfix_verify\f1_abm_regression.py <mut_scale> 120
  aggregate fit_robust  : success=True fun=2.3308806774e-03 R2=0.8172166205 conv=True at_bounds=['p','q','r','s']
  agent     fit_robust  : success=True fun=8.7810436994e-03 R2=0.5614577559 conv=True at_bounds=['q','r','s']
  aggregate single-start: success=True fun=3.0606298750e-03 R2=0.7599910295 conv=True at_bounds=['r','s']
```
> **无法复现项（如实报告）**：提交信息称"steps=120 缩放 R²=0.7065 vs 撤销 0.9661；steps=240 缩放 -0.1377 vs 撤销 0.9390"。我用**相同调用路径与相同规模**（两户五口、n_starts=8）得到的对应数字是 **0.9714 vs 0.8172**；合成 logistic 上退化是 **1.0000 vs -5.3405**。退化方向、机制（速率参数被迫乘窗口长度、参数贴上界）、以及"撤销后能恢复真值"三者都被我独立证实，但**具体两位小数的数字与提交不符**。我判断差异来自随机种子/数据实例（提交未给 seed），不构成"修复为假"，但**提交里写死的这几个数字不应被当作可复现证据引用**。

### 2.2 F2：正则扫描 + Node 复算 + 扫描测试突变

```
$ grep -n "\|\| *0\b" base/family_abm/web/static/js/dashboard.js
270: params[inp.dataset.param] = parseFloat(inp.value) || 0;     # 合法：输入框解析兜底
441: // 用 `|| 0` 会把"不存在"伪造成 0 ...（注释）
470: x: res.niches.map(n => n.position.economic || 0),          # 合法：niche 坐标兜底
471: y: res.niches.map(n => n.position.social || 0),
# 时序图(旧 :406)、拟合图(旧 :483)的 `r[col] || 0` 已消失
```

**真实 payload 在 Node 里逐字复刻新旧逻辑（`/api/run steps=40`，287 行 × 20 列，两户五口）**
```
$ node f2_aggregate.js payload.json
  state_health               owners/time=5/7 旧逻辑偏差 mean=-28.5714% (每时点一致=true) 新逻辑==参考=true
  state_happiness            owners/time=5/7 旧逻辑偏差 mean=-28.5714% (每时点一致=true) 新逻辑==参考=true
  state_stress               owners/time=5/7 旧逻辑偏差 mean=-28.5714% (每时点一致=true) 新逻辑==参考=true
  state_energy / state_education                同样 -28.5714%
  state_housing_quality 等 6 个 Household 列     旧逻辑偏差 -71.4286%
  ...
最差旧逻辑偏差: state_housing_quality = -71.4286%
理论 1 - 5/7 = 28.5714%
全 null 列混入后 traces 数=12（无异常抛出）；traces 数>0 时 Plotly 正常渲染
```
新逻辑与参考的逐点一致性是 **12/12 列**；旧逻辑偏差是**每个时点恒定**的 28.5714%（不是平均出来的近似值），因此这就是一个乘性稀释因子，与审计给的 28.6% 完全同一个数。

**patchwork / 全 null 列是否会画空图而不报错 —— 判断：不会崩，会退化成"暂无数据"提示**
- `buildTimeSeries`（`dashboard.js:436-455`）：`if (!t.length) return null;` → `.filter(Boolean)`；若**所有**列都全 null，`traces.length===0` → `Plotly.purge` + 显示 `charts.no_data` 文案。
- `buildFitChart`（`:532-547`）：`if (!t.length) return;` 直接跳过该列；只有全部列都空才会 `Plotly.newPlot('chartFit', [])`（画一张空图）。
- 现状下所有 `state_` 列都至少有一个非 null 时点，所以实际不会触发空图路径。
- **但我实测一个真实隐患**：`state_cultural_level` 只被 Household 拥有（605/847 为 null、按 time 聚合 ptp=0），`/api/models` 的 `suggested_mapping` 第一个就指向它。前端按"过滤 null 后取均值"拿到的是 2 户常量 0.5 序列——**服务端 groupby.mean 跳过 NaN 得到同一条序列，所以前端拟合图与拟合目标是自洽的**；问题不在前端，在"建议映射指向常量列"（见 §3-2）。

**扫描测试是否真会失败（突变实验）**
```
$ python apply_js_mutant.py   # 只改 TEMP 副本，把两处 push 改回 push(r[col] || 0)
   440: byTime[r.time].push(r[col] || 0);
   532: byTime[r.time].push(r[col] || 0);
$ pytest mut_js/tests/test_data_contract.py::test_frontend_does_not_coerce_null_to_zero -q
E       AssertionError: 发现把缺失值当 0 的写法（应改为 null 检查）：['byTime[r.time].push(r[col] || 0);', 'byTime[r.time].push(r[col] || 0);']
1 failed in 3.77s
$ pytest base/tests/test_data_contract.py::test_frontend_does_not_coerce_null_to_zero -q
1 passed in 3.80s
$ node --check mut_js/.../dashboard.js   -> exit 0     # 突变体语法合法，不是因为语法错才失败
```
> 该测试的正则 `r"\[[A-Za-z_$][\w$]*\]\s*\|\|\s*0\b"` **只**命中"变量下标 + `|| 0`"，实测不会误报 `params[inp.dataset.param] = ... || 0`、`n.position.economic || 0` 与 `byTime[r.time] || []`（后者是 `|| []` 不是 `|| 0`）。判定：**这条扫描测试有效，不是恒真测试。**

### 2.3 F3：7 模型逐个实测

```
$ python -X utf8 %TEMP%\bcfix_verify\f3_models.py <base>       # steps=120, robust=True
POST /api/run -> 200 {'steps':120,'agents':7,'observations':847}
available_state_columns = [cultural_level, education, energy, happiness, health,
                           housing_quality, income, neighborhood_quality, savings,
                           social_capital, stress, total_income]  （均带 state_ 前缀）
  square_law            directly_fittable=False -> 200 R2=0.960095  conv=True  at_bounds=['beta','eps1']  (49.3s)
  linear_law            directly_fittable=False -> 200 R2=-4.05968  conv=True  at_bounds=['alpha','beta'] (4.7s)
  influence             directly_fittable=False -> 200 R2=0.979737  conv=True  at_bounds=['target2']     (55.3s)
  wellbeing             directly_fittable=True  -> 200 R2=0.96911   conv=True  at_bounds=[]              (84.8s)
  logistic              directly_fittable=False -> 200 R2=0.0       conv=True  at_bounds=[]              (1.7s)
  lotka_volterra        directly_fittable=False -> 200 R2=0.98579   conv=True  at_bounds=['a']           (83.4s)
  resource_competition  -> 500 {"error":"RuntimeError: All fitting attempts failed."}
```
```
$ python -X utf8 %TEMP%\bcfix_verify\f3_variance.py <base>     # 同上数据，robust=False（快）
  square_law            success=True fun=643.2   R2=-227526.590507 conv=True  sentinel=False
  linear_law            success=True fun=0.01527 R2=-4.402769      conv=True  sentinel=False
  influence             success=True fun=8.22e-4 R2=0.709192       conv=True  sentinel=False
  wellbeing             success=True fun=2.185e-5 R2=0.992271      conv=True  sentinel=False
  logistic              success=True fun=0       R2=0.0            conv=True  sentinel=False
  lotka_volterra        success=True fun=6.797e-4 R2=0.75956       conv=True  sentinel=False
  resource_competition  success=True fun=1e+12   R2=None   conv=False sentinel=True   ← fun=SENTINEL，不是真拟合
```
**`suggested_mapping` 指向的列（按字母序取前 N 个 `state_` 列）**
```
  square_law/linear_law/influence/lotka_volterra/resource_competition
        -> {'..1': 'state_cultural_level', '..2': 'state_education'}
  wellbeing -> {'happiness': 'state_cultural_level', 'stress': 'state_education'}
  logistic  -> {'population': 'state_cultural_level'}
各列按 time 聚合的 ptp: state_cultural_level=0, state_housing_quality=0,
  state_neighborhood_quality=0, state_savings=0, state_social_capital=0（均为 Household 专属常量列）
  state_education=0.261, state_happiness=0.378, state_stress=0.579, state_health=0.680（成员列，健康）
```

**`resource_competition` 500 的根因隔离**
```
$ python -X utf8 %TEMP%\bcfix_verify\f3_rc.py <base>
A. 建议映射（第一列常量）: robust=False -> success=True fun=1e+12 R2=None sentinel=True
                          robust=True  -> RuntimeError: All fitting attempts failed.
B. 换成两个真实变化列(state_happiness/state_stress):
                          robust=False -> fun=1e+12 R2=None sentinel=True
                          robust=True  -> RuntimeError: All fitting attempts failed.
                          fit_global   -> success=True fun=3.889e-04 R2=0.9695022215 conv=True sentinel=False
C. steps=30 也一样失败（两种映射都 fun=1e+12）
```
→ 结论：**与选列无关**。`resource_competition` 在默认边界 (1e-4,5.0) + L-BFGS-B 下，解会发散（`r*(1-R/K)` 在 R<0 时指数增长），`_solve`/MSE 返回哨兵 1e12，于是 8 次多起点全部退化，`fit_robust` 抛 RuntimeError → `/api/fit` 的 `except Exception` 包成 **500**。换成 `fit_global`（differential_evolution）能成功且 R²=0.9695。**Web 端只走 L-BFGS-B，所以这个模型在界面/API 上仍然不可用。**

**B. `Bounds` 入参 / `compare_models`**
```
$ python -X utf8 %TEMP%\bcfix_verify\extras.py <base>
E1. fit_from_dataframe  OK  bounds=[(0.0001,5.0)]*5  R2=0.964210
    fit_robust          OK  R2=0.964210   summary.bounds=[[0.0001,5.0]]*5
    fit_global          OK  R2=0.964210
    scalar Bounds       OK  bounds=[(0.0001,5.0)]*5
    错长 Bounds(3)      ValueError: The number of bounds is not compatible with the length of `x0`.   ← 非本库抛
    混合 list 入参       OK
E2. compare_models 正常使用 OK: {'wellbeing': 0.96421, 'square_law': -55206.536166}
    未请求的模型 -> ValueError: state_mappings 含有未请求的模型：['square_law']
    缺映射       -> ValueError（第一条行）: 模型状态 ['R1','R2'] 找不到对应数据列。
    部分映射     -> ValueError（第一条行）: 模型状态 ['R2'] 找不到对应数据列。
    旧式 state_mapping= -> TypeError: ABMFitter.fit_from_dataframe() got an unexpected keyword argument 'state_mapping'
```
**C. `converged` 多 seed 与告警呈现**
```
E3. wellbeing 聚合 fit_robust（seed=0..5）：全部 R2=0.96421 converged=True at_bounds=[]
    高 R² 却被判未收敛的 seed: 无                       ← 原 C4 的假阴性已消除
    反例：square_law R2=-55206.536166 converged=True ；linear_law R2=-9.808944 converged=True
    summary() 输出（influence 映射到 happiness/stress）：
      R^2: 0.949414 / Converged: True / 参数被边界钉住: ['gamma']（该方向不可辨识或边界不合适）
      warnings raised during fit: []                    ← 告警走 summary 字符串，不走 warnings 通道
```

**D. 前端管线（下拉 / 竞态 / UI 告警）**
```
$ python -X utf8 %TEMP%\bcfix_verify\final_checks.py <base>
index.html:90  <select id="fitModel">{% for m in models %}<option value="{{m}}">{{m}}</option>{% endfor %}</select>
服务端渲染 option: ['square_law','linear_law','influence','wellbeing','logistic','lotka_volterra','resource_competition']
是否等于全部 MODEL_REGISTRY 键: True
modelInfo 未加载时点拟合（state_mapping=null）:
  square_law -> 400  模型状态 ['R1','R2'] 找不到对应数据列。
  logistic   -> 400  模型状态 ['population'] 找不到对应数据列。
  wellbeing  -> 200
loadModelInfo(): sel.innerHTML = options.join(''); 若 wellbeing 可直接拟合则 sel.value='wellbeing'
fitKPIs 模板: 只有 r_squared 与 converged 两个 KPI
是否包含 params_at_bounds / hit_sentinel: False
dashboard.js 全文出现 params_at_bounds 次数: 0
```

**E. 全量测试 / 基线 / 卫生**
```
$ cd %TEMP%\bcfix_verify\base && python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
............................................                             [100%]
44 passed in 122.95s (0:02:02)
$ python -X utf8 tools/baseline.py --check baseline/default_seed42.json
[OK] 与基线一致：baseline\default_seed42.json        baseline exit=0
$ node --check family_abm/web/static/js/dashboard.js -> exit 0
$ git status --short -> （空；仅本报告为唯一新增写入）
```

---

## 3. 新引入的问题

1. **`/api/models` 的 `suggested_mapping` 会主动把抽象模型指向常量列，制造"像模像样的假拟合"（新引入的误导路径）**
   `app.py:171-172` 用 `available_states[i]` 按字母序取前 N 列；第一列 `state_cultural_level` 是 Household 专属、按 time 恒定 0.5 的列（ptp=0）。结果：`logistic` 拟合一条常数 → `ss_total==0` → `_r_squared` 返回 **0.0**，且 `converged=True`，前端并排显示 **"R²=0.0000 / Converged 是"**；`square_law` R² 可达 **-2.3e5**。旧行为是 400（诚实但不可用），新行为是 200 + 误导性结论。`fitter.py:61-62` 与 `app.py:194-195` 的注释都在讲"禁止拟到方差为 0 的列上"，而建议映射恰好这么做了。**建议**：`suggested_mapping` 排除 ptp≈0 的列并标注"该模型无可直接对应的状态列"，或按 `agent_type` 优先成员列。

2. **`resource_competition` 在 Web 上仍然不可用（500）**
   见 §2.3。若"7 个模型都能用"是 F3 的验收面，则未达成；若只要求"传映射不再永久 400"，则部分达成。**建议**：`/api/fit` 对 `RuntimeError('All fitting attempts failed.')` 返回 400 + 可操作提示（或对多起点全失败自动回退 `fit_global`），并把"哨兵解"明确报告为"未获得有效拟合"而不是 500。

3. **`converged=True` 与"拟合可用"脱钩，且 UI 不显示任何区分信息**
   `converged` 现在只等于"`result.success` 且 `fun` 未到哨兵 且 R² 有限"。实测 `square_law` 的 `R²=-227526.5905` 与 `logistic` 的 `R²=0.0` 都报 `converged=True`；而 `dashboard.js` 完全不渲染 `params_at_bounds`/`hit_sentinel`（出现 0 次），用户只能看到"Converged 是"。**建议**：前端把 `params_at_bounds`/`hit_sentinel` 作为告警徽标展示（JSON 已经在返回了，只差 UI），或在 R²≤0 时把 `converged` 显示为"优化器收敛（拟合不可用）"。

4. **`compare_models` 仍是"一损俱损"**
   单模型失败即抛异常终止整批（`fitter.py:497-503`），审计建议的"逐模型 try/except + 错误字段"未实现。实测 `compare_models(df, [...,'resource_competition'], robust=True, ...)` 直接 `RuntimeError`。

5. **小回归/健壮性**：错长 `scipy.optimize.Bounds` 的校验缺失（`_normalize_bounds` 只对 list 分支做 `len(pairs)!=n` 检查，`Bounds` 分支把校验交给 scipy，报错文案不可控）；`loadModelInfo()` 每次 run 后 `sel.innerHTML` 重建下拉，会把用户此前选中的抽象模型重置为 `wellbeing`。

---

## 4. 未复现 / 存疑项

1. **提交信息中的精确数字无法复现**：`steps=120 缩放 0.7065 vs 撤销 0.9661`、`steps=240 -0.1377 vs 0.9390`。我实测（两户五口、seed=0、n_starts=8）为 `0.9714 vs 0.8172`；合成 logistic 为 `1.0000 vs -5.3405`。**方向一致、数值不一致**，疑因提交未固定随机种子/数据实例。我未把"数字不符"判为修复为假，但建议提交补上可复现脚本与 seed。
2. **`square_law` 的 R² 极不稳定**：同一数据同一映射，`robust=False` 得 R²=-227526.6，`robust=True`（多起点）得 R²=0.960095；换映射为 happiness/stress 又得 -55206.5。数值发散（`RuntimeWarning: overflow encountered in square`）来自模型本身在默认边界下的爆炸，属**既有模型脆弱性**，非本次修复引入，我未深挖。
3. **`test_converged_is_false_when_parameters_are_pinned_at_bounds` 的第一半是弱断言**：`fitter.py:360-380` 的 `converged` **根本不读** `_parameters_at_bounds`，所以"把参数钉在下界"对 `converged` 没有任何因果作用；测试第一半构造的是 `success=False` 且 `r_squared` 仍为 `None`，`converged=False` 同时由两个条件成立导致，**"参数贴边"这一条并未被真正检验**（该测试名与 docstring 有过度宣称）。第二半（成功+贴边+高 R² → True）是有效断言。相对地，`test_long_horizon_fit_recovers_known_parameters` 与 `test_frontend_does_not_coerce_null_to_zero` 经突变实验证明**确实有判别力**。
4. **F2 的"新逻辑 == 成员子集均值"在单 agent 选择下未被原审计要求覆盖**：我实测 `buildFitChart` 先按 `agent_id` 过滤再按列过滤 null，与服务端按 agent 拟合`_extract_agent_series`（该 agent 每个时点恰好 1 行、非 null）一致，因此**不存在"图与拟合目标错位"**；此处未发现新问题，仅记录已核。
5. `_objective_hit_sentinel()` 用 `fun >= 1e12` 判定哨兵：若某个模型的真实 MSE 恰好 ≥1e12 会被误判（极端量纲下可能）。本环境 7 模型实测未触发该歧义（哨兵案例的 `fun` 都精确等于 1e12）。

---

## 5. 放行结论

**有条件放行。**

三项 P1 的修复动作**都是真的、可复现、且经突变实验证明不会被悄悄改回**：

- **F1 已修复**——`_integration_scale`/`_SCALE_THRESHOLD` 从代码中消失，`_solve` 与"原样 t 积分"逐位一致，已知参数 (r=0.35,K=1.2) 在 120/240 步都被恢复到 6 位有效数字；把缩放按阶段B原机制加回后，提交自带的判别测试立刻失败（r=5.0 / R²=-5.34）。**这是本次最扎实的一项。**
- **F2 已修复**——两处 `r[col] || 0` 已改为 null 检查+跳过，真实 payload 上旧逻辑每时点恒定偏低 28.5714%（与审计引用同一个数），新逻辑与成员子集均值逐点一致；扫描测试对 `|| 0` 突变真会失败。**"不会复活"有测试兜底。**
- **F3 部分修复**——`/api/models`、`FitRequest.state_mapping`、前端 `currentStateMapping()` 三者串通了，7 个模型中 6 个能返回 200。**但 `resource_competition` 仍然 500；`suggested_mapping` 会指向零方差 Household 列，导致 `logistic` 给出"R²=0.0 / Converged 是"、`square_law` 给出 R²=-2.3e5 的误导性结论。**

**放行前必须先修（按优先级）**

1. **`/api/fit` 对"多起点全部失败/哨兵解"不要返回 500**（`app.py:221-225` + `fitter.py:259-260`）：至少转成 400 + 可操作提示，或对 `resource_competition` 这类模型回退 `fit_global`。当前实测：`resource_competition` + `suggested_mapping` → **HTTP 500**，F3 的"7 个模型都能用"未达成。
2. **`/api/models` 的 `suggested_mapping` 必须排除零方差列**（`app.py:171-172`，可用 `_sim_df.groupby('time')[col].mean().ptp()` 过滤），并显式标注"该模型在 ABM 里没有语义可对应的状态列"。否则前端一键拟合会把抽象模型喂给常量列，产出"Converged 是 / R²=0.0"这类比 400 更糟的误导输出。
3. **前端展示 `params_at_bounds` / `hit_sentinel` 告警**（`dashboard.js:507-514`，`dashboard.js` 目前对这两个字段出现 0 次）。`summary_json` 已经在返回它们，只差 UI；否则"贴边只作告警"在用户可见层面并不存在。

**可同批修的次要项**：`compare_models` 逐模型 try/except（`fitter.py:497-503`）；`Bounds` 分支补长度校验（`fitter.py:302-309`）；修正 `test_converged_is_false_when_parameters_are_pinned_at_bounds` 的名称/docstring 使其与实际断言一致（或补一条真正依赖 `params_at_bounds` 的断言）；提交信息里的 `0.7065/0.9661/-0.1377/0.9390` 换成带 seed 可复现的脚本与数字（我实测为 `0.8172/0.9714`，合成 logistic 为 `-5.34/1.0000`）。
