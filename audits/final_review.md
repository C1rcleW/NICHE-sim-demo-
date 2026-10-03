# NICHE-sim / family_abm — 只读审查总报告（Lead 汇总）

- 审查对象：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`（Python 包 `family_abm`，约 2024 行 Python + 前端 JS/HTML/CSS）
- 审查方式：**只读**。5 名审查员并行分域审查 + 1 名独立验证员对抗性复核；Lead 全程交叉复核关键结论。
  **未修改任何源码/配置/前端**；所有实验脚本写在 `$env:TEMP`。
- 分域报告（含逐条 `文件:行` 证据、复现脚本、README 对照表）：
  [`audits/core_family.md`](core_family.md) · [`audits/fitting_niche.md`](fitting_niche.md) ·
  [`audits/ml_viz.md`](ml_viz.md) · [`audits/web_packaging.md`](web_packaging.md) ·
  [`audits/verification.md`](verification.md)（对抗性验证）
- 严重度：**P1** 正确性错误/装不上/结论级错误；**P2** 设计或健壮性缺陷；**P3** 可读性与小优化
- 运行环境：CPython 3.14.3 / numpy 2.4.3 / pandas 3.0.2 / scipy 1.17.1 / matplotlib 3.10.9 / networkx 3.6.1 / fastapi 0.136.1

> **最重要的前置事实：仓库根目录没有 README.md**（全仓库无任何 `.md`/`.rst`，也**不是 git 仓库**）。
> 因此下文的「README 声称」是按你提供的 README 文本逐条对代码核对，无法核对仓库原文。

---

## 1. 结论摘要

一句话：**算法骨架清晰、API 设计有想法，但当前版本存在「装不上（非 editable 路径）」「默认参数下模型校准快速崩溃」「拟合结果不可辨识却上报高 R²」「ML 特征标签被伪造」「四维社会空间实际退化为一维」五类结论级问题；README 的多数功能声称与实现存在可量化偏差。**

### 1.1 必修（P1，会直接导致错误结论或不可用）

| # | 问题 | 证据 | 实测 |
|---|---|---|---|
| **P1-1** | **非 editable 安装必崩**：`setup.py` 无 `package_data`/`include_package_data`，无 `MANIFEST.in`/`pyproject.toml` → wheel/sdist **不含** `web/templates`、`web/static` | `setup.py:1-8`、`web/app.py:27` | 独立构建 wheel = **27,693 B / 30 entries / 无 templates+static**；`pip install` 后 `import family_abm.web` → `RuntimeError: Directory '...\web\static' does not exist`。**`pip install -e .`（README 推荐路径）是唯一掩盖它的方式** |
| **P1-2** | **依赖声明与实际严重不符**：`install_requires` 只有 numpy/pandas，而 `import family_abm` 顶层即拉入 `scipy`(fitting) + `matplotlib`(viz) | `setup.py:7`、`family_abm/__init__.py:14-25` | 缺 matplotlib 或 scipy 时 `import family_abm` → `ModuleNotFoundError`；`egg-info/requires.txt` 同样只有两项 |
| **P1-3** | **默认参数下健康校准崩溃**：教育只削减「年龄加速项」，基础衰减不受保护，月度损失 ≈0.0065，健康在 10–15 年内触底硬下限 0.01 | `family_member.py:113-120` + `:16-18` | deterministic 下 30 岁→**41.7 岁触底**（20/40/50 岁→34.4/49.8/58.4）；默认 `randomness=0.02` 时 120 步末 `health<0.2` 概率 **81.7%**、真正触底概率仅 **10%**（触底约需 137 步）。健康/幸福维度在长仿真中彻底失去区分度 |
| **P1-4** | **拟合结果不可辨识却上报**：`wellbeing` 的 `p` 与 `income` 只以乘积 `p*income` 出现，两个自由参数永远无法分别确定 | `lanchester.py:44-52`、`fitter.py:306` | 乘积不变族 (0.01,100)…(1e-8,1e8) 的目标函数**逐位相同**；残差雅可比 SVD σ_min≈4e-10（秩 4/5）；固定 `income=0.5` 与 `=5.0` 得**完全相同**的 `R²=0.950314`。UI 展示的 `p`/`income` 估计值无意义 |
| **P1-5** | **拟合失败被静默美化**：`r_squared = max(0.0, ...)` 把负 R² 截断为 0，而 `converged` 又要求 R²>0 → 「拟合失败」与「拟合极差」不可区分；选起点用未截断值，与上报值不一致 | `fitter.py:233`、`:249-254`、`:171` | 原始 R²=**-3.5175** → 上报 **0.0**；`square_law` 拟合上报 `success=True`、`r_squared=0.0`、`fun=627`（MSE 627 对 0.2–1.0 量纲的观测，等于完全没拟合） |
| **P1-6** | **ML 标签被伪造**：`shift(-lag).fillna(0)` 把「没有下一步」写成真值 0，且特征矩阵 `fillna(0)` | `features.py:36-40` | ml_ready 面板 **485/1680 = 28.9% 标签是伪造 0**（逐行对照 ground truth：485 行无真实下一步，**无一为真实 0**）；选定 11 列的特征矩阵 **51.9%** 单元格是伪造 0 |
| **P1-7** | **ML 标签语义依赖行顺序**：`groupby(...).shift(-lag)` 是组内位置操作，隐含「行序 == 时间序」假设且无任何校验 | `features.py:39` | native / `sort(agent,time)` 错位 0；**`df.sample(frac=1)` 错位 1190/1195 = 99.6%**，`iloc[::-1]` 错位 100%；错位行平均绝对误差 0.0993 ≈ target 标准差 0.0988（监督信号被抹成噪声），且**无任何报错** |
| **P1-8** | **`square_law` 结构性发散且被当成功返回**：系数矩阵特征值 `±√(αβ)` 是不稳定鞍点，无自限项，`eps` 只平移不稳定平衡点 | `lanchester.py:9-17`、`fitter.py:118/149/203` | `y0=[1,0.8], params=[0.3,0.25,0.5,0.4]` → `R1=2.4872e13`、`R2=-2.2705e13`（两名审查员+验证员逐位一致）。**数据质量提示**：措辞应精确为「结构上存在不稳定鞍点、大 α/β 下发散」，并非边界内必然发散（α=β=eps=1e-4 时有界） |
| **P1-9** | **Web 端全局单例状态串台 + 阻塞事件循环**：模块级 `_sim_*` 被所有请求共享；`async def` 内同步跑 CPU 密集拟合 | `web/app.py:30-33, 85-165` | 客户端 A 跑完 ClientA 后，B 跑 ClientB，**A 的 `/api/data` 返回 B 的数据**；uvicorn 实测 wellbeing robust **156.3 s**，期间另一客户端 `GET /api/params` 延迟 **155.33 s**。`fit_global` 按实测 35.7 ms/eval 外推 5 参数 `maxiter=1000` ≈ **45–57 分钟**（足以拖死服务） |
| **P1-10** | **仪表板可稳定触发 500**：`income_age_spread` 输入框 `min="0"`，`parseFloat(v)||0` 会把空值变 0，而 `math.exp(-x/(2*spread**2))` 直接除零 | `family_member.py:104-106`、`dashboard.js:255,266`、`web/app.py:90` | `income_age_spread=0` → `ZeroDivisionError`（`/api/run` 无 try/except）；`age=NaN` → `/api/data` 500（`JSONResponse` 拒绝 NaN）；`steps=-5` 静默空跑 |
| **P1-11** | **`examples/fitting_viz_demo.py` 在声明支持的 Python 版本上 import 即报错**：用了 `pd.DataFrame` 注解但**从未 import pandas**，且无 `from __future__ import annotations` | `examples/fitting_viz_demo.py:54,82,134,177` | `python_requires>=3.9`：3.9–3.13 上 import 期 `NameError: name 'pd' is not defined`；本机 3.14 因 PEP 649 惰性注解被掩盖（访问 `__annotations__` 即抛错）→ 典型「本机能跑、用户装完就崩」 |

### 1.2 高优先（P2，设计/健壮性）

| # | 问题 | 证据 |
|---|---|---|
| P2-1 | **仿真完全不可复现**：全包仿真链路无任何 seed 入口（仅拟合/graph layout 用了固定值）；调度顺序的随机消耗会平移所有状态轨迹 | `family_member.py:48,52-56,110,119,130,142,147`、`relationships.py:17-21,32-34`、`scheduler.py:17-23`；实测同输入两次 happiness 0.4151 vs 0.3835 |
| P2-2 | **缺 t=0 基线**：先 `step()` 后 `record()`，`run(3)` 只记录 [1,2,3]；fitter 的 `y0` 实为「走完第一步后的状态」→ 所有拟合存在 1 步相位偏移 | `simulation.py:30-36`、`fitter.py:112,145,199`、`viz/plots.py:287` |
| P2-3 | **`reset()` 不重置 `Scheduler.time`**：`run(5)`→reset→`run(3)` 记录 [6,6,7,7,8,8]，时间轴断裂且状态未回滚 | `simulation.py:48-52` vs `scheduler.py:32` |
| P2-4 | **双时钟可让时间倒流**：`Environment.step()` 与 `Scheduler.step()` 各有一套自增逻辑，混用后 `env.time` 回退 | `environment.py:37-41`、`scheduler.py:28-33` |
| P2-5 | **家庭层无因果**：`Relationship` 是纯随机游走（无任何模块读取其状态），`Household.total_income` 滞后成员一步且无人读取，`roles.py` 四个角色类从未被实例化，`ROLE_REGISTRY` 导入即弃 | `relationships.py:31-34`、`household.py:54-62`、`roles.py:5-59`、`web/app.py:17` |
| P2-6 | **`total_income` 滞后一步**（sequential 下 Household 先 step）：实测 step1 成员 0.0236 / 家庭 0.0，step2 才会出现 | `household.py:58-62`、`scheduler.py:29` |
| P2-7 | **角色与年龄脱钩**：构造时 `role` 直接写 `role_name`（默认 "adult"），不按年龄推导；`role_name="parent"`（README 示例与 UI 都用）首步落兜底乘数 0.2，次步被覆盖 | `family_member.py:40,50,68-73,78,107-108` |
| P2-8 | **`dt_months` 语义不一致**：只作用于教育/健康/年龄三段，stress/happiness/energy 未乘 dt；energy 甚至完全忽略 dt | `family_member.py:88,98,118,151` vs `:122-148` |
| P2-9 | **`dt_months` 是隐性参数**且不在 `DEFAULT_PARAMS`；UI 实际暴露 **19** 个参数而非 README 的 18 个 | `family_member.py:10-30,88`、`web/app.py:71-78`（1+4+3+4+6+1=19） |
| P2-10 | **失败哨兵 `1e12` 不是上界**：合法发散参数的目标函数可达 `3.17e44`，优化被驱向「积分失败平台」（梯度 0，L-BFGS-B 原样返回起点且 `success=True`） | `fitter.py:86-94`；实测 `params=[5,5,5,5]` → `objective=1.0e12` |
| P2-11 | **默认参数边界一刀切** `(1e-4, 5.0)`：对 `K`/`k1`/`k2`/`target1`/`target2` 量纲不合适，`target2=0.0` 根本不可达；`influence` 恒收敛到固定 target，无法表现共识/极化 | `fitter.py:118,149,203`、`lanchester.py:30-41` |
| P2-12 | **`/api/fit` 静默错误映射**：列名不匹配时把 `R1/R2/O1/O2` 映射到任意前 N 个 `state_` 列（实测落到 `state_total_income`、`state_savings`——后者**恒为 0**），返回 200 与看似合理的 R² | `web/app.py:154-161`；实测 `influence` 拟到方差为 0 的列还报 R²=0.878 |
| P2-13 | **NaN→0 静默数据污染**：recorder 对 Household 行没有成员状态列（实测 5760 个 NaN 单元格），`/api/data` 用 `fillna(0)` 抹平 → 前端聚合比真实值**低 28.6%**，与 fitter 的 NaN 跳过均值不是同一序列 | `ml/recorder.py:23-38`、`web/app.py:130-134`、`fitter.py:55-66` |
| P2-14 | **「四维社会空间」实际退化**：`social_capital` 只有 Household 有，成员行为 NaN → `min(1.0, nan)=1.0` 使 **social 维度恒为 1.0**；`economic` 直接吃 `income`（≈0.008–0.13）无归一化，压在低端 | `micro_niche.py:15-17,45-54`、`household.py:20`、`web/app.py:202-208`；实测跨 agent 标准差 [0.055, 0.165, **0.000**, 0.014] |
| P2-15 | **`MicroNiche.distance_to` 对维度顺序敏感**：两个位置字典完全相同的 niche，只要 `dimensions` 顺序不同，距离就不是 0（实测 0.447）；维度数不同直接 `ValueError` | `micro_niche.py:19-34` |
| P2-16 | **`Resource.transfer_to` 不守恒**：`other.add()` 受 capacity 截断但差额不退回 | `resources.py:12-28`；实测 1.0→1.0 转 0.5，总量 2.0→**1.5**（凭空消失 0.5） |
| P2-17 | **`Resource` 无负数防护**：`add(-3)` 使值变负、`remove(-5)` 使值变大；`ResourceBundle.get()` 对未知 key 静默回退 economic | `resources.py:12-23,61-68` |
| P2-18 | **`viz/plots.py` 在 import 期强制 `matplotlib.use("Agg")`**，覆盖调用方后端且 `plt.show()` 失效；而 README 示例 `plot_timeseries(df)` 无 `save_path` | `viz/plots.py:8`；实测 svg→Agg + `FigureCanvasAgg is non-interactive` |
| P2-19 | **`plot_timeseries` 不按 agent 分组**：6 agents×30 steps 画成一条 180 点、含 150 次重复 t 的折线；`plot_aggregate` 把 Household 专属列与成员列画在一起 | `viz/plots.py:41-50,70-82` |
| P2-20 | **无测试、无 CI、无 LICENSE、无 .gitignore、非 git 仓库**；`__pycache__` 与 `family_abm.egg-info` 已入库（`SOURCES.txt` 已过期，不含 templates/static） | 全仓库 glob 证据 |

### 1.3 P3（选摘）

- `Agent.attributes/state` 用 `x or {}` 直接持有调用方字典（**非空则别名共享、空则换新对象**），`get_state()` 又是浅拷贝，嵌套 `personality` 可被外部改坏（`agent.py:14-15,22-29`）。
- `add_hook` 对拼错的 stage 静默丢弃；`Scheduler` 构造时不校验 method（错误延迟到首次 step）；`Scheduler("parallel"/"simultaneous")` 直接 `ValueError`（`simulation.py:22-24`、`scheduler.py:8-10,12-26`）。
- `Environment.width/height/properties/x/y` 全是死参数，暗示存在空间模型而实际没有（`environment.py:7-20`）。
- `compare_models` 对 7 个模型中 6 个直接不可用（不做 state 映射），且不能传 `state_mapping`（`fitter.py:336-350`）。
- 前端：首次加载中文时参数区仍是英文（`init` 未 `await loadParams`）；Plotly 仅 CDN 无离线回退；agent/家庭名走 `innerHTML`（注入风险）；`income_age_peak`/`income_age_spread` 默认 45/18 与输入框 `max="5"` 冲突（`dashboard.js:249-259,369,515,564-566`、`index.html:8`）。
- README 的 `from family_abm import make_fitter, wellbeing_balance, solve_model, ...` 实际上 `make_fitter`/`wellbeing_balance` 等**不在** `family_abm.__all__` 中（能用、但未声明导出，`__init__.py:14-42`）。
- 全库无 `sklearn`/`torch` import、`FeatureExtractor` 无 `fit/transform` → README 的「可直接对接 sklearn / PyTorch 工作流」是**能力声称**（输出 ndarray 可喂）而非适配实现。

---

## 2. README 声称 vs 实际实现

| README 声称 | 实际 | 判定 |
|---|---|---|
| `pip install -r requirements.txt` + `pip install -e .` | 只有 `-e` 能跑；普通安装 wheel 缺 templates/static，`import family_abm.web` 抛 `RuntimeError` | ❌ **仅在 `-e` 下成立** |
| `python -m family_abm.web` → `http://127.0.0.1:8520` | 端口 8520 / host 127.0.0.1 / 1.5 s 后开浏览器，均与文档一致；`import family_abm.web` 不绑端口 | ✅ 一致 |
| Setup / Charts / Fitting / Network 四个标签页 | index.html 四个 tab 齐备；⚙ 切换 English/简体中文齐备 | ✅ 一致 |
| **18 个动力学参数**可在仪表板实时调整 | `/api/params` 实际暴露 **19** 个（Education 1 + Income 4 + Health 3 + Stress 4 + Happiness 6 + Noise 1）；`DEFAULT_PARAMS` 也是 19 个键 | ❌ 数量不符（唯一自洽口径是「排除 randomness = 18」） |
| 7 种内置 ODE 模型 | `MODEL_REGISTRY` 7 个 ✓，但 `square_law` 结构性发散、`influence` 恒收敛到固定 target、`wellbeing` 的 p/income 不可辨识 → **名义 7 个、可信可用约 3–4 个** | ⚠️ 部分成立 |
| 拟合支持多起点鲁棒优化 + 差分进化全局搜索 | 两条路径都存在；但 `fit_robust` 上报值被截断、`fit_global` 5 参数外推 45–57 分钟、`influence` 模型在 UI 中可能被静默映射到无关列 | ⚠️ 功能存在、质量不达标 |
| 状态记录 → DataFrame → 特征提取，可直接对接 sklearn / PyTorch | DataFrame ✓；但标签/特征被 `fillna(0)` 伪造、无 sklearn 适配层、无 train/test 划分 | ❌ 声称过度 |
| 小生境理论：四维社会空间（经济/文化/社会/情感）+ 距离与重叠度 | 维度定义存在，但 **social 恒为 1.0**、economic 无归一化 → 实际约一维；`overlap` 全落在 0.90–0.98 区间无区分度 | ❌ **名实不符** |
| 每个人拥有独立人格、年龄轨迹、教育、收入、健康、情绪状态 | 字段与更新逻辑齐备 ✓；但默认参数下健康 10–15 年内触底、压力在 neuroticism>0.67 被 clamp 饱和、角色与年龄脱钩 | ⚠️ 结构 ✓ / 校准 ✗ |
| 收入 = 基础值 ×(1+教育加成×受教育水平)×年龄曲线×角色乘数 | 公式一致 ✓（`family_member.py:102-109`） | ✅ 一致 |
| 健康 = 基础衰减 + 年龄加速衰减，**教育减缓健康衰减** | 教育只削减「年龄加速项」，**基础衰减不受保护**（`:117-118` 的 `edu_protect` 只乘在 `age_decay` 上） | ❌ 与文字不符 |
| 压力 = 基础 + 工作负荷，受神经质放大，自然衰减 | 公式一致 ✓，但默认均衡点 ≥1 被 clamp 截断，神经质 0.7 以上几乎失效 | ⚠️ 部分成立 |
| 幸福 = 均值回归，目标 = 基底 + 健康权重×健康 + 收入权重×收入 + 教育权重×教育 − 压力惩罚×压力 | 结构一致 ✓；但用的是**更新前的 health/stress** 与更新后的 edu/income（步内混合读写），且收入项额外乘 3 再截断（未文档化） | ⚠️ 部分成立 |
| 精力 = 简单恢复-消耗循环 | 存在硬编码 0.92/0.06，完全忽略 dt；初值 [0.6,1.0] 与稳态 0.75 不一致 → 前 20 步是初始化漂移 | ⚠️ 过于简化 |
| 依赖：numpy, pandas, scipy, matplotlib, networkx, fastapi, uvicorn, jinja2 | requirements.txt ✓ 齐；但 `setup.py` 只声明 numpy/pandas；实际还隐性依赖 `pydantic` | ❌ setup.py 不完整 |
| 项目结构树 `core/ family/ niche/ ml/ fitting/ viz/ web/` | 与代码一致 ✓；但 `web/templates` 与 `web/static` 未被打包 | ⚠️ 源码 ✓ / 分发 ✗ |
| `from family_abm import Environment, ..., make_fitter, wellbeing_balance, solve_model, plot_timeseries, plot_fit_diagnostics` | 全部可导入 ✓（`make_fitter`/`wellbeing_balance` 不在 `__all__` 但可用） | ✅ 可用 |
| `plot_timeseries(df)` / `plot_fit_diagnostics(df, fitter)` 直接调用 | 可调用 ✓，但后台被强制 Agg，不传 `save_path` 时图看不到 | ⚠️ 部分成立 |

---

## 3. 优化建议（按投入产出排序）

### 阶段一：让项目「装得上、跑得对」（建议 1–2 天，最高优先级）

1. **打包修复**：新增 `pyproject.toml`（含 `[project] dependencies` 完整清单 + `[tool.setuptools.package-data]` 或 `include-package-data = true` + `MANIFEST.in` 收 `templates/**`、`static/**`）；`setup.py` 补齐 scipy/matplotlib/networkx/fastapi/uvicorn/jinja2/pydantic；CI 里加一条「构建 wheel → 装进干净 venv → `import family_abm.web` + `GET /` = 200」的冒烟测试，彻底堵住 P1-1/P1-2。
2. **健康/压力校准**：把 `edu_protect` 改为对总衰减生效（`hp_change = -(base_decay + age_decay) * (1 - edu_protect) * dt`），并把 `health_decay_age` 从 `1.5e-4` 降到 ~`2e-5` 量级或引入下限恢复项，使 50 年仿真内健康仍具区分度；压力改为解析均衡 + 对神经质归一化（或去掉 clamp、改用 `tanh` 饱和），保证 `neuroticism` 在整个 [0,1] 单调有效。
3. **可复现性**：`Simulation(seed=...)` → 注入 `random.Random(seed)` 与 `np.random.Generator`，在 `FamilyMember`/`Relationship`/`Scheduler` 中改用实例 RNG；Web 端为每个 `run_id` 建独立会话与种子。
4. **修仪表板 500**：参数做 pydantic 约束（`income_age_spread > 0`、`steps ∈ [1, 5000]`、参数白名单与类型强校验），`/api/run` 包 try/except 返回结构化错误；前端 `parseFloat(v) ?? default` 并去掉与默认值冲突的 `max="5"`。
5. **修 ML 标签**：`extract_features` 先 `sort_values(["agent_id","time"])`，用 `mask = y.notna()` 丢弃无下一步的样本（**不要 `fillna(0)`**），删除 no-op 截断；特征改为「按 `agent_type` 分表 + 排除 `attr_*`/target 自身 + 保留 NaN 交给 pipeline」。
6. **修正确性上报**：去掉 `max(0.0, ...)`，直接上报真实 R²（允许负值）；`converged` 改为「优化器成功 **且** R² ≥ 阈值 **且** 无参数贴边」；目标函数改用 `np.inf` 表示失败，并对发散设置上界检查（如 `|y| > 1e6` 直接判失败）。

### 阶段二：让模型「讲得通」（建议 3–5 天）

7. **恢复 ODE 模型的可解释性**：`square_law` 加自限/损耗项或饱和项（如 `-α·R2 - c1·R1`），否则该模型只能拟合到发散分支；`wellbeing` 把 `income` 从自由参数改为**输入序列**（或固定 `p`、只拟合比值），消除 P1-4；`influence` 增加不对称/时变 target 以支持极化结局。
8. **拟合协议升级**：按模型给参数设置**物理量纲相关的边界**（`K`、`k1/k2`、`target1/2`）；引入参数个数惩罚（AIC/BIC）与留出验证；`compare_models` 支持 `state_mapping` 并对「映射后语义不匹配」直接报错而非静默拟合。
9. **Niche 模型补全**：为每个 `FamilyMember` 派生 `social_capital`/`cultural_level` 状态（例如由关系网络度数 + 教育合成），并对 economic 做 min-max/对数归一化；`distance_to` 改为按 `dimensions` 对齐取值（`np.array([self.position[d] ... for d in sorted(set(self.dimensions)|set(other.dimensions))])`）；`transfer_to` 返回未转移量、`Resource.add/remove` 拒绝负数并**添加守恒断言**。
10. **家庭层因果闭环**：让 `Household`/`Relationship` 反向影响成员（如通过 `Relationship.influence_weight` 对 happiness/stress 施加耦合项），或明确把家庭层降级为「只读聚合视图」并删除死代码（`roles.py` 的四个 Role 类、`InfluenceRelation`、`Environment` 的空间参数），避免「看起来有机制、实际不产生因果」。

### 阶段三：工程化与性能（建议持续）

11. **可观测性与测试**：新增 `tests/`（pytest）：① 时间轴 [1..N] 且 `reset` 后回到 [1..N]；② `to_dataframe` 列契约与 NaN 语义；③ 每个 ODE 模型的有界性与守恒；④ `extract_features` 的标签对齐（用 ground-truth 查表断言）；⑤ 打包冒烟。补 LICENSE、.gitignore（`__pycache__`、`*.egg-info`、`examples/output`）、把仓库纳入 git。
12. **性能**：`_extract_aggregate_series` 的逐时刻循环改向量化 `groupby().mean()`；目标函数中 ODE 求解改为「一次 `solve_ivp` + `t_eval` 复用」并对高频数据降采样；`fit_global` 的 `maxiter` 从 1000 降到 50–100 或改用 `polish` + 多起点混合；`/api/fit` 改为后台任务（`BackgroundTasks`/线程池 + `run_id` 轮询），避免 155 s 级阻塞。
13. **Web 架构**：消除模块级 `_sim_*` 单例，改为 `run_id → session` 的显式存储（带 TTL/LRU 上限）；`setup.py`/前端参数单一真源（由 `/api/params` 生成，顺带修正「18 vs 19」的文档口径）；Plotly 本地化以支持离线；`innerHTML` 注入点改 `textContent`。

---

## 4. 审查过程中产生的副作用（需要你知晓）

- **源码/配置/前端零改动**（已核验：近 3 小时内没有任何 `.py/.js/.html/.css/.txt` 被修改）。
- 但 `examples/fitting_viz_demo.py` 被审查员按 README 实跑了一次，**按脚本自身逻辑覆盖重写了 `examples/output/` 下的 10 个 PNG**（12:44），并产生 `examples/__pycache__/simple_family.cpython-314.pyc`。由于仿真未播种，这些图与你原先的产物**不会逐像素相同**——如果你的仓库对这些 PNG 有版本管理，请自行决定是否还原。
- 新增文件仅 `audits/` 下的 5 份报告（`core_family.md`、`fitting_niche.md`、`ml_viz.md`、`web_packaging.md`、`verification.md`）与本汇总。

## 5. 存疑与未证实项（透明说明）

1. `square_law` 拟合的 `fun=602.966` 这一具体数值**不可移植**（验证员在 0.0004–799.9 区间随数据/映射变化），但「`success=True` + R² 上报 0.0」这一结论可复现；严重度不变。
2. `wellbeing` 的 p/income 不可辨识已严格证实（SVD 秩 4/5、目标函数逐位相同）；具体 SVD 数值随数据不同，不具唯一性。
3. 健康触底的年龄（41.7 vs 41.8）与门限概率取决于是否固定 `randomness`；报告中的里程碑已在验证报告中概率化修正。
4. `pd.concat` 重复段落导致的标签错位依赖具体构造（验证员测到拼接自身不错位），不影响 P1-7 的定性。
5. Web 端 155 s 阻塞实测用的是 `TestClient`/本地 uvicorn；真实浏览器端到端 HTTP 行为（含 CORS、超时、多标签页竞争）未做完整压测。
6. `niche` 的重叠度 `overlap` 在 4 维上全落在 0.90–0.98，我判断其区分度不足，但「合适阈值」属建模选择，未下定论。
7. `pip install -e .` 掩盖打包缺陷一事已在干净 venv 中验证；但不同 pip/setuptools 版本下 editable 实现（`.pth` 的 MAPPING vs `__editable__` finder）行为可能不同。
