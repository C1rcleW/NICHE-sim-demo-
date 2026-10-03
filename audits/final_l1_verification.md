# L1 最终验证报告

- **验证对象**：`a6de5d4` `fix(web,fitting): 落实 F3 复核意见——哨兵告警可达、收窄 except、方差判据改用拟合目标`
- **被验证的评审**：`audits/f3_fix_verification.md`（对 `3c6b16f` 的复核，提出 5 项"必须先修"）
- **仓库**：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`
  - `git log --oneline -3` → `a6de5d4 / 3c6b16f / 15a8294`（HEAD 确为 `a6de5d4`）
  - 验证期间 `git status --short` → 空（本报告写入前）；写入后仅 `audits/final_l1_verification.md` 一项
- **环境**：Python 3.14.3 / numpy 2.4.3 / pandas 3.0.2 / scipy 1.17.1 / fastapi 0.136.1 / httpx 0.28.1 / Node v24.14.0
- **方法（只读仓库）**：全部实验在 `%TEMP%\l1verify\` 下的副本中进行
  - `base\`＝`a6de5d4` 副本；`prefix\`＝把 `family_abm/web/app.py` 换成 `3c6b16f` 版本的"修复前"对照
  - 突变体：`mutpooled\`＝方差判据退回"全表 pooled 跨度"；`mutsentinel\`＝哨兵解退回 400；`mutt\`＝`dashboard.js` 恢复 `const t =` 遮蔽
  - 脚本全部写在 `%TEMP%\l1verify\scripts\`；**未在仓库根产生任何文件，未运行 examples 绘图路径**
- **默认立场**：先认定修复为假/不完整/有新副作用，逐项用确定性桩、构造数据、突变体与真机执行反证。

---

## 1. 判定汇总表

| 项 | 判定 | 我的实测 | 要求 | 差异 |
|---|---|---|---|---|
| **H1 except 收窄**（F3 必须先修 #1） | **已修复（附 1 项新增过宽捕获）** | 确定性桩逐条（`python -X utf8 %TEMP%\l1verify\scripts\h1_except.py %TEMP%\l1verify\base`）：① `predict()` 抛 `RuntimeError` → **HTTP 500 `prediction_failed`**（不是 400 all_starts_failed）；② `predict()` 抛 `ValueError`/`KeyError` → 同样 **500 prediction_failed**；③ `fit_robust` 抛 `RuntimeError('All fitting attempts failed.')` → **400 `all_starts_failed`**；④ `success=False` → **400 `optimizer_failed`**；⑤ 返回 `None` → **400 `optimizer_failed`**；⑥ 真实 `make_fitter` 未知模型 → **400 `unknown_model`**；⑦ `TypeError`/`ZeroDivisionError`（服务器真 bug）→ **仍 500**（未被吞）。`app.py:265-274` 的内层 `try` 只包住 fit 调用，`app.py:291-303` 的 `predict` 已移到 400 分支之外 —— 实现与提交说明一致 | predict 的 RuntimeError → 500+prediction_failed（不得误诊为 400）；未知 model_name → 400+unknown_model；多起点全失败 → 400+all_starts_failed；success=False → 400+optimizer_failed；不依赖"某模型必然失败" | 4 条断言全部达成、全部用确定性桩复现。**但新增的 `except KeyError`（`app.py:307-312`）过宽**：拟合阶段抛的 `KeyError` 也被改写成 400 `unknown_model`——实测 `df` 缺 `time` 列 → `400 {"status":"unknown_model","error":"未知模型名 'time'…"}`；`df` 无 `agent_id` 列且传 `agent_id` → `400 … 'agent_id' …`（对照 `prefix`：修复前均为 `500 KeyError: 'time'`）。这正是本提交要修掉的"把真实错误伪装成另一类错误"的同一反模式（见 §3-P2） |
| **H2 方差判据改用拟合目标**（F3 必须先修 #2） | **已修复（附 2 处残留缺口）** | `h2_variance.py`：① 四类列划分正确 —— "每 agent 恒定/跨 agent 不同"（pooled 跨度 0.8）→ `constant=['state_per_agent_constant']`，真正随时间变化 → `usable`，完全常量 → `constant`，全 NaN → `unverifiable`；② 判据确为 `series.groupby(df['time']).mean().dropna()`（同数据 pooled=0.8 而聚合跨度=0.0）；③ 阈值实测：span `1e-12`→constant、`1e-9`→constant（严格 `>`）、`1.0000001e-9`→usable、`1e-8`→usable；`[1e6, 1e6+1e-8]`（相对变化 1e-14）仍判 usable（绝对阈值量纲盲，F3 已列为次要项）；④ 构造 happiness/stress 常量数据 → `wellbeing.directly_fittable=False`、`needs_manual_mapping=True`、`missing=['happiness','stress']`、`unusable_default_columns={'happiness':'state_happiness','stress':'state_stress'}`；⑤ `fitter.py:89-103` 已删除按字母序的"示意映射"（自带测试 + 代码阅读双重确认） | 使用按 time 聚合后的均值序列而非 pooled 跨度；默认映射列为常量时 `directly_fittable=False`；`fitter` 错误提示不再给示意映射 | 要求全部达成。**残留 1**：`/api/models` 只看全表聚合，不看 `agent_id` 子集 —— 构造"agent A 恒定 0.5 / agent B 变化 / 全表均值变化"，`logistic` 仍 `needs_manual_mapping=False`，`/api/fit(agent_id='A')` → **200 + R²=0.0 + converged=True**（B 为 0.9866）；**残留 2**：`dropna()` 与拟合器取序列语义不一致 —— 某个 time 分组全为 NaN 时判 `usable`，但 `/api/fit` → `400 'Data contains NaN values.'` |
| **H3 哨兵告警可达 + R² 非正告警**（F3 必须先修 #3） | **部分修复（真实管线仍不可达）** | ① 后端确定性桩（真实 `ABMFitter`，只把 `_objective` 钉成 `1e12`）→ **200 + `status=model_not_applicable` + `warning`**，`summary.hit_sentinel=True`；② node + 最小 DOM 桩真实执行 `dashboard.js`（`node scripts\h3_ui.js …`）：真实抓取的 200 响应体 → `#fitKPIs` 出现 `<div class="fit-warning">…优化停在失败哨兵…` ✔；③ 反向实验：`mutsentinel`（哨兵改回 400）的**真实 400 响应体**喂进去 → `fitKPIs` 为空字符串、`fit-warning=false`，告警条再次不可达 ✔（证明修复对该路径必要）；④ "R² 非正"告警：真实 `/api/fit`（square_law，robust=true）响应体 `R²=-3.098347, converged=true, params_at_bounds=[]` → `fit-warning` + 「R² 非正」渲染 ✔；⑤ i18n `fitting.warn_r2_nonpositive` 中英各 1 次、`t()` 渲染正确 ✔；⑥ **但在真实管线里 200+哨兵不可达**：`app.py:291-303` 先做 `predict`，`app.py:316-320` 先返回 `prediction_failed`，`app.py:327-337` 的哨兵 200 在其后。`h3_probe.py` 无桩扫描（5 模型 × steps=10/20/40/60 × robust T/F）显示**唯一命中哨兵的真实组合 `resource_competition` robust=False 一律 `predict=FAIL`**；`h3_e2e.py` 实测 `/api/fit` → **HTTP 500 `prediction_failed`**（错误文案"拟合成功但预测轨迹生成失败"与事实相反：该解从未积分成功），而 `prefix`（3c6b16f）同一请求为 **400 `model_not_applicable`** | 命中哨兵 → 200+model_not_applicable+warning，且该 warning 在 dashboard.js 真正渲染；R² 非正有告警与中英键 | 机制已实现且经前端真实执行验证；**但真实数据下哨兵告警条仍不可达**（被 predict 失败挡成 500），且该路径相对 3c6b16f 是 400→500 的回归（见 §3-P1）。"前端总是发 robust=true，此时 `resource_competition` → 400 all_starts_failed"，两种走法都不渲染哨兵告警条 |
| **H4 needs_manual_mapping 不再是死路**（F3 必须先修 #4） | **部分修复** | ① `dashboard.js:395-397`：`needs_manual_mapping` 的模型渲染为 `<option … disabled>`；node 实测全禁用 payload → `sel.options.every(o=>o.disabled)===true` ✔；② 默认选中：`dashboard.js:402-404` 的 `preferred.find(n => modelInfo[n] && !modelInfo[n].needs_manual_mapping)` → 正常 payload 选中 `wellbeing`（非 disabled）；把 preferred 里除 `resource_competition` 外全部置为 needs_manual → 选中 `resource_competition`（非 disabled）✔，**不会选中 disabled 项**（disabled ⇔ needs_manual_mapping，两个条件互补）；③ **全禁用场景实测**：`sel.value === ''`、`selectedIndex === -1`（HTML 规范：单选 select 无未禁用 option 时无选中项；赋值不存在的 value 结果同为空串），但页面**没有禁用"拟合模型"按钮、也没有任何说明**，点击后 `runFitting` 照发 `{"model_name":"","agent_id":null,"robust":true,"state_mapping":null}` → 服务端 `400 unknown_model`，`statusText` 变成原始混杂文案 `未知模型名 'Unknown model "". Choose: […'`；`fitKPIs` 为空 | 下拉置灰；默认选中项不得是被 disabled 的模型；说明"全禁用时是否仍能点拟合" | 置灰与默认选中两项达成。**全禁用时"没有可选模型但用户仍能点拟合"成立**：不崩溃、但得到一个不可读的服务端错误，用户无从知道为什么所有模型都灰了（见 §3-P3）。另：`dashboard.js:510-515` 的 `mapping === undefined` 分支在 UI 上已不可达（该分支存在的前提是能选中 needs_manual 模型），成为死代码 |
| **H5 `t` 遮蔽崩溃**（F3 必须先修 #5） | **已修复（无任何自动化测试覆盖）** | ① `git show a6de5d4 -- dashboard.js` 确认 `buildFitChart` 内 `const t = …` → `const timeKeys = …`（`dashboard.js:573-581`）；② **真实执行**：node 最小 DOM/Plotly 桩里跑真实 `dashboard.js`，`H.simData = <含 null 值的仿真数据>`、`H.buildFitChart({predict_trace:[…]})` → **未抛异常**，`Plotly.newPlot` 收到 4 条 trace，name 为 `"happiness 数据"`；③ **阴性对照**：同一 harness 跑 `3c6b16f:family_abm/web/static/js/dashboard.js` → `TypeError: t is not a function`，证明 harness 有判别力；④ `node --check` → exit 0；⑤ **突变实验**：把 `const timeKeys` 改回 `const t`（`mutt`）跑全量 `pytest tests/ -q` → **55 passed**，0 失败 | `buildFitChart` 内不再有 `const t =` 遮蔽；真正执行不再抛 TypeError | 修复本身确认有效。**但本提交未新增任何测试覆盖该项**：回退该修复后 55 个测试全绿（见 §2.3-③），属"修了但无回归保护" |
| 额外：`/api/models` 字段变化是否破坏前端/测试 | **未破坏，但有契约变更** | 全仓库 grep `resolved_columns` → 仅 `family_abm/fitting/fitter.py:44/86/407`（`_resolved_columns` 内部字段）与 `tests/…:239/409/499`（fitter 内部断言）；**`/api/models` 响应里的 `resolved_columns` 无任何消费方**（前端 0 次引用）。`api/fit` 响应里的 `state_columns` 取自 `fitter._resolved_columns`（`app.py:330`），仍在、仍正确 | 不破坏前端与既有测试 | 无破坏。但 `resolved_columns` 是已发布的响应字段，本次直接删除未做兼容；新增的 `unusable_default_columns`/`unverifiable_state_columns` 在 JS/其它 Python 中**引用次数均为 0**（未被消费，`dashboard.js` 只用 `directly_fittable`/`needs_manual_mapping`） |
| 额外：pytest / node --check / git status | **通过** | `cd %TEMP%\l1verify\base; python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider` → **55 passed in 61.29s，无 skip 行**；`node --check family_abm/web/static/js/dashboard.js` → exit 0；`python tools/baseline.py --check baseline/default_seed42.json` → `[OK] 与基线一致`；仓库 `git status --short` → 空（本报告写入前） | 全绿、无 skip、语法通过、仅本报告为新增写入 | 与提交声明一致。`python -m ruff check`（默认规则）在三个改动文件上 **9 errors**：其中 `tests/test_simulation_and_fitting.py:557-558` 的新测试引入 **4 个新的 F811**（局部重复导入遮蔽模块级导入，`ABMFitter`/`MODEL_PARAM_NAMES`/`MODEL_REGISTRY`/`MODEL_STATE_NAMES`）；基线同文件为 5 个（含 `Path` F401，现已消除） |
| 额外：新增测试质量 | **有判别力，但有 2 处弱断言 + 1 处覆盖缺口** | 突变实验见 §2.3：`mutpooled` → `test_variance_report_uses_time_aggregated_target_not_pooled_span` **FAILED**（`usable=['state_per_agent_constant','state_time_varying']`）；`mutsentinel` → `test_web_fit_returns_200_with_warning_for_sentinel_solution` **FAILED**（`assert 400 == 200`）；`mutt` → **全绿**（H5 无覆盖）。恒真断言扫描：未发现恒真断言 | 无恒真/弱断言；测试名与断言一致 | **弱断言 1**：`test_api_fit_returns_400_when_all_starts_fail`（`tests/…:368-385`）仍依赖"`resource_competition` 在 steps=10 必然失败"（提交说明自己说不再依赖），且断言 `status ∈ {all_starts_failed, model_not_applicable}`——在本版本里 400 响应**不可能**带 `model_not_applicable`，该备选已成死分支；**弱断言 2**：`test_frontend_warns_on_non_positive_r_squared`（`:537-548`）是源码字符串 grep，不执行 JS（真正执行 JS 的是我 §2.4 的 harness）；**覆盖缺口**：H5 修复无测试。另：提交信息"新增 6 项"与实际不符——`git diff 3c6b16f a6de5d4 -- tests/` 有 8 个 `+def test_`，其中 1 个是改名，实际 **新增 7 项**（48→55） |

### 结论一句话

**H2 与 H5 是兑现得最干净的两项**（H2 判据确为 time 聚合序列、`directly_fittable` 已覆盖常量默认列，并经 pooled 突变体证明测试有判别力；H5 经真实执行 + 3c6b16f 阴性对照确认崩溃消失）；**H1 的四条断言全部达成、全部用确定性桩复现**，但新增的 `except KeyError` 复制了刚被修掉的"错误类型误诊"反模式；**H3 与 H4 都只兑现一半**：H3 的哨兵告警机制在前端真的能渲染（我用真实响应体 + 反向突变体双向验证），但**真实数据下唯一命中哨兵的场景被 `predict` 失败挡成 `500 prediction_failed`**，相对 3c6b16f 的 `400 model_not_applicable` 是回归，提交声称的"200 + model_not_applicable + warning"在真机上不出现；H4 的置灰与默认选中正确，但**全禁用时用户仍能点拟合**，得到一条不可读的服务端错误。

---

## 2. 反证 / 突变实验记录

所有脚本：`%TEMP%\l1verify\scripts\`；仓库副本 `base`＝`a6de5d4`。

### 2.1 H1 确定性桩逐条（`h1_except.py`）

```
=== H1 确定性桩逐条验证 ===
 [1] predict() 抛 RuntimeError
  RuntimeError: HTTP 500  {'status': 'prediction_failed', 'error': '拟合成功但预测轨迹生成失败：RuntimeError: ODE solver failed: required step size is less than spacing'}
 [2] predict() 抛 ValueError      -> HTTP 500  {'status': 'prediction_failed'}
 [3] predict() 抛 KeyError        -> HTTP 500  {'status': 'prediction_failed'}
 [4] fit 抛 RuntimeError("All fitting attempts failed.")
  fit RuntimeError: HTTP 400  {'status': 'all_starts_failed', 'error': 'All fitting attempts failed.（多起点拟合全部失败…'}
 [5] fit 返回 success=False       -> HTTP 400  {'status': 'optimizer_failed', …}
 [6] fit 返回 None                -> HTTP 400  {'status': 'optimizer_failed'}
 [7] fit 内部抛 KeyError（真实服务器 bug 模拟）
  fit KeyError: HTTP 400  {'status': 'unknown_model', 'error': "未知模型名 'state_happiness'。可用模型：[…]"}
 [8] fit 内部抛 TypeError         -> HTTP 500  {'error': 'TypeError: unsupported operand'}
 [9] fit 内部抛 ZeroDivisionError -> HTTP 500  {'error': 'ZeroDivisionError: division by zero'}
=== 未知 model_name（走真实 make_fitter）===
  no_such_model: HTTP 400  {'status': 'unknown_model', 'error': '未知模型名 \'Unknown model "no_such_model". Choose: […'}
=== 真实代码路径：输入数据异常（不桩任何东西）===
  df 缺 time 列:       HTTP 400  {'status': 'unknown_model', 'error': "未知模型名 'time'。可用模型：[…]"}
  df 为空（0 行）:     HTTP 400  {'error': 'Need at least 10 time points, got 0.'}
  df 只有 1 行:        HTTP 400  {'error': 'Need at least 10 time points, got 1.'}
  df 有 5 行:          HTTP 400  {'error': 'Need at least 10 time points, got 5.'}
  df 含 NaN:           HTTP 400  {'error': 'Data contains NaN values.'}
  state_mapping 指向不存在的列: HTTP 400 {'error': "模型状态 ['happiness'] 找不到对应数据列。"}（无 status 字段）
  state_mapping 指向 time 列:   HTTP 200 status=ok（不校验映射列必须以 state_ 开头）
  state_mapping 重复映射:       HTTP 400 {'error': "状态列存在重复映射：['state_stress']…"}
  state_mapping 含多余键:       HTTP 200 status=ok（静默忽略）
```

附加（`h1_agentid.py`，不桩任何东西）：

```
  df 无 agent_id 列 + agent_id="m1" -> HTTP 400 status=unknown_model err="未知模型名 'agent_id'。可用模型：[…]"
```

对照 `prefix`（`family_abm/web/app.py` 换成 `3c6b16f` 版本，`prefix_keyerror.py`）：

```
  [df 缺 time 列]                  HTTP 500 status=None err="KeyError: 'time'"
  [df 无 agent_id 列 + agent_id=m1] HTTP 500 status=None err="KeyError: 'agent_id'"
```

**应有状态码判断（我的独立判定）**：`df` 缺 `time` / 缺 `agent_id` 列属于**调用方数据问题**，合理值是 `400` 且 `status` 应表达"数据缺列"（例如 `missing_columns`），错误文案必须指出缺失的列名；当前 `400 + unknown_model + "未知模型名 'time'"` 是**错误归因**，比修复前的 `500 KeyError: 'time'` 更难诊断（500 至少暴露了真实异常类型与键名）。`state_mapping` 指向不存在的列 → 400 正确（但缺 `status`，与同批次其它 400 不一致）；`state_mapping` 指向非 `state_` 列（如 `time`）→ 建议 400，当前 200 会拟合出无意义结果。

### 2.2 H2 方差判据（`h2_variance.py`）

```
=== H2-A 四类列的划分 ===
  每 agent 恒定但跨 agent 不同 (0.1/0.9)  usable=[] constant=['state_per_agent_constant'] unverifiable=[]  pooled_span=0.8
  随时间变化                              usable=['state_time_varying'] constant=[] unverifiable=[]  pooled_span=0.5
  完全常量                                usable=[] constant=['state_flat'] unverifiable=[]  pooled_span=0.0
  全 NaN                                  usable=[] constant=[] unverifiable=['state_allnan']  pooled_span=None
=== H2-A2 同一份数据两种判据对照 ===
  pooled_span=0.8 (旧判据会判 usable)
  新判据 groupby(time).mean() 跨度=0.0 -> ['state_per_agent_constant']
=== H2-B 阈值 1e-9 的实际行为 ===
  span=1e-12 -> constant ; span=1e-9 -> constant ; span=1.0000001e-9 -> usable ; span=1e-8 -> usable
  span=1e-8 @量级 1e6（相对变化 1e-14）-> usable  (绝对阈值量纲盲)
=== H2-C 判据 vs 拟合器真实目标 ===
  每 agent 恒定但跨 agent 不同  fitter目标 ptp=0.000e+00  判为 constant
  随时间变化                    fitter目标 ptp=2.000e-01  判为 usable
  完全常量                      fitter目标 ptp=0.000e+00  判为 constant
  全 NaN                        fitter目标 ptp=nan       判为 unverifiable
=== H2-C2 dropna 分歧 ===
  判据: usable=['state_x']（t=0 组全 NaN 被 dropna 丢掉）
  拟合器 _extract_aggregate_series 会拿到含 NaN 的序列: [nan, 0.1 … 0.9]
  /api/models 说 usable=['state_x']，但 /api/fit -> HTTP 400 'Data contains NaN values.'
=== H2-D 默认映射列恰为常量 ===
  usable=[] constant=['state_happiness','state_stress']
  wellbeing: directly_fittable=False needs_manual_mapping=True missing=['happiness','stress']
             unusable_defaults={'happiness':'state_happiness','stress':'state_stress'} suggested=None
  直接用默认映射调 /api/fit -> HTTP 200 status=ok R2=-1.52e+22 converged=True warning=False
       （前端因 needs_manual_mapping 置灰，UI 不可达；且 R²<=0 会触发前端 R² 非正告警）
=== H2-D2 常量默认列 + 2 个其它有变化列 ===
  usable=['state_aaa','state_zzz']  wellbeing: directly=False needs_manual=False
  suggested={'happiness':'state_aaa','stress':'state_zzz'} -> /api/fit 200 R2=0.97195
=== H2-E 残留缺口：/api/models 不看 agent 子集 ===
  全表: usable=['state_p'] constant=[]   logistic: directly=False needs_manual=False suggested={'population':'state_p'}
  agent A 自己的 state_p 序列 ptp=0.0 (恒定)
  /api/fit(agent_id=A) -> HTTP 200 status=ok R2=0.0   converged=True warning=False
  /api/fit(agent_id=B) -> HTTP 200 status=ok R2=0.986641 converged=True warning=False
```

阈值判定：`VARIANCE_EPS = 1e-9`、严格 `>`（`app.py:186`）。`1e-12 → constant`、`1e-8 → usable`，与提交说明一致；**但它是绝对阈值**，对"量级 1e6、相对变化 1e-14"的列判 usable，且与 `fitter.py:137` 自己的近零方差告警阈值 `np.ptp < 1e-5` 不一致（灰带 1e-9…1e-5 内 /api/models 说 usable、fitter 说 may be unreliable）。判定：**分类行为合理但量纲盲**（F3 已列为可同批修的次要项，本提交未处理）。

### 2.3 突变实验（判别力）

**(1) `mutpooled`：方差判据退回"全表 pooled dropna 跨度"**

```
$ cd %TEMP%\l1verify\mutpooled; python -X utf8 -m pytest tests/test_simulation_and_fitting.py -q -p no:cacheprovider \
      -k "variance_report or constant_columns or needs_manual"
>       assert usable == ["state_time_varying"], f"usable={usable}"
E       AssertionError: usable=['state_per_agent_constant', 'state_time_varying']
FAILED tests/test_simulation_and_fitting.py::test_variance_report_uses_time_aggregated_target_not_pooled_span
1 failed, 2 passed, 25 deselected
```

**(2) `mutsentinel`：哨兵解退回 400（`make_mutant_sentinel.py` 注入 + 真实抓取 400 体）**

```
$ cd %TEMP%\l1verify\mutsentinel; python -X utf8 -m pytest tests/test_simulation_and_fitting.py -q -p no:cacheprovider \
      -k "sentinel or optimizer_failure or all_starts"
>       assert response.status_code == 200, response.body
E       AssertionError: … "status":"model_not_applicable","summary":{"hit_sentinel":true,…}
E       assert 400 == 200
FAILED tests/test_simulation_and_fitting.py::test_web_fit_returns_200_with_warning_for_sentinel_solution
1 failed, 3 passed, 24 deselected
```

**(3) `mutt`：`dashboard.js` 恢复 `const t =` 遮蔽（H5 回退）**

```
$ cd %TEMP%\l1verify\mutt; python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
.......................................................                  [100%]
55 passed in 70.42s          <- H5 修复被回退，测试全绿：**零覆盖**
```

### 2.4 H3/H4/H5 前端真实执行（`node scripts\h3_ui.js …`，zh 语言，最小 DOM/Plotly 桩）

```
A) i18n
  t('fitting.warn_sentinel')       = 优化停在失败哨兵：该解未成功积分，R² 无意义。
  t('fitting.warn_r2_nonpositive') = R² 非正：该模型结构不适合这些状态列，Converged 只表示优化器跑完了。
  [en] warn_sentinel / warn_r2_nonpositive 均存在；'fitting.warn_r2_nonpositive': 出现次数 = 2（中英各 1）
B) H5: 真实执行 buildFitChart
  buildFitChart 未抛异常 ✔  traces = 4  数据点 trace name = "happiness 数据"
  --- 阴性对照：同一 harness 跑 3c6b16f 的 dashboard.js ---
  旧版本抛异常（符合 F3 报告）: TypeError: t is not a function
C) H3: 哨兵告警条可达性（真实抓取的响应体）
  [修复后：哨兵 200 + warning] HTTP=200 status=model_not_applicable
    statusText = "拟合完成 (R^2=0.3415)"
    fitKPIs 非空 = true  含 fit-warning = true
  [反向实验：突变体把哨兵改回 400] HTTP=400 status=model_not_applicable
    statusText = "模型 wellbeing 在给定数据与参数边界下未能积分出可用解…"
    fitKPIs 非空 = false  含 fit-warning = false        <- 告警条不可达（证明修复必要）
  [真实数据实测：哨兵但 predict 失败 -> 500] HTTP=500 status=prediction_failed
    statusText = "拟合成功但预测轨迹生成失败：RuntimeError: ODE solver failed: required step size is less than spacing"
    fitKPIs 非空 = false  含 fit-warning = false        <- 真实管线里哨兵告警条仍不可达
  --- 200 + R² 非正 ---
    含 fit-warning = true  含 R² 非正文案 = true
D) H4
  正常 payload: sel.value = "wellbeing"  options = .:square_law .:linear_law .:influence .:wellbeing …（无 X）
  选中的 option 是 disabled 吗 = false
  全禁用 payload: sel.value = ""  selectedIndex = -1  全 disabled = true
    runFitting 实际发出: {"model_name":"","agent_id":null,"robust":true,"state_mapping":null}
    statusText = "未知模型名 'Unknown model \"\". Choose: [\\'square_law\\', …]'。可用模型：[…]"
    fitKPIs 内容长度 = 0
  preferred 全禁用、只剩 resource_competition: sel.value = "resource_competition"  disabled = false
  currentStateMapping: directly_fittable -> null ; 有建议 -> {"a":"state_x"} ; needs_manual -> undefined ; 未加载 -> null
E) 前端对 /api/models 字段的引用次数
  unusable_default_columns: 0 ; unverifiable_state_columns: 0 ; usable_state_columns: 0 ;
  constant_state_columns: 0 ; available_state_columns: 0 ; resolved_columns: 0
```

真实响应体的 R² 非正告警（`node scripts\h3_real_r2.js …`）：

```
真实响应体: HTTP 200 status= ok R2= -3.098347 bounds= []
fitKPIs 含 fit-warning = true  含「R² 非正」= true
statusText = "拟合完成 (R^2=-3.0983)"
fitKPIs = … <div class="fit-warning"><div>⚠ R² 非正：该模型结构不适合这些状态列，Converged 只表示优化器跑完了。</div></div>
```

### 2.5 H3 真实数据上的哨兵/预测组合（`h3_probe.py`，无任何桩）

```
steps= 10 resource_competition   robust=False sentinel=True  R2=None conv=False predict=FAIL RuntimeError: ODE solver failed: Required step size is less than spacing between numbers.
steps= 10 resource_competition   robust=True  fit 抛 RuntimeError: All fitting attempts failed.
steps= 20 resource_competition   robust=False sentinel=True  R2=None conv=False predict=FAIL RuntimeError: …
steps= 20 resource_competition   robust=True  fit 抛 RuntimeError: All fitting attempts failed.
steps= 20 square_law             robust=True  sentinel=False R2=-4788.947289 conv=True predict=OK
steps= 40 square_law             robust=True  sentinel=False R2=-66288.626675 conv=True predict=OK
steps= 60 square_law             robust=True  sentinel=False R2=-98555.599356 conv=True predict=OK
（steps=10/20/40/60 × square_law/linear_law/logistic/wellbeing/resource_competition × robust T/F 全表见脚本输出）
```

干净进程端到端（`h3_e2e.py`，`/api/run steps=20` 后逐模型拟合，`robust` 取前端实际值 true）：

```
  robust=True  square_law             HTTP 200 status=ok  R2=0.960933
  robust=True  linear_law             HTTP 200 status=ok  R2=-4.794646
  robust=True  influence              HTTP 200 status=ok  R2=0.927871
  robust=True  wellbeing              HTTP 200 status=ok  R2=0.997207
  robust=True  logistic               HTTP 200 status=ok  R2=0.954198
  robust=True  lotka_volterra         HTTP 200 status=ok  R2=0.828281
  robust=True  resource_competition   HTTP 400 status=all_starts_failed
  robust=False resource_competition   HTTP 500 status=prediction_failed   <- 前一版为 400 model_not_applicable
```

before/after 对照（`prefix\` 用 `3c6b16f` 的 `app.py`，同一请求）：

```
[3c6b16f app.py] resource_competition robust=False -> HTTP 400 status=model_not_applicable
                 err='模型 resource_competition 在给定数据与参数边界下未能积分出可用解（优化停留在失败哨兵）…'
[3c6b16f app.py] resource_competition robust=True  -> HTTP 400 status=all_starts_failed
```

### 2.6 卫生检查

```
$ cd %TEMP%\l1verify\base
$ python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
.......................................................                  [100%]
55 passed in 61.29s (0:01:01)          （-rs 未列出任何 skip）
$ node --check family_abm/web/static/js/dashboard.js     -> exit 0
$ python -X utf8 tools/baseline.py --check baseline/default_seed42.json
[OK] 与基线一致：baseline\default_seed42.json            -> exit 0
$ cd F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim; git status --short
（空；本报告写入前）
$ python -m ruff check family_abm/web/app.py family_abm/fitting/fitter.py tests/test_simulation_and_fitting.py --output-format concise
family_abm\web\app.py:17:28: F401 `..family.roles.ROLE_REGISTRY` imported but unused        （既有）
tests\test_simulation_and_fitting.py:21:39: F401 `ABMFitter` imported but unused            （既有）
tests\test_simulation_and_fitting.py:22:43/62/78: F401 MODEL_PARAM_NAMES/MODEL_REGISTRY/MODEL_STATE_NAMES（既有）
tests\test_simulation_and_fitting.py:557:43 / 558:47/66/82: F811 重新定义 …                 （本提交新增 4 项）
Found 9 errors.
```

---

## 3. 新引入的问题

### P1 —— 哨兵解的判定被排到 `predict` 之后，真实哨兵场景返回 500 并给出与事实相反的文案（`app.py:291-337`）

- **证据**：`h3_probe.py` 无桩扫描显示真实数据上命中哨兵的唯一组合（`resource_competition`，`robust=False`，steps=10/20/40/60）**一律 `predict` 失败**；`h3_e2e.py` 实测该请求 → `HTTP 500 {"status":"prediction_failed","error":"拟合成功但预测轨迹生成失败：RuntimeError: ODE solver failed…"}`；`prefix`（`3c6b16f`）同一请求 → `HTTP 400 model_not_applicable`。
- **为什么是 P1**：① 文案"拟合成功但…"与事实相反（该解从未积分成功，`summary.hit_sentinel=True`）；② 把一个"模型不适用"的输入问题重新包装成 5xx——这正是 F3 上一轮"必须先修 #1"要消除的现象，本提交在**哨兵这一条路径上把它又变回 500**；③ 提交声明"哨兵解返回 200 + status=model_not_applicable + warning"，但真机上该响应从不出现，`dashboard.js:529-530` 的哨兵告警条在真实管线里**仍然不可达**，H3 的验收标准未达成。当前 200 路径只在"桩造出来的哨兵解 + predict 恰好成功"时可达（我的 `h3_backend.py` 场景 1 即此类）。
- **建议**：把哨兵判定移出 predict 之后（先取 `summary`，若 `hit_sentinel` 直接返回 200 + warning + 空 `predict_trace`，不再调 `predict`）；或在 `prediction_error is not None and hit_sentinel` 时仍返回 200 + warning（把预测失败降级为 warning 文本），只有"非哨兵且 predict 失败"才 500。

### P2 —— 新增 `except KeyError` 过宽，把拟合阶段/数据缺列的真实错误改写为"未知模型名"（`app.py:307-312`）

- **证据**：桩 `fit` 抛 `KeyError('state_happiness')` → `400 {"status":"unknown_model","error":"未知模型名 'state_happiness'…"}`；真实路径 `df` 缺 `time` 列 → `400 unknown_model "未知模型名 'time'"`；`df` 无 `agent_id` 列且传 `agent_id` → `400 unknown_model "未知模型名 'agent_id'"`（对照 `prefix`：三者修复前分别为 `500 KeyError: 'state_happiness'`、`500 KeyError: 'time'`、`500 KeyError: 'agent_id'`）。
- **为什么是 P2**：与 H1 要修的"RuntimeError 过宽"是同一个反模式，只是类型换了；`KeyError` 的唯一合法来源是 `make_fitter`（`fitter.py:436-437`），却把整个 `try` 都覆盖了。
- **建议**：只把 `make_fitter(...)` 单独包一个 `try/except KeyError`（或改为预校验 `if req.model_name not in MODEL_REGISTRY: return 400 unknown_model`），拟合阶段与数据缺列分别给 `400` + 明确 `status`（如 `missing_columns`）。

### P3-1 —— H4 全禁用场景：下拉全灰但"拟合模型"按钮仍可点，得到不可读的服务端错误（`dashboard.js:391-405`、`506-521`）

- **证据**：node 实测全禁用 payload（每个模型 `needs_manual_mapping=true`）→ `sel.value === ''`、`selectedIndex === -1`、所有 option `disabled`；点击后 `runFitting` 发出 `{"model_name":"","agent_id":null,"robust":true,"state_mapping":null}`；`statusText` 变成 `未知模型名 'Unknown model "". Choose: [\'square_law\', …]'。可用模型：[…]`。
- **影响**：H4 想解决的"死路"在"所有模型都需人工映射"时以另一种形式复现——用户看到 7 个灰项、无任何解释、按钮照样能点。`dashboard.js:510-515` 的 `mapping === undefined` 分支（会给出中文提示"该模型的状态名与 ABM 列名没有默认对应关系…"）在 UI 上已不可达，成为死代码。
- **建议**：无可用模型时 `disabled` 拟合按钮并在下拉下方给出解释（例如"当前数据没有足够的有变化状态列；请调整仿真或先运行仿真"）。

### P3-2 —— H2 判据未覆盖 `agent_id` 子集；`dropna` 语义与拟合器不一致（`app.py:181-186`）

- **证据**：`h2_variance.py` 场景 E —— 全表聚合有变化（`usable=['state_p']`）而 agent A 自身恒定 → `/api/fit(agent_id='A')` → `200 status=ok R²=0.0 converged=True`（后端 `warning=False`；前端 R² 非正告警会兜底显示）。场景 C2 —— 某个 time 分组全为 NaN → 判 `usable`，但 `/api/fit` → `400 'Data contains NaN values.'`。
- **影响**：`/api/models` 的语义是"相对当前数据的可映射性"，但前端提供逐 agent 拟合下拉（`dashboard.js:556-558`），两者的"当前数据"不一致。真实 ABM 数据未触发（F3 也确认"被标为 usable 但对某些 agent 恒定的列：无"）。
- **建议**：`api_models` 接受可选 `agent_id`，或在前端切换 agent 时重取 `/api/models`；判据改用与 `_extract_aggregate_series` 完全同源的取序列函数（不 dropna）。

### P3-3 —— H5 修复无任何测试覆盖

- **证据**：`mutt` 突变体（`const timeKeys` → `const t`）跑全量 `pytest tests/ -q` → `55 passed`。
- **建议**：把"执行 `buildFitChart` 不抛异常"做成真实可跑的用例（node 桩或抽出纯函数），否则该回归会再次静默复活。

### P3-4 —— 测试与提交信息的小问题

- `test_api_fit_returns_400_when_all_starts_fail`（`tests/…:368-385`）仍依赖"`resource_competition` 必然失败"，断言 `status ∈ {all_starts_failed, model_not_applicable}`——后者在本版本里不可能出现在 400 响应中，属死分支。
- `test_frontend_warns_on_non_positive_r_squared`（`:537-548`）为源码 grep 断言，不执行 JS。
- `tests/…:557-558` 的局部重复导入引入 4 个新的 ruff `F811`（`python -m ruff check …` 9 errors）。
- 提交信息"测试：新增 6 项"与实测不符：实际新增 **7 项**（48→55）+ 1 项改名。
- 提交信息与实机数字不可复现：`api_run` 无 seed（`app.py:89`），我实测 `square_law robust=true` 的 R² 在四个进程里为 `-3.098 / -4788.9 / -66288.6 / -98555.6`，提交所写的 `-142.97` 无法复现（结论方向——"R² 非正且 converged=True 时前端有告警"——已用真实响应体验证成立）。

### P3-5 —— 响应契约变更无消费方确认、新字段无人使用

- `/api/models` 删除 `resolved_columns`：全仓库无消费方（grep 命中仅为 `_resolved_columns` 内部字段），前端与既有测试均不破；但这是已发布字段的直接删除，未做兼容或版本说明。
- 新增 `unusable_default_columns` / `unverifiable_state_columns` 在 JS 与其它 Python 中引用次数均为 0——目前是"只写不读"的字段。

---

## 4. 未复现 / 存疑项

1. **提交声称"哨兵解返回 200 + model_not_applicable + warning"**：我用**确定性桩**（真实 `ABMFitter`，只钉 `_objective=1e12`）能复现该 200 响应及其前端渲染；但在**真实数据**上无法复现（唯一命中哨兵的 `resource_competition robust=False` 被 predict 失败挡成 500）。故我判定该 200 路径"机制存在、真机不可达"。
2. **`resource_competition robust=True`（前端实际发送配置）**在真实数据上是 `400 all_starts_failed`，不是哨兵路径——所以 UI 用户目前看不到哨兵告警条，但也拿不到 P1 的 500。P1 的可达面为：`robust=false` 的 API 调用方 + 无 seed 的其它数据分布。
3. **`square_law` 的 R² 数值跨进程不稳定**（无 seed），我只能确认"稳定地出现 R²≤0 且 converged=True"，不能复现提交里的具体数字。
4. **`needs_manual_mapping` 的"全禁用"场景**我是用 node 规范级 DOM 桩判定的（单选 select 在选项全部 disabled 时 `selectedIndex=-1`、`value=''`；赋值不存在的 value → 同样为空串）。我没有真实浏览器/jsdom 可用，故这一条的置信度为"高但非浏览器实测"。其余 H3/H4/H5 结论都基于真实抓取的响应体与真实 `dashboard.js` 源码执行。
5. **`agent_id` 子集缺口**：我的构造数据是合成的（10 个时间点、A 恒定 / B 变化），真实 ABM 数据上未复现该缺口（与 F3 报告一致）。
6. **阈值灰带（1e-9…1e-5）**：真实数据没有落进该区间的列，只按构造值说明分类行为。

---

## 5. 放行结论

**有条件放行。**

5 项"必须先修"的落实情况：**2 项已修复（H2、H5）**、**2 项部分修复（H1 附新增过宽捕获、H3 真机哨兵路径不可达、H4 全禁用仍可点）**、**H1 的四条验收断言全部达成**、**H5 修复正确但零测试覆盖**。代码整体比 `3c6b16f` 明显更正确（真实数据上已无 500、`logistic` 的 R²=0.0 误导路径消失、方差判据与拟合目标对齐、哨兵告警机制在前端真的能渲染、R² 非正已有可见告警、`t` 遮蔽崩溃消失），但**存在 1 项 P1 回归：哨兵场景从 400 model_not_applicable 变成 500 prediction_failed，且提交声明的 200+warning 在真机上不出现**——这正好落在 H3 的验收标准上，因此不能无条件放行。

### 放行前必须先修

1. **（P1）`app.py:291-337`：哨兵判定必须先于 `predict`。** 先取 `summary = fitter.summary_json()`；若 `hit_sentinel` 为真 → 直接 `200 + status=model_not_applicable + warning`（`predict_trace` 置空，不再调 `predict`）；`predict` 失败只在"非哨兵"时返回 500。修完后请用 `resource_competition` + `robust=false` 的真机请求验证拿到的是 `200 + model_not_applicable + warning`（我用的复现脚本：`%TEMP%\l1verify\scripts\h3_probe.py` / `h3_e2e.py` 的同构写法），而不是继续依赖桩。
2. **（P2）`app.py:307-312` 收窄 `KeyError` 分支**：只覆盖 `make_fitter` 的未知模型名（建议改为入口处 `if req.model_name not in MODEL_REGISTRY`），让"`df` 缺 `time`/`agent_id` 列"落到带明确 `status`（如 `missing_columns`）的 400，而不是 `unknown_model`。
3. **（P3-1）`dashboard.js` 全禁用时禁用拟合按钮并给出原因**，避免 `model_name=""` 的请求与服务端原始文案。

### 可同批修（不阻塞放行）

- 给 H5 的 `buildFitChart` 补一条真正执行 JS 的回归测试（当前回退该修复 55 个测试全绿）。
- `app.py:186` 的绝对阈值 `1e-9` 改为相对跨度，并与 `fitter.py:137` 的 `1e-5` 告警阈值对齐。
- `/api/models` 支持 `agent_id`（或前端切换 agent 时重取），并把判据的取序列逻辑与 `_extract_aggregate_series` 统一（去掉 `dropna` 分歧）。
- 把 `test_api_fit_returns_400_when_all_starts_fail` 改为确定性桩并断言单一 `status`；把 `test_frontend_warns_on_non_positive_r_squared` 改为执行 JS；清理 `tests/…:557-558` 的重复导入（4 个 `F811`）。
- 提交信息修正："新增 6 项"→7 项；`api_run` 补 `seed` 参数以便复核的 R² 数字可复现。
