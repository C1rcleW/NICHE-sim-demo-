# L1 收尾确认报告

- **验证对象**：`cad2fb6` `fix(web): L1 收尾——恢复错误契约、竞态防护、前端行为测试（含突变验证）`
  - `git log --oneline -3` → `cad2fb6 / 04ae058 / a6de5d4`；`git rev-parse HEAD` → `cad2fb69d2fd4e2cba8421793de82e991d8e4a2f`（哈希确认一致）
- **被验证的上一轮报告**：`audits/l1_final_signoff.md`（对 `04ae058` 的复核，提出 3 个新缺口 **P3-1** 错误契约退化 / **P2-1** 原因说明被覆盖 / **P2-2** 竞态，以及弱断言 **P3-3**）
- **仓库**：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`
  - 验证开始时 `git status --short` → 空；**完成全部实验后、写入本报告前仍为空**；写入本报告后 → 仅 `?? audits/l1_signoff_confirmation.md`（唯一新增写入）
- **环境**：Python 3.14.3 / numpy 2.4.3 / pandas 3.0.2 / scipy 1.17.1 / fastapi 0.136.1 / httpx 0.28.1 / **Node v24.14.0（可用）**
- **只读约束遵守情况**：全部突变与实验在 `%TEMP%\l1conf\` 下的仓库副本（`base`＝`cad2fb6`；`a6de5d4`＝用 `git archive` 导出的对照树；`mut_*`＝注入突变后的副本）中进行。`ruff` 一律 `--no-cache`；`pytest` 一律 `-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`；**未运行 examples 绘图路径**；**未修改仓库任何源码/测试/配置/已有报告**，仓库内唯一新增写入是本文件。
- **默认立场**：先认定修复为假/不完整/有新副作用，逐条用真机（真实 uvicorn 进程 + TestClient）、确定性桩、独立自写的 Node harness、以及 11 个突变体反证。
- 复现脚本：`%TEMP%\l1conf\scripts\`（`m1_real.py` / `m1_uvicorn.py` / `m1_stub.py` / `m1_residual.py` / `m2m3.js` / `mutate.py` / `run_mutants.ps1`）

---

## 1. 判定汇总表

| 项 | 判定 | 我的实测 | 要求 | 差异 |
|---|---|---|---|---|
| **M1 错误契约恢复**（上一轮 P3-1） | **部分修复** | ① **真机 uvicorn**（`m1_uvicorn.py`，真实 HTTP）：`state_mapping={'happiness':'agent_id','stress':'state_stress'}` → `robust=False` **HTTP 500 `content-type: application/json`** `{"error":"TypeError: Cannot perform reduction 'mean' with string dtype","status":"fitting_error"}`；`robust=True`（**前端 runFitting 实际用的值**）同样 **application/json 500 fitting_error**。② **真机 TestClient**（`raise_server_exceptions=False`）复现同一结果。③ **确定性桩 12 种异常**（`m1_stub.py`）：`ValueError→400 invalid_input`、`RuntimeError→400 all_starts_failed`、`KeyError/TypeError/ZeroDivisionError/OverflowError/MemoryError/IndexError/AttributeError/FloatingPointError/Exception→500 fitting_error`（**全部 `application/json`，无一 text/plain**）。④ **反向实验**（`mut_no_fallback`＝删掉 `except Exception` 整段）：TestClient → `500 text/plain; charset=utf-8` / `Internal Server Error`；**真机 uvicorn** → 同样 `text/plain`（robust 两种取值都是）；`pytest tests/ -q` → **2 failed, 62 passed**，FAILED ＝ `test_unexpected_fitting_error_keeps_structured_json`、`test_real_string_column_mapping_yields_structured_500`（**新测试确有判别力**） | 拟合中的未预期异常返回 application/json + 500 + `status=fitting_error`；反向删兜底应退化为 text/plain 且被测试抓到 | **主路径达成**。**差异 1（残余）**：新兜底只包住 `app.py:292-296` 的两次 fit 调用，**未包住** `app.py:280-286` 的 `make_fitter`、`app.py:326`（主成功路径）与 `app.py:323`（optimizer_failed 分支）的 `summary_json()`。4 条探针实测（`m1_residual.py`）：`R1 optimizer_failed+summary_json() 抛`、`R2 make_fitter 抛 TypeError`、`R2b make_fitter 抛 ValueError` 在 `cad2fb6` 全部退化为 **text/plain 500**，而**同一个探针在 `a6de5d4` 上分别是 application/json 500 / 500 / 400** —— 即**新兜底比 `a6de5d4` 被删掉的那个更窄**，契约恢复不完整。**差异 2**：兜底把"调用方输入错误"（state_mapping 指向字符串列）归为 **500**（服务端错误）而不是 400，与上一轮 P3-4"过宽捕获"同类。**差异 3**：新增的 `test_real_string_column_mapping_yields_structured_500`（`tests/…:753`）断言写成 `status_code in (400,500)`（`tests/…:767`）+ `status in {"fitting_error","invalid_input"}`，**无法判别 400/500 误分类**，只有 content-type 那一句在起作用 |
| **M2 竞态防护**（上一轮 P2-2） | **已修复（主体）／部分** | ① **代码就位**：`dashboard.js:392-393` `_modelInfoSeq` / `_modelInfoDebounce`；`:398` `const seq = ++_modelInfoSeq;`；`:409` `if (seq !== _modelInfoSeq) return false;`；`:443-446` `scheduleLoadModelInfo()` 200ms 防抖；`:475` onchange 改走防抖。② **独立自写 harness 真执行**（`m2m3.js`，不复用仓库脚本）：真乱序（A 先发、B 后发，**B 先 resolve、A 后 resolve**）→ `in-flight=2`，最终 `fitRunBtn.disabled=false`、`blocked=false`、`allDisabled=""`，且下拉 `innerHTML` 含 `beta_model` **不含** `alpha_model` → **最新响应胜出**；正向顺序同样收敛到最新。③ **反向实验**（`no_seq_guard`＝删掉 `:409` 那一行）：**仓库 harness FAIL**（`[FAIL] 最终采用最新请求的结果（按钮可用）`、`[FAIL] 陈旧响应未覆盖新响应`，exit 1）＋ **我的独立 harness FAIL 4 项**（M2-1×3、M2-2）＋ `pytest` **1 failed, 63 passed**（`test_dashboard_behavior_harness_passes`）→ **竞态测试有效，不是空转**。④ 防抖实测：5 次快速 `onchange` → 立刻 1 个请求、300ms 后累计 2 个（含 runSimulation 那次），**5 次切换合并为 1 个请求**（旧版为 5 个并发）。⑤ `/api/models` 返回 `{error}` → `loadModelInfo` 返回 `false` 且 `setStatus('error', "没有 agent_id='zzz' 的记录。")` 可见 | 请求序号＋陈旧响应丢弃；agent 下拉防抖；`/api/models` 失败时给出状态 | **三项断言都成立**。**差异 1（P3）**：防抖把"陈旧窗口"从一次 RTT **放大到 ≥200ms** —— 实测切到 agent B 后立即点拟合，发出的请求是 `{"model_name":"logistic","agent_id":"B","robust":true,"state_mapping":{"population":"state_from_A"}}`，即 **agent_id=B 却用了 A 的评估映射**（旧版同样有此问题，但窗口更短，属加重而非全新）。**差异 2（P3）**：`/api/models` 失败后**下拉/按钮仍保留上一个 agent 的状态**（实测 `before={dis:false,all:"",html:true}` / `after={dis:false,all:"",html:true,blocked:false}`）→ 上一轮"400 被静默吞掉导致状态陈旧"只修了状态文案，未清选择态。**差异 3（P3）**：序号守卫把"陈旧"与"不可拟合"合并成同一个 `false`，`runSimulation` 因此会把**可拟合**的仿真报成 `none_available`（实测，见 §2 M2-8）。**差异 4（P3）**：防抖**零覆盖** —— `no_debounce` 突变体（onchange 回退成直接 `loadModelInfo()`）→ 仓库 harness exit 0、`pytest` **64 passed** 全绿 |
| **M3 原因说明可见**（上一轮 P2-1） | **已修复（主路径）** | ① **Node 真执行 runSimulation 全链路**（`m2m3.js` M3-1，请求序 `/api/params → /api/run → /api/data → /api/models`）：全禁用 payload → `statusText="No directly fittable model for the current data (too few usable state columns, or all are constant)."`、`statusDot.className="dot"`（**不是 `dot ok`**）、`fitRunBtn.disabled=true` → **不再被"仿真完成"覆盖**。② 仅一个可用 → `statusText="Simulation complete"`、按钮可用（`hasFittable=true` 分支正确）。③ `loadModelInfo()` 全禁用返回 `false`；此前置空 `statusText` 后调 `buildFittingView()` → 文本被重新写为 `none_available` → **切到拟合页也说明原因**。④ 反向突变 `runsim_overwrite`（把 `dashboard.js:379-384` 还原成 `await loadModelInfo(); setStatus('ok', t('status.simDone'));`）→ 仓库 harness **exit 0**、`pytest` **64 passed** 全绿 | 全禁用时状态栏显示 none_available 而非"仿真完成"；切到拟合页也说明 | **主路径达成，代码写法正确**（`loadModelInfo` 返回布尔、调用方决定状态）。**差异 1（P3）**：`/api/models` **请求失败**时，`loadModelInfo` 写的错误文案会被 `runSimulation` 立刻覆盖成 `none_available` —— 实测 `statusText` 最终为 `"No directly fittable model …"`，而真实原因（网络/500）不可见（这与 P2-1 是**同一个"覆盖"反模式，只是搬到了新加的错误分支上**）。**差异 2（P3）**：`/api/models` 失败时 `dataset.allDisabled` 保持 `undefined`，`buildFittingView()` 因此**什么都不说明**（实测文本被清空后未被重写）。**差异 3（P3）**：`runSimulation` 这条主线**零测试覆盖** —— `runsim_overwrite` 突变体全绿 |
| **M4 弱断言修复与 harness 判别力**（上一轮 P3-3） | **部分修复** | ① `test_dashboard_behavior_harness_passes`（`tests/…:774`）**确实调用 node**：`tests/…:786-791` 用 `shutil.which("node")` + `subprocess.run([node, harness], capture_output=True, timeout=120)`，当前环境 node 可用，`-k "dashboard_behavior or frontend_blocks"` → **2 passed in 1.99s，无 skip**。harness 覆盖 3 场景（全禁用 / 仅一个可用 / 乱序）✅。② **4 个必做突变**（`run_mutants.ps1`，每个突变体分别跑「仓库 harness」与「全量 pytest」）：**(a)** `fitSelectionBlocked()` 恒 `return false` → harness **FAIL**（`[FAIL] fitSelectionBlocked() 返回 true`，exit 1）＋ pytest **1 failed, 63 passed**（`test_dashboard_behavior_harness_passes`）→ **抓到**；**(b)** 删掉 `if (btn) btn.disabled = !anySelectable;` → harness **FAIL**（`[FAIL] 拟合按钮被禁用`）＋ pytest **2 failed**（旧的 `test_frontend_blocks_fit_when_no_model_is_selectable` **也**抓到）→ **抓到**；**(c)** 删掉 `if (seq !== _modelInfoSeq) return false;` → harness **FAIL**（场景 3 两项）＋ pytest **1 failed** → **抓到**；**(d)** 把 harness 调用换回纯源码 grep → `grep_only+blocked_false` **64 passed**、`grep_only+no_seq_guard` **64 passed**（(a)(c) **失去判别力**）、`grep_only+no_disable_btn` **2 failed**（(b) 仍被字符串断言抓到）→ **判别力部分丧失（不是全部）**。③ 三种 harness 覆盖场景均实测有效 | pytest 真调用 node harness；harness 覆盖三场景；4 个突变被 harness 或 pytest 抓到 | **4 条自证突变全部独立复现（提交说明属实）**。**差异（P3，覆盖缺口）**：harness **从不执行 `runSimulation`**（全文 0 次），故本提交的头号交付 P2-1 无覆盖（`runsim_overwrite` 全绿）；失败分支（`no_status_on_failure` → harness exit 0 + 64 passed）与防抖（`no_debounce` → 全绿）同样无覆盖；「被拦截时不发起 /api/fit 请求」这条断言在所选 payload 下**是空转的**（全禁用模型的 `needs_manual_mapping=true`，`runFitting` 会被 `mapping === undefined` 提前拦住；实测 (a) 突变下该检查仍是 `实际 0 次`）。**桩不忠实**至少 3 处（见 §3-P3-5） |
| **M5 回归面** | **通过（无新增问题）** | ① `pytest tests/ -q -rs` → **64 passed，`-rs` 未列出任何 skip**（SKIPPED 行数 0）——在 `cad2fb6` 副本上 78.90s，在**仓库内直跑** 72.40s，两次结果一致；node 可用已确认，harness 测试未 skip（`-k` 单跑 2 passed / 1.99s）。② `node --check` 两文件 **exit 0**（`dashboard.js` / `tools/check_dashboard_behavior.js`）；`python tools/baseline.py --check baseline/default_seed42.json` → **`[OK] 与基线一致` exit 0**。③ `ruff check --no-cache family_abm tests tools`：**HEAD 16 errors**（全在 `family_abm/`：`family_member.py` F401+5×E701、`relationships.py` F401、`lanchester.py` F401、`resources.py` F401、`viz/plots.py` 6×F401+1×F841）vs **`a6de5d4` 28 errors** → **净减 12，无新增**；`tests/` 与 `tools/` **0 error**。④ 全仓库 grep：`prediction_error` **0 命中**、`fin` 单词 **0 命中**、`resolved_columns` 作为响应字段 **0 命中**（只剩 fitter 内部 `_resolved_columns`）、`ROLE_REGISTRY` 只剩 `roles.py:54` 定义处；`missing_states` 仍是"只写不读"（`app.py:247` 生产 + tests 断言，**JS 引用 0 次**，非本提交引入）。⑤ `tools/check_dashboard_behavior.js` **已入库**（`git ls-files tools/` 有它），`git check-ignore` exit 1（**未被 .gitignore 排除**）。⑥ **完成全部实验后** `git status --short` → 空；写入本报告后 → 仅 `?? audits/l1_signoff_confirmation.md` | 全绿无 skip；`node --check` 通过；基线一致；ruff 无新增；无死字段引用；新增 JS 入库；工作区只有本报告 | **无新增回归**。**备注**：本仓库**无 CI 配置**（无 `.github/`、无 CI yml），且 `pyproject.toml` 的 `dev` extra 不含 node —— 在没装 node 的机器上唯一的"前端行为测试"会**静默 skip**（`pytest.skip`），P3-3 等于退回纯 grep 且无任何红灯信号。 |
| **额外：提交说明自证** | **属实** | 「恢复错误契约（真机路径 application/json）」✅（我另用真实 uvicorn 复验）；「竞态序号＋防抖」✅；「原因说明可见」✅（主路径）；「harness 三场景＋三个突变 FAIL」✅（我逐条独立复现）；「pytest 64 passed / node --check 两文件 exit 0 / 基线 [OK] / ruff 本轮改动范围 All checks passed」✅ **四条全部可复现**；「tests 移除未使用导入与 F811、app.py 移除 ROLE_REGISTRY、web/__main__.py 清理」✅（ruff 计数 28→16 印证） | 提交说明与实测一致 | 无差异。唯一措辞偏乐观处是「恢复结构化错误契约」未区分"只覆盖 fit 调用"这一点（见 M1 差异 1） |

### 结论一句话

**上一轮点名的 3 个新缺口在"被诊断出的那条路径"上都被真实修掉了，而且证据链完整**：错误契约在**真实 uvicorn** 下已是 `application/json` + 500 + `fitting_error`（删掉兜底即退化 text/plain，且 2 条新测试立刻 FAIL）；竞态守卫经**真乱序**验证"最新响应胜出"（删掉守卫则仓库 harness、我的独立 harness、pytest 三方同时 FAIL）；状态栏在全禁用时显示原因而非"仿真完成"。**弱断言 P3-3 也补上了真执行 JS 的行为测试**，4 个突变实验我全部独立复现。**但它们仍然各有"最后一口气"**：① 新兜底比 `a6de5d4` 被删的那个**更窄**（`make_fitter`/`summary_json` 仍会退化为 text/plain 500，探针实测 3 条路径），且把调用方输入错误归为 500；② 竞态修好了"陈旧响应覆盖"，但防抖把陈旧窗口放大到 200ms（实测发出了 `agent_id=B` + A 的 `state_mapping` 的请求）、失败后遗留旧选择态、并把"陈旧"误当"不可拟合"；③ P2-1 的修复代码本身**零测试覆盖**（还原成旧代码全绿）。**没有发现 P1/P2 级新回归**，`pytest 64 passed / 0 skip`、`node --check` exit 0、基线 `[OK]`、ruff **16 vs 28 净减**、无死字段引用、工作区干净。

---

## 2. 反证 / 突变实验记录（命令 + 实测输出）

所有命令在 `%TEMP%\l1conf\` 下执行；`base` ＝ `cad2fb6` 的仓库副本，`a6de5d4` ＝ `git archive a6de5d4` 导出的对照树，`mut_*` ＝ 每例从 `base` 重新复制并注入突变。

### 2.1 M1 —— 真机（真实 uvicorn 进程 + 真实 HTTP）

```
$ cd %TEMP%\l1conf\base; python -X utf8 %TEMP%\l1conf\scripts\m1_uvicorn.py %TEMP%\l1conf\base
uvicorn up on http://127.0.0.1:51830
/api/run -> 200
robust=False -> HTTP 500  content-type=application/json
    body[:160]={"error":"TypeError: Cannot perform reduction 'mean' with string dtype","status":"fitting_error"}
robust=True  -> HTTP 500  content-type=application/json
    body[:160]={"error":"TypeError: Cannot perform reduction 'mean' with string dtype","status":"fitting_error"}
```

TestClient（`raise_server_exceptions=False`，`m1_real.py`）同结论；同一脚本在 `mut_no_fallback` 上：

```
$ cd %TEMP%\l1conf\mut_no_fallback; python -X utf8 %TEMP%\l1conf\scripts\m1_uvicorn.py %TEMP%\l1conf\mut_no_fallback
uvicorn up on http://127.0.0.1:55986
/api/run -> 200
robust=False -> HTTP 500  content-type=text/plain; charset=utf-8
    body[:160]=Internal Server Error
robust=True  -> HTTP 500  content-type=text/plain; charset=utf-8
    body[:160]=Internal Server Error
```

`pytest` 在同一突变体上（`-rf --tb=line`）：

```
FAILED tests/test_simulation_and_fitting.py::test_unexpected_fitting_error_keeps_structured_json
FAILED tests/test_simulation_and_fitting.py::test_real_string_column_mapping_yields_structured_500
2 failed, 62 passed in 77.49s
（`test_real_string_column_mapping_yields_structured_500` 的失败点是 content-type 断言；
  其 `status_code in (400,500)` / `status in {"fitting_error","invalid_input"}` 两句**在裸 500 下仍然成立**）
```

### 2.2 M1 —— 各异常类型的最终状态码表（`m1_stub.py`，确定性桩，逐条实测）

| 抛出位置 | 异常类型 | 最终 HTTP | content-type | status |
|---|---|---|---|---|
| `app.py:292-296` fit 调用内 | `ValueError`（含"内部 bug：数组形状不匹配"） | **400** | application/json | `invalid_input` |
| 同上 | `RuntimeError` | **400** | application/json | `all_starts_failed` |
| 同上 | `KeyError` | **500** | application/json | `fitting_error` |
| 同上 | `TypeError`（string dtype，真实路径） | **500** | application/json | `fitting_error` |
| 同上 | `ZeroDivisionError` | **500** | application/json | `fitting_error` |
| 同上 | `OverflowError` | **500** | application/json | `fitting_error` |
| 同上 | `MemoryError` | **500** | application/json | `fitting_error` |
| 同上 | `IndexError` | **500** | application/json | `fitting_error` |
| 同上 | `AttributeError` | **500** | application/json | `fitting_error` |
| 同上 | `FloatingPointError` | **500** | application/json | `fitting_error` |
| 同上 | 裸 `Exception` | **500** | application/json | `fitting_error` |
| `app.py:280-286` `make_fitter` | `KeyError` | **400** | application/json | `unknown_model` |
| `app.py:280-286` `make_fitter` | `TypeError` / `ValueError` | **逃出端点** → 500 | **text/plain** | 无 |
| `app.py:326` 主成功路径 `summary_json()` | `RuntimeError`/`AttributeError`/`TypeError` | **逃出端点** → 500 | **text/plain** | 无 |

**逐路径与 `a6de5d4` 对照（`m1_residual.py`，同一桩、同一次运行）**：

```
######## cad2fb6 (base) ########
R1 optimizer_failed + summary_json() raises          -> HTTP 500 ctype=text/plain; charset=utf-8    body=Internal Server Error
R2 make_fitter raises TypeError                      -> HTTP 500 ctype=text/plain; charset=utf-8    body=Internal Server Error
R2b make_fitter raises ValueError                    -> HTTP 500 ctype=text/plain; charset=utf-8    body=Internal Server Error
R3 success path summary_json() raises                -> HTTP 500 ctype=text/plain; charset=utf-8    body=Internal Server Error

######## a6de5d4 (older, wider fallback) ########
R1 optimizer_failed + summary_json() raises          -> HTTP 500 ctype=application/json             body={'error': 'RuntimeError: summary blew up in optimizer_failed branch'}
R2 make_fitter raises TypeError                      -> HTTP 500 ctype=application/json             body={'error': 'TypeError: bad mapping type'}
R2b make_fitter raises ValueError                    -> HTTP 400 ctype=application/json             body={'error': 'bad name'}
R3 success path summary_json() raises                -> HTTP 500 ctype=text/plain; charset=utf-8    body=Internal Server Error
```

→ **新兜底的作用域比 `a6de5d4` 的旧兜底窄**：`a6de5d4` 的 `except Exception`（其 `app.py:313`）覆盖 `254-303` 行（含 `make_fitter` 与 optimizer_failed 分支里的 `summary_json()`），`cad2fb6` 的 `except Exception`（`app.py:305-310`）只覆盖 `292-296`。

**可达性说明（不夸大）**：`make_fitter` 只对未知模型名抛 `KeyError`（`fitter.py:436-437`），`state_mapping` 受 pydantic `dict[str,str]` 约束，`ABMFitter.bounds` 恒被规范化为列表（`fitter.py:298-308`）且 `summary_json()` 内部对易抛点都包了 try（`fitter.py:382-398`）—— 故 R1/R2/R2b/R3 是**防御面**而非当前可达输入；我把它们记为"契约不完整"而非线上 bug。

### 2.3 M2/M3 —— 独立自写 Node harness（`m2m3.js`，真执行 `dashboard.js`）

```
$ node %TEMP%\l1conf\scripts\m2m3.js %TEMP%\l1conf\base\family_abm\web\static\js\dashboard.js
== M3-1) runSimulation end-to-end, ALL DISABLED (real call chain) ==
   requests: /api/params , /api/run , /api/data , /api/models
   statusText = "No directly fittable model for the current data (too few usable state columns, or all are constant)."
   statusDot  = "dot"   fitRunBtn.disabled = true
[PASS] M3-1 status bar shows none_available (not "Simulation complete")
[PASS] M3-1 fit button disabled
== M3-2) runSimulation end-to-end, ONE AVAILABLE ==
   statusText = "Simulation complete"   fitRunBtn.disabled = false
[PASS] M3-2 status bar shows simDone when fittable
== M3-3) buildFittingView() after all-disabled load ==
   loadModelInfo() returned false
[PASS] M3-3 switching to fitting tab explains the reason
== M3-4) buildFittingView() when /api/models FAILED (no allDisabled flag) ==
   loadModelInfo() -> false; status after load = "boom-network"; after buildFittingView = "<<wiped>>"
[FAIL] M3-4 buildFittingView still explains after a failed /api/models
== M3-5) runSimulation when /api/models fails: which message wins ==
   statusText = "No directly fittable model for the current data (too few usable state columns, or all are constant)."  btn.disabled=true
[FAIL] M3-5 network error message survives runSimulation
== M2-1) TRUE out-of-order: A fires, B fires, B resolves FIRST, A LAST ==
   in-flight /api/models = 2
   returns: A=false B=true; fitModel.value="logistic"; fitRunBtn.disabled=false; blocked=false; allDisabled=""
[PASS] M2-1 exactly two requests in flight / [PASS]×3 newest (B) wins
== M2-2) SAME but responses distinguishable by model name ==
   fitModel.value = "beta_model"  innerHTML has alpha=false beta=true
[PASS] M2-2 dropdown reflects the NEWEST response (beta)
== M2-3) reverse direction: A resolves FIRST, B LAST (normal order) ==
[PASS] M2-3 in-order case still ends on newest
== M2-4) debounce: rapid agent switches ==
   /api/models right after 5 rapid switches = 1; after 300ms = 2
[PASS] M2-4 5 rapid switches coalesce into 1 request
== M2-5) STALE WINDOW: switch agent, click Fit within 200ms ==
   /api/fit body = {"model_name":"logistic","agent_id":"B","robust":true,"state_mapping":{"population":"state_from_A"}}
   [BUG ] state_mapping uses A's evaluation while agent_id=B (stale window)
== M2-7) /api/models returns res.error (HTTP 4xx JSON) ==
   returned false; statusText="没有 agent_id='zzz' 的记录。"; btn.disabled=false; allDisabled=undefined
[PASS] M2-7 error surfaced in status bar / [PASS] returns false on API error
== M2-7b) good load (button enabled) then /api/models 400: is state reset? ==
   before={"dis":false,"all":"","html":true}
   after ={"dis":false,"all":"","html":true,"blocked":false}
   [BUG ] stale selection state after a failing /api/models
== M2-8) seq guard conflates "stale" with "nothing fittable" inside runSimulation ==
   runSimulation's own /api/models in flight = 1
   after a superseding load: pending = 2
   statusText = "No directly fittable model for the current data (too few usable state columns, or all are constant)."   btn.disabled=false
   [BUG ] latest response WAS fittable, yet runSimulation reports none_available
RESULT: FAIL (5) -> [...]
```

同一脚本在 `mut_no_seq_guard` 上（删掉 `dashboard.js:409` 的守卫）：

```
[FAIL] M2-1 newest (B) response wins: button enabled
[FAIL] M2-1 newest (B) response wins: selection not blocked
[FAIL] M2-1 newest (B) response wins: allDisabled not set
[FAIL] M2-2 dropdown reflects the NEWEST response (beta)
RESULT: FAIL (8) -> [...]
```

→ **竞态守卫是真的在起作用**（不是"测试写得太松所以永远绿"）：拿掉守卫后，真乱序下陈旧响应确实覆盖了新响应。

### 2.4 M4 —— 11 个突变体 ×（仓库 harness ｜ 全量 pytest）

每条命令：`robocopy base → mut_<name>` → `python scripts/mutate.py <name> mut_<name>` → `cd mut_<name>` → `node tools\check_dashboard_behavior.js` → `python -X utf8 -m pytest tests/ -q -rf --tb=no -p no:cacheprovider`。

| # | 突变体 | 内容 | node harness | pytest | 结论 |
|---|---|---|---|---|---|
| (a) | `blocked_false` | `fitSelectionBlocked()` 体 → `return false;` | **FAIL (exit 1)** `[FAIL] fitSelectionBlocked() 返回 true` | **1 failed, 63 passed** → `test_dashboard_behavior_harness_passes` | **抓到** |
| (b) | `no_disable_btn` | 删 `if (btn) btn.disabled = !anySelectable;` | **FAIL (exit 1)** `[FAIL] 拟合按钮被禁用` | **2 failed, 62 passed** → `test_frontend_blocks_fit_when_no_model_is_selectable` + `test_dashboard_behavior_harness_passes` | **抓到（双重）** |
| (c) | `no_seq_guard` | 删 `if (seq !== _modelInfoSeq) return false;` | **FAIL (exit 1)** `[FAIL] 最终采用最新请求的结果（按钮可用）`、`[FAIL] 陈旧响应未覆盖新响应` | **1 failed, 63 passed** | **抓到** |
| (d1) | `grep_only+blocked_false` | 把 harness 调用换回纯源码 grep **＋ (a)** | FAIL（我手工用 `DASHBOARD_JS` 指向突变体） | **64 passed** ← **(a) 不再被抓到** | **判别力丧失** |
| (d2) | `grep_only+no_seq_guard` | 同上 **＋ (c)** | FAIL（同上） | **64 passed** ← **(c) 不再被抓到** | **判别力丧失** |
| (d3) | `grep_only+no_disable_btn` | 同上 **＋ (b)** | FAIL（同上） | **2 failed, 62 passed** ← (b) 仍被字符串断言抓到 | **判别力部分保留** |
| 额外 1 | `runsim_overwrite` | `dashboard.js:379-384` 还原成 `await loadModelInfo(); setStatus('ok', t('status.simDone'));` | **exit 0（全过）** | **64 passed** | **P2-1 修复零覆盖** |
| 额外 2 | `no_debounce` | `sel.onchange = () => { loadModelInfo(); };` | **exit 0（全过）** | **64 passed** | **防抖零覆盖** |
| 额外 3 | `no_buildfitting_reason` | 删 `buildFittingView()` 里的 `allDisabled` 说明 | **FAIL (exit 1)** `[FAIL] 切到拟合页时给出原因` | **1 failed, 63 passed** | **抓到** |
| 额外 4 | `no_status_on_failure` | 删 `loadModelInfo` 里 `res.error` 分支的 `setStatus(...)` | **exit 0（全过）** | **64 passed** | **失败分支零覆盖** |
| 额外 5 | `dom_rename` | 把 `index.html` 的 `id="statusText"` 改名 | **exit 0（全过）** | **64 passed** | **桩凭空造元素，模板坏了也全绿** |

基线对照：

```
$ cd %TEMP%\l1conf\base; python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
64 passed in 78.90s          （-rs 未列出任何 skip）
$ cd %TEMP%\l1conf\base; node tools\check_dashboard_behavior.js
… [PASS]×12 …
结果：全部通过      (exit 0)
$ cd F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim
$ python -X utf8 -m pytest tests/test_simulation_and_fitting.py -q -v -k "dashboard_behavior or frontend_blocks" -rs
tests\test_simulation_and_fitting.py ..   [100%]
2 passed, 35 deselected in 1.99s          （无 skip → node 真被调用）
```

`dom_rename` 突变的危害性证明（真实页面会炸，而测试全绿）：

```
$ node -e "…print setStatus…"
function setStatus(state, msg) {
  const dot = document.getElementById('statusDot');
  dot.className = 'dot' + (state === 'ok' ? ' ok' : '');
  document.getElementById('statusText').textContent = msg;   // ← 真实页面此处 null.textContent → TypeError
}
```

### 2.5 M5 —— 卫生检查

```
$ cd %TEMP%\l1conf\base
$ python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
64 passed in 78.90s                              （SKIPPED 行数 = 0）
$ cd F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim
$ node --check family_abm\web\static\js\dashboard.js           -> exit 0
$ node --check tools\check_dashboard_behavior.js               -> exit 0
$ python -X utf8 tools\baseline.py --check baseline\default_seed42.json
[OK] 与基线一致：baseline\default_seed42.json                  -> exit 0
$ python -m ruff check --no-cache family_abm tests tools --output-format concise
… family_abm\family\family_member.py / relationships.py / fitting\lanchester.py / niche\resources.py / viz\plots.py …
Found 16 errors.                                 （tests 与 tools 零 error）
$ cd %TEMP%\l1conf\a6de5d4; python -m ruff check --no-cache family_abm tests tools --output-format concise
… 含 web\__main__.py F401/F541×2、web\app.py F401 ROLE_REGISTRY、tests 4×F401 + 4×F811 …
Found 28 errors.
$ git ls-files tools/
tools/baseline.py
tools/check_dashboard_behavior.js        <- 已入库
tools/verify_install.py
$ git check-ignore -v tools/check_dashboard_behavior.js   -> exit 1（未被忽略）
$ cd F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim
$ python -X utf8 -m pytest tests/ -q -rs --no-header -p no:cacheprovider
64 passed in 72.40s                                       （仓库内直跑，-rs 无 skip）
$ git status --short
?? audits/l1_signoff_confirmation.md                      （唯一新增写入；无源码/测试/配置改动）
```

**未在仓库根产生其它文件**：全程 `PYTHONDONTWRITEBYTECODE=1` + `pytest -p no:cacheprovider` + `ruff --no-cache`，故没有新增 `__pycache__` / `.pytest_cache` / `.ruff_cache`；`git status --short` 只列出本报告。

---

## 3. 新引入的问题

> 全部为 **P3**；**未发现 P1/P2 级回归**。以下 5 条都是"本提交新引入或本提交本应覆盖而未覆盖"的。

### P3-1 —— 恢复的兜底比 `a6de5d4` 更窄：`make_fitter` / `summary_json()` 仍退化为 text/plain 500（`app.py:305-310` 的作用域）

- **证据**：`m1_residual.py` 同一桩在 `cad2fb6` 与 `a6de5d4` 上对照（见 §2.2 末）——`R1 optimizer_failed + summary_json() 抛`、`R2 make_fitter 抛 TypeError`、`R2b make_fitter 抛 ValueError` 三条在 `cad2fb6` 全部是 `500 text/plain`；同三条在 `a6de5d4` 是 `500 application/json` / `500 application/json` / `400 application/json`。
- **为什么是 P3**：`a6de5d4` 的 `except Exception` 在函数末尾，作用域覆盖 `254-303` 行；`cad2fb6` 把它挂在拟合段的 `try` 上，只覆盖 `292-296`。故"恢复错误契约"只恢复到**拟合调用**这一层，其余仍是"未捕获异常 → FastAPI 默认 `Internal Server Error`"。当前输入面（pydantic `dict[str,str]`、`bounds` 恒被规范化、`summary_json` 内部已包 try）让这三条**不易自然触发**，属防御性缺口，但它确实是"修 A 时把兜底缩窄"。
- **建议**：把 `api_fit` 的函数体整体包进一个"只做结构化封装、不改变已定状态码"的最外层 `try/except Exception → 500 {'status': 'fitting_error'}`，或至少把 `make_fitter`、`fitter.summary_json()`、`fitter._resolved_columns` 三处纳入现有兜底。

### P3-2 —— 调用方输入错误被判为 500（`app.py:305-310`）

- **证据**：真实路径（`state_mapping={'happiness':'agent_id'}`，`robust` 两种取值）→ **HTTP 500 `status=fitting_error`**；`m1_stub.py` 里 `KeyError`/`TypeError` 一律 500。这两类异常在语义上是"你给的映射指向了字符串列/列名不存在"，与已在 `app.py:297-299` 被判 400 `invalid_input` 的"找不到对应数据列"是同一族。
- **影响**：前端/调用方无法区分"我的输入错了"与"服务器崩了"；而新增测试 `tests/…:753-772` 恰好用 `status_code in (400,500)`（`:767`）+ `status in {"fitting_error","invalid_input"}` 把这个区别**断言掉了**，所以这条误分类不会被测试发现。
- **建议**：在兜底之前对 `state_mapping` 做一次列 dtype 校验（或把 pandas 的 string-dtype `TypeError` 归入 `invalid_input` 400），并把测试的 status/code 断言收紧到唯一定值。

### P3-3 —— 防抖把"陈旧评估窗口"放大到 ≥200ms，且失败后遗留旧选择态（`dashboard.js:443-446` / `:410-413`）

- **证据**（`m2m3.js` M2-5）：已载入 agent A 的评估后切到 B 并在 200ms 内点拟合 → 实际请求 `{"model_name":"logistic","agent_id":"B","robust":true,"state_mapping":{"population":"state_from_A"}}` —— **`agent_id` 是新值，模型与 `state_mapping` 全来自 A**。
- **证据**（`m2m3.js` M2-7b）：先成功加载（按钮可用）再把 agent 切成一个会让 `/api/models` 返回 400 的值 → `{dis:false, all:"", html:true, blocked:false}` 与切换前**逐字段相同**，即下拉仍是上一个 agent 的模型、按钮仍可点。
- **为什么是 P3**：序号守卫保证了"最终态正确"，但瞬时态仍可发出**跨 agent 的错误拟合请求**；`no_debounce` 突变体全绿说明防抖本身零覆盖，所以这条也没有测试兜着。
- **建议**：`runFitting` 入口处若 `_modelInfoDebounce` 尚在计时或最近一次 `loadModelInfo` 尚未完成，先 `await loadModelInfo()` 再继续；`res.error` 分支同时清空 `sel.innerHTML` / 置 `dataset.allDisabled='1'` / 禁用按钮。

### P3-4 —— 序号守卫把"陈旧"当成"不可拟合"，且错误文案被同一反模式覆盖（`dashboard.js:379-384` / `:409-412`）

- **证据**（`m2m3.js` M2-8）：`runSimulation` 自己的 `/api/models` 在飞时被一次更新的加载取代 → `loadModelInfo()` 返回 `false` → `runSimulation` 走到 `else setStatus('error', t('fitting.none_available'))`，而**最新响应其实有可拟合模型**（`btn.disabled=false`）→ 状态栏说的是"没有可直接拟合的模型"，与事实相反。
- **证据**（`m2m3.js` M3-5）：`/api/models` 请求失败时 `loadModelInfo` 已写出真实错误（`"models-500"`），紧接着被 `runSimulation` 的 `none_available` **覆盖** —— 这正是上一轮 P2-1 抱怨的同一个"覆盖"反模式，只是从成功分支搬到了**本提交新加的错误分支**上。`M3-4` 同源：失败后 `dataset.allDisabled` 仍是 `undefined`，`buildFittingView()` 什么都不说明。
- **可达性**：M2-8 需要 `runSimulation` 在飞期间另有一次加载（例如上一次 onchange 的防抖计时器恰好在此时到期）；发生时是**瞬时**误导（后到的响应会纠正）。M3-5 需要 `/api/models` 失败。
- **建议**：`loadModelInfo` 区分三种返回（`true` / `false` / `'stale'` 或抛错），`runSimulation` 只在明确"无可用"时写 `none_available`，失败/陈旧时保留已写入的错误文案。

### P3-5 —— harness 的覆盖与保真缺口（4 项）

1. **不执行 `runSimulation`**：`tools/check_dashboard_behavior.js` 全文 0 次调用 `runSimulation`（三个场景分别只碰 `loadModelInfo` / `buildFittingView` / `runFitting`）。→ 本提交头号交付 P2-1 的修复分支**零覆盖**：`runsim_overwrite` 突变体（还原成旧代码）harness exit 0 且 pytest 64 passed。
2. **失败分支零覆盖**：harness 的 `fetchStub` 永远返回 `{ok:true,status:200,json:…}`，从不返回 `{error}`、非 200、非 JSON 或网络异常。→ `no_status_on_failure` 突变体全绿；`loadModelInfo` 新加的 `catch (err)`（`dashboard.js:404-407`）在 harness 里是**死代码**。
3. **"被拦截时不发起 /api/fit" 这句断言在所选 payload 下是空转的**：`ALL_DISABLED` 的模型全是 `needs_manual_mapping=true`，于是 `runFitting` 会被 `currentStateMapping() === undefined`（`dashboard.js:572-576`）提前拦住。实测 (a) `blocked_false` 突变下该检查仍打印 `实际 0 次`——**真正抓到 (a) 的只有 `fitSelectionBlocked() 返回 true` 这一句**。
4. **桩可能不忠实之处（≥2，已实测）**：
   - **`<select>` 语义**：仓库桩在设置 `innerHTML` 时**恒取第 0 个 option**（`check_dashboard_behavior.js:75-76`），而 HTML 规范是"取第一个**非 disabled** 的 option"。实测差异（`m2m3.js` M2-6，模型 `[zzz_disabled(disabled), aaa_fittable]` 且都不在 `preferred` 列表）：仓库式 → `value="zzz_disabled"`、`blocked=true`；忠实式 → `value="aaa_fittable"`、`blocked=false`。现有三个场景恰好都用 `preferred` 里的名字（`wellbeing`/`logistic`）兜住了，所以这个偏差没暴露，但它随时可以让 harness 报出真实浏览器里不存在的失败（或反之）。
   - **凭空造 DOM**：`makeDocument` 的 `getElementById` 对任何 id 都现场 `makeElement`，且 harness **从不读 `index.html`**（全文 0 命中）。实测 `dom_rename` 突变体（把 `index.html` 的 `id="statusText"` 改名，真实页面会让 `setStatus` 抛 `null.textContent`）→ harness exit 0、pytest **64 passed**。同理 `statusDot`/`fitModel`/`fitAgent`/`fitControlCard`/`fitWarning` 是否在模板里存在完全不受检。
   - 附带：`querySelectorAll` 恒返回 `[]`、`classList.toggle` 是空实现 —— `refreshI18n()`、tab 切换、`.param-input` 取值等真实路径在 harness 里全是 no-op，故 i18n 与 DOM 显隐类回归它抓不到。

### P3-6 —— 其它次要项（沿用/未处理）

- `pytest` 里旧的 `test_frontend_blocks_fit_when_no_model_is_selectable`（`tests/…:702-714`）**并未删除**，仍是纯源码 grep；本提交只是在旁边新增了 harness 测试。故 (d) 场景下 (a)/(c) 依然漏网（(b) 侥幸被字符串断言挡住）。
- **无 CI，且 node 不是声明的 dev 依赖**（`pyproject.toml` 的 `dev = ["pytest","build","httpx"]`）：在没装 node 的机器上 `test_dashboard_behavior_harness_passes` 会 `pytest.skip`，P3-3 的修复**静默失效**且没有红灯。
- `missing_states` 仍是"只写不读"（`app.py:247` 生产，JS 引用 0 次）；`except ValueError` 仍偏宽（`app.py:297-299`，内部 `ValueError` → 400 `invalid_input`）。二者均为本提交前既有，未处理。

---

## 4. 未复现 / 存疑项

1. **§3-P3-1 的三条 text/plain 残余路径，我无法用真实（非桩）输入自然触发**：它是用 monkeypatch 替换 `make_fitter` / `summary_json` 得到的。我把可达性判定为"防御面"，因此只给 P3。若评审认为"契约必须全函数覆盖"，则这条应升级为先修项。
2. **前端结论全部基于 Node + 自写最小 DOM 桩**（本机无可用的 jsdom/真实浏览器）。M2-5 的陈旧窗口、M2-7b 的选择态遗留、M2-8 的误报、M3-4/M3-5 的覆盖，都是**在桩上真实执行 `dashboard.js` 源码**得到的；"真实浏览器渲染"这一层是规范级推断（`<select>` 语义已按 HTML 规范在 §3-P3-5 单独对照过）。后端结论则全部是真实代码路径 + 真实 HTTP。
3. **M2-8（"陈旧被当成不可拟合"）的可达性我没有在真实使用序列里构造出来**：它需要在 `runSimulation` 的 `/api/models` 在飞期间另有一次性加载（最可能是上一次切换 agent 的 200ms 防抖计时器恰好在此时到期）。我按"可达但瞬时、且后到响应会纠正"记为 P3。
4. **`state_mapping` 指向字符串列应当算 400 还是 500**：这是语义判断而非事实判断。我的依据是它与 `app.py:297-299` 已判 400 的"找不到对应数据列"同族（都是调用方给的映射有问题）。提交作者显然把它当成"未预期异常"，故写成 500 —— 我保留分歧并如实标注。
5. **"全禁用"场景在默认 ABM 数据下不可达**（沿用上一轮结论，本提交未改）：默认数据下 7 个模型都可直接拟合，故 M3-1/M3-3 是防御性数据路径。
6. **`a6de5d4` 的 ruff 28 与 `cad2fb6` 的 16 是同一把 ruff、同一组目录下的计数**；两次 `ruff` 均加 `--no-cache`，但两次运行的 ruff 版本相同（同一解释器），可比。
7. **未验证 uvicorn 下的响应头是否含 `server` 等额外字段**：我只取了 `content-type` 与 body，判决依据是 content-type（`application/json` vs `text/plain`），不受其它头影响。

---

## 5. 放行结论

**有条件放行。**

**必须先修项：无。** 上一轮点名的 3 个新缺口（P3-1 错误契约退化 / P2-1 原因说明被覆盖 / P2-2 竞态）在**被诊断出的路径**上全部真实修好，且我用"真机 + 反向删改"双向验证过；弱断言 P3-3 也补上了真执行 JS 的行为测试并具备判别力（4 个突变实验全部独立复现）。本轮**没有发现 P1/P2 级回归**，M5 卫生面（pytest 64 passed / 0 skip、`node --check` exit 0、基线 `[OK]`、ruff 16 vs 28 净减、无死字段引用、新增 JS 已入库、工作区干净）全部通过。

| 上一轮缺口 | 判定 | 关键实测证据 |
|---|---|---|
| **P3-1** 错误契约退化 | **部分修复** | 真实 uvicorn：`state_mapping→agent_id`（robust 两种）→ **application/json + 500 + `fitting_error`**；删掉兜底 → **text/plain `Internal Server Error`** 且 pytest **2 failed**。残余：`make_fitter`（非 KeyError）与 `summary_json()` 仍 text/plain，且 `a6de5d4` 在同一探针下是 JSON（新兜底更窄）；输入错误被判 500 |
| **P2-2** 竞态 | **已修复（主体）** | 真乱序（B 先 resolve、A 后 resolve）→ 最新响应胜出（下拉/按钮/allDisabled 三处一致）；删守卫 → 仓库 harness FAIL 2 项 + 我的独立 harness FAIL 4 项 + pytest 1 failed；5 次快速切换 → 1 个请求。残余：防抖放大陈旧窗口（实测发出 `agent_id=B` + A 的 mapping）、失败后遗留旧选择态、防抖零覆盖 |
| **P2-1** 原因说明被覆盖 | **已修复（主路径）** | Node 真执行 `runSimulation` 全链路：全禁用 → `statusText=none_available`、`dot` 非 `ok`、按钮禁用；仅一个可用 → `Simulation complete`；`buildFittingView()` 也说明。残余：`/api/models` 失败时错误文案被 `none_available` 覆盖、失败时 `buildFittingView` 不说明、该分支零测试覆盖（`runsim_overwrite` 全绿） |
| **P3-3** 弱断言 | **部分修复** | `test_dashboard_behavior_harness_passes` 真调用 node（2 passed / 1.99s / 无 skip）；(a)(b)(c) 三个突变 harness 或 pytest 都抓到；(d) 换成纯 grep 后 (a)(c) 漏网（64 passed）、(b) 仍被字符串断言抓到 → 判别力**部分**丧失；harness 不跑 `runSimulation`、不覆盖失败分支与防抖；桩 ≥3 处不忠实（select 语义、凭空造 DOM、fetch 恒 200/JSON） |

**放行条件（建议紧随其后同批收尾，均为 P3，不阻塞 L1）**：

1. 把 `api_fit` 的兜底作用域扩回函数级（至少纳入 `make_fitter` 与 `summary_json()`），使"未预期异常 → 500 JSON"成为**全函数**契约；顺手把"映射指向字符串列"这类输入错误归 400 `invalid_input`，并把 `test_real_string_column_mapping_yields_structured_500` 的 `in (400,500)` / `in {...}` 收紧为唯一定值。
2. 让 `loadModelInfo` 区分"陈旧/失败/无可用"三种结果，避免 `runSimulation` 把失败或陈旧误报成 `none_available`；`res.error` 分支同时清空选择态并禁用按钮。
3. 给 `runSimulation` 的状态分支、`/api/models` 失败分支、`scheduleLoadModelInfo` 防抖各补一条 harness 场景（当前三者都是"改了也全绿"），并把 harness 的 `ALL_DISABLED` 场景换成能让 `runFitting` 真正走到发请求的 payload，使"不发 /api/fit"这句断言不再是空转；同时让 harness 至少校验 `index.html` 里的关键 id 存在、并按规范实现 `<select>` 的"首个非 disabled option"语义。
4. 把 node 写进 `dev` 依赖说明（或加 CI 时显式 `node --version` 前置检查），避免行为测试静默 skip 后无人察觉。
