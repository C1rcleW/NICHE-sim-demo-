# L1 收尾验证报告

- **验证对象**：`04ae058` `fix(web): 落实 L1 最终复核意见——哨兵判定前置等 3 项必须先修`
- **被验证的评审**：`audits/final_l1_verification.md`（对 `a6de5d4` 的复核，提出 3 项"必须先修"：P1 哨兵判定前置 / P2 收窄 `except KeyError` / P3-1 全禁用禁止拟合）
- **仓库**：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`
  - `git log --oneline -3` → `04ae058 / a6de5d4 / 3c6b16f`（HEAD 确为 `04ae0582800706f52d3a94627002dd10433f9758`）
  - 验证开始与报告写入前 `git status --short` → 空
- **环境**：Python 3.14.3 / numpy 2.4.3 / pandas 3.0.2 / scipy 1.17.1 / fastapi 0.136.1 / httpx 0.28.1 / Node v24.14.0
- **只读约束遵守情况**：全部实验在 `%TEMP%\l1signoff\` 下的仓库副本（`base`＝`04ae058`）与突变体副本（`mut`）中进行；`pytest` 用 `-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`，`ruff` 用 `--no-cache` 且只在副本里跑；**未在仓库根产生任何文件、未运行 examples 绘图路径、未改仓库任何源码/测试/配置/已有报告**。仓库内唯一新增写入是本文件。
- **默认立场**：先认定修复为假/不完整/有新副作用，逐条用**真机**（TestClient 驱动真实 `api_run`/`api_fit`，只对 `predict` 做计数插桩，不替换行为）、确定性桩、构造数据、突变体与 node 真实执行反证。
- 复现脚本：`%TEMP%\l1signoff\scripts\`（`k1_real2.py` / `k2_except.py` / `k2_http500.py` / `k3_ui.js` / `k3c_real.js` / `k4_models.py` / `k4_residual2.py` / `k4_race.js` / `i18n_check.py` / `probe_*.py` / `run_mutants.py`）

---

## 1. 判定汇总表

| 项 | 判定 | 我的实测 | 要求 | 差异 |
|---|---|---|---|---|
| **K1 哨兵判定前置**（上一轮 P1） | **已修复** | ① **真机**（`k1_real2.py`，路径 A：`resource_competition` + 显式 `state_mapping={'R1':'state_education','R2':'state_energy'}`＝上一轮 `h3_probe.py` 的同一前置）steps **10/20/40/60 + robust=false** → **HTTP 200 / `status=model_not_applicable` / `hit_sentinel=True` / `warning` 非空 / `predict_trace=[]` / `prediction_skipped=true` / `predict` 调用数 = 0**；**robust=true** → **HTTP 400 `all_starts_failed`**（语义正确，非 500）。② 路径 B（`/api/models` 的 `suggested_mapping`，＝上一轮 `h3_e2e.py`/前端路径）steps 10/20 × robust × 7 模型 + 路径 B2（逐 agent）共 **98 次真机拟合：`HTTP>=500` 的组合数 = 0**。③ **反向实验**（`sentinel_after` 突变体＝把哨兵判定移回 `predict` 之后，即 `a6de5d4` 的顺序）真机复现 **steps 10/20/40/60 的 `robust=false` 一律 `HTTP 500 prediction_failed`**（`app.py` 突变后 `err=拟合成功但预测轨迹生成失败：RuntimeError: ODE solver failed: Required step...`）；`pytest tests/ -q` → **2 failed, 59 passed**，失败用例为 `test_web_fit_returns_200_with_warning_for_sentinel_solution` 与 `test_sentinel_check_precedes_prediction`（**测试确有判别力**）。④ **非哨兵 predict 失败仍 500**（确定性桩，5 种异常）：`RuntimeError/ValueError/KeyError/TypeError/MemoryError` → 全部 **HTTP 500 `status=prediction_failed`**（未被吞、未被误诊为 400） | 命中哨兵 → 200 + `model_not_applicable` + warning + 空 `predict_trace` + `prediction_skipped=true`，且**根本没有调用 predict**；`robust=false` 不再出现 500 `prediction_failed`；非哨兵 predict 失败仍 500 | **要求全部达成，且是我这一轮唯一"零差异"的一项。** `app.py:318-337` 的哨兵早返回位于 `app.py:340-354` 的 predict 之前；`prediction_skipped` 是新增字段（上一轮无），对前端是纯增量。计数插桩是在**真实方法外层转调**，不是桩 |
| **K2 `except KeyError` 收窄 + 缺列明确报错** | **已修复（但同一提交把最外层兜底 `except Exception` 删掉了，见 §3-P3-1）** | ① `df` 缺 `time` 列 → **HTTP 400 `status=invalid_dataframe`**，`err=仿真数据缺少必需列 ['time']（当前列：['agent_id','state_happiness']）。`，**不含"未知模型名"**；`df` 缺 `agent_id` 列且传 `agent_id` → 同上（`['agent_id']`）。② 合法 df + 未知 `model_name` → **400 `unknown_model`**（唯一来源）；`model_name=""`（全禁用时前端曾发的请求）→ 400 `unknown_model`（合理）。③ 反向实验（`keyerror_wide` 突变体＝删掉前置列校验 + 把 `except KeyError` 加回拟合段）：**`df` 缺 `agent_id` 列 + 传 `agent_id` → HTTP 400 `status=unknown_model` `err=未知模型名 'agent_id'。`** —— 上一轮的反模式被完整复现；`pytest` → **1 failed**（`test_missing_time_or_agent_column_reports_invalid_dataframe`，`assert 'invalid_input' == 'invalid_dataframe'`）。④ `except KeyError`（`app.py:281-287`）现在只包 `make_fitter`，`app.py:290-302` 只包 fit 调用 | `df` 缺 `time`/`agent_id` → 400 + `invalid_dataframe` + 列出当前列，不得出现"未知模型名"；只有未知 `model_name` 才 400 `unknown_model` | 两条断言全部达成、并用反向实验双向确认。**新增副作用**：`a6de5d4` 里有 `except Exception → 500 {'error': 'TypeName: ...'}`（结构化 500），本提交把它**整段删除**，导致其它非预期异常变成**未捕获异常 → 裸 500 `text/plain: Internal Server Error`**（详见 §3-P3-1，我用真实 HTTP 抓到了） |
| **K3 全禁用时禁止拟合**（上一轮 P3-1） | **已修复（状态栏说明在主导用户路径上被覆盖，见 §3-P2-1）** | ① **node 真实执行 `dashboard.js`**（`k3_ui.js`，最小 DOM 桩 + 真实源码）：全模型 `needs_manual_mapping=true` 的 payload → `btn.disabled = true`、`sel.value=""`、`selectedIndex=-1`、全 option disabled、`sel.dataset.allDisabled="1"`、**`fitSelectionBlocked() = true`**、`runFitting()` 实际发出的 `/api/fit` 请求数 = **0**（入口拦截）、`statusText="当前数据下没有可直接拟合的模型（可用状态列过少或全为常量）。"`。② 边界"只有 logistic 可拟合"：合成 payload → `btn.disabled=false`、`sel.value="logistic"`、`selectedIndex=4`、选中项非 disabled、`blocked=false`、`runFitting` 只发 1 次且 `model_name="logistic"`；**真实 payload 交叉验证**（`k3c_real.js` 跑 `models_only_logistic.json`，由真实 `_sim_df` 仅含 `state_education` 时抓取）→ `options = X:square_law X:linear_law X:influence X:wellbeing .:logistic X:lotka_volterra X:resource_competition`，`sel.value="logistic"`，`btn.disabled=false`，`blocked=false`，`currentStateMapping('logistic')={"population":"state_education"}`。③ 下拉为空串/`selectedIndex=-1`/`fitModel` 元素缺失 → `fitSelectionBlocked()` 均 **true**。④ i18n：`fitting.none_available` 中英**各 1 次且 en 是真英文** | `fitSelectionBlocked()` 在全禁用时返回 true，按钮 disabled，`runFitting` 入口拦截；只有 logistic 时按钮可用且默认选中它；空串时正确返回 true | 要求全部达成。**差异**：提交说明写的"状态栏说明原因"只在**切换 agent** 这条支路可见；跑完仿真走的主路径上，`dashboard.js:377-378` 在 `await loadModelInfo()` 之后立刻 `setStatus('ok', t('status.simDone'))`，把 `dashboard.js:418` 设的 `none_available` 说明**覆盖成"仿真完成"**（node 端到端实测：`btn.disabled=true` 但 `statusText="仿真完成"`、`statusDot.className="dot ok"`）。用户看到灰按钮、无任何原因解释 |
| **K4 H2 残留修正** | **部分修复** | ① 全表 vs 子集：构造"整体有变化但 agent A 恒定"（`state_happiness` A=0.5 恒定 / B 变化）→ 全表 `usable=['state_happiness','state_stress']`，`wellbeing directly_fittable=True`；**`/api/models?agent_id=A` → `usable=['state_stress'] constant=['state_happiness']`，`wellbeing directly_fittable=False needs_manual=True missing=['happiness'] suggested=None`** ✔；真实 ABM 数据也确认 `agent_id` 参数生效（逐 agent 的 `suggested_mapping` 可用）。② 只有一个有效时间分组的列：`state_only_one_group`（t=1 组全 NaN）→ **`unverifiable_state_columns`**（`usable=[] constant=['state_flat'] unverifiable=['state_allnan','state_only_one_group']`）；旧判据对照实测 `旧(means.empty)=constant` vs `新(len<2)=unverifiable` ✔。③ `agent_id` 不存在 → `400 {"error": "没有 agent_id='no-such-agent' 的记录。"}`（**无 `status` 字段**）；`?agent_id=`（空串，非 None）→ `400 "没有 agent_id='' 的记录。"`；`df` 无 `agent_id` 列 → `400 "没有仿真数据或数据缺少 agent_id 列。"`；无仿真数据 + 不传 `agent_id` → 200（全部 `needs_manual_mapping=true`）。④ 前端 onchange：`buildAgentList()` 用**赋值**注册 `sel.onchange = () => { loadModelInfo(); }`（无监听器累积），但 `loadModelInfo()` 是 fire-and-forget、**无去抖/无取消/无请求序号** | `/api/models?agent_id=...` 按 agent 子集评估，"整体有变化但该 agent 恒定" → `directly_fittable=False`；单分组列归入 `unverifiable_state_columns`；检查 `agent_id` 不存在时的返回；检查前端 onchange 是否形成请求风暴或竞态 | ①② 达成。**残留 1（P2-2）**：快速切换 agent 实测 **5 次切换 = 5 个并发 `/api/models` 请求**，乱序返回时**陈旧响应覆盖新响应**——先返回 `?agent_id=e` 再返回 `?agent_id=a` 后，下拉最终显示 `MODEL_FROM_A`，而 `fitAgent.value==="e"`（用户看到的是别的 agent 的评估结果）；且 `/api/models` 返回 400 时 `loadModelInfo` 在 `dashboard.js:393` 直接 `return`，下拉/按钮保持上一个 agent 的状态（实测：切到 400 的 agent 后 `btn.disabled=false`、`fitSelectionBlocked()=false`、下拉不变 → 可用错误 agent 的模型发拟合）。**残留 2（P3-2）**：后端 `/api/fit` **自己不做常量列守卫**——构造仅 `state_education` 且对 agent A 恒定的数据，`/api/models?agent_id=A` 报 `anySelectable=False`（UI 全灰），但 `/api/fit(agent_id='A', logistic, {'population':'state_education'})` → **HTTP 200 `status=ok` `R2=0.0` `converged=True`**，正是本轮整条 H2 线要消除的误导结果（前端置灰挡住了，API 调用方没被挡；配合上面的陈旧响应竞态，UI 也可达） |
| **额外：全禁用"说明文案"的 i18n 与契约面** | **通过** | `i18n_check.py`：`fitting.none_available` zh 块 1 次 / en 块 1 次，en 文本是真英文；`fitting.need_mapping`/`mapping_suffix`/`manual_suffix`/`warn_sentinel`/`warn_r2_nonpositive`/`warn_bounds`/`converged_yes`/`converged_no` 中英均齐。`t()` 的兜底链是 `当前语言 → en → 原样返回 key`（`dashboard.js:150-155`），故 en 缺失会直接显示裸 key | 新 i18n 键中英双语齐全 | 无差异。注意 `tests/…:709` 的 `source.count("fitting.none_available':") == 2` 只数出现次数，若把两条都放进 zh 块同样为 2（该断言的"双语齐全"语义未被真正验证，属弱断言，见 §2.3-(9)） |
| **额外：`resolved_columns` / `missing_states` / 死符号残留** | **通过（无残留引用）** | 全仓库 grep：`resolved_columns` 作为**响应字段**已 0 处（真实响应体 `"resolved_columns" 是否出现在响应 = False`，`/api/models` 顶层键只剩 `available_state_columns / constant_state_columns / models / unverifiable_state_columns / usable_state_columns`），仅存 fitter 内部 `_resolved_columns`（`fitter.py:44/86/407`）与测试断言；`missing_states` 仅 `app.py:248`（生产者）+ `tests/…:257/329`，**JS/HTML 引用 0 次**（旧报告已指出该字段无消费方，本提交未改）；`fin`、`prediction_error` → **全仓库 0 匹配**（死变量清理干净，无悬挂引用） | 无残留引用已删除/改名前的字段；无新死代码 | 无差异。`missing_states` 仍是"只写不读"字段（非本提交引入） |
| **额外：`pytest` / `node --check` / 基线 / `git status` / ruff** | **通过（无新增 ruff 问题）** | 副本内 `python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider` → **61 passed in 63.55s**，`-rs` **未列出任何 skip**（SKIPPED 行数 = 0）；`node --check family_abm/web/static/js/dashboard.js` → **exit 0**；`python -X utf8 tools/baseline.py --check baseline/default_seed42.json` → **[OK] 与基线一致** exit 0；仓库 `git status --short` → 空（本报告写入前）。`ruff check --no-cache` 仅对两个 .py：**9 errors** —— `app.py:17 F401`、`tests:21/22` 4×F401、`tests:624-625` 4×F811；对 `a6de5d4` 的同两个文件跑同样命令也是 **9 errors（完全同名同类，仅行号 557/558→624/625）** | 全绿、无 skip、语法通过、基线 OK、仅本报告为新增写入、无新增静态检查问题 | **无新增**，但也**未清理**上一轮列为"可同批修"的 4 个 F811（不阻塞）。提交说明"61 passed / node --check exit 0 / 基线 [OK]"三条全部可复现 |
| **额外：新增测试数量与判别力** | **数量如实，判别力 5/6（1 条有行为盲区）** | `git diff a6de5d4 04ae058 -- tests/` → `+def test_` **恰好 6 行**（该文件 28→34，总 55→61）。突变实验（§2.3）6 条新测试中被我逐条打靶：`variance_empty`→FAILED、`no_agent_subset`→FAILED、`js_t_shadow`→FAILED、`js_i18n_en_removed`→FAILED、`js_btn_nodisable`→FAILED、`missing_time…`（`keyerror_wide`/`no_precheck`）→FAILED；**唯一漏洞**：`test_frontend_blocks_fit_when_no_model_is_selectable` 在 `fitSelectionBlocked()` 被改成恒 `return false` 后**仍 4 passed** | 无恒真/弱断言；测试名与断言一致；关键新测试有判别力 | 提交说明"新增 6 项"这次**准确**（它列出的 7 项里含 1 项是对既有哨兵测试增补断言）。但那条新测试是纯源码字符串 grep，**不执行 JS**：把 `fitSelectionBlocked()` 的函数体换成 `return false;`（保留函数名与其余字符串）→ `pytest` **4 passed**，而 node 实测同突变体下全禁用场景 `fitSelectionBlocked()=false`、`runFitting` 照发 1 次 `model_name=""` 请求、`statusText` 变成 `未知模型名 'Unknown model "". Choose: [...]'`（正是本轮要消灭的不可读错误）——行为零覆盖（§3-P3-3） |

### 结论一句话

**3 项"必须先修"在功能层面全部兑现**：哨兵判定确已前置（真机 98 次拟合零 5xx，且 `predict` 调用数为 0），缺列不再被误诊成"未知模型名"，全禁用时按钮确实 disabled 且入口确实拦截——这三点我都用**真机 + 反向突变体**双向做了证。**但它们各自的"配套边角"都还差一口气**：① 哨兵前置时顺手删掉了 `except Exception` 兜底，把其它非预期异常从"结构化 500 JSON"退化成"裸 500 `text/plain`"（我用真实 HTTP 抓到了，前端会把它显示成 JSON 解析错误）；② 全禁用的"原因说明"在跑完仿真这条主路径上被 `setStatus('ok','仿真完成')` 覆盖，用户只看到灰按钮；③ H2 的 `agent_id` 子集评估加上了，但前端切换 agent 是**无去抖无序号**的 fire-and-forget（5 次切换 5 个并发请求，乱序时陈旧响应覆盖），且 400 被静默吞掉导致状态陈旧，后端 `/api/fit` 自身仍接受常量列（`R²=0.0 + converged=True`）——即上一轮的 P3-2 由"完全没修"变成"UI 单点修了、竞态与 API 面没修"。以上均非阻塞级，但其中 ① 是**新引入的错误契约退化**。

---

## 2. 反证 / 突变实验记录

所有命令均在 `%TEMP%\l1signoff\` 下执行；`base` = `04ae058` 副本，`mut` = 注入突变后的副本（每例从 `base` 重新复制）。

### 2.1 K1 真机复验（`k1_real2.py`，无桩；`predict` 只做计数插桩）

```
=== 路径 A：resource_competition + 显式 mapping（h3_probe.py 的前置） ===
$ cd %TEMP%\l1signoff\base; python -X utf8 %TEMP%\l1signoff\scripts\k1_real2.py
steps  robust  code                status  sent  warn  trc  skip  pcl  head
   10   False   200  model_not_applicable  True  True    0  True    0  模型 resource_competition 在给定数据与参数边界下未能积分出可用解（优化停留在失败哨兵）；…
   10    True   400     all_starts_failed  None False    0  None    0  All fitting attempts failed.（多起点拟合全部失败；…）
   20   False   200  model_not_applicable  True  True    0  True    0  …预测轨迹已跳过。…
   20    True   400     all_starts_failed  None False    0  None    0  All fitting attempts failed.（…）
   40   False   200  model_not_applicable  True  True    0  True    0  …
   40    True   400     all_starts_failed  None False    0  None    0  …
   60   False   200  model_not_applicable  True  True    0  True    0  …
   60    True   400     all_starts_failed  None False    0  None    0  …

=== 路径 B：全部模型 + /api/models suggested_mapping（h3_e2e.py / 前端路径），steps 10/20 ===
（共 56 行，全部为 200 ok 或 400 all_starts_failed / 400 invalid_input / 200 model_not_applicable，摘录异常行）
   10    True   400         invalid_input  None False    0  None    0  `x0` violates bound constraints.
   10   False   200  model_not_applicable  True  True    0  True    0  …（sentinel 行）
   10    True   400     all_starts_failed  None False    0  None    0  …
   20   False   200  model_not_applicable  True  True    0  True    0  …
   20    True   400     all_starts_failed  None False    0  None    0  …

=== 路径 B2：/api/models?agent_id=... 的 suggested_mapping（逐 agent，steps 20，3 个 agent） ===
（共 42 行，首行摘录）
   20   False   400      optimizer_failed False False    0  None    0  模型 square_law 的优化未能收敛（optimizer success=False）。…
（其余为 200 ok / 200 model_not_applicable / 400 all_starts_failed）

=== 汇总：非 2xx / 非 ok 且非预期 的异常组合 ===
  HTTP>=500 的组合数 = 0
DONE
```

**`pcl` 列是真实 `predict` 被调用的次数**（`fitter_mod.ABMFitter.predict` 被包一层计数器后转调真实实现）。所有哨兵行 `pcl=0`，非哨兵行 `pcl=1` —— "根本没有调用 predict" 得到直接证据，而非靠响应体推断。

第一版 `k1_real.py` 我漏了 `state_mapping`，`resource_competition` 直接 400 `invalid_input`（"模型状态 ['R1','R2'] 找不到对应数据列"）——这本身是正确行为，但它不是上一轮那条路径，故改用 `k1_real2.py` 的路径 A/B 重做。

### 2.2 K2 确定性桩 + 真实路径逐条（`k2_except.py`）

```
$ cd %TEMP%\l1signoff\base; python -X utf8 %TEMP%\l1signoff\scripts\k2_except.py %TEMP%\l1signoff\base
K2-1 断言：df 缺必需列 -> 400 + invalid_dataframe + 列出当前列，不得出现"未知模型名"
  缺 time 列（有 agent_id）              HTTP 400 status=invalid_dataframe 误报未知模型名=False err=仿真数据缺少必需列 ['time']（当前列：['agent_id', 'state_happiness']）。
  缺 time 列（只有 state_ 列）           HTTP 400 status=invalid_dataframe 误报未知模型名=False err=仿真数据缺少必需列 ['time']（当前列：['state_happiness']）。
  缺 agent_id 列 + 传 agent_id          HTTP 400 status=invalid_dataframe 误报未知模型名=False err=仿真数据缺少必需列 ['agent_id']（当前列：['time', 'state_happiness']）。
  缺 time 与 agent_id（传 agent_id）    HTTP 400 status=invalid_dataframe 误报未知模型名=False err=仿真数据缺少必需列 ['agent_id', 'time']（当前列：['state_happiness']）。
K2-2 断言：只有未知 model_name 才返回 400 unknown_model
  合法 df + 未知 model_name              HTTP 400 status=unknown_model  err=未知模型名 'no_such_model'。可用模型：[…]
  合法 df + model_name=""（全禁用时前端曾发的请求）HTTP 400 status=unknown_model err=未知模型名 ''。可用模型：[…]
  合法 df + 缺 time + 未知 model_name（顺序）HTTP 400 status=invalid_dataframe err=仿真数据缺少必需列 ['time']…
K2-3 其它 KeyError / ValueError 路径的归类实测
  state_mapping 指向不存在的列             HTTP 400 status=invalid_input  err=模型状态 ['happiness'] 找不到对应数据列。 期望列名：['state_nope'] …
  state_mapping 键名不匹配（应为 happiness/stress）HTTP 200 status=ok
  state_mapping 只给一半                  HTTP 200 status=ok
  state_mapping 值重复映射                 HTTP 400 status=invalid_input  err=状态列存在重复映射：['state_stress']。…
  state_mapping 映射到 time 列             HTTP 200 status=ok                       <- 拟合到时间轴，无校验
  state_mapping 映射到 agent_id 列         HTTP UNCAUGHT_TypeError  status=None   err=TypeError: Cannot perform reduction 'mean' with string dtype
  state_mapping 含多余键                   HTTP 200 status=ok
  空 DataFrame（有列）                     HTTP 400 status=invalid_input  err=Need at least 10 time points, got 0.
  只有 1 行                               HTTP 400 status=invalid_input  err=Need at least 10 time points, got 1.
  _sim_df 只有 time 列                    HTTP 400 status=invalid_input  err=模型状态 ['happiness','stress'] 找不到对应数据列。…可用状态列：[]
  _sim_df 只有 time+agent_id 列           HTTP 400 status=invalid_input  err=（同上）
  df 含 NaN                              HTTP 400 status=invalid_input  err=Data contains NaN values.
  只有 1 个 time 分组（12 行同 time）        HTTP 400 status=invalid_input  err=Need at least 10 time points, got 1.
  agent_id 传了不存在的值                   HTTP 400 status=invalid_input  err=数据中没有 agent_id='nope' 的记录。可用 agent_id：['m1']
K2-4 确定性桩：拟合阶段抛 ValueError 的归类（服务器真 bug vs 调用方输入）
  fit 抛 ValueError         -> HTTP 400 status=invalid_input      500 与否=否 err=内部 bug：数组形状不匹配 (12,) vs (13,)
  fit 抛 ValueError         -> HTTP 400 status=invalid_input      500 与否=否 err=Data contains NaN values.
  fit 抛 KeyError           -> HTTP UNCAUGHT_KeyError status=None 500 与否=是(裸500) err=KeyError: 'state_happiness'
  fit 抛 TypeError          -> HTTP UNCAUGHT_TypeError status=None 500 与否=是(裸500) err=TypeError: unsupported operand
  fit 抛 ZeroDivisionError  -> HTTP UNCAUGHT_ZeroDivisionError status=None 500 与否=是(裸500) err=ZeroDivisionError: division by zero
  fit 抛 RuntimeError       -> HTTP 400 status=all_starts_failed  500 与否=否 err=All fitting attempts failed.（…）
  fit 抛 OverflowError      -> HTTP UNCAUGHT_OverflowError status=None 500 与否=是(裸500) err=OverflowError: math range error
K2-5 确定性桩：非哨兵 predict 失败仍必须 500 prediction_failed
  predict 抛 RuntimeError     -> HTTP 500 status=prediction_failed err=拟合成功但预测轨迹生成失败：RuntimeError: ODE solver failed
  predict 抛 ValueError       -> HTTP 500 status=prediction_failed err=…ValueError: bad shape
  predict 抛 KeyError         -> HTTP 500 status=prediction_failed err=…KeyError: 'state_x'
  predict 抛 TypeError        -> HTTP 500 status=prediction_failed err=…TypeError: bad type
  predict 抛 MemoryError      -> HTTP 500 status=prediction_failed err=…MemoryError: oom
K2-6 确定性桩：哨兵命中 + predict 会失败 -> 必须 200 且不得调用 predict
  HTTP 200 status=model_not_applicable warning=True predict_trace=[] prediction_skipped=True predict_calls=0
DONE
```

裸 500 的真实 HTTP 形态（`k2_http500.py`，`raise_server_exceptions=False`，走真实路径：`state_mapping={'happiness':'agent_id'}`）：

```
$ cd %TEMP%\l1signoff\base; python -X utf8 %TEMP%\l1signoff\scripts\k2_http500.py %TEMP%\l1signoff\base
status = 500
content-type = text/plain; charset=utf-8
body = 'Internal Server Error'
```

对照 `a6de5d4` 的 `app.py`（其 `except Exception as e: return JSONResponse({'error': f'{type(e).__name__}: {e}'}, 500)` 在本提交中被删除）：同一类异常过去返回的是 **`500 application/json` + `{"error": "TypeError: …"}`**。前端 `api()`（`dashboard.js:231-238`）对非 JSON 会 `catch` 并 `return { error: e.message }`，于是 `statusText` 会变成 `res.json()` 的解析错误文案（如 `Unexpected token 'I', "Internal Server Error" is not valid JSON`），而不是异常类型与信息 —— 这是由"删除兜底"直接导致的诊断信息丢失（§3-P3-1）。

### 2.3 突变实验（判别力，`run_mutants.py`）

**(1) `sentinel_after`：哨兵判定移回 `predict` 之后（＝`a6de5d4` 的顺序）**

```
$ cd %TEMP%\l1signoff\mut; python -X utf8 -m pytest tests/ -q --tb=no -rf --no-header -p no:cacheprovider
FAILED tests/test_simulation_and_fitting.py::test_web_fit_returns_200_with_warning_for_sentinel_solution
FAILED tests/test_simulation_and_fitting.py::test_sentinel_check_precedes_prediction
2 failed, 59 passed in 70.50s

$ cd %TEMP%\l1signoff\mut; python -X utf8 %TEMP%\l1signoff\scripts\probe_sentinel.py   # 真机
      app file = C:\Users\asus\AppData\Local\Temp\l1signoff\mut\family_abm\web\app.py
      steps  robust  code                 status  trc  pcl  err/warn
         10   False   500      prediction_failed    0    1  拟合成功但预测轨迹生成失败：RuntimeError: ODE solver failed: Required step
         10    True   400      all_starts_failed    0    0  All fitting attempts failed.（…）
         20   False   500      prediction_failed    0    1  …
         20    True   400      all_starts_failed    0    0  …
         40   False   500      prediction_failed    0    1  …
         40    True   400      all_starts_failed    0    0  …
         60   False   500      prediction_failed    0    1  …
         60    True   400      all_starts_failed    0    0  …
```

→ 上一轮的 P1 回归被**完整复现**（`robust=false` 一律 500 `prediction_failed`），且**有测试能抓到**（2 条 FAILED）。这既是"修复必要"的证明，也是"修复有效"的反向证明。

**(2) `keyerror_wide`：删掉前置列校验 + 把 `except KeyError` 加回拟合段**

```
    -> pytest_full: 1 failed, 60 passed
    _________ test_missing_time_or_agent_column_reports_invalid_dataframe _________
    E  assert 'invalid_input' == 'invalid_dataframe'
    -> probe_k2（真机）
      缺 time 列（有 agent_id）        HTTP 400 status=invalid_input  err=模型状态 ['stress'] 找不到对应数据列。…
      缺 agent_id 列 + 传 agent_id    HTTP 400 status=unknown_model err=未知模型名 'agent_id'。可用模型：[…]     <- 反模式复现
      合法 df + 未知 model_name        HTTP 400 status=unknown_model err=未知模型名 'no_such_model'。…
```

**(3) `no_precheck`：只删前置列校验（保留收窄后的 except）**

```
    -> pytest_full: 1 failed, 60 passed
    -> probe_k2（真机）
      缺 agent_id 列 + 传 agent_id    HTTP UNCAUGHT_KeyError status=None err=KeyError: 'agent_id'
```

→ 证明 `app.py:268-276` 的前置校验是 `invalid_dataframe` 的**唯一**来源；没有它，缺列不但回到误诊，而且是**裸 500**。

**(4) `variance_empty`：`if len(means) < 2:` → `if means.empty:`**

```
$ pytest tests/ -q -k "variance or constant_columns or single_group"
>  assert "state_only_one_group" in unverifiable, f"unverifiable={unverifiable}"
E  AssertionError: unverifiable=[]
1 failed, 2 passed, 58 deselected in 2.00s
```

**(5) `no_agent_subset`：`if agent_id is not None:` → `if False:`**

```
$ pytest tests/ -q -k "models_endpoint or agent_subset or variance"
>  assert "state_happiness" in subset["constant_state_columns"], "agent A 的 happiness 恒定"
E  AssertionError: agent A 的 happiness 恒定
1 failed, 3 passed, 57 deselected in 1.87s
```

**(6) `js_t_shadow`：`dashboard.js` 的 `timeKeys`（4 处）→ `t`（＝回退上一轮 H5 修复）**

```
$ pytest tests/ -q -k "frontend or shadow or fit_chart"
>  assert not re.search(r"\b(?:const|let|var)\s+t\s*=", body), "buildFitChart 内不得声明名为 t 的变量（会遮蔽 i18n）"
E  AssertionError: buildFitChart 内不得声明名为 t 的变量（会遮蔽 i18n）
E  assert not <re.Match object; span=(827, 836), match='const t ='>
1 failed, 3 passed, 57 deselected in 1.79s
```

→ 上一轮"H5 修复零覆盖（回退后 55 全绿）"的缺口**已被补上**。

**(7) `js_i18n_en_removed`：删掉 en 字典里的 `fitting.none_available`**

```
$ pytest tests/ -q -k "frontend or shadow or fit_chart"
>  assert source.count("fitting.none_available':") == 2, "该 i18n 键应中英双语齐全"
E  AssertionError: 该 i18n 键应中英双语齐全
E  assert 1 == 2
1 failed, 3 passed, 57 deselected in 1.94s
```

**(8) `js_btn_nodisable`：删掉 `if (btn) btn.disabled = !anySelectable;`**

```
$ pytest tests/ -q -k "frontend or shadow or fit_chart"
>  assert "btn.disabled = !anySelectable" in source
1 failed, 3 passed, 57 deselected in 2.19s
```

**(9) `js_selection_weak`：`fitSelectionBlocked()` 函数体改成 `return false;`（函数名与其余源码字符串全部保留）—— 弱断言**

```
$ cd %TEMP%\l1signoff\mut; python -X utf8 -m pytest tests/ -q -k "frontend or shadow or fit_chart"
4 passed, 57 deselected in 2.02s              <- 测试全绿：这条"全禁用禁止拟合"测试对行为零覆盖

$ cd %TEMP%\l1signoff\mut; node %TEMP%\l1signoff\scripts\k3_ui.js %TEMP%\l1signoff\mut %TEMP%\l1signoff\bodies
K3-B) 全模型 needs_manual_mapping：按钮 disabled / runFitting 是否拦截
  btn.disabled = true  (要求 true)
  sel.value = ""  selectedIndex = -1  全 disabled = true
  sel.dataset.allDisabled = "1"
  fitSelectionBlocked() = false  (要求 true)          <- 行为已坏，测试抓不到
  runFitting 后 /api/fit 请求数 = 1  (要求 0 —— 入口拦截)   <- 拦截失效
  statusText = "未知模型名 'Unknown model \"\". Choose: [...]'"   <- 正是本轮要消灭的不可读错误
  fitKPIs 长度 = 0
K3-D [b] 正常 payload 但被强制置空 value（selectedIndex=-1）
      sel.value = ""  selectedIndex = -1  fitSelectionBlocked() = false  (要求 true)
```

→ 该测试是源码字符串 grep（`"fitSelectionBlocked" in source` + `"btn.disabled = !anySelectable" in source` + i18n 计数），**不执行 JS**；把判断逻辑掏空后 4 条断言仍全部通过。对比之下，同一提交里 `test_build_fit_chart_does_not_shadow_i18n_function` 虽然也是源码断言，但用了正则且覆盖了变量声明形态，所以 (6) 能抓到。

### 2.4 K3/K4 前端真实执行（node + 最小 DOM/Plotly 桩，真实 `dashboard.js` 源码）

`base` 上的完整结果（`k3_ui.js` / `k4_race.js` / `k3c_real.js`）：

```
K3-A) 正常数据: btn.disabled=false  sel.value="wellbeing" selectedIndex=3  blocked=false
K3-B) 全禁用:   btn.disabled=true   sel.value="" selectedIndex=-1 全disabled=true
                dataset.allDisabled="1"  blocked=true
                statusText="当前数据下没有可直接拟合的模型（可用状态列过少或全为常量）。"
                runFitting 后 /api/fit 请求数 = 0   statusText 不变   fitKPIs 长度=0
K3-C) 只有 logistic（真实 payload models_only_logistic.json）:
                options = X:square_law X:linear_law X:influence X:wellbeing .:logistic X:lotka_volterra X:resource_competition
                btn.disabled=false  sel.value="logistic" selectedIndex=4  选中项 disabled=false
                blocked=false  currentStateMapping(logistic)={"population":"state_education"}
                runFitting 发出请求数=1  model_name="logistic"
K3-D) [a] 全禁用 payload: value="" selectedIndex=-1 blocked=true
      [b] 正常 payload 但 sel.value=""  : blocked=true
      [c] selectedIndex 手动置 -1       : blocked=true
      [d] fitModel 元素不存在            : blocked=true
K3-E) runSimulation 端到端（全禁用 payload）:
      /api/params -> /api/run -> /api/data -> /api/models
      btn.disabled = true
      statusText 最终 = "仿真完成"        <- 覆盖了 none_available 说明
      statusDot.className = "dot ok"
      对照（有可拟合模型）: btn.disabled=false statusText="仿真完成"

K4-5a) 竞态：5 次快速切换 agent
      in-flight /api/models = 5   URL = ?agent_id=a, b, c, d, e
      先返回 agent_id=e => 下拉 = MODEL_FROM_E
      后返回 agent_id=a => 下拉 = MODEL_FROM_A      <- 陈旧响应覆盖
      此时 fitAgent 的值 = "e"
K4-5b) /api/models 返回 400 时
      [正常]          下拉=wellbeing_model  btn.disabled=false allDisabled="" blocked=false
      [切到 400 的 agent] 下拉=wellbeing_model  btn.disabled=false allDisabled="" blocked=false
      => 400 被静默吞掉，状态陈旧，用户可用错误 agent 的模型点拟合
```

### 2.5 K4 后端（`k4_models.py` / `k4_residual2.py`，真实代码路径）

```
K4-1 /api/models 按 agent 子集评估（agent A 恒定 / agent B 变化）
  全表（不传 agent_id）  HTTP 200 usable=['state_happiness', 'state_stress'] constant=[] unverifiable=[]
  agent A 子集           HTTP 200 usable=['state_stress'] constant=['state_happiness'] unverifiable=[]
    [全表]    wellbeing directly_fittable=True  needs_manual=False missing=[]      suggested={'happiness':'state_happiness','stress':'state_stress'}
    [agent A] wellbeing directly_fittable=False needs_manual=True  missing=['happiness'] suggested=None

K4-2 只有一个有效时间分组 / 全 NaN / 常量
  4 行数据  HTTP 200 usable=['state_normal'] constant=['state_flat'] unverifiable=['state_allnan','state_only_one_group']
  "只有一个有效分组" 落点 = unverifiable
  对照：state_only_one_group 有效分组数=1 旧(means.empty)=constant 新(len<2)=unverifiable
        state_allnan        有效分组数=0 旧=unverifiable 新=unverifiable
        state_flat          有效分组数=2 旧=constant     新=constant

K4-3 异常入参
  agent_id 不存在                  HTTP 400 body={'error': "没有 agent_id='no-such-agent' 的记录。"}
  agent_id=""（HTTP ?agent_id=）   HTTP 400 body={'error': "没有 agent_id='' 的记录。"}
  df 无 agent_id 列 + 传 agent_id  HTTP 400 body={'error': '没有仿真数据或数据缺少 agent_id 列。'}
  无仿真数据 + 传 agent_id         HTTP 400 body={"error":"没有仿真数据或数据缺少 agent_id 列。"}
  无仿真数据 + 不传 agent_id       HTTP 200（全部 needs_manual_mapping=true）

K4-4 契约
  顶层键 = ['available_state_columns','constant_state_columns','models','unverifiable_state_columns','usable_state_columns']
  "resolved_columns" 是否出现在响应 = False
  "missing_states" 出现次数 = 7（每模型一次；JS 引用 0 次）

K4 残留（精确构造：唯一 state_ 列对 agent A 恒定）
  /api/models(全表)    usable=['state_education']            唯一可选 = ['logistic']      anySelectable=True
  /api/models(agent A) usable=[] constant=['state_education'] 全部 needs_manual=True      anySelectable=False
  /api/fit(agent=A, logistic, 常量列) HTTP 200 status=ok R2=0.0 converged=True bounds=[]
```

### 2.6 卫生检查

```
$ cd %TEMP%\l1signoff\base
$ python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
.............................................................            [100%]
61 passed in 63.55s (0:01:03)          （-rs 未列出任何 skip；SKIPPED 行数 = 0）
$ node --check family_abm/web/static/js/dashboard.js     -> node_check_exit=0
$ python -X utf8 tools/baseline.py --check baseline/default_seed42.json
[OK] 与基线一致：baseline\default_seed42.json            -> baseline_exit=0
$ python -m ruff check --no-cache family_abm/web/app.py tests/test_simulation_and_fitting.py --output-format concise
family_abm\web\app.py:17:28: F401 [*] `..family.roles.ROLE_REGISTRY` imported but unused
tests\test_simulation_and_fitting.py:21:39: F401 [*] `family_abm.fitting.fitter.ABMFitter` imported but unused
tests\test_simulation_and_fitting.py:22:43 / 62 / 78: F401 [*] MODEL_PARAM_NAMES / MODEL_REGISTRY / MODEL_STATE_NAMES
tests\test_simulation_and_fitting.py:624:43 / 625:47 / 66 / 82: F811 [*] Redefinition of unused …
Found 9 errors.
（对照 a6de5d4 同两文件同样命令：也是 9 errors，同名同类，仅 F811 行号 557/558 → 624/625）
$ cd F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim; git status --short
（空；本报告写入前）
```

i18n 独立检查（`i18n_check.py`）：

```
fitting.none_available          zh=OK(M) en=OK(E)
      zh: 当前数据下没有可直接拟合的模型（可用状态列过少或全为常量）。
      en: No directly fittable model for the current data (too few usable state columns,…
fitting.need_mapping / mapping_suffix / manual_suffix / warn_sentinel / warn_r2_nonpositive / warn_bounds / converged_yes / converged_no  → 中英均 OK
源文件里 "fitting.none_available':" 出现次数 = 2 ； zh 块内 = 1 ； en 块内 = 1
```

---

## 3. 新引入的问题

### P2-1 —— 全禁用的"原因说明"在跑完仿真这条主路径上被覆盖（`dashboard.js:377-378` vs `418`）

- **证据**：node 端到端 `runSimulation()`（全禁用 payload）→ `btn.disabled = true`、`statusDot.className = "dot ok"`、**`statusText = "仿真完成"`**；`fitting.none_available` 的中文说明只出现在 `loadModelInfo` 内部（`dashboard.js:418`），随后被 `dashboard.js:377-378` 的 `await loadModelInfo(); setStatus('ok', t('status.simDone'));` 覆盖。切到"拟合"标签页时 `onTabSwitch('fitting')` 只调 `buildFittingView()`（`dashboard.js:209-213` / `526-529`），既不重取 `/api/models` 也不重设状态，故说明**在主路径上永远不可见**；只有用户之后手动切换"拟合对象"下拉（`dashboard.js:449`）才会重新写出说明。
- **为什么是 P2**：提交说明把"状态栏说明原因"列为 ③ 的交付内容之一，实际用户流程里这条说明被覆盖，用户只看到一个灰按钮和一个"仿真完成"的绿点，与上一轮 P3-1"用户无从知道为什么所有模型都灰了"的体验缺口只解决了一半。
- **可达性说明（不夸大）**：默认 ABM 数据下 7 个模型都 `needs_manual_mapping=False`（我实测 `anySelectable=True`），全禁用需要"可用状态列 < 模型状态数"的退化数据，故这是**防御性/非默认路径**；但一旦命中，说明就是不可见的。
- **建议**：把 `setStatus('ok', …)` 放在 `loadModelInfo()` 之前，或让 `loadModelInfo` 把"全禁用"状态存进变量、由 `buildFittingView()` 负责显示；并在无可用模型时把 `#fitModel` 旁的非 select 提示元素一并置为可见。

### P2-2 —— 切换 agent 时的 `/api/models` 请求风暴与陈旧响应覆盖（`dashboard.js:449` + `387-420`）

- **证据**：`sel.onchange = () => { loadModelInfo(); };` 是 fire-and-forget，`loadModelInfo` 内部无去抖、无 `AbortController`、无请求序号或"仅接受最后一次"校验。node 实测：5 次快速切换 → **5 个并发 `/api/models?agent_id=…` 请求**；乱序返回时，**后到的旧响应覆盖先到的新响应**——先 resolve `?agent_id=e`（下拉变 `MODEL_FROM_E`），再 resolve `?agent_id=a`（下拉变 `MODEL_FROM_A`），此时 `fitAgent.value === "e"`。用户界面展示的是 agent A 的可拟合性评估，而拟合对象是 e —— `directly_fittable`/`needs_manual_mapping`/`suggested_mapping` 全部错配，可能把该 agent 上恒定（不可拟合）的列当成可用，或反之置灰本可用的模型。
- **连带**：`loadModelInfo` 在 `res.error || !res.models` 时于 `dashboard.js:393` 直接 `return`，不清理旧状态。实测切到 `/api/models` 返回 400 的 agent 后，下拉内容、`btn.disabled`、`sel.dataset.allDisabled` 全部保持上一个 agent 的值（`blocked=false`），用户仍可点"拟合模型"，发出的请求带着错误 agent 的模型/映射。
- **为什么是 P2**：这是本提交**新引入**的异步路径（`agent_id` 查询参数 + onchange 重取），而 H2 残留修正的全部价值都依赖"UI 上看到的评估属于当前 agent"这一前提；竞态直接破坏该前提，且现有 6 条新测试无一覆盖（`test_models_endpoint_respects_agent_subset` 只测后端纯函数）。
- **建议**：在 `loadModelInfo` 内引入"请求序号/最后一次生效"守卫（`const seq = ++modelReqSeq; … if (seq !== modelReqSeq) return;`），或对 onchange 加 ~150ms 去抖；`res.error` 分支至少清空 `sel.innerHTML` 并保持/收紧按钮禁用态。

### P3-1 —— 删除最外层 `except Exception` 兜底，非预期异常退化为裸 500（`app.py:262-363`）

- **证据**：`a6de5d4` 的 `api_fit` 末尾有 `except Exception as e: return JSONResponse({'error': f'{type(e).__name__}: {e}'}, 500)`；本提交的 diff 把它整段删掉（`git show 04ae058 -- family_abm/web/app.py` 中该 4 行是 `-`）。后果：拟合段的 `KeyError`/`TypeError`/`ZeroDivisionError`/`OverflowError`（我逐条用确定性桩验证）**全部逃出 `api_fit`**；真实 HTTP 形态实测为
  `status = 500`、`content-type = text/plain; charset=utf-8`、`body = 'Internal Server Error'`（触发条件用**真实代码路径**即可复现：`state_mapping` 指向字符串列 `agent_id` → pandas `TypeError: Cannot perform reduction 'mean' with string dtype`）。
- **影响**：① 500 的响应体不再带异常类型与信息，排障信息丢失（上一轮的 H1 验收里"服务器真 bug → 仍 500（未被吞）"是以**结构化 500 JSON** 达成的，本提交退化为无信息 500）；② 前端 `api()`（`dashboard.js:231-238`）对非 JSON 响应会在 `res.json()` 抛错后返回 `{ error: e.message }`，`statusText` 显示的是 JSON 解析错误而非真实异常。
- **为什么是 P3（而非 P1/P2）**：原始状态码仍是 500（没有被误诊成 4xx），且这条路径在默认前端流程中不易触发；但它确实是**本提交引入的错误契约退化**，属于"修 A 时顺手删了 B 的兜底"。
- **建议**：恢复一个**只做记录与结构化封装**的最外层 `except Exception`（返回 `500 + {'error': f'{type(e).__name__}: {e}', 'status': 'internal_error'}`），不要用它来把异常改成 4xx。

### P3-2 —— `/api/fit` 自身仍不校验"常量列 / 单调可用列"，`R²=0.0 + converged=True` 仍可达（`app.py:290-294`）

- **证据**：构造唯一 `state_` 列且对 agent A 恒定 → `/api/models?agent_id=A` 正确报 `usable=[]`、`anySelectable=False`（UI 全灰）；但 `/api/fit(agent_id='A', model_name='logistic', state_mapping={'population':'state_education'})` → **HTTP 200 `status=ok` `R2=0.0` `converged=True` `params_at_bounds=[]`**。前端置灰挡住了 UI 路径，但（a）任何 API 调用方不被挡，（b）叠加 §3-P2-2 的陈旧响应竞态后 UI 也可达。
- **为什么是 P3**：与上一轮 P3-2 同源，本提交把"判定"从 `/api/models` 扩展到了 `agent_id` 子集（这一步是真实改进），但**守卫仍在 UI/端点层，未下沉到 `api_fit`**。
- **建议**：在 `api_fit` 内对 `fitter._resolved_columns` 逐列做与 `/api/models` 同源的方差判据（按 `req.agent_id` 取子集），命中则 400 并复用 `invalid_input`/新增 `constant_columns` 状态；或至少在响应里带 `degenerate_columns` 警告。

### P3-3 —— `test_frontend_blocks_fit_when_no_model_is_selectable` 是纯源码 grep，行为零覆盖（`tests/…:701-713`）

- **证据**：`js_selection_weak` 突变体（`fitSelectionBlocked()` 体 → `return false;`，函数名与所有被断言字符串保留）→ `pytest -k "frontend or shadow or fit_chart"` **4 passed**；同突变体下 node 实测：全禁用场景 `fitSelectionBlocked()=false`、`runFitting` 发出 1 次 `model_name=""` 请求、`statusText = 未知模型名 'Unknown model "". Choose: [...]'`。
- **对照**：同一批新增测试里的 `test_build_fit_chart_does_not_shadow_i18n_function`（也是源码断言）在 (6) 突变下 FAILED，`test_variance_report_treats_single_group_as_unverifiable`、`test_models_endpoint_respects_agent_subset`、`test_missing_time_or_agent_column_reports_invalid_dataframe` 在各自突变下均 FAILED —— 6 条新测试里 5 条有判别力，这条没有。
- **建议**：把 `fitSelectionBlocked()` 改造成可注入 DOM 的纯函数并写断言，或把 `k3_ui.js` 那套最小 DOM 桩搬进 `tests/`（node 子进程调用），至少断言"全禁用 payload 下 `runFitting` 不发 `/api/fit`"。

### P3-4 —— 其它次要项

- `except ValueError`（`app.py:295-297`）仍偏宽：确定性桩下 `fit` 抛 `ValueError('内部 bug：数组形状不匹配')` → **400 `invalid_input`**，把服务器内部错误标成"调用方输入问题"。真机里也确实出现了这条路径：`steps=10 robust=true` 的某个模型返回 `400 invalid_input` 且 `err= `x0` violates bound constraints.` —— 这是 scipy 的**边界/初值**问题，语义上更接近 `optimizer_failed` 而非 `invalid_input`。属上一版就存在的过宽捕获，本提交未处理，且新加的 `status: 'invalid_input'` 让误诊更"像真的"。
- `/api/models` 的 400 分支不返回 `status` 字段（`app.py:218/221`：`{'error': …}`），与同提交 `/api/fit` 的 400 全部带 `status` 的约定不一致；前端 `loadModelInfo` 也不看 `status`。
- `/api/models?agent_id=`（空串）返回 `400 "没有 agent_id='' 的记录。"`：`Optional[str] = None` 使空串被当作"已指定 agent"。前端用 `(agentSel.value || '')` 做了真值保护，故 UI 不受影响，但 API 语义上"空串 ≠ 未指定"略显意外。
- `state_mapping` 指向 `time` 列 → **200 ok**（把模型拟到时间轴上），`state_mapping` 键名不匹配/只给一半/含多余键 → **200 ok**（静默忽略）：这些上一轮已指出，本提交未处理，非回归。
- 上一轮列为"可同批修"的 4 个 ruff `F811`（现 `tests/…:624-625`）未清理；`missing_states` 仍是"只写不读"字段（JS 引用 0 次）。均不阻塞。

---

## 4. 未复现 / 存疑项

1. **提交说明"robust=true -> 400 all_starts_failed"**：在我这 4 个 steps × 真机 4 个进程里成立（`resource_competition` + 显式 mapping）。但路径 B（用 `/api/models` 的 `suggested_mapping`）下 `steps=10 robust=true` 的某个模型给出的是 `400 invalid_input` + `` `x0` violates bound constraints. ``，不是 `all_starts_failed`；说明"robust=true 必然 all_starts_failed"的表述只在显式 `{'R1':'state_education','R2':'state_energy'}` 映射下成立。`api_run` 仍**无 `seed` 参数**（`app.py:89-115`），故具体 R²/具体映射组合跨进程不可复现（我实测同一请求的 `square_law robust=true` R² 在不同进程里可有数量级差异），这一点与上一轮一致，本提交未改。
2. **`state_mapping` 指向 `agent_id`（字符串列）→ 裸 500**：我用真实路径确认了 `TypeError: Cannot perform reduction 'mean' with string dtype` 逃出 `api_fit`，但**未用真实 uvicorn 进程**验证（只用 `TestClient(raise_server_exceptions=False)`），其 `text/plain: Internal Server Error` 是 Starlette 默认 500 的形态；真实 uvicorn 下响应头可能多带 `server` 等字段，结论方向不受影响。
3. **前端 `api()` 对裸 500 的实际文案**：我给出的 `Unexpected token 'I', "Internal Server Error" is not valid JSON` 是按 V8 `Response.json()` 在非 JSON 输入上的典型报错**推演**（依据是实测的 `text/plain` 响应体 + `dashboard.js:231-238` 的 `catch`）。我**没有**起真实 uvicorn + 浏览器/真实 `fetch` 复现该字符串，故只作为"信息丢失"的定性结论，不引用具体文案作为证据。
4. **前端 DOM 校验的置信度**：`K3`/`K4-5` 的结论基于 node + 最小 DOM 桩（含按 HTML 规范实现的"单选 select 无未禁用 option 时 `selectedIndex=-1`/`value=''`"）真实执行 `04ae058` 的 `dashboard.js`；我没有可用的真实浏览器/jsdom，故"浏览器实际渲染"这一层是规范级推断（与上一轮同一口径）。所有后端结论都是真实代码路径 + 真实 HTTP 响应体。
5. **"全禁用"场景在真实 ABM 数据下不可达**：默认 5 个 agent / steps 20 的数据下 7 个模型全部 `needs_manual_mapping=False`（实测），故 §3-P2-1 的说明被覆盖、以及 K3 的全禁用行为，都只在构造/退化数据上观察到；我未尝试找到能自然产生"可用状态列 < 模型状态数"的 ABM 参数组合。
6. **阈值灰带（`VARIANCE_EPS=1e-9` 绝对阈值、与 `fitter.py` 的 `1e-5` 告警阈值不一致）**：本提交未改（上一轮列为"可同批修"），我按构造值说明分类行为，未在真实数据上找到落在 1e-9…1e-5 灰带的列。

---

## 5. 放行结论

**放行（建议把 §3 的 P2-1 / P2-2 作为紧随其后的一批小修）。**

3 项"必须先修"逐条判定：

| 必须先修项 | 判定 | 关键实测证据 |
|---|---|---|
| ①（上一轮 P1）哨兵判定必须先于 `predict` | **已修复** | 真机 steps 10/20/40/60 + `robust=false` → 200 `model_not_applicable` + warning + 空 trace + `prediction_skipped=true` + **`predict` 调用数 0**；全量真机扫描 **`HTTP>=500` 组合数 = 0**；反向突变体完整复现 `500 prediction_failed` 且 `pytest` 2 failed |
| ②（上一轮 P2）收窄 `except KeyError`，缺列明确报错 | **已修复** | 缺 `time`/缺 `agent_id` → 400 `invalid_dataframe` + 列出当前列 + 无"未知模型名"；只有未知 `model_name` → 400 `unknown_model`；反向突变体把缺 `agent_id` 变回 `400 unknown_model`（`pytest` 1 failed） |
| ③（上一轮 P3-1）全禁用时禁止拟合 | **已修复（说明文案在主导路径被覆盖）** | node 真实执行：`btn.disabled=true`、`blocked=true`、`runFitting` 发 0 请求、状态栏显示原因；`logistic` 单可用时按钮可用且默认选中（真实 payload 交叉验证）；空串/`selectedIndex=-1` 均 true |

**放行理由**：3 项全部在功能层面兑现，且每一项都用"真机 + 反向突变体"做了双向验证；`pytest` 61 passed **0 skip**、`node --check` exit 0、基线 `[OK]`、**无新增 ruff 问题**、无残留字段引用（`resolved_columns`/`fin`/`prediction_error` 均干净）、i18n 中英齐全、6 条新测试中 5 条有判别力（其中 H5 的零覆盖缺口已补上）。没有发现新的 5xx 回归、没有发现把输入问题错报成 5xx、也没有发现被吞掉的真实异常改变状态码。

**为什么不是"无条件放行"**：本提交在修 ① 的同时**删掉了 `api_fit` 的最外层 `except Exception`**，把其它非预期异常从"结构化 500 JSON"退化成"裸 500 `text/plain`"（§3-P3-1，我用真实 HTTP 抓到了 `content-type: text/plain` + `Internal Server Error`）——这是新引入的错误契约退化；另外 ③ 的"原因说明"在跑完仿真这条主路径上被 `setStatus('ok','仿真完成')` 覆盖（§3-P2-1），H2 的 `agent_id` 修正则被**无去抖/无序号的 onchange 竞态**削弱（§3-P2-2：5 次切换 5 个并发请求 + 陈旧响应覆盖 + 400 静默吞掉导致状态陈旧）。这三条都不改变"3 项必须先修已达成"的结论，但都是本提交自己带进来的新缺口。

### 建议紧随其后修（不阻塞本次放行）

1. **（P2-1）** 调整 `dashboard.js:377-378` 的顺序，或让 `buildFittingView()` 负责显示"无可拟合模型"的原因，确保跑完仿真后用户能看到说明。
2. **（P2-2）** 给 `loadModelInfo` 加"最后一次请求生效"守卫（或 onchange 去抖）；`res.error` 分支不要静默 return，至少清空下拉并收紧按钮禁用态。
3. **（P3-1）** 恢复一个只做结构化封装的最外层 `except Exception`（`500 + {'error': f'{type(e).__name__}: {e}', 'status': 'internal_error'}`）。
4. **（P3-2）** 把常量列守卫下沉到 `api_fit`（按 `req.agent_id` 取子集做与 `/api/models` 同源的方差判据）。
5. **（P3-3）** 把 `test_frontend_blocks_fit_when_no_model_is_selectable` 从源码 grep 改为可执行断言（至少覆盖"全禁用下 `runFitting` 不发 `/api/fit`"）。
6. 顺带：`except ValueError` 收窄到已知的拟合输入错误；`/api/models` 的 400 补 `status`；清理 `tests/…:624-625` 的 4 个 `F811`；`api_run` 补 `seed` 让复核数字可复现；把 `1e-9` 绝对阈值改为相对跨度并与 `fitter.py` 的 `1e-5` 对齐。
