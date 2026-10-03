# web + packaging 审查报告

审查员：`web-packaging-auditor`（只读审查，未修改任何仓库源码/配置/前端文件）
审查对象：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`
审查范围：`family_abm/web/app.py`、`web/__main__.py`、`web/__init__.py`、`web/templates/index.html`、
`web/static/js/dashboard.js`、`web/static/css/style.css`、`family_abm/__init__.py`、`setup.py`、
`requirements.txt`、`family_abm.egg-info/`（用 `audits/` 目录外的一切文件均为只读）

## 0. 验证方法与可复现性

- 运行环境（实测）：Python 3.14.3；fastapi 0.136.1；starlette 1.0.0；pydantic 2.12.5；jinja2 3.1.6；
  scipy 1.17.1；numpy 2.4.3；pandas 3.0.2；matplotlib / networkx / uvicorn 均已安装。
- 全部 python 验证均以 `PYTHONDONTWRITEBYTECODE=1` 执行，脚本写在 `%TEMP%\niche_audit\`（仓库外），
  因此**没有向仓库写入任何字节**（仓库内 `.py/.html/.js/.css/.txt` 的 mtime 仍为 2026-04-27，见下）。
- 进程内验证：`fastapi.testclient.TestClient`（默认 families，120 步）。
- 真实服务验证：**曾临时启动 uvicorn 于 `127.0.0.1:8599`**（`python -m uvicorn family_abm.web.app:app --port 8599`），
  用于并发/事件循环阻塞与跨客户端状态泄漏测试；**验证结束已 kill 该后台作业，`Test-NetConnection 127.0.0.1 -Port 8599`
  实测 `False`（已关闭）**，且系统内无残留 python 进程。端口 **8520 从未被占用**（`Test-NetConnection ... -Port 8520` = False）。
- 打包验证：把仓库**复制到 TEMP**（`%TEMP%\niche_audit\repocopy`）后 `pip wheel --no-deps --no-build-isolation`，
  再 `pip install --target` 到 TEMP 并尝试 `import family_abm.web`。仓库本体未参与构建，未产生 `build/`、`dist/`、`*.egg-info` 等写入。
- 反例说明：仓库根目录**不是 git 仓库**（`git rev-parse --is-inside-work-tree` → `fatal: not a git repository`），
  因此「是否已提交」无法用 git 证实，只能给出工作区中存在的事实 + `疑似` 标注（见 §4）。

---

## 1. 结论摘要（最关键问题）

1. **P1｜`/api/fit` 在 `async def` 里同步跑差分/L-BFGS 拟合，实测阻塞整个事件循环 155 秒。**
   实测：一次 `POST /api/fit {"model_name":"wellbeing","robust":true}` 耗时 **156.3 s**，期间同一服务上的
   `GET /api/params` 延迟 **155.33 s**（拟合一结束立刻 0.02 s 返回）。证据 `app.py:144-165`、`fitter.py:128-159`。
   无超时、无取消、无进度、无 `run_in_threadpool`；UI 只显示「拟合中...」，多标签/多用户完全不可用。

2. **P1｜全局单例仿真状态（`_sim_env/_sim_df/_sim_recorder`）被所有客户端共享，实测跨客户端串数据。**
   实测（8599）：客户端 A 跑 `ClientA/Alice`，客户端 B 跑 `ClientB/Bob`，随后 **A 的 `GET /api/data` 返回
   `[('Bob','adult')]`、`GET /api/network` 返回 `['ClientB Household']`**。证据 `app.py:30-33, 85-111, 114-141`。

3. **P1｜非 editable 安装完全不可用：`templates/` 与 `static/` 没有进入发行包。**
   实测从副本构建的 wheel（27 693 B）**只含 26 个 `.py`（+4 个 dist-info 条目），不含 `web/templates/index.html` 与 `web/static/**`**；
   `pip install` 该 wheel 后 `import family_abm.web` 直接崩：
   `RuntimeError: Directory '...\family_abm\web\static' does not exist`（`app.py:27`）。
   证据 `setup.py:1-9`（无 `package_data`/`MANIFEST.in`）、`family_abm.egg-info/SOURCES.txt`（无 templates/static）。

4. **P1｜`setup.py` 依赖声明与实际 import 严重不一致，装完即 `ImportError`。**
   `setup.py:7` 只声明 `numpy,pandas`；实际用到 `scipy`（`fitter.py:6-7`）、`matplotlib`+`networkx`
   （`viz/plots.py:7-11,201`）、`fastapi/pydantic`（`app.py:6-10`）、`uvicorn`（`__main__.py:27`）、`jinja2`（`app.py:9`）。
   顶层 `family_abm/__init__.py:14-25` 直接导入 fitting+viz，因此**连 `import family_abm` 都需要 scipy+matplotlib**
   （实测 `sys.modules` 中出现 matplotlib、scipy）。wheel 的 METADATA 与 `egg-info/requires.txt` 均只有 numpy/pandas。

5. **P2｜NaN→0 的静默数据污染让图表与拟合互相矛盾、「四维社会空间」退化。**
   实测默认 120 步：recorder DataFrame 840×20，**5760 个 NaN 单元格**（240 个 Household 行缺成员状态列，
   600 个成员行缺 household 状态列）；`app.py:130-134` 用 `fillna(0)` 抹平后，前端聚合曲线
   `mean(state_happiness)=0.2556`，而成员真实均值（也是 fitter 聚合用的 NaN 跳过均值）为 `0.3578`，**偏低 28.6%**。
   同一份 NaN 还让 `/api/niche` 的 social 维度**恒为 1.0**（实测 5 个 agent 全是 1.0，`app.py:202-208` +
   `micro_niche.py:15-17` 的 `min(1.0, nan)=1.0`），economic 被未归一化的 income 压到 0–0.13。

6. **P2｜`/api/fit` 的 state 自动映射把抽象模型静默套到「任意前 N 个 state 列」上，产出「成功但无意义」的拟合。**
   实测映射：`square_law/linear_law/resource_competition/influence` 的 `R1/R2,O1/O2` → `state_total_income,state_savings`；
   `logistic` 的 `population` → `state_total_income`；`lotka_volterra` → `total_income/savings`。
   而 `state_savings` 恒为 0（Household.step 从不更新，`household.py:54-62`）。
   实测 `square_law` robust：25.8 s、**r²=0.0、converged=False、参数卡在边界**（alpha=beta=5.0 上界，eps1=eps2=1e-4 下界），
   接口仍返回 200 + 完整「拟合结果」卡片。证据 `app.py:154-161`。

7. **P2｜参数/请求体几乎没有服务端校验，实测可稳定打出 500 或静默忽略。**
   实测：`params.income_age_spread=0` → 500（`family_member.py:106` 除零，而 UI 恰恰允许 `min="0"`，`dashboard.js:255`）；
   `params.randomness="abc"` → 500；`families` 缺 `name` / 成员带未知键 / `age="old"` → 500；
   拼错参数名 → 200 但被静默忽略；`steps=-5` → 200 且 `observations:0`。
   另外 `age: NaN`（`json.loads` 接受 NaN 字面量，pydantic 对 `list[dict]` 不校验）会使 `GET /api/data` **500**，
   因为 starlette 的 `JSONResponse` 是 `allow_nan=False`（已单独验证 `JSONResponse({"x": nan})` →
   `ValueError: Out of range float values are not JSON compliant`）。

8. **P2｜前端首次加载的中文界面参数区仍是英文**（i18n 时序 bug）、**Plotly 仅 CDN 无本地回退**、
   **agent/家庭名直接 `innerHTML` 注入（DOM XSS）**、**两个参数的 `max="5"` 与默认值 45/18 冲突**（`dashboard.js:255`）。
   详见 §3。

---

## 2. 后端 API 发现

> 行号均指当前仓库文件。所有「实测」均在本机复现，命令与端口见 §0。

### P1-1 `/api/fit` 阻塞事件循环，实测 155 s 全站不可用

**证据**

```python
# family_abm/web/app.py:144-165
@app.post('/api/fit')
async def api_fit(req: FitRequest):            # ← async，但函数体全是同步 CPU 密集调用
    ...
    fitter = make_fitter(req.model_name, state_mapping=mapping if mapping else None)
    if req.robust:
        fitter.fit_robust(_sim_df, agent_id=req.agent_id)   # ← 同步，几十秒~几分钟
```
```python
# family_abm/fitting/fitter.py:128-159
def fit_robust(self, df, agent_id=None, bounds=None, n_starts: int = 8, seed: int = 42):
    ...
    for i in range(n_starts):                                    # 8 次重启
        result = minimize(self._objective, p0, ..., options={'maxiter': 3000, ...})
```
`_objective` 每次调用都跑一次 `solve_ivp`（`fitter.py:78-94`），即 8×(≤3000) 次数值积分。

**实测**

| 场景 | 结果 |
|---|---|
| TestClient `POST /api/fit wellbeing robust=true` | 200，**73.54 s** |
| 真实 uvicorn(8599) `POST /api/fit wellbeing robust=true` | 200，**156.33 s** |
| 拟合进行中 `GET /api/params`（另一客户端） | 延迟 **155.33 s**（拟合结束瞬间才返回） |
| 拟合结束后 `GET /`、`GET /api/niche` | 0.02 s / 0.03 s |
| 其它模型 | influence 28.1 s；square_law 25.8 s；logistic 0.42 s；linear_law 0.41 s |

**影响**：单进程单事件循环被独占，浏览器其它标签/其它请求全部挂起，反向代理/浏览器 fetch 会超时；
无法取消；`robust=True` 由前端硬编码（`dashboard.js:449`），用户无从选择；双击按钮会排队多次长任务。
**修复建议**：①把 CPU 工作移出事件循环——把端点改成 `def`（FastAPI 自动走线程池）或
`await run_in_threadpool(fitter.fit_robust, ...)`；②加 `asyncio.wait_for` 超时并把 `n_starts`/`maxiter`
作为请求参数（默认调小）；③更好的做法是作业化：`POST /api/fit` 立刻返回 `job_id`，
后台线程/进程执行，`GET /api/fit/{job_id}` 轮询进度，`DELETE` 取消；④前端按钮加 disabled/loading 状态。

### P1-2 全局可变状态被所有请求共享（跨客户端数据错乱）

**证据**

```python
# family_abm/web/app.py:29-33
# ── Global simulation state ────────────────────────────────────────────────
_sim_env: Optional[Environment] = None
_sim_df: Optional[pd.DataFrame] = None
_sim_recorder: Optional[StateRecorder] = None
_last_fitter = None
```
`/api/run` 写（`app.py:87,103-104`），`/api/data`（`116-118`）、`/api/niche`（`191-193`）、`/api/network`（`220-222`）、
`/api/fit`（`146-148`）读；请求里没有任何 run/session 标识。

**实测（8599，两个 httpx 客户端）**：A 跑 `ClientA/Alice` → B 跑 `ClientB/Bob` → A 的
`GET /api/data` 返回 `[('Bob','adult')]`，`GET /api/network` 返回 `['ClientB Household']`。
另：所有端点都是 `async def` 且不含 `await`，请求被串行化，因此这里不是「读脏中间态」的竞态，
而是**语义上的会话串台**：后一次 run 静默覆盖前一次，用户看到的图表/拟合属于别人的仿真。
`_last_fitter`（`app.py:33,166`）只写不读，是死状态。

**修复建议**：`/api/run` 返回 `run_id`（uuid），把 `env/df/recorder/fitter` 放进 `dict[run_id]`（带 TTL/LRU 上限），
`/api/data|niche|network|fit` 都要求 `run_id`；同时用 `asyncio.Lock` 做单飞（single-flight），
并发 run 返回 `409 Conflict` + 明确文案；将来若要给其它用户用，再加会话/鉴权。

### P1-3 非 editable 安装即失败：`templates/` + `static/` 未打包

**证据（分三层，全部可复现）**

```python
# setup.py:1-9
setup(
    name="family_abm",
    version="0.1.0",
    packages=find_packages(),                      # ← 只收 .py
    install_requires=["numpy>=1.21.0", "pandas>=1.3.0"],
    python_requires=">=3.9",
)                                                  # ← 无 package_data / include_package_data / MANIFEST.in
```
`family_abm.egg-info/SOURCES.txt`（920 B）列出 27 个路径，**没有任何 `web/templates/*` 或 `web/static/*`**（`setup.py` 本身在列）。

**实测从仓库副本构建的 wheel 内容**（`pip wheel --no-deps --no-build-isolation`，27 693 B）：
`family_abm-0.1.0.dist-info/{METADATA,RECORD,WHEEL,top_level.txt}` + 26 个 `family_abm/**/*.py`，
**无 index.html、无 dashboard.js、无 style.css**。

**实测 `pip install --target` 后导入**：
```
File "...\family_abm\web\app.py", line 27, in <module>
    app.mount('/static', StaticFiles(directory=str(HERE / 'static')), name='static')
RuntimeError: Directory '...\family_abm\web\static' does not exist
```
`StaticFiles` 默认 `check_dir=True`（`app.py:27`）→ **导入 `family_abm.web` 即崩**，
`python -m family_abm.web` 直接不可用；即便绕过，`GET /` 也会因 `templates.get_template('index.html')`
（`app.py:24,62`）抛 `TemplateNotFound`。README 的 `pip install -e .` 恰好是唯一能工作的路径，因此该缺陷被长期掩盖。

**修复建议**：加 `MANIFEST.in`（`recursive-include family_abm/web/templates *.html` / `.../static *`）
并在 `pyproject.toml` 写
`[tool.setuptools.package-data] family_abm = ["web/templates/*.html", "web/static/**/*"]`；
CI 增加「构建 wheel → 装到干净环境 → `import family_abm.web` → `GET /`」的冒烟测试（这条测试本身就能挡住本问题）。

### P1-4 `setup.py` vs `requirements.txt` vs 真实 import 三方不一致

**证据**

| 依赖 | 代码引用（证据行） | requirements.txt | setup.py install_requires | egg-info/requires.txt |
|---|---|---|---|---|
| numpy | `fitter.py:4`, `app.py:4` | ✅ `:1` | ✅ `:7` | ✅ |
| pandas | `recorder.py:3`, `app.py:5` | ✅ `:2` | ✅ `:7` | ✅ |
| scipy | `fitter.py:6-7`、`lanchester.py:4` | ✅ `:3` | ❌ | ❌ |
| matplotlib | `viz/plots.py:7-11` | ✅ `:4` | ❌ | ❌ |
| networkx | `viz/plots.py:201` | ✅ `:5` | ❌ | ❌ |
| fastapi | `app.py:6-9` | ✅ `:6` | ❌ | ❌ |
| uvicorn | `web/__main__.py:27` | ✅ `:7` | ❌ | ❌ |
| jinja2 | `app.py:9`（`Jinja2Templates`） | ✅ `:8` | ❌ | ❌ |
| pydantic | `app.py:10`（`BaseModel`） | ❌（靠 fastapi 传递） | ❌ | ❌ |

实测 wheel 的 METADATA：
```
Requires-Python: >=3.9
Requires-Dist: numpy>=1.21.0
Requires-Dist: pandas>=1.3.0
```
实测 `import family_abm` 会把 `matplotlib`、`scipy` 拉进 `sys.modules`（因为 `family_abm/__init__.py:14-25`
无条件导入 `.fitting`、`.viz`）；`uvicorn` 只在 `main()` 内导入（`__main__.py:27`），因此「导入 family_abm.web 是否触发端口绑定」
的答案是**否**（实测：`import family_abm.web` 之后仍能成功 bind 8520，且无监听 socket；只有 `main()` 调用 `uvicorn.run`）。
→ Lead 第 8 条中「import 触发端口绑定」的猜想**证伪**；「自动开浏览器」**证实**（`__main__.py:22-25`）。

**修复建议**：迁移到 `pyproject.toml`：
```toml
[project]
dependencies = ["numpy>=1.23", "pandas>=1.5", "scipy>=1.9", "matplotlib>=3.6", "networkx>=2.8"]
[project.optional-dependencies]
web = ["fastapi>=0.100", "uvicorn>=0.23", "jinja2>=3.1", "pydantic>=2"]
[project.scripts]
family-abm-web = "family_abm.web.__main__:main"
```
或至少把 `setup.py:7` 与 `requirements.txt` 同步并补 pydantic；`requirements.txt` 再加 `pytest`/`httpx`（dev）。

### P2-1 `/api/niche` 的 social 维度恒为 1.0（NaN 被 clamp 成上界）

**证据**

```python
# family_abm/web/app.py:202-208
agent_state = {
    'income':     last.get('state_income', 0),
    'education':  last.get('state_education', 0.5),
    'social_capital': last.get('state_social_capital', 0.5),   # ← 列存在！Series.get 返回 NaN，不是 0.5
    'happiness':  last.get('state_happiness', 0.5),
}
n.update_from_agent_state(agent_state)
```
```python
# family_abm/niche/micro_niche.py:15-17
def set_position(self, dimension: str, value: float) -> None:
    if dimension in self.dimensions:
        self.position[dimension] = max(0.0, min(1.0, value))     # min(1.0, nan) == 1.0  → nan 变 1.0
```
原因：`state_social_capital` 是 Household 专属状态（`household.py:20`），成员行该列是 NaN；
DataFrame 里「列存在」所以 `Series.get` 的默认值 0.5 永远不生效，NaN 进入 `set_position` 后
`min(1.0, nan)` → `1.0`，`max(0.0, 1.0)` → `1.0`。

**实测（默认 families，120 步）**：5 个成员 `social` 全为 `1.0`；`economic` = income ∈ [0, 0.1317]；
`cultural` ∈ [0.45, 0.71]；`emotional` = happiness ∈ [0.2, 0.33]。
即「四维社会空间」实际退化为三维 + 一条恒为 1.0 的边界线，且 economic 被 income 的 0–0.13 量纲压扁。

**修复建议**：取值为 None/NaN 时显式回退（`if v is None or pd.isna(v): v = default`），
并对 income 做与模型中一致的归一化（参考 `family_member.py:137` 的 `min(1.0, income*3)`）；
更彻底的做法是让 `/api/niche` 接受 `run_id` 并按 agent 自身状态计算，避免读取不属于该 agent 的列。

### P2-2 `/api/data` 的 `fillna(0)` 污染聚合曲线（实测偏低 28.6%）

**证据**

```python
# family_abm/web/app.py:130-134
df = _sim_df.copy()
for c in df.columns:
    if pd.api.types.is_float_dtype(df[c]):
        df[c] = df[c].round(4).fillna(0)      # ← Household 行缺成员状态列 → 补 0，进入平均
df = df.fillna(0)
```
```javascript
// dashboard.js:403-409（未选 agent 时把 7 行一起平均）
series.forEach(r => { byTime[r.time] = byTime[r.time] || []; byTime[r.time].push(r[col] || 0); });
const vals = t.map(ti => byTime[ti].reduce((a, b) => a + b, 0) / byTime[ti].length);
```

**实测**：840×20 的 DataFrame 共 **5760 个 NaN 单元格**（`attr_age/attr_gender/attr_role/state_health/state_happiness/...`
各 240 个 = Household 行；`state_total_income/savings/housing_quality/neighborhood_quality/cultural_level/social_capital`
各 600 个 = 成员行）。前端聚合 `mean(state_happiness) = 0.2556`；成员真实均值 `0.3578`；
**fitter 自己的聚合（`fitter.py:55-66` 用 pandas 分组均值，自动跳过 NaN）= 0.3578**。
→ 同一份数据，「ABM 数据 vs ODE 拟合」图里的 ABM 点（前端算的，偏低 29%）和拟合用的目标序列不是同一个东西。

**修复建议**：`/api/data` 按 `agent_type` 过滤（或分 `agents`/`households` 两个数组返回），
物理量不要 `fillna(0)`（返回 `null` 让前端 `??` 处理）；前端只画成员状态列（当前 12 条线里有 6 条是
Household 级状态，`state_savings` 实测 max=0.0000，是一条恒零线）。

### P2-3 NaN → 500（`JSONResponse` 拒绝 NaN/Inf）

**证据/实测**

```python
# family_abm/web/app.py:127
'age': round(a.get_attribute('age'), 1),     # ← 若属性为 NaN，round 后仍 NaN，写进 JSONResponse
```
- 实测 `POST /api/run`（raw body 里写 `"age": NaN`，Python `json` 解析器接受 NaN 字面量，且
  `SimConfig.families: list[dict]` 不校验）→ **200 OK**；随后 `GET /api/data` → **500 Internal Server Error**。
- 单独验证 starlette：`JSONResponse({"x": float("nan")})` → `ValueError: Out of range float values are not JSON compliant: nan`。
- 同类风险位（疑似，本次未触发）：`/api/fit` 的 `summary_json()`（`fitter.py:256-284`，`fun`/`r_squared`/`params`）
  与 `predict_trace`（`app.py:169-177`）在数值溢出时可能是 NaN/Inf；因为成功路径的 `JSONResponse` 构造
  也在 `try` 内（`app.py:179-186`），异常会被自己 catch 成 500，错误文案会变成
  “Out of range float values are not JSON compliant”，完全看不出真实原因（实测已观察到
  `fitter.py:170-171` 的 `overflow encountered in scalar divide` 警告）。
- `fitter.py:73` 的 `np.ptp(y, axis=0).max() < 1e-5` 只在**所有**状态都无方差时告警；`state_savings` 恒 0
  这类单列退化不漏报。

**修复建议**：pydantic 侧 `model_config = ConfigDict(allow_inf_nan=False)` 并在成员/参数模型上做有限性校验；
输出侧统一用安全编码器（把 NaN/Inf 转 `None`），或自定义 `ORJSONResponse` + `orjson.OPT_NON_STR_KEYS` 之前先 sanitize；
`/api/fit` 里把「构造响应」移出 `try`，或分别捕获。

### P2-4 请求模型过弱：无校验、500 满天飞、拼错参数静默忽略

```python
# family_abm/web/app.py:37-55
class SimConfig(BaseModel):
    steps: int = 120
    params: dict = {}                 # ← 无键/值类型约束、无范围、无 allow_inf_nan
    families: list[dict] = [ ... ]    # ← 成员结构完全未建模
class FitRequest(BaseModel):
    model_name: str = 'wellbeing'
    agent_id: Optional[str] = None
    robust: bool = True
```
```python
# family_abm/web/app.py:89-96
env = Environment(); env.params = cfg.params          # 裸 dict 直接生效
for fam in cfg.families:
    hh = Household(name=f"{fam['name']} Household")   # ← 缺 key → KeyError → 500
    for m in fam['members']:
        member = FamilyMember(**m)                    # ← 未知 key → TypeError → 500
```

**实测矩阵**

| 请求 | 状态码 | 说明 |
|---|---|---|
| `{"steps":"abc"}` | 422 | 唯一一处正常校验（pydantic int） |
| `{"steps":-5}` / `{"steps":0}` | **200** | `observations:0`，静默空跑 |
| `params.income_age_spread=0` | **500** | `family_member.py:106` `2*spread**2` 除零；UI 允许 `min="0"` |
| `params.randomness="abc"` | **500** | `family_member.py:89` `float()` 失败 |
| `params.happines_baseline=9`（拼错） | **200** | `family_member.py:65` `.get(key, DEFAULT)` 静默忽略 |
| `params.health_decay_age=-5` | **200** | 无范围校验 |
| `families:[{"members":[]}]`（缺 name） | **500** | `app.py:92` KeyError |
| 成员带未知键 `foo` | **500** | `app.py:95` → `Agent.__init__` TypeError |
| `age:"old"` | **500** | `family_member.py:52` 算术 TypeError |
| `families:[]` | 200 | agents=0，后续 `/api/data` 返回空 |
| `age: NaN` | 200 → `/api/data` **500** | 见 P2-3 |
| `model_name:"nope"`（fit） | **500** | 应为 422；文案 `'Unknown model "nope". Choose: [...]'` |
| 时间点数 <10（fit） | **500** | `fitter.py:69-70` 用户输入错误却报 500 |
| `agent_id` 不存在（fit） | **500** | `'Need at least 10 time points, got 0.'` |

**修复建议**：为 `params` 建 `dict[str, confloat(ge=0, le=..)]` 并**用 `DEFAULT_PARAMS` 的键做白名单**（未知键 422，
提示最近的合法键）；为 family/member 建嵌套模型（`name: str, age: float = Field(ge=0, le=120), gender: Literal[...],
role_name: Literal[...]`，`extra="forbid"`）；`steps: int = Field(120, ge=1, le=5000)`；
`income_age_spread` 用 `gt=0`；用 `@app.exception_handler` 或显式 try 把领域错误映射为 400/422，
并对未知模型返回 422；`except Exception` 里加 `logger.exception` 保留堆栈（`app.py:185-186` 现在只返回 `str(e)`）。

### P2-5 `/api/fit` 的 state 自动映射静默错配（Lead 第 7 条：证实）

```python
# family_abm/web/app.py:154-161
state_names = MODEL_STATE_NAMES.get(req.model_name, [])
state_cols = [c for c in _sim_df.columns if c.startswith('state_')]
mapping = {}
for i, sn in enumerate(state_names):
    if f'state_{sn}' not in _sim_df.columns and i < len(state_cols):
        mapping[sn] = state_cols[i]          # ← 静默取「第 i 个 state_ 列」，与被拟合的物理量无关
```
`state_` 列顺序（实测）= `[state_total_income, state_savings, state_housing_quality, state_neighborhood_quality,
state_cultural_level, state_social_capital, state_health, state_happiness, state_stress, state_energy,
state_education, state_income]`（Household 先入 env，列序由 Household 状态决定）。

**实测映射结果**

| 模型 | 模型状态名 | 实际映射到的列 | 语义 |
|---|---|---|---|
| `wellbeing` | happiness, stress | `state_happiness`, `state_stress` | ✅ 正确 |
| `square_law` / `linear_law` | R1, R2 | `state_total_income`, `state_savings` | ❌ R2 恒为 0 |
| `resource_competition` | R1, R2 | 同上 | ❌ |
| `influence` | O1, O2 | 同上 | ❌ |
| `logistic` | population | `state_total_income` | ❌ 把「家庭总收入」当人口 |
| `lotka_volterra` | prey, predator | `state_total_income`, `state_savings` | ❌ |

`state_savings` 恒 0（`household.py:15` 初始化为 0，`household.py:54-62` 的 `step()` 只更新 `total_income`），
因此这些拟合实际是「单变量 + 一条零序列」的退化问题。

**实测 `square_law` robust**：25.8 s，`r_squared=0.0`，`converged=False`，
`params={alpha:5.0, beta:5.0, eps1:0.0001, eps2:0.0001}`（**全卡在 bounds** `(1e-4, 5.0)`，`fitter.py:149`），
`fun=0.0154`；接口返回 200，前端照常展示「拟合结果」卡片（`dashboard.js:453-467`），
用户看不出这是无意义拟合。
（Lead 说「参数停在下界 0.5」：实测 `p0` 是 `[0.5]*n`（`fitter.py:116`）或随机，最终 alpha/beta 在**上界 5.0**、
eps 在**下界 1e-4**；结论一致——参数被边界锁死。）

`wellbeing` 还有一个固有可辨识性问题：`wellbeing_balance`（`lanchester.py:44-52`）的 `income` 项是常数，
`MODEL_STATE_NAMES["wellbeing"]` 不含 income，所以 `income=0.5` 是**固定假设**而非数据；`summary_json()`
却把它作为「拟合参数」展示（实测 `params` 里出现 `income: 0.662815`——那是它被当作自由参数拟合出来的值）。

**修复建议**：把映射显式登记（每个模型一个 `MODEL_STATE_MAP`），只在列数与状态数匹配且显式声明时才允许；
否则返回 422 并列出可用列；`make_fitter` 里用 `param_fix` 固定不应拟合的参数（接口已支持，见 `fitter.py:302-333`，
但 Web 层没用）；响应里回传生效的 `state_mapping` 并在 UI 显示；对恒零/恒常数列直接报错（把
`fitter.py:73` 的 `ptp(...).max()` 改为逐列检查）。

### P2-6 无随机种子：同一个仿真无法复现（疑似影响拟合结论）

**证据**：`app.py:98-101` 建 Simulation 时无 seed 参数；`family_member.py:47-57`、`relationships.py:17-21`
全部用全局 `random`；`fitter.py:151` 的 `np.random.RandomState(42)` 只固定了拟合初值，不固定数据。
**实测**：连续 3 次完全相同的 `POST /api/run`（30 步），`sum(state_happiness)` = `16.4476 / 15.2104 / 14.7557`
→ 不相等。**影响**：同一配置每次点「运行」结果不同，`/api/fit` 的 R² 也随之漂移（实测两次 wellbeing robust
R²=0.9672 / 另一次收敛到不同参数），用户无法复验；对「仿真仪表板」这是可信度问题。
**修复建议**：`SimConfig.seed: Optional[int]`，`random.seed(seed)` 或（更好）把 `random.Random(seed)` 注入
FamilyMember/Relationship；响应回传 seed 并在 UI 显示/可复制。

### P3 其它后端发现

- **P3｜错误语义**：未知模型/数据点不足/agent 不存在都返回 500（见 P2-4 表）；`/api/run` 完全没有 try/except，
  异常直接冒泡成未处理 500，且项目没有任何 logging 配置 → 生产排障困难。
- **P3｜`/api/run` 未限制规模**：实测 `steps=5000` 仅 0.12 s（单户），但 `GET /api/data` 返回 **4 647 566 B**；
  默认 7 agent 配置按实测 475 B/记录外推，5000 步 ≈ **16 MB** 单次 JSON，无分页/降采样（`app.py:136-141`）。
- **P3｜版本号不一致**：`app.py:26` `version='0.2.0'` vs `setup.py:5` `version="0.1.0"`。
- **P3｜列名/默认值双份维护**：`SimConfig.families`（`app.py:40-50`）与前端 `defaultFamilies`（`dashboard.js:279-289`）
  是两份手工同步的默认值；`/api/params` 的 `groups`（`app.py:71-78`）与 `DEFAULT_PARAMS`（`family_member.py:10-29`）
  也是两份；本次实测二者**完全一致**（set 相等，19/19），但一旦只改一处就会静默漂移（前端少渲染一个参数或后端忽略它）。
  建议由单一数据源生成 groups，并在 import 时 assert 集合相等。
- **P3｜`_last_fitter` 死状态**（`app.py:33,166`），从未被读。
- **P3｜`web/__init__.py:1` 的属性遮蔽**：`from .app import app` 使 `family_abm.web.app`
  在属性访问时指向 FastAPI 实例而不是模块（实测 `import family_abm.web.app as A` 得到的是 `FastAPI` 对象）。
  uvicorn 的 `'family_abm.web.app:app'` 字符串导入仍正常（8599 实测可用），但 `import ... as` 的工具/测试会困惑。
- **P3｜时间从 1 开始**：`Simulation.step` 先 `scheduler.step`（`environment.py:37-41` 里 `time += 1`）
  再 `recorder.record`（`simulation.py:30-36`）→ 录制时间为 1..steps（实测 min=1,max=120），
  与请求的 `steps=120` 差 1，前端 x 轴没有 t=0 点。
- **P3｜无 CORS / 无速率限制**：`app.py:26-27`。默认只绑 127.0.0.1（`__main__.py:28`），本地单机可接受；
  若按 README 之外的方式暴露到局域网，`POST /api/run` 就是无鉴权的 CPU 放大器（配合 P1-1 可作为 DoS）。
  同时未启用 `TrustedHostMiddleware`（DNS rebinding 面），本地风险低，标注即可。
- **P3｜`/docs`、`/redoc`、`/openapi.json` 默认开启**（FastAPI 默认），本地无碍。
- **P3｜`from ..family.family_member import DEFAULT_PARAMS` 放在函数内**（`app.py:70`），无必要。

---

## 3. 前端发现

### P2-1 首次加载时中文界面的参数区仍是英文（i18n 时序 bug）

```javascript
// dashboard.js:563-567（Init）
buildFamilyConfigs();
loadParams();          // async：await fetch 之后才 buildParams()，而这一行不 await
refreshI18n();
setLang(currentLang);  // 同步执行完毕时，参数 DOM 还不存在
```
```javascript
// dashboard.js:228-233
async function loadParams() {
  const res = await api('/api/params');
  ...
  buildParams();       // ← 在 refreshI18n() 之后才注入 DOM
}
// dashboard.js:238-248 / 250-256：注入的标题/标签是硬编码英文 enLabels
html += `<div class="param-group"><h4 ... data-i18n="param.${group}">${group}</h4>...`;
html += `<label data-i18n="param.${key}">${enLabels[key] || key}</label>`;
```
用户上次选中文、刷新页面后：`refreshI18n()` 先跑（此时 `#paramGroups` 为空），随后 `buildParams()` 注入英文标题 → 
参数区显示 `Education / Learn Rate / Base Income ...`；只有再手动切一次语言才会翻译。
**注意（证伪「漏配 key」）**：实测静态核对——`index.html` 26 个 `data-i18n` 键、`dashboard.js` 25 个 `t('...')` 字面量键、
`param.<group>`（6 个）与 `param.<参数名>`（19 个）**全部**在 zh/en 两个字典中存在（各 74 键，无不对称、无缺失）；
唯一「定义了但没人用」的是 `status.error`（`dashboard.js:15,78`）。
**修复**：把 init 改为 `(async () => { buildFamilyConfigs(); await loadParams(); refreshI18n(); setLang(currentLang); })()`，
或在 `buildParams()` 末尾调用 `refreshI18n()`。

### P2-2 两套 role 词表 + role 被年龄覆盖 → 下拉框形同虚设

```python
# family_member.py:50
self.set_attribute("role", role_name)          # UI 传 parent/child/adult/elder
# family_member.py:75-78
def age_increment(...): ... self.set_attribute("role", self._role_at_age(new_age))
# family_member.py:68-73 → preschool/child/student/adult/elder
```
**实测**：`FamilyMember(name="kid", age=10, gender="male", role_name="parent")` → step 一次后 `role="child"`；
默认 120 步运行后 `/api/data` 的 role 是 `adult/adult/student/adult/student`（UI 里根本没有 student/preschool）。
前端 `roleColors = {parent, child, adult, elder}`（`dashboard.js:422,526`）→ `student` 落到 `#95a5a6` 灰点，
`parent` 永不出现。附带：第 1 步的收入乘数按**新词表**查表（`family_member.py:107-108`），
`role='parent'` 落到默认 `0.2`、`role='child'` → `0.0`，即首步用了错误乘数（其后自愈）。
**修复**：统一 role 词表；若 `_role_at_age` 是权威，就把 UI 的角色下拉改成「初始角色（仅第 1 步生效）」或直接删除；
把 `student/preschool` 加进 `roleColors`。

### P2-3 DOM XSS：agent/家庭名直接拼进 innerHTML

```javascript
// dashboard.js:368-370
list.innerHTML = simData.agents.map(a =>
  `<span class="agent-chip" data-id="${a.id}" onclick="selAgent(this,'${a.id}')">${a.name} (${a.role})</span>`
).join('');
// dashboard.js:515
`<div class="card"><div class="card-header"><h2>${net.name}</h2></div>...`
// dashboard.js:295（默认家庭名）、:461-463（拟合参数键值）
```
成员名由用户在 Setup 页自由输入并经服务端原样回显（`app.py:92,95,125`、`app.py:244`），
把成员名填成 `<img src=x onerror=alert(document.cookie)>` 即可在仪表板执行脚本；
`onclick="selAgent(this,'${a.id}')"` 也是把服务端数据拼进事件属性。
**影响**：单机自伤为主（P3 级），但只要 `POST /api/run` 能被本机其它进程/局域网访问，
就是同源下的脚本执行入口（配合无 CORS/无鉴权）。**修复**：用 `createElement`+`textContent` 构建节点，
或统一 escape；用 `addEventListener` + `dataset` 取代内联 `onclick`。

### P2-4 Plotly 仅 CDN，无本地回退、无 SRI

```html
<!-- index.html:8 -->
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
```
`family_abm/web/static/` 下**没有** plotly 本地文件（glob 全仓库仅此一个引用）。
CDN 不可达（离线/内网/被墙）时 `Plotly` 未定义 → `buildTimeSeries`（`dashboard.js:412`）抛
`ReferenceError: Plotly is not defined`，用户只看到空白图表区，状态仍显示「仿真完成」，
错误只在 console；同时缺 `integrity`/`crossorigin`（供应链风险）。
**修复**：把 `plotly.min.js` 放进 `static/js/` 并改本地引用（README 若声称离线可用，这条是硬要求）；
保留 CDN 时加 SRI + `onerror` 回退脚本 + 显式错误提示。

### P2-5 参数输入约束与真实默认值冲突（含可触发 500 的 `min="0"`）

```javascript
// dashboard.js:253-256
<input type="number" class="param-input" data-param="${key}" value="${val}" step="0.001" min="0" max="5">
```
- `income_age_peak` 默认 **45**、`income_age_spread` 默认 **18**（`family_member.py:14-15`），
  全部参数共用 `min="0" max="5"` → 渲染出来就有 2 个输入在 :invalid 状态，点微调箭头会被 clamp 到 5；
  `step="0.001"` 对「年龄峰值」这种量纲也不合适。
- `min="0"` 允许 `income_age_spread=0` → **实测服务端 500**（见 §2 P2-4）。
**修复**：让 `/api/params` 一并返回每个参数的 `min/max/step/unit`（单一数据源），前端据此渲染，
服务端再独立校验一次。

### P2-6 `parseFloat(...) || 0` 把空输入静默变成 0

```javascript
// dashboard.js:263-269
params[inp.dataset.param] = parseFloat(inp.value) || 0;   // '' → NaN → 0；'abc'（type=number 下难输入）同样
```
清空「年龄跨度」输入框再点运行 → 传 0 → 服务端 500。**修复**：`Number.isFinite(v) ? v : paramDefaults[key]`，
并对无效字段加红色提示/阻止提交。

### P3 其它前端发现

- **P3｜语言切换会重置状态栏**：`index.html:20` 的 `#statusText` 带 `data-i18n="status.ready"`，
  而 `refreshI18n()` 对所有 `[data-i18n]` 无差别 `textContent = t(key)`（`dashboard.js:143-146`）→
  跑完仿真/拟合后切换语言，状态从「仿真完成」「拟合完成 (R^2=0.9672)」被重置为「Ready/就绪」，结果信息丢失。
- **P3｜硬编码未翻译文案**：`dashboard.js:458-459` 的 `R^2`、`Converged` 不随语言变化（值已翻译）；
  成员表单里的 `male/female/parent/child/adult/elder`（`dashboard.js:298-309`）也是英文常量。
- **P3｜错误态没有视觉区分**：`setStatus('error', ...)`（`dashboard.js:557-561`）只把 dot 的 class 设为 `dot`，
  样式表里只有 `.dot.ok`（`style.css:21-22`），没有 `.dot.error`（虽然 `style.css:66` 定义了 `.error` 但无人使用）
  → 失败与正常状态除了文字几乎一样。
- **P3｜切换语言后拟合图标题不更新**：`setLang` 只调 `buildCharts()`（`dashboard.js:170`），
  ODE 拟合图只在点「拟合模型」时重建（`buildFittingView` 仅 display 切换，`dashboard.js:437-440`），
  网络图只在切 tab 时重建（`onTabSwitch`，`dashboard.js:193-197`）→ 已渲染的拟合图保持旧语言标题。
- **P3｜网络图 200 ms `setTimeout` 后绘制**（`dashboard.js:518-553`）：切换 tab 太快或容器被替换时
  `Plotly.newPlot('networkChart'+i, ...)` 可能拿到 `null` 而抛错。直接同步绘制即可（DOM 已插入）。
- **P3｜`api()` 不看 `res.ok`**：`dashboard.js:215-222` 只 `res.json()`。
  FastAPI 的 422 体是 `{"detail":[...]}`（实测），调用方只判断 `res.error`（`dashboard.js:346,349,451,511`）
  → 这类响应会被当成成功；`runSimulation` 随后拿 `/api/data` 的**上一次**数据当成本次结果展示
  （「Simulation complete」+ 旧数据）。UI 现有输入路径不易触发（`steps` 被 `parseInt||120` 兜住），
  但作为健壮性缺陷必须修：`if (!res.ok) return {error: body.detail || res.statusText}`，
  并给每个 tab 保留独立的错误提示位。
- **P3｜图表序列混入 Household 状态**：前端 `stateCols`（`dashboard.js:403,478`）取全部 `state_` 列共 12 条，
  其中 6 条是 Household 级（成员行恒 0，实测 `state_savings` max=0.0000）→ 图表出现多条恒零线；
  y 轴硬编码 `range:[0,1]`（`dashboard.js:414,432,500`）对当前默认配置够用（实测 max 0.98），
  但家庭 `total_income` 是成员收入求和（`household.py:58-62`），大家庭会超过 1 被裁掉。
- **P3｜切换语言后家庭名会被污染（疑似，纯代码推导）**：`buildFamilyConfigs` 在 init 时按当时的语言写入
  `<h3>Smith ${t('setup.family')}</h3>`（`dashboard.js:295`，无 `data-i18n` 所以刷新语言不会更新它），
  而 `getFamilyConfigs` 用**当前**语言的 `t('setup.family')` 去 `replace`（`dashboard.js:320-321`）→
  先切语言再运行，家庭名变成 `"Smith Family"`（中英混合）→ 后端 Household 名变
  `"Smith Family Household"`。仅影响命名，标疑似。
- **P3｜无加载态/防重复提交**：`runSimulation`/`runFitting` 期间按钮不 disabled（`style.css:53` 已有 `.btn:disabled` 样式），
  连点会向本已阻塞的服务端再排长任务。
- **P3｜`⚙` 按钮语义**：`index.html:22` `title="Settings"`，实际是语言切换；无 `aria-*`/键盘操作
  （`document.addEventListener('click')` 关闭下拉，`dashboard.js:210-212`），可访问性弱。

---

## 4. 打包 / 工程化发现

### P1（同 §2 P1-3/P1-4）

- **P1｜`templates/`+`static/` 不在发行包**：`setup.py:1-9` 无 `package_data`/`MANIFEST.in`；
  `egg-info/SOURCES.txt` 与实测 wheel 内容均无这些文件；实测装 wheel 后 `import family_abm.web` →
  `RuntimeError: Directory ...\web\static does not exist`（`app.py:27`），`GET /` 亦会 `TemplateNotFound`（`app.py:24,62`）。
- **P1｜依赖声明不一致**：`setup.py:7` 只 numpy+pandas；`requirements.txt:1-8` 有 8 项但缺 pydantic；
  实际 import 见 §2 P1-4 表；wheel METADATA / `egg-info/requires.txt` 均只有 numpy+pandas。

### P2 元数据 / 工程化缺失（逐条核实 Lead 第 6 条）

| 项目 | 结论 | 证据（实测） |
|---|---|---|
| README.md | **不存在** | 仓库根仅有 `examples/`、`family_abm/`、`family_abm.egg-info/`、`requirements.txt`、`setup.py`（+ 本次审查团队新建的 `audits/`）；全仓库无任何 `.md`（glob `*.md` 仅命中 `audits/`） |
| tests/ | **不存在** | 全仓库无 `test*` 目录、无 `pytest.ini`/`tox.ini`/`conftest.py`；`requirements.txt` 无 pytest |
| LICENSE | **不存在** | 无 `LICENSE*` 文件；`setup.py:3-9` 也无 `license=`/`classifiers=`/`author=`/`url=` |
| .gitignore | **不存在** | 根目录无 `.gitignore`（glob 全仓库无匹配） |
| pyproject.toml | **不存在** | 无 `pyproject.toml`/`setup.cfg`；构建走 legacy `setup.py`（`pip wheel` 日志显示 "Preparing metadata (pyproject.toml)" 是 pip 的兜底，仓库内并无该文件） |
| `__pycache__` | **存在**（17 个 `.pyc`，cpython-314） | `family_abm/**/__pycache__/*.pyc`；mtime ≥ 对应 `.py`，属**当前**字节码而非过期缓存 |
| `family_abm.egg-info` | **存在且与现状不符** | `PKG-INFO`/`requires.txt` 只有 numpy+pandas（跟随 setup.py）；`SOURCES.txt` **既无 templates/static，也无 `examples/`** → 该 egg-info 是在 web 层与 examples 之前生成的，**已过期** |
| 构建产物 | **存在** | `examples/output/01..10*.png`（10 个）在工作区中（注：本次会话中有其它审查成员重跑 examples，mtime 显示 2026-10-03 12:44，非本审查员所为） |

> **「误提交」的可靠性说明**：`git rev-parse --is-inside-work-tree` → `fatal: not a git repository`，
> 仓库**根本没有 .git**，因此「是否已被 git 追踪/提交」**无法证实（疑似）**；
> 能证实的是「这些缓存/构建产物确实存在于交付目录中」，这才是打包卫生的实际问题。

### P2 其它

- **P2｜无 pyproject/构建系统声明**：没有 `[build-system]`（PEP 518），构建依赖不可复现；
  现代 pip/build 前端会退化到 legacy 路径。建议 `pyproject.toml` 承担所有元数据 + `[tool.setuptools.package-data]`
  + `[project.optional-dependencies]`，`setup.py` 仅留兼容 shim 或删除。
- **P2｜无任何测试与 CI**：本次 P1-3（wheel 缺静态资源）本可被一条「装 wheel 后 `import family_abm.web` + `GET /`」测试挡住。
  建议最小测试集：`tests/test_api.py`（TestClient 覆盖 5 个端点 + 400/422 分支 + NaN 输入）、
  `tests/test_packaging.py`（构建 wheel、检查 `web/templates/index.html` 在包内）。

### P3

- **P3｜`python_requires=">=3.9"` 的语法核对**：全仓库**无** `match` 语句、**无** PEP 604 `X | Y` 注解；
  使用 PEP 585 `list[...]`/`dict[...]`（3.9 支持）且每个模块都有 `from __future__ import annotations`
  （实测 grep 43 处泛型注解均为 `list[...]`/`Optional[...]` 形式）→ 语法层面 3.9 可用（**证实**，
  即「3.10+ 语法」的猜想**证伪**）。
  但版本下限**未被验证**且与实际运行环境脱节：实测运行环境是 Python 3.14 + pandas 3.0，
  `numpy>=1.21/pandas>=1.3/scipy>=1.7/matplotlib>=3.4/networkx>=2.6` 这些下限本身在 3.14 上无 wheel
  （会尝试源码构建），是否真兼容**未测**（**疑似**）。建议改用 `>=` 的现代下限 + 在 CI 里跑 3.9/3.12/3.13 矩阵。
- **P3｜`web/__main__.py`**：`ROOT`（`:10`）未被使用；无 CLI 参数（`--port/--host/--no-browser`），
  端口只能改源码；无条件 `webbrowser.open`（`:22-25`，1.5 s 后 daemon 线程）→ 无头/CI/容器里是多余副作用，
  README 若未说明则属未披露行为；`host='127.0.0.1'`（`:28`）是安全的好默认。
- **P3｜`requirements.txt`** 缺 `pydantic`（直接被 `app.py:10` 使用）、缺 dev 依赖（pytest/httpx），
  混装了「运行库」与「viz 库」（matplotlib/networkx 只因 `family_abm/__init__.py` 的顶层导入而成为硬依赖——
  考虑改成惰性导入，让 `import family_abm` 不再强依赖 matplotlib，从而把 web 场景的依赖面收窄）。
- **P3｜`audits/` 产物**：本次审查团队新增（`core_family.md`、`ml_viz.md`、本文件），
  与 `examples/output/*.png` 一样属于「不应进发行包」的内容，`.gitignore`/`MANIFEST.in` 应排除。

---

## 5. 18 参数前后端字段一致性核对表

后端唯一数据源：`family_abm/family/family_member.py:10-29` 的 `DEFAULT_PARAMS`；
分组唯一来源：`app.py:71-78`；前端**完全由 `/api/params` 动态渲染**（`dashboard.js:249-259` 遍历 `paramGroups`，
`data-param="${key}"` 原样使用后端键名；`getParams()` 于 `dashboard.js:263-269` 按 `data-param` 回传）——
因此字段名不存在硬编码漂移。

**实测：`/api/params` 返回 19 个默认参数，分组键与 `DEFAULT_PARAMS` 集合完全相等（`defaults not in groups = ∅`，
`groups not in defaults = ∅`）。**

| 参数名 | 后端（定义行 / 读取行） | 前端（渲染来源 / 标签） | 是否一致 |
|---|---|---|---|
| education_rate | `family_member.py:11` / `:93` | `/api/params` → `data-param`，`param.education_rate` 双语齐备 | ✅ |
| income_base | `:12` / `:102` | 同上 | ✅ |
| income_edu_boost | `:13` / `:103` | 同上 | ✅ |
| income_age_peak | `:14` / `:104` | 同上（**默认 45 > `max="5"`，约束冲突**） | ✅（命名）/ ⚠ 约束 |
| income_age_spread | `:15` / `:105`（`:106` 除零风险） | 同上（**默认 18 > `max="5"`；`min="0"` 可致 500**） | ✅（命名）/ ⚠ 约束 |
| health_decay_base | `:16` / `:115` | 同上 | ✅ |
| health_decay_age | `:17` / `:116` | 同上 | ✅ |
| health_edu_protection | `:18` / `:117` | 同上 | ✅ |
| stress_base | `:19` / `:124` | 同上 | ✅ |
| stress_work_add | `:20` / `:125` | 同上 | ✅ |
| stress_decay | `:21` / `:126` | 同上 | ✅ |
| stress_neuro_sensitivity | `:22` / `:128` | 同上 | ✅ |
| happiness_baseline | `:23` / `:135` | 同上 | ✅ |
| happiness_health_weight | `:24` / `:136` | 同上 | ✅ |
| happiness_income_weight | `:25` / `:137` | 同上 | ✅ |
| happiness_edu_weight | `:26` / `:138` | 同上 | ✅ |
| happiness_stress_penalty | `:27` / `:139` | 同上 | ✅ |
| happiness_recovery | `:28` / `:141` | 同上 | ✅ |
| randomness | `:29` / `:89` | 同上（`param.randomness` 在 `Noise` 组） | ✅ |
| **dt_months（隐藏参数）** | `:88` `_p("dt_months", 1.0)`；**不在 `DEFAULT_PARAMS`、不在 `/api/params`** | **UI 无法设置**（但 API 客户端可借由 `env.params` 传入，见 `app.py:90`） | ❌ 前后端能力不对称 |

**核对结论**

1. **UI 实际暴露 19 个参数，不是 18**（Education 1 + Income 4 + Health 3 + Stress 4 + Happiness 6 + Noise 1 = 19）。
   若「18 个动力学参数」是**把 `randomness` 排除在外**的口径，则数字自洽（19−1=18）；
   否则 README 文案与实现差 1。前端/模板中**没有**任何硬编码的「18」文案（实测三个 web 资源文件均无 `\b18\b`），
   19 个输入框全部由 `/api/params` 渲染。
2. 除 `dt_months` 外，**所有参数名前后端逐字一致**（19/19），i18n 标签 `param.<name>` 与分组标签 `param.<组名>`
   在 zh/en 两侧均齐备（各 74 键，0 缺失）。
3. 缺陷不在「名字」，而在**约束**：所有输入共用 `min="0" max="5"`（`dashboard.js:255`），
   与 `income_age_peak=45`、`income_age_spread=18` 的默认值冲突，且允许会打出 500 的 `0`。
4. **「实时调整」表述偏强**：参数只在点「运行仿真」时随 `POST /api/run` 生效（`dashboard.js:340-345`），
   没有「改动即重算」的联动。

---

## 6. README 声称 vs 实际 差异表

> 前置事实：**仓库根目录不存在 README.md**（实测，见 §4），
> 因此下列「声称」按任务书给出的 README 文案逐条核对实现；README 缺失本身即是 P2 交付缺陷。

| # | README 声称 | 实际（证据） | 判定 |
|---|---|---|---|
| 1 | `pip install -r requirements.txt` | `requirements.txt:1-8` 覆盖 numpy/pandas/scipy/matplotlib/networkx/fastapi/uvicorn/jinja2，**缺 pydantic**（靠 fastapi 传递安装，本次实测 2.12.5 可用） | ⚠ 基本可行（不完整） |
| 2 | `pip install -e .` | 可用——editable 安装不依赖 `package_data`，所以模板/静态文件都在源码树里 | ✅（但掩盖了 P1-3） |
| 3 | `python -m family_abm.web` | `__main__.py:32-33` 存在；`main()` 启动 uvicorn 并（1.5 s 后）自动开浏览器 | ✅ |
| 4 | 访问 `http://127.0.0.1:8520` | `__main__.py:14` `port = 8520`；`:15` `url = http://127.0.0.1:8520`；`:28` `host='127.0.0.1', port=port` | ✅ 一致 |
| 5 | 四个标签页 Setup / Charts / Fitting / Network | `index.html:14-17`（按钮）+ `:34,70,83,114`（四个 section） | ✅ |
| 6 | 右上角 ⚙ 切换 English/简体中文 | `index.html:21-27`（⚙ + 两个 `lang-item`）；逻辑 `dashboard.js:166-171,200-212`；偏好存 `localStorage`（`:131-132`） | ✅（但 ⚙ 的 `title="Settings"`、无 aria；首屏参数区翻译有 bug，见 §3 P2-1） |
| 7 | 18 个动力学参数在仪表板实时调整 | 实际 **19** 个（`app.py:71-78`、`family_member.py:10-29`）；参数仅在下次 Run 生效；2 个字段约束与默认值冲突 | ❌（数量）/ ⚠（「实时」） |
| 8 | REST API（run, data, fit, niche, network） | 5 个端点齐备：`app.py:85,114,144,189,218`；另有未提及的 `GET /api/params`（`:68`）与 `/docs`、`/openapi.json` | ✅（+2 个未列出） |
| 9 | `templates/` 用 data-i18n 双语支持 | `index.html` 26 个 `data-i18n` 键；`dashboard.js` 定义 zh/en 各 74 键；实测 0 缺失、0 不对称 | ✅ |
| 10 | `static/` 放 CSS+JS | `static/css/style.css`（90 行）、`static/js/dashboard.js`（567 行）；**Plotly 走 CDN 不在 static**（`index.html:8`） | ✅（Plotly 除外） |
| 11 | 依赖清单（见 requirements.txt） | requirements.txt 8 项与实际 import 基本吻合（缺 pydantic/dev 依赖）；但**与 `setup.py:7` 严重不一致** | ⚠ |

---

## 7. 建议改进（按收益排序）

1. **修打包（收益最高，直接决定「能不能装」）**：`pyproject.toml` + `[tool.setuptools.package-data]` +
   `MANIFEST.in` 收进 `web/templates`、`web/static`；补全 `dependencies`（scipy/matplotlib/networkx）
   与 `[project.optional-dependencies] web`（fastapi/uvicorn/jinja2/pydantic）；用**实际 wheel 安装**做一次冒烟。
2. **把拟合搬出事件循环**：`run_in_threadpool`（或改 `def`）+ `asyncio.wait_for` 超时 + `n_starts/maxiter` 可配；
   理想是作业化（job_id + 轮询 + 取消）—— 直接消除 §2 P1-1 的 155 s 全站挂起。
3. **会话化运行状态**：`run_id` 键控的存储 + 单飞锁 + TTL，消除跨客户端串数据（§2 P1-2）。
4. **补齐输入校验（pydantic 模型化 + 白名单 + 范围 + `allow_inf_nan=False`）**：
   一次消灭 §2 P2-4 的 11 类 500/静默忽略与 P2-3 的 NaN→500；同时把领域错误映射为 400/422。
5. **修数据语义（让图表可信）**：`/api/data` 按 `agent_type` 分离、取消 `fillna(0)`；
   `/api/niche` 显式 NaN 回退 + income 归一化；`/api/fit` 显式 state 映射注册表并把映射回传/展示（§2 P2-1/P2-2/P2-5）。
6. **可复现性**：`SimConfig.seed` + 注入式 `random.Random`，UI 显示 seed —— 让同一配置可复算。
7. **前端修缮（按价值）**：`await loadParams()` 后再 i18n；家庭名/agent 名改 `textContent`（消 XSS）；
   本地内置 Plotly（或 SRI+回退）；参数级 min/max/step 由 `/api/params` 提供；`api()` 检查 `res.ok`；
   统一 role 词表；按钮 loading/disabled；`#statusText` 排除出 i18n 无差别覆盖。
8. **工程化收口**：README.md（完整启动/离线/端口/浏览器行为/参数数量说明）、LICENSE、`.gitignore`
   （`__pycache__/`、`*.egg-info/`、`build/`、`dist/`、`examples/output/`、`audits/`）、删除工作区中的
   `family_abm.egg-info/` 与 17 个 `.pyc`、`tests/`（pytest + httpx）+ CI（含 wheel 安装冒烟）。
9. **小项**：统一版本号（`app.py:26` vs `setup.py:5`）；`/api/params` 的 `groups` 由 `DEFAULT_PARAMS` 生成并断言相等；
   `__main__.py` 支持 `--port/--host/--no-browser`；接线 `_last_fitter` 或删除；`/api/data` 加降采样/上限。

---

## 附：本次实测数据速查（供 Lead 交叉核对）

| 项 | 实测值 | 证据/方法 |
|---|---|---|
| `GET /` | 200，5630 B，含 8 个模型 `<option>` | TestClient |
| `/api/params` | 200；19 个默认参数，分组 1/4/3/4/6/1=19，集合与 `DEFAULT_PARAMS` 相等 | TestClient |
| `POST /api/run`（默认 families, 120 步） | 200；`agents=7`、`observations=840`、0.02 s | TestClient |
| `/api/data`（120 步） | 200，399 176 B，840 条；`min time=1, max=120`；无 NaN/Infinity 字样 | TestClient |
| `/api/data`（5000 步，1 户 1 人） | 200，4 647 566 B，10 000 条，0.12 s | TestClient |
| NaN 单元格 | 840×20 中 **5760** 个 | `df.isna().sum()` |
| 聚合均值差异 | 前端 0.2556 vs 成员/拟合 0.3578（**−28.6%**） | 实测 |
| `/api/niche` social | 5 个 agent 全 **1.0** | 实测 |
| 拟合耗时 | wellbeing robust **73.5 s**（TestClient）/ **156.3 s**（uvicorn）；influence 28.1；square_law 25.8 | 实测 |
| 并发阻塞 | 拟合期间 `GET /api/params` 延迟 **155.33 s**；拟合结束瞬间 0.02 s | uvicorn 8599 |
| 跨客户端串数据 | A 的 `/api/data` 返回 B 的 `Bob`；`/api/network` 返回 `ClientB Household` | uvicorn 8599 |
| 不可复现 | 3 次相同 run 的 `sum(state_happiness)` = 16.4476 / 15.2104 / 14.7557 | uvicorn 8599 |
| 500 复现 | `income_age_spread=0`；`randomness="abc"`；缺 `name`；未知成员键；`age="old"`；`age=NaN` 后 `/api/data` | TestClient |
| 200 但静默 | `steps=-5`、`steps=0`、拼错参数名、负参数 | TestClient |
| wheel 内容 | 26 个 `.py`，**无 templates/static**；安装后导入 → `RuntimeError: Directory ...static does not exist` | TEMP 构建 + 安装 |
| 导入副作用 | `import family_abm` 引入 matplotlib/scipy；`import family_abm.web` **不绑定端口**（8520 可 bind）；仅 `main()` 调 `uvicorn.run` + `webbrowser.open` | 实测 |
| 端口 | 验证用 8599 **已关闭**；8520 从未占用；无残留 python 进程 | `Test-NetConnection` / `job_kill` |
