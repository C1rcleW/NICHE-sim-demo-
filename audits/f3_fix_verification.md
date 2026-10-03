# F3 修复验证报告

- **验证对象**：`3c6b16f` `fix(web): 落实 B/C 复核意见——建议映射排除零方差列、失败路径返回 400、告警可见`（HEAD）
- **上一轮报告**：`audits/bc_fix_verification.md`（对 `15a8294` 的复核，提出 3 项必须先修）
- **仓库**：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`（`git log --oneline -3` 确认 HEAD 为 `3c6b16f`；验证期间仓库 `git status --short` 在写入本报告前为空）
- **环境**：Python 3.14.3 / numpy 2.4.3 / scipy 1.17.1 / pandas 3.0.2 / fastapi 0.136.1 / httpx 0.28.1 / Node v24.14.0
- **方法**：**只读仓库**；全部实验在 `%TEMP%\f3verify\` 下的仓库副本中进行（`base/`＝HEAD 副本；`mutsort/`＝把 `/api/models` 恢复成"按字母序取前 N 列"的完全回退突变体；`mutsuggest/`＝保留 usable/constant 分类键但建议映射重新按字母序取全部列的"半吊子"突变体）。脚本全部写在 `%TEMP%\f3verify\scripts\`，**未在仓库根产生任何文件，未运行 examples 绘图路径**。
- **默认立场**：先认定修复为假/不完整，逐项做独立复算、构造场景与突变实验。

---

## 1. 判定汇总表

| 项 | 判定 | 我的实测 | 要求 | 差异 |
|---|---|---|---|---|
| **G1 `/api/models` 的 suggested_mapping 已排除零方差列** | **已修复（附 1 项判据缺口）** | ① 真实 payload（`/api/run steps=20`，147 行×20 列）独立复算：12/12 列分类与 `usable_state_columns`/`constant_state_columns` 一致（pooled dropna 跨度 **和** fitter 真实目标 `groupby('time').mean()` 跨度两种判据都与 payload 相同）；两集合互斥且并集=全部 `state_` 列；`available_state_columns == usable+constant`；7 个模型 `suggested_mapping` 全部落在 usable 内，**违规 0 项**。② 构造"只剩 1 个有变化 `state_` 列而模型需 2 个状态"：`needs_manual_mapping=True` 且 `suggested_mapping=None`（7 个模型中对 6 个需要 2 状态的全部成立；logistic 只需 1 状态仍给出建议）——**该标志真的会 True，不是只在正常场景看到 False**。③ 反向实验：完全回退突变体上 `logistic` 建议映射变回 `state_cultural_level`，`/api/fit` 复现 **200 + R²=0.0 + converged=True**（robust 真/假都是）；半吊子突变体上自带测试 **FAILED**（`square_law 的建议映射包含零方差列 state_cultural_level`） | 建议映射不含常量列；划分正确（自算跨度、注意 NaN 与成员/户主子集）；候选不足时 `needs_manual_mapping=True` 且建议为空；去掉修复逻辑能复现 R²=0.0 且仓库测试 FAIL | 要求全部达成。**但判据本身与拟合目标不等价**（`app.py:171-174` 用"全表 dropna 后的 min/max"而非复核建议的 `groupby('time')[col].mean().ptp()`）：我构造出"每户各自恒定、跨户不同"的数据，pooled 跨度 0.2 被判 usable，而 fitter 实际目标恒为 0.6（span=0），`/api/fit` 返回 **200 + R²=-9.6e14 + converged=True** —— 同一类误导输出仍可复现（见 §2.2-C、§3-4）；`directly_fittable` 模型完全不参与方差判据（见 §2.2-D） |
| **G2 `/api/fit` 失败路径返回 400 而非 500** | **已修复（附 1 项过宽捕获）** | 真实代码路径 + 最小桩实测：哨兵解（把 `ABMFitter._objective` 钉成 `1e12`，其余全真）→ **400 `model_not_applicable`**，带 `summary.hit_sentinel=True`；`fit_robust` 真抛 RuntimeError（把 `_solve` 桩成 None，让真实多起点全部失败）→ **400 `all_starts_failed`**；`TypeError`/`KeyError` → **500**（未被吞）；无映射 logistic → 400（`ValueError` 分支，不带 status）；端到端 `resource_competition` + 新建议映射 → **400**（上一轮实测为 500） | 哨兵→400+model_not_applicable；RuntimeError→400+all_starts_failed；未知异常仍 500；不依赖"某模型必然失败"；检查 except 顺序与类型是否过宽 | 三项断言全部达成，端到端 500→400 确认。**副作用**：新增的 `except RuntimeError` 过宽——拟合成功后 `fitter.predict()`（`fitter.py:353` / `solve_model`）抛的 RuntimeError 也被改写成"多起点拟合全部失败"的 400 并丢弃 `summary`（实测 §2.4-6）；未知模型名仍 500（KeyError） |
| **G3 拟合告警在 UI 可见** | **部分修复** | 真实 `dashboard.js` 在 Node vm 沙箱里跑：① i18n 4 个新键（`mapping_suffix`/`manual_suffix`/`warn_sentinel`/`warn_bounds`）**中英两个字典都在**（zh 80 键 == en 80 键，无单边缺失），各被 `t()` 引用 1 次，`{0}` 占位替换有效，中文渲染文本正确；`.fit-warning` 样式存在（`style.css:66-70`）。② `params_at_bounds` **真的渲染**：返回 `params_at_bounds:['r1','k1']` 的 200 响应 → `#fitKPIs` 里出现 `<div class="fit-warning">⚠ 参数被边界钉住：r1, k1（…）</div>`。③ `hit_sentinel` 代码存在（`dashboard.js:522`）且单独喂 200 响应时能渲染中文哨兵告警——**但真实管线中不可达**：`/api/fit` 只要 `hit_sentinel` 为真就返回 400（`app.py:223-232`），而 `runFitting` 在 `dashboard.js:514` 对任何 `res.error` 提前 return，`#fitKPIs` 内容为空字符串。④ `currentStateMapping` 在 `needs_manual_mapping` 时返回 `undefined`，`runFitting` 拒绝发请求并提示（fetch 调用数 = 0）。⑤ `modelInfo` 未加载时返回 `null` → **静默降级**：照发不带 `state_mapping` 的请求，最终显示服务端 400 文本 | 读取并渲染 `params_at_bounds` 与 `hit_sentinel`；中英键都存在且被引用；`.fit-warning` 存在；`needs_manual_mapping` 时返回 undefined 且拒绝发请求；说明 modelInfo 未加载时是否静默降级 | **`hit_sentinel` 告警条在真实管线中永远不会被渲染**（与本次新增的 400 语义自相矛盾），这一半只算"代码在，效果不在"；`modelInfo` 未加载确实静默降级（靠服务端 400 兜底）；`needs_manual_mapping` 虽拒绝发请求，但**界面没有任何手工指定映射的入口**（`index.html` 全文无 mapping 输入），用户对该模型彻底无法拟合（死路）。另发现既有崩溃：`dashboard.js:565` `TypeError: t is not a function`（见 §3-5） |
| 额外：`_sim_df` 为空/1 行/全 NaN 时 `/api/models` 健壮性 | **通过** | 未 run（`_sim_df=None`）→ 200，`usable=[] constant=[]`，所有模型 `suggested_mapping=None`、`needs_manual_mapping=True`；只有 1 行 → 200，该列判 constant；全 NaN 列 → 200，判 constant（`len(series)` 守卫生效）；`time` 为 NaN → 200；完全空表 → 200；`/api/fit` 未 run → 400。**全程无异常** | 不抛异常 | 无差异。仅提示：该端点对"尚未 run"返回 200 + 全空列表（前端 `loadModelInfo` 只在 run 之后调用，实际不触发） |
| 额外：阈值 `1e-9` 是否合理 | **部分合理（量纲盲）** | `span=1e-12` → constant；`span=1e-8` → usable。但 `[1e6]*9+[1e6+1e-8]`（相对变化 1e-14）也判 **usable** —— 绝对阈值对量纲不敏感；且与 fitter 自己的近零方差告警阈值 `np.ptp < 1e-5`（`fitter.py:139`）不一致（1e-9 与 1e-5 之间是"端点说 usable、fitter 说 may be unreliable"的灰带） | 说明分类行为 | 当前 ABM 各列跨度要么精确 0，要么 ≥1e-2，灰带未被真实数据触发；属潜在缺陷 |
| 额外：新增测试质量 | **基本有效，有 1 处弱断言 + 1 处覆盖缺口** | 5 个相关测试在 HEAD 全 PASS；`test_api_models_excludes_constant_columns_from_suggestions` 经**两种突变体**证明有判别力（完全回退→KeyError FAILED；半吊子回退→AssertionError FAILED）。**但全仓库测试里 `needs_manual_mapping` 出现 0 次** —— G1 要求的"候选不足"场景无任何测试覆盖（我本次是外部构造验证的）。`test_web_fit_maps_*` 两个桩测试只验证"若 `summary_json` 说 hit_sentinel 则 400"，**绕过了真实的 `_objective_hit_sentinel()`**，检测逻辑坏掉它们也不会失败（我用真实 `ABMFitter`+只桩 `_objective` 补做了该集成验证）。`test_api_fit_returns_400_when_all_starts_fail` 恰恰依赖"resource_competition 必然失败"（提交信息自己说不必靠这个），且只断言 `status ∈ {两个值}`，偏弱 | 无弱断言/恒真断言；测试名与断言一致 | 无恒真测试；`test_converged_reflects_optimizer_state_not_bound_hits` 更名后名实相符（新增 `_parameters_at_bounds(...) == param_names` 是真断言）。提交信息称"新增 3 项"，实际新增 **4 项**（44→48） |
| 额外：测试/卫生 | **通过** | `python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider` → **48 passed in 86.41s，0 skip**（`-rs` 未列出任何 skip）；`node --check dashboard.js` → exit 0；`tools/baseline.py --check baseline/default_seed42.json` → `[OK] 与基线一致` exit 0；仓库 `git status --short` → 空（本报告写入前） | 全绿、无 skip | 与提交声明一致 |

### 结论一句话

**G2 是三项里兑现得最干净的一项（端到端 500→400 已复现、确定性与异常边界都正确，只是 `except RuntimeError` 过宽）；G1 的要求在真实数据与"候选不足"构造场景下全部达成、且经两种突变体证明自带测试有判别力，但判据（全表 pooled min/max）与被拟合目标（`groupby('time').mean()`）不等价，我构造出了仍能返回"200 + converged=True + 离谱 R²"的路径；G3 只兑现了一半——`params_at_bounds` 真的可见，`hit_sentinel` 告警条被本提交新增的 400 语义挡死、在真实管线中永不渲染。**

---

## 2. 反证 / 突变实验记录

所有脚本位于 `%TEMP%\f3verify\scripts\`，仓库副本 `base`＝HEAD `3c6b16f`。

### 2.1 G1：真实 payload 的独立复算

```
$ python -X utf8 %TEMP%\f3verify\scripts\g1_independent.py %TEMP%\f3verify\base 20
family_abm from: C:\Users\asus\AppData\Local\Temp\f3verify\base\family_abm\__init__.py
POST /api/run -> 200
data shape: (147, 20) cols: [...]
column                           n_nonNull    pooled_span   aggmean_span  payload    my_pooled
state_cultural_level                  42      0.000e+00      0.000e+00  constant   constant
state_education                      105      5.122e-01      8.612e-02  usable     usable
state_energy                         105      2.176e-01      3.426e-02  usable     usable
state_happiness                      105      2.303e-01      5.662e-02  usable     usable
state_health                         105      2.960e-01      1.246e-01  usable     usable
state_housing_quality                 42      0.000e+00      0.000e+00  constant   constant
state_income                         105      1.217e-01      6.836e-02  usable     usable
state_neighborhood_quality            42      0.000e+00      0.000e+00  constant   constant
state_savings                         42      0.000e+00      0.000e+00  constant   constant
state_social_capital                  42      0.000e+00      0.000e+00  constant   constant
state_stress                         105      5.992e-01      4.172e-01  usable     usable
state_total_income                    42      2.353e-01      1.709e-01  usable     usable

分类划分检查:
  usable ∩ constant = set()
  usable ∪ constant == 全部 state_ 列: True
  available_state_columns == usable+constant: True
  我按 pooled dropna span 复算的不一致列: 无
  我按 fitter 真实目标(groupby time mean) span 复算的不一致列: 无

逐模型 suggested_mapping 检查:
  square_law             directly=False needs_manual=False missing=['R1', 'R2']       suggestion={'R1': 'state_education', 'R2': 'state_energy'}
  linear_law             directly=False needs_manual=False missing=['R1', 'R2']       suggestion={'R1': 'state_education', 'R2': 'state_energy'}
  influence              directly=False needs_manual=False missing=['O1', 'O2']       suggestion={'O1': 'state_education', 'O2': 'state_energy'}
  wellbeing              directly=True  needs_manual=False missing=[]                 suggestion={'happiness': 'state_happiness', 'stress': 'state_stress'}
  logistic               directly=False needs_manual=False missing=['population']     suggestion={'population': 'state_education'}
  lotka_volterra         directly=False needs_manual=False missing=['prey', 'predator'] suggestion={'prey': 'state_education', 'predator': 'state_energy'}
  resource_competition   directly=False needs_manual=False missing=['R1', 'R2']       suggestion={'R1': 'state_education', 'R2': 'state_energy'}
  违规: 无
```

NaN / Household-成员子集差异已按 `dropna()` 语义处理：成员列的 42 个 Household 行（`state_*` 为 NaN）被剔除，`state_total_income` 等 Household 专属列的 105 个成员行被剔除；`aggmean` 用 `df.groupby('time')[col].mean()`（pandas 跳过 NaN）与 fitter `_extract_aggregate_series`（`fitter.py:124-132`）逐字同义。

### 2.2 G1：构造场景（含"候选不足"必测项）

```
$ python -X utf8 %TEMP%\f3verify\scripts\g1_construct.py %TEMP%\f3verify\base

=== A: 仅 1 个 usable 列，模型需要 2 个状态 (rows=40) ===
  usable  : ['state_happiness']
  constant: ['state_cultural_level']
    square_law             directly=False needs_manual=True  suggestion=None
    linear_law             directly=False needs_manual=True  suggestion=None
    influence              directly=False needs_manual=True  suggestion=None
    wellbeing              directly=False needs_manual=True  suggestion=None
    logistic               directly=False needs_manual=False suggestion={'population': 'state_happiness'}
    lotka_volterra         directly=False needs_manual=True  suggestion=None
    resource_competition   directly=False needs_manual=True  suggestion=None
  [断言] 需要 2 状态的模型 needs_manual_mapping 全为 True: True
  [断言] 这些模型 suggested_mapping 全为 None/空: True

--- 用 A 的建议映射直接调 /api/fit（logistic）---
(400, {'error': "模型状态 ['population'] 找不到对应数据列。… 请显式传入 state_mapping（示意，需按语义核对）：{'population': 'state_cultural_level'} …"})

=== C: 每户内部恒定、但跨户不同 (pooled span=0.2, 按 time 均值 span=0) (rows=60) ===
  usable  : ['state_housing_quality']        constant: []
  logistic  suggestion = {'population': 'state_housing_quality'}
  [关键] 拟合器实际目标 groupby(time).mean() 的 span = 0.0
  [关键] 是否被 /api/models 判为 usable -> True
  [关键] /api/fit(logistic, 建议映射) -> 200
        r_squared= -962406869313826.8  converged= True  hit_sentinel= False  fun= 1.186e-17

=== D: wellbeing 的期望列存在但都是常量 (rows=40) ===
  usable  : []      constant: ['state_happiness', 'state_stress']
    wellbeing  directly=True  needs_manual=False suggestion={'happiness': 'state_happiness', 'stress': 'state_stress'}
  [关键] /api/fit(wellbeing) -> 200
        r_squared= 0.0  converged= True

=== E1: 尚未 run（_sim_df=None）=== 200  usable: []  constant: []
  suggested 全为 None: True     needs_manual 全为 True: True     /api/fit -> 400
=== E2: 只有 1 行 === 200 ['state_x'] []
=== E3: 全 NaN 列 === 200 usable: [] constant: ['state_x']
=== E4: time 为 NaN === 200 []
=== E5: 完全空表 === 200 usable: [] constant: []

=== F: 阈值边界（绝对阈值 1e-9）===
  state_tiny     span=1e-12 -> constant
  state_small    span=1e-08 -> usable
  state_huge     span=1e-08 -> usable
```

场景 C 的根因（探针脚本 `g1_caseC_probe.py`）：

```
$ python -X utf8 %TEMP%\f3verify\scripts\g1_caseC_probe.py %TEMP%\f3verify\base
agg 序列唯一值: [0.6]  span= 0.0
y_true shape: (30, 1)  ptp: 0.0  唯一值: [0.6]
ss_total: 3.697785493223493e-31          ← 不是精确 0，fitter.py:183 的 `if ss_total == 0` 守卫失效
success: True  fun: 1.1862580533091034e-17  x: [0.498 0.6]
fitter.r_squared = -962406869313826.8
summary r_squared = -962406869313826.8  converged = True
```

### 2.3 G1：突变实验（反向实验）+ 仓库测试是否 FAIL

```
$ python -X utf8 %TEMP%\f3verify\scripts\make_mutant_sort.py %TEMP%\f3verify\base %TEMP%\f3verify\mutsort
突变体已生成: …\mutsort
  /api/models 恢复为按字母序取前 N 个 state_ 列；/api/fit 的 400 处理保持 HEAD 不变

$ python -X utf8 %TEMP%\f3verify\scripts\g1_mutant_check.py %TEMP%\f3verify\mutsort
payload keys: ['available_state_columns', 'models']
  square_law             needs_manual=None  suggestion={'R1': 'state_cultural_level', 'R2': 'state_education'}
  logistic               needs_manual=None  suggestion={'population': 'state_cultural_level'}
logistic 建议映射 = {'population': 'state_cultural_level'}
  robust=False -> HTTP 200 R2=0.0 conv=True sentinel=False status=ok
  robust=True  -> HTTP 200 R2=0.0 conv=True sentinel=False status=ok     ← 上一轮的误导路径完整复现

$ cd %TEMP%\f3verify\mutsort; python -X utf8 -m pytest tests/test_simulation_and_fitting.py -q -p no:cacheprovider -k "constant_columns"
E       KeyError: 'constant_state_columns'
tests\test_simulation_and_fitting.py:284: KeyError
FAILED tests/test_simulation_and_fitting.py::test_api_models_excludes_constant_columns_from_suggestions
1 failed, 20 deselected

$ python -X utf8 %TEMP%\f3verify\scripts\make_mutant_suggest.py base mutsuggest     # 保留分类键、建议仍按字母序取全部列
$ cd %TEMP%\f3verify\mutsuggest; python -X utf8 -m pytest tests/test_simulation_and_fitting.py -q -p no:cacheprovider -k "constant_columns"
E                   AssertionError: square_law 的建议映射包含零方差列 state_cultural_level
E                   assert 'state_cultural_level' not in ['state_cultural_level', 'state_housing_quality', 'state_neighborhood_quality', 'state_savings', 'state_social_capital']
FAILED tests/test_simulation_and_fitting.py::test_api_models_excludes_constant_columns_from_suggestions
1 failed, 20 deselected

$ cd %TEMP%\f3verify\base; python -X utf8 -m pytest tests/test_simulation_and_fitting.py -q -p no:cacheprovider \
    -k "constant_columns or all_starts_fail or sentinel_solution or converged_reflects"
.....  5 passed, 16 deselected in 3.54s
```

判定：**回退修复逻辑 → 复现 logistic R²=0.0/converged=True；仓库自带测试在两种突变体上都 FAIL、在 HEAD 上 PASS，确实有判别力。**

### 2.4 G2：失败路径（真实代码路径 + 最小桩）

```
$ python -X utf8 %TEMP%\f3verify\scripts\g2_failures.py %TEMP%\f3verify\base %TEMP%\f3verify\sentinel400.json
POST /api/run -> 200 steps=20

=== 1) 哨兵解（真实 FitRequest/ABMFitter，仅把 _objective 钉成 1e12）===
  HTTP 400
  status: model_not_applicable  hit_sentinel: True  r_squared: -12.088172  fun: 1000000000000.0
  error 片段: 模型 wellbeing 在给定数据与参数边界下未能积分出可用解（优化停留在失败哨兵）…

=== 2) fit_robust 真实 RuntimeError（把 _solve 桩成 None，真实多起点全失败）===
  HTTP 400  status: all_starts_failed
  error: All fitting attempts failed.（多起点拟合全部失败；请检查状态列选择与参数边界，或减少起点数重试）

=== 3) 真正的服务端 bug（TypeError / KeyError）是否仍为 500 ===
   TypeError -> HTTP 500  {'error': 'TypeError: unsupported operand'}
    KeyError -> HTTP 500  {'error': "KeyError: 'state_happiness'"}

=== 4) ValueError 输入问题 ===
  logistic 无映射 -> HTTP 400  status: None  error 首行: 模型状态 ['population'] 找不到对应数据列。

=== 5) 未知模型名（KeyError）===
  no_such_model -> HTTP 500 {'error': 'KeyError: \'Unknown model "no_such_model". …'}

=== 6) 过度捕获：拟合成功之后 predict() 抛 RuntimeError ===
  HTTP 400  status: all_starts_failed
  error: ODE solver failed: required step size is less than spacing between numbers.（多起点拟合全部失败…）
  -> 真实原因被改写为"多起点拟合全部失败"，且丢掉 summary

=== 7) 真实端到端：resource_competition（上一轮实测 500）===
  新 suggested_mapping = {'R1': 'state_education', 'R2': 'state_energy'}
  steps=10 robust=True -> HTTP 400 status=all_starts_failed
  steps=20 robust=True -> HTTP 400 status=all_starts_failed
  logistic       robust=False mapping={'population': 'state_education'}        -> HTTP 200 R2=0.958385 conv=True sentinel=False
  square_law     robust=False mapping={'R1': 'state_education', 'R2': 'state_energy'} -> HTTP 200 R2=0.967177
  wellbeing      robust=False mapping={'happiness': 'state_happiness', …}      -> HTTP 200 R2=0.998728
  influence      robust=False mapping={'O1': 'state_education', 'O2': 'state_energy'} -> HTTP 200 R2=0.969565
```

**except 顺序与类型审查**（`app.py:252-262`）：`ValueError` → `RuntimeError` → `Exception` 三者类型互不包含，顺序本身无坑；`TypeError`/`KeyError` 确实落到最后的 500。**问题在语义宽度**：`RuntimeError` 在本模块里不只 `fit_robust` 会抛（`ABMFitter.predict` → `fitter.py:353`，`solve_model` → `lanchester.py:132`），实测 §2.4-6 把服务端积分失败伪装成了"模型不适用"。

### 2.5 G3：真实 `dashboard.js` 在 vm 沙箱中执行

```
$ node %TEMP%\f3verify\scripts\g3_ui.js %TEMP%\f3verify\base %TEMP%\f3verify\sentinel400.json
currentLang 生效检查: zh | t(app.title)= 家庭ABM仪表板

=== 1) i18n ===
  zh 键数: 80  en 键数: 80
  zh 有而 en 没有: []
  en 有而 zh 没有: []
  fitting.mapping_suffix     zh=true en=true t()引用次数=1
  fitting.manual_suffix      zh=true en=true t()引用次数=1
  fitting.warn_sentinel      zh=true en=true t()引用次数=1
  fitting.warn_bounds        zh=true en=true t()引用次数=1
  .fit-warning 在 style.css: true
  t() 支持 {0} 占位: true
  中文渲染 t(warn_bounds,"a, b") = 参数被边界钉住：a, b（该方向可能不可辨识或边界不合适）。
  中文渲染 t(warn_sentinel)       = 优化停在失败哨兵：该解未成功积分，R² 无意义。
  中文渲染 t(manual_suffix)       =  （需人工指定映射）

=== 2) currentStateMapping ===
  directly_fittable   -> null
  需映射(有建议)      -> {"R1":"state_education"}
  needs_manual_mapping-> undefined (undefined = 必须人工指定)
  modelInfo 未加载    -> null (null = 静默降级)

=== 3) runFitting: needs_manual_mapping ===
  fetch 调用: []  statusText: 该模型的状态名与 ABM 列名没有默认对应关系，无法直接拟合。
  -> 拒绝发请求: true
=== 3b) runFitting: modelInfo 未加载（静默降级）===
  fetch 调用: ["/api/fit"]  statusText: 模型状态 ['R1','R2'] 找不到对应数据列。

=== 4) /api/fit 返回 400 哨兵（Python 实测抓下来的真实响应体）===
  body.status = model_not_applicable  body.summary.hit_sentinel = true
  statusText: 模型 wellbeing 在给定数据与参数边界下未能积分出可用解（优化停留在失败哨兵）。常见 ...
  fitKPIs 是否渲染告警条: false  fitKPIs 内容: ""          ← 哨兵告警条永不渲染

=== 5) /api/fit 200 + params_at_bounds ===
  [case5] runFitting 抛异常: TypeError: t is not a function
  含 fit-warning: true  含参数名 r1, k1: true
  fitKPIs: …<div class="fit-warning"><div>⚠ 参数被边界钉住：r1, k1（该方向可能不可辨识或边界不合适）。</div></div>
  statusText 最终值: 拟合中...   ← 成功路径被异常打断（既有缺陷，见 §3-5）

=== 6) 假设 200 + hit_sentinel=true（当前 API 已不可能返回该组合）===
  [case6] runFitting 抛异常: TypeError: t is not a function
  含 fit-warning: true
  fitKPIs: …<div class="fit-warning"><div>⚠ 优化停在失败哨兵：该解未成功积分，R² 无意义。</div></div>
```

### 2.6 真实数据：每 agent 子集方差 + 7 模型 × 新建议映射

```
$ python -X utf8 %TEMP%\f3verify\scripts\g_sweep.py %TEMP%\f3verify\base 20
被标为 usable 但对某些 agent 恒定的列: 无          ← 本数据上不存在"pooled 有用但单 agent 恒定"的活口子
--- robust=False ---
square_law             …education/energy    0.988818  conv=True  sentinel=False  at_bounds=[]       HTTP 200 ok
linear_law             …education/energy   -2.998527  conv=True  sentinel=False  at_bounds=['alpha','beta'] HTTP 200 ok
influence              …education/energy    0.985130  conv=True  sentinel=False  at_bounds=[]       HTTP 200 ok
wellbeing              happiness/stress     0.996159  conv=True  sentinel=False  at_bounds=['p','s','income'] HTTP 200 ok
logistic               …education           0.989593  conv=True  sentinel=False  at_bounds=[]       HTTP 200 ok
lotka_volterra         …education/energy    0.984794  conv=True  sentinel=False  at_bounds=['d']    HTTP 200 ok
resource_competition   …education/energy        None  conv=False sentinel=True   at_bounds=[]       HTTP 400 model_not_applicable
--- robust=True（前端实际发送的配置）---
square_law             …education/energy  -14.349726  conv=True  sentinel=False  at_bounds=[]       HTTP 200 ok
linear_law             …education/energy   -2.998527  conv=True  sentinel=False  at_bounds=['alpha','beta'] HTTP 200 ok
influence              …education/energy    0.986182  conv=True  sentinel=False  at_bounds=[]       HTTP 200 ok
wellbeing              happiness/stress     0.996045  conv=True  sentinel=False  at_bounds=['s','income'] HTTP 200 ok
logistic               …education           0.989593  conv=True  sentinel=False  at_bounds=[]       HTTP 200 ok
lotka_volterra         …education/energy    0.984794  conv=True  sentinel=False  at_bounds=['d']    HTTP 200 ok
resource_competition   …education/energy        None  None       None             None               HTTP 400 all_starts_failed
```

> `logistic` 从上一轮的 **R²=0.0/converged=True** 变成 **0.9896**，7 个模型不再有 500 —— 这一针对"误导性假拟合"的修复在真实数据上确实生效。
> 但 `square_law` 在 `robust=true` 下给出 **R²=-14.35**（steps=20）/ **-94265.68**（steps=60）且 `converged=True`、`params_at_bounds=[]`、`hit_sentinel=False` → **界面上不会出现任何告警**（复现脚本 `g_squarelaw.py`，进程内逐次完全一致；跨进程数值随未固定种子的仿真数据变化）。

### 2.7 测试 / 卫生 / 语法

```
$ cd %TEMP%\f3verify\base
$ python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
................................................         [100%]
48 passed in 86.41s (0:01:26)

$ node --check family_abm/web/static/js/dashboard.js      -> exit 0
$ python -X utf8 tools/baseline.py --check baseline/default_seed42.json
[OK] 与基线一致：baseline\default_seed42.json             -> exit 0
$ cd F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim; git status --short
（空；仅本报告 audits/f3_fix_verification.md 为唯一新增写入）
```

---

## 3. 新引入的问题

1. **`except RuntimeError` 过宽，会把服务端真 bug 伪装成"模型不适用"**（`app.py:255-260`，本提交新增）
   实测 §2.4-6：拟合**已经成功**（`_save_result` 已执行），随后 `fitter.predict()` 因积分器失败抛 `RuntimeError('ODE solver failed: …')`，被改造为 `400 {"status":"all_starts_failed","error":"ODE solver failed: …（多起点拟合全部失败；…）"}` —— 诊断信息完全错误（与多起点无关），且丢掉了 `summary`。**建议**：只捕获 `fit_robust` 抛的那一种（如 `if str(e) == 'All fitting attempts failed.'`，或让 `fit_robust` 抛专用异常类），把 `predict` 移到单独的 try 或提前返回。

2. **`hit_sentinel` 的 UI 告警条在真实管线中不可达，承诺"告警可见"只兑现一半**
   `app.py:223-232` 只要 `hit_sentinel` 为真就返回 400；`dashboard.js:514` 对任何 `res.error` 提前 return，`:522` 的哨兵告警分支被越过。实测 §2.5-4：真实 400 响应体喂进去后 `fitKPIs` 为空字符串。**建议**：把告警渲染也接在错误分支上（400 响应已带 `summary`），或把哨兵降级为 200 + 告警（与"converged=False"一致），二者选一，别让代码与语义互相抵消。

3. **`needs_manual_mapping` 是死路：拒绝发请求，但界面没有手工指定映射的入口**
   `index.html` 全文无 mapping 输入控件（仅有 `<select id="fitModel">`），`dashboard.js:504-508` 直接报错返回。用户在下拉里看到"（需人工指定映射）"，点"拟合模型"只会得到一句"无法直接拟合"，**没有任何途径指定映射**。上一版至少会给出一个（错误的）建议映射。**建议**：给 `needs_manual_mapping` 的模型提供映射选择 UI，或把该 option 直接禁用并说明原因。
   附：`modelInfo` 未加载时 `currentStateMapping` 返回 `null`（不是 `undefined`），`runFitting` 会**静默发出不带 `state_mapping` 的请求**，靠服务端 400 兜底（实测 §2.5-3b）。这不算新回归，但"静默降级"确实存在。

4. **G1 的方差判据与拟合目标不等价（`app.py:171-174`），同类误导路径仍可构造**
   代码取"全表 `dropna()` 后 `max-min`"，复核建议的是 `_sim_df.groupby('time')[col].mean().ptp()`。构造"每户各自恒定、跨户不同"的数据即得：`state_housing_quality ∈ usable`、`logistic.suggested_mapping = {population: state_housing_quality}`、`/api/fit → 200 + R²=-9.6e14 + converged=True`（§2.2-C）。此外：
   - `directly_fittable` 模型**完全不查方差**：期望列存在但恒定 → `wellbeing` 仍 `suggested_mapping = {'happiness': …, 'stress': …}`，`/api/fit → 200 + R²=0.0 + converged=True`（§2.2-D）。
   - 阈值 `1e-9` 是绝对值，量纲盲（§2.2-F）。
   - `fitter.py:93-96` 的**错误提示里**仍按字母序取前 N 列，实测会把 `state_cultural_level` 作为"示意映射"回给用户（§2.2-A 输出的 `请显式传入 state_mapping（示意…）：{'population': 'state_cultural_level'}`）——"建议指向常量列"这一问题在库层没有修。
   - 顺带暴露 `fitter.py:183` 的 `if ss_total == 0` 守卫对浮点噪声无效（`ss_total=3.7e-31` 时 R² 直接炸到 -9.6e14，且 `converged=True`）。属既有实现问题，但正是它让"拟到近常数列"的后果从"显示 0.0"恶化成"显示 -1e15"。

5. **既有崩溃（非本提交引入，但挡在 G3 的验收路径上）：`dashboard.js:565` `TypeError: t is not a function`**
   `buildFitChart` 的 `stateCols.forEach` 回调内 `dashboard.js:561` 用 `const t = Object.keys(byTime)…` 遮蔽了全局 i18n 函数 `t()`，紧接着 `:565` 调用 `t('fitting.data_suffix')` → 抛 TypeError。我在 `15a8294` 的同一行确认**写法完全相同**，故非本提交引入。后果：**每次拟合成功都会在画拟合图时抛异常**，`dashboard.js:537-538` 的 `setStatus('ok', …)` 永不执行（实测 statusText 停在"拟合中..."），拟合曲线图始终画不出来；`params_at_bounds` 告警条因为在 `:526` 已写入 DOM，所以**仍可见**。**建议本次一并修掉**（改名为 `ts`/`times` 或用 `t('fitting.data_suffix')` 前先取别名）。

6. **提交信息与事实的两处不一致（不影响功能）**
   - "测试：新增 3 项" —— 实际新增 **4 项**（44 → 48：`test_api_models_excludes_constant_columns_from_suggestions`、`test_api_fit_returns_400_when_all_starts_fail`、`test_web_fit_maps_sentinel_solution_to_400`、`test_web_fit_maps_all_starts_failure_to_400`）。
   - "后两者用确定性桩而非依赖'模型必然失败'" —— `test_api_fit_returns_400_when_all_starts_fail`（`tests/test_simulation_and_fitting.py:298-315`）恰恰依赖 `resource_competition` 在 steps=10 时必然失败，且只断言 `status ∈ {all_starts_failed, model_not_applicable}`。

---

## 4. 未复现 / 存疑项

1. **提交信息里的具体 R² 数字我复现不一致**：提交称"wellbeing/influence/logistic 均 200（R²=0.9876/0.7179/0.9863）"。我在 steps=20、robust=True 下实测为 **0.996045 / 0.986182 / 0.989593**（robust=False 为 0.996159/0.985130/0.989593）。原因已定位：`api_run`（`app.py:89-108`）**没有 seed 参数**，仿真数据随进程的全局 RNG 变化，跨进程不可比（同一进程内重复调用结果一致）。**方向与结论（不再命中常量列、不再出现 R²=0.0）可复现且确凿**，但提交里的这些数字不应作为证据引用。
2. **`square_law` 的 R² 极不稳定且无告警**：同一份数据、同一新建议映射，robust=False 得 0.9888，robust=True（前端实际发送）得 -14.35；steps=60 时得 -94265.68。`converged=True`、`params_at_bounds=[]`、`hit_sentinel=False` → UI 上不会出现任何告警，用户看到的是"R²=-94265.6763 / Converged 是"。**这是上一轮报告"R²≤0 时应在 UI 上区分"的建议未落实的直接后果**，且多起点比单起点更差说明 `fit_robust` 的"取最大 R²"策略在该模型上失效（可能因 8 个随机起点都落在坏盆地，而默认起点 [0.5,…] 反而更好）。我未深挖模型本身的数值脆弱性（既有问题，非本次引入）。
3. **`needs_manual_mapping` 无任何自动化测试覆盖**：`grep needs_manual_mapping tests/` → 0 命中。我是用构造场景（§2.2-A）外部验证的，仓库测试留了这个缺口。
4. **两个 `test_web_fit_maps_*` 桩测试绕过了真实哨兵检测**：桩 fitter 的 `summary_json()` 直接返回 `hit_sentinel: True`，所以即使 `fitter._objective_hit_sentinel()` 完全坏掉，这两个测试仍会通过。我用"真实 `ABMFitter` + 只把 `_objective` 钉成 `1e12`"补做了集成验证（§2.4-1），结论是真实路径可用。
5. **`1e-9` 与 fitter 自身 `np.ptp < 1e-5` 阈值不一致**：当前真实数据没有落在 (1e-9, 1e-5) 区间的列，无法实测灰带行为，仅按构造值说明分类（§2.2-F）。
6. **`/api/models` 在"尚未 run"时返回 200 + 全空列表**（而非 400）：不算缺陷（未 run 就无法分类），但 `needs_manual_mapping` 全 True 的语义容易被前端误读为"所有模型都需人工映射"；本次实测前端只在 run 之后调用 `loadModelInfo`，未触发。

---

## 5. 放行结论

**有条件放行。**

三项"必须先修"里，**两项半是真的落地了**，且我都能独立复现并给出突变/反证证据：

- **G2 已修复（最扎实）**：哨兵解 → 400 `model_not_applicable`、`fit_robust` 全失败 → 400 `all_starts_failed`、`TypeError`/`KeyError` 仍 500、真实 `resource_competition` 端到端从 **500 → 400**。这是本轮质量最高的一项。唯一新副作用是 `except RuntimeError` 过宽。
- **G1 已修复（真实数据与验收场景全部通过）**：真实 payload 的分类经我独立复算 12/12 一致、两集合互斥且穷尽、7 个模型建议映射全部避开常量列；"候选不足"构造场景下 `needs_manual_mapping=True` 且建议为空；完全回退与半吊子回退两种突变体都能复现旧 bug 并让自带测试 FAIL。**但判据取的是"全表 pooled min/max"，与拟合目标 `groupby('time').mean()` 不等价**，我构造出仍返回 `200 + R²=-9.6e14 + converged=True` 的路径；`directly_fittable` 模型更是完全不做方差检查。
- **G3 部分修复**：`params_at_bounds`、i18n（中英齐全、占位正确）、`.fit-warning`、`needs_manual_mapping` 拒绝发请求 —— 都实测通过；**但 `hit_sentinel` 告警条被本提交新增的 400 语义挡死，真实管线永不渲染**；且"需人工指定映射"没有可指定映射的 UI 入口。

### 放行前必须先修（按优先级）

1. **`app.py:255-260` 收窄 `except RuntimeError`**：只认 `fit_robust` 的"All fitting attempts failed."（建议定义专用异常），避免把 `predict()`/积分器的真实失败包装成 400"模型不适用"并丢弃 `summary`。同时可顺手把未知 `model_name`（`KeyError`，实测 500）转成 400。
2. **`app.py:171-174` 改用拟合目标本身的跨度判据**（`_sim_df.groupby('time')[col].mean()` 的 ptp，或直接复用 fitter 的取序列逻辑），并把方差闸门同时应用到 `directly_fittable` 模型的期望列上；`fitter.py:93-96` 的错误提示"示意映射"也应排除零方差列。
3. **`dashboard.js` 的哨兵告警落到用户可见处**：在 `res.error` 分支里读取 400 响应携带的 `summary` 并渲染 `.fit-warning`（后端已经把 `summary` 放进 400 body 了），否则请修正提交信息中"拟合告警在界面上可见"的表述。
4. **给 `needs_manual_mapping` 一条出路**：补映射选择 UI，或将该 option 置灰并说明"ABM 当前数据无法提供 2 个有变化的状态列"。
5. **`dashboard.js:565` 的 `t` 遮蔽崩溃**（既有缺陷，非本提交引入）：修掉它，否则每次成功拟合都会中断在画图阶段、状态永远停在"拟合中..."。

### 可同批修的次要项

- `fitter.py:183` 的 `if ss_total == 0` 改为相对容差（如 `ss_total <= 1e-12 * max(1.0, np.sum(y_true**2))`），否则近常数列会报出 -1e15 量级的 R²。
- `app.py:174` 的绝对阈值 `1e-9` 改为相对跨度（如 `span <= 1e-9 * max(1.0, abs(series.mean()))`），并与 `fitter.py:139` 的 `1e-5` 告警阈值对齐。
- 补一条 `needs_manual_mapping` 的自动化测试；把两个 `test_web_fit_maps_*` 改成"真实 `ABMFitter` + 只桩 `_objective`/`_solve`"，以免哨兵检测逻辑坏掉时测试仍然全绿；`test_api_fit_returns_400_when_all_starts_fail` 建议改为确定性桩或断言更具体的 `status`。
- `fit_robust` 在"多起点全失败/明显差于默认起点"时回退 `p0=[0.5]*n` 或 `fit_global`（可缓解 `square_law` 的 R²=-9.4e4 却 `converged=True` 无告警问题）。
- 提交信息修正："新增 3 项"→4 项；`wellbeing/influence/logistic` 的 R² 数字改为带 seed 的可复现脚本（`api_run` 目前无 seed 参数，建议补上以便复核）。
