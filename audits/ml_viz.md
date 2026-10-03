# ml + viz + examples 审查报告

- 审查对象：`F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`（Python 包 `family_abm`）
- 审查方式：只读代码审查 + pwsh 实跑验证（临时脚本写在 `%TEMP%`，未修改仓库任何文件；唯一写入为本报告）
- 实跑环境：Windows / Python **3.14.3**、numpy 2.4.3、pandas **3.0.2**、scipy 1.17.1、matplotlib 3.10.9、networkx 3.6.1；工作目录=仓库根，`PYTHONPATH=<repo>`，`PYTHONUTF8=1`
- 审查范围：`family_abm/ml/{recorder,features,__init__}.py`、`family_abm/viz/{plots,__init__}.py`、`family_abm/__init__.py`、`examples/{simple_family,ml_ready,fitting_viz_demo}.py`（另读了只读依赖：`core/*`、`family/*`、`niche/*`、`fitting/*`、`setup.py`、`requirements.txt`）

---

## 1. 结论摘要（最关键问题）

> **P1 的准确定性（Lead 已裁定并撤回其原线索 1 中「跨 agent 边界错位 = agent 数」的说法）**：ml 侧的 P1 是以下四条，而不是"边界错位"：
> **(a)** `features.py:39` 对标签 `fillna(0)` → 伪造监督标签；
> **(b)** `features.py:39` 的标签语义**依赖行顺序**（组内 `shift` = 组内位置，而非"时间相邻"），重排/采样/拼接即**静默错位**；
> **(c)** `features.py:39-40` 的 `[:len(X)]` / `X[:len(y)]` 截断是 **no-op**（`len(y) == len(X)`），既不修对齐也不修尾部，纯误导；
> **(d)** `features.py:31-36` 特征侧 `fillna(0)` + 选列口径错误（Household 专属列、`attr_age` 静态属性、target 自泄漏）。

1. **P1(a) 标签污染**：`FeatureExtractor.extract_features`（`features.py:39`）对 target 做 `shift(-lag).fillna(0)`，把「没有下一步」写成真值 0。实测 `examples/ml_ready.py` 的面板：1680 条标签里 **485 条（28.9%）是伪造的 0**（480 条 Household 行 + 7 个 agent 的末步）。当前状态下**不能**直接拿去做监督学习。
2. **P1(b) 标签语义依赖行顺序**：三种正常面板顺序（原生录制顺序 / `sort(agent,time)` / `sort(time)`）实测位置错位 **0/116**——即 Lead 原线索 1 的「跨 agent 边界错位」**经双方独立 ground-truth 复核后证伪并撤回**；但 `sample()` 打乱后错位 **113/116**（Lead 独立复核：**146/150**），`pd.concat` 追加重复段落错位 3 处 → 重排即静默错位，属真实 P1 隐患（详见 ML-2）。
3. **P1(c) 截断无效**：`features.py:39-40` 的 `[:len(X)]`、`X[:len(y)]` 永远不生效（实测 y、X 行数相同），读起来像"已对齐"，实际未做任何对齐/去尾。
4. **P1(d) 特征污染**：同一函数（`features.py:36`）对特征做 `fillna(0)`，实测选定 11 列的 X 中 **9600/18480 = 51.9% 单元格是伪造 0**；默认列（`features.py:31-34`）还会把 `attr_age` 静态属性和 target 列本身选进来（零单元格 51.1%）。Household 行几乎是全 0 向量。
5. **P1 时间轴/数据契约被破坏**：`Simulation.reset()` 不重置 `scheduler.time`（`simulation.py:48-52` vs `scheduler.py:32`），实测 `run(5)`→`[1,1..5,5]`，`reset()`+`run(3)`→`[6,6,7,7,8,8]`，同一 recorder 内两个 episode 时间轴不连续。另外 **t=0 基线从未被记录**（`run(12)` → `[1..12]`），fitter 的 `y0` 因此相位晚一步（ML-11）。
6. **P1 依赖/安装**：`setup.py:7` 只声明 `numpy/pandas`，但 `import family_abm` 需要 matplotlib 和 scipy（`family_abm/__init__.py:14-25`）。实测导入阻断：缺 matplotlib → `ModuleNotFoundError`，缺 scipy → 同样失败。
7. **P1 examples 在声明的 Python 版本上会崩**：`examples/fitting_viz_demo.py:54` 使用未导入的 `pd.DataFrame` 注解且文件无 `from __future__ import annotations`，在 `python_requires>=3.9` 的 3.9–3.13 上 import 期 `NameError: name 'pd' is not defined`；本机 3.14 因 PEP 649 惰性注解被掩盖（实测访问 `__annotations__` 即抛错）。
8. **P2 可视化正确性**：`viz/plots.py:8` 在 import 期强制 `matplotlib.use("Agg")`，实测覆盖调用方后端（svg→Agg）且 `plt.show()` 报 `UserWarning: FigureCanvasAgg is non-interactive`；`plot_timeseries` 不按 agent 分组，实测 6 agents×30 steps 的 180 行被画成**一条 180 点、含 150 次重复 t 的折线**；`plot_aggregate` 默认把 Household 专属列与成员列画在同一均值面板。

---

## 2. ml 发现

### ML-1 [P1] `extract_features` 用 `fillna(0)` 伪造监督标签
- **证据**：`family_abm/ml/features.py:38-40`
  ```python
  y = df.groupby("agent_id")[target_column].shift(-lag_steps).fillna(0).values[:len(X)]
  X = X[:len(y)]
  ```
- **实测（`examples/ml_ready.py` 面板，1680 行 / 7 agents，含 2 个 Household）**：
  - `y == 0` 计 **485 / 1680 = 28.9%** = Household 行 480（其 `state_happiness` 全为 NaN）+ 每个 agent 末步 7。
  - 小面板（180 行 / 6 agents）同样成立：64/180 = 35.6%。
- **影响**：把「无标签」当成「幸福感=0」的强负样本，模型会学到 Household 行/末步 → 0 的伪规律；R²/RMSE 与任何下游训练全部失真。
- **修复建议**：
  ```python
  df = df.sort_values(["agent_id", "time"]).reset_index(drop=True)
  y = df.groupby("agent_id")[target_column].shift(-lag_steps)
  mask = y.notna()                      # 有真实下一步才保留
  return X[mask.values], y[mask].to_numpy()
  ```
  或直接改用 `build_transition_dataset`（它内部按 agent 排序，语义正确）。

### ML-2 [P1] 标签语义依赖行顺序：重排/拼接/抽样后静默错位（Lead 线索 1 的证伪 + 双方独立 ground-truth 复核）
- **证据**：`family_abm/ml/features.py:39` —— `groupby("agent_id")[...].shift(-lag)` 是**组内位置**操作，隐含假设「同一 agent 的行序 == 时间序」；而 `features.py:36` 的 `X` 用的是 `df[...].values` 的**行位置**。
- **我的实测（ground truth = 逐行查「同一 agent 下一个 time」的记录）**：

  | 面板变体 | 有真实下一步的行 | 位置错位 |
  |---|---|---|
  | 原生录制顺序（step-major，agent 交错） | 116 | **0** |
  | `sort_values(["agent_id","time"])` | 116 | **0** |
  | `sort_values("time")` | 116 | **0** |
  | `df.sample(frac=1.0)` 打乱 | 116 | **113** |
  | `pd.concat([df, df.iloc[:5]])` 附加段落 | 119 | **3**（跨拼接边界回绕到 t=1） |

  另有直接证据：`SeriesGroupBy.shift` 返回的 index 顺序 == df 行序（`shift result index equals df index order: True`），所以**不是**「跨 agent 边界错位」，而是「重排后组内位置 ≠ 时间相邻」。
- **Lead 的独立复核（同一 ground-truth 方法，独立面板/面板规模）**：native order **0/145**、`sort(agent,time)` **0/145**、`sample` 打乱后 **146/150** —— 与我的结论一致。
- **裁定与记录**：Lead 已撤回原线索 1 中「跨 agent 边界错位 = agent 数」的说法。**证实**的部分是：`y[0]=0.0` 源于第 0 行是 Household（`state_happiness` 全 NaN，见 ML-1）；`[:len(X)]` 截断无效（见 ML-1 / ML-12）。**证伪**的部分是：正常顺序下 X/y 位置对齐本身是正确的。
- **影响**：用户只要 `sample()`/`concat()`/自定义重排（做 train/test 划分时非常常见），就会拿到**静默错位**的标签，毫无报错。
- **修复建议**：在 `extract_features` 内先 `df.sort_values(["agent_id","time"]).reset_index(drop=True)` 再 shift（配合 ML-1），并删除无意义的 `[:len(X)]`；更稳妥是让 `extract_features` 直接复用 `build_transition_dataset` 的结果——后者在 `features.py:55-57` 内部 `groupby` 后 `sort_values("time")`，实测**顺序鲁棒**：native 与 `sample()` 打乱两种面板下，19/19 个 `(t, t+1)` 配对与 native 真值完全一致。

### ML-3 [P1] 特征矩阵 `fillna(0)` + 选列口径错误（Household 列、静态属性、target 自泄漏）
- **证据**：`family_abm/ml/features.py:31-36`
  ```python
  numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
  if "time" in numeric_cols: numeric_cols.remove("time")
  feature_cols = feature_columns or numeric_cols
  X = df[feature_cols].fillna(0).values
  ```
- **实测（ml_ready 面板 1680×20）**：
  - 显式传入的 11 列 X：NaN 单元格 9600/18480 = **51.9%** 被填成 0；
  - 默认 `feature_cols`（13 列）= `state_total_income, state_savings, state_housing_quality, state_neighborhood_quality, state_cultural_level, state_social_capital, attr_age, state_health, state_happiness, state_stress, state_energy, state_education, state_income`；
  - 其中 `state_happiness` 就是 target（**同一时刻的目标值进入 X**，若按"预测当前值"理解即直接泄漏；即使按"预测下一步"也属自回归，函数未文档化、未排除）；
  - `attr_age` 是**静态属性**而非状态；`alive` 常量列也被视为候选；
  - Household 专属列（total_income/savings/...）在成员行上全 NaN，成员列在 Household 行上全 NaN → 两类 agent 各自被填成大片 0，`X` 行向量分布完全不可比。
- **影响**：距离/方差/树分裂阈值被大量伪造 0 扭曲；两个 Household 在特征空间里几乎是零点；任何 imputer/scaler 都失去意义。
- **修复建议**：默认列改为「按 `agent_type` 分表 + 只取该类型真实存在的 state 列」，禁止对特征 `fillna(0)`（保留 NaN 交给 pipeline 或显式 `SimpleImputer`），显式排除 `attr_*`/`alive`/`target_column`，并新增文档说明列语义。

### ML-4 [P2] 环境级状态（population / properties）无法导出为 DataFrame/CSV
- **证据**：`family_abm/ml/recorder.py:40-46`
  ```python
  def get_data(self): return {"environment": self.history, "agents": self.agent_history}
  def to_dataframe(self):
      if self.agent_history: return pd.DataFrame(self.agent_history)
      return pd.DataFrame()
  ```
  实测：`record_agents=False` 时 `to_dataframe()` 返回 `(0, 0)` **无列空表**；`get_data()["environment"]` 的 20 条 step 级记录（`{'time':1,'population':3,'environment':{...}}`）**没有任何导出通道**；`to_csv` 同样只写 agents。
- **影响**：README 声称的「状态记录 → DataFrame」只覆盖 agent 级；人口/环境时间序列必须手工 `get_data()` 再拼。
- **修复建议**：`to_dataframe(level="agent"|"environment"|"both")`；`to_parquet`（仓库全库 0 处 parquet，见 README 对照表）；`to_csv` 按 level 分文件。

### ML-5 [P2] `get_data()` 返回内部 list 引用（别名共享）
- **证据**：`family_abm/ml/recorder.py:41` 直接返回 `self.history` / `self.agent_history`，未 copy。实测向返回值 append 后 `recorder.history` 长度 20→21（`aliasing!`）。
- **影响**：调用方（含 web 层 `family_abm/web/app.py` 使用 `to_dataframe`）无意中修改记录器内部状态；`to_dataframe()` 反而每次新建对象（实测 `is not` 为 True，这点是好的）。
- **修复建议**：返回 `list(...)` / `copy.deepcopy`（或文档声明只读）。

### ML-6 [P2/疑似] 非标量与 numpy 标量被静默丢弃
- **证据**：`family_abm/ml/recorder.py:32-37`
  ```python
  if isinstance(attr_val, (str, int, float, bool)): record[f"attr_{attr_key}"] = attr_val
  ...
  if isinstance(state_val, (int, float)): record[f"state_{state_key}"] = state_val
  ```
  实测：`isinstance(np.int64(3), int)` = **False**、`isinstance(np.float32(.5), float)` = **False**、`isinstance(np.bool_(True), bool)` = **False**（`np.float64` 为 True）。
- **影响**：`FamilyMember` 的 `personality` 是 dict（`family/family_member.py:47-49`，含 neuroticism 等 5 维，是 stress 方程的因果输入）被**静默丢弃**，面板里没有 `attr_personality_*`；若下游用 numpy 标量写 state/attribute，也会无声消失。
- **修复建议**：用 `numbers.Real`/`np.number` 判定；对 dict 型属性做 `attr_personality_neuroticism` 之类的展开或 JSON 序列化；未识别类型至少 `warnings.warn`。

### ML-7 [P2] 全量历史无上限、无流式导出，内存随步数线性增长
- **证据**：`family_abm/ml/recorder.py:11-12,38`（`list[dict]` + 每步 append，`__init__` 只有 `record_agents/record_environment`，无 `max_steps/flush/buffer`）。
- **实测**：21 agents × 200 steps = 4200 行，`tracemalloc` 保留 **5.02 MB ≈ 1196 B/行**（每行 11 键的 dict）。外推：100 agents × 10⁴ steps = 10⁶ 行 ≈ **1.2 GB**。
- **修复建议**：`max_steps` 环形缓冲、`flush_every` 批量写 CSV/parquet、`to_dataframe()` 结果缓存（避免 ml_ready 那样 4 次调用各自重建整表）。

### ML-8 [P2] `build_transition_dataset` 在混合 agent 类型面板上 100% 行含 NaN
- **证据**：`family_abm/ml/features.py:52-66`，`state_cols` 取**所有** `state_` 列（Household 专属 + 成员专属）。
- **实测（ml_ready 面板）**：1673 行 **全部 1673 行含 NaN（100.0%）**；行样例如 `state_total_income_t = NaN`。
- **影响**：README 宣称「Transition dataset for Markov / sequence models」实际不可用，必须用户手工删列。
- **修复建议**：按 `agent_type` 分表生成；或输出 long 格式 `(agent_id, time, state_name, value_t, value_t+lag)`；函数内 `dropna(subset=state_cols)` 并提供 `require_complete=True`。

### ML-9 [P2] `build_network_features` 名不符实且口径混合
- **证据**：`family_abm/ml/features.py:69-78`（实际是 per-agent `mean/std/min/max`，不是任何网络/关系量）。
- **实测**：ml_ready → `(7, 53)`，176 个 NaN 单元格；**不含 `agent_type` 列**，Household 与 FamilyMember 混在一张表；Household 专属统计列在成员行全 NaN，反之亦然。
- **修复建议**：改名 `build_agent_summary(df, by="agent_type")`；网络特征应从 `Household.relationships`（affection/trust/conflict/power）单独计算并显式返回 `agent_type`。

### ML-10 [P2] sklearn 兼容性是「数组可喂」而非适配
- **证据**：全仓库 grep `sklearn|torch|parquet|pyarrow` → **0 命中**；`FeatureExtractor` 方法只有 `build_agent_panel / build_agent_trajectories / build_network_features / build_transition_dataset / extract_features`，**无 `fit` / `transform` / `fit_transform`**（实测 `[]`）。
- **结论**：不存在 sklearn 硬依赖，也不存在适配代码；`X` 是 2-D ndarray、`y` 是 1-D ndarray，符合 sklearn 约定但需用户自己做 split/scaler。README「可直接对接 sklearn / PyTorch 工作流」属**能力声称（输出 ndarray）**，不是已实现适配；且受 ML-1/ML-3 影响，当前不宜直接用于监督训练。

### ML-11 [P2] 缺 t=0 基线：录制先 step 后 record，fitter 的 `y0` 相位晚一步（Lead 追加线索，已证实）
- **证据**：`family_abm/core/simulation.py:30-36`
  ```python
  def step(self) -> None:
      self._run_hooks("pre_step")
      self.scheduler.step(self.environment)   # scheduler.py:32 自增并写入 environment.time
      for recorder in self.recorders:
          recorder.record(self.environment)   # 此刻 env.time 已是 1
      ...
  ```
  `environment.py:41`（`self.time += 1`）与 `scheduler.py:32`（`self.time += 1; environment.time = self.time`）都推进时间，录制发生在推进之后，**模型的真实初始状态（t=0）从未进入任何 recorder**。
- **实测（12 步）**：
  - `run(12)` 记录的时间 = `[1, 2, ..., 12]`（无 0；Lead 所述 `run(3)` → `[1,2,3]` 成立）；
  - 真实初始状态（运行前读取）：`happiness=0.662881, stress=0.268639`；
  - 首条记录（t=1）：`happiness=0.656148, stress=0.294042`；
  - `ABMFitter._extract_agent_series`（`fitting/fitter.py:46-53`）取 `t[0]=1.0`、`y0=y_true[0]`，即 **`y0` = 走完第一步之后的状态**。
- **影响**：`plot_fit_diagnostics`（`viz/plots.py:287` `y0 = y_true[0]`）与所有 `fit_*` 都用「晚一步」的初始条件作为 ODE 初值，t 轴整体偏 1；对纯拟合 R² 影响不大（实测小样本 R²=0.972，参数可自行吸收偏移），但**拟合出的初值/参数不可解释为 ABM 的 t=0 状态**，任何基于导数的比较（如 dH/dt 在 t=0）都会错开一步；若用户自行在 `run()` 前额外 `record()`，又会与 `run_until`/多次 run 的时间轴打架。
- **修复建议**：新增 `StateRecorder.record_initial=True`（在 `Simulation.run()` 首步前录制一次）或让 `Simulation.step()` 在 `scheduler.step()` **之前**录制（并让 `t=0` 有明确语义）；至少在文档中声明「时间从 1 开始、t=0 初始状态不落盘」。

### ML-12 [P3] 其它 ml 细节
- `features.py:34` `feature_columns or numeric_cols`：传 `[]` 会静默回退到全列（实测 `[]` → 13 列）；应区分 `None` 与 `[]`。
- `features.py:19` `sort_values([...])` 未 `reset_index(drop=True)`，返回的 index 是原始标签，按位置取值会踩错。
- `features.py:39` 的 `[:len(X)]` / `X[:len(y)]` 是 no-op，读起来像"已对齐"，建议删除。
- 未知特征列报错为 pandas 原生 `KeyError: "None of [Index(['nope'], dtype='str')] are in the [columns]"`（信息够用，但建议显式 `ValueError` 列出可用列）。
- `to_dataframe()` 行序 = 录制顺序（step-major；`Scheduler("random")` 下同一步内 agent 顺序随机，实测两次运行 stdout md5 不同），建议默认按 `(time, agent_id)` 排序。
- （时间轴始于 1、t=0 基线缺失见 ML-11。）

---

## 3. viz 发现

### VIZ-1 [P2]（viz 中影响面最大）模块级 `matplotlib.use("Agg")` 强制覆盖调用方后端
- **证据**：`family_abm/viz/plots.py:7-9`
  ```python
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  ```
  并被顶层 re-export（`family_abm/__init__.py:21-25`），故 `import family_abm` 即生效。
- **实测**：`matplotlib.use("svg")` → `import family_abm` → `get_backend() == 'Agg'`；对返回 Figure 调 `plt.show()` → `UserWarning: FigureCanvasAgg is non-interactive, and thus cannot be shown`。
- **影响**：任何嵌入 Jupyter/桌面 GUI 的使用者都无法交互查看；README 示例 `plot_timeseries(df)`（不传 `save_path`）在 Agg 下必须自行 `savefig`，否则图无出口。
- **修复建议**：删除模块级 `use("Agg")`；若确实要在无显示环境兜底，改为 `if not os.environ.get("DISPLAY") and "matplotlib.pyplot" not in sys.modules: matplotlib.use("Agg")`，或提供显式 `family_abm.viz.use_headless()`；README 补 `plt.show()` 用法。

### VIZ-2 [P2] `plot_timeseries` 未按 agent 分组，多 agent 被拼成一条折线
- **证据**：`family_abm/viz/plots.py:41-50`
  ```python
  if agent_id is not None: df = df[df["agent_id"] == agent_id].copy()
  cols = state_columns or [c for c in df.columns if c.startswith("state_")]
  df = df.sort_values("time")
  ...
  ax.plot(df["time"].values, df[col].values, label=label, lw=1.5)
  ```
- **实测**（6 agents × 30 steps，180 行）：`ax.lines[0]` 含 **180 个点**（=面板全部行），x 出现 **150 次** 重复 t（`np.diff(x) <= 0` 计数），即 6 个 agent 的轨迹被首尾相接成锯齿线。`examples/fitting_viz_demo.py:57` 正是这样调用（7 agents → 12 条线，各 840 点交错），生成物 `examples/output/01_timeseries.png` 因此是误导性图像。
- **修复建议**：
  ```python
  for aid, g in df.groupby("agent_id"):
      for col in cols:
          g = g.sort_values("time")
          ax.plot(g["time"], g[col], label=f"{aid[:6]}:{col.replace('state_','')}")
  ```

### VIZ-3 [P2] `plot_aggregate` 默认把所有 state 列混在同一均值面板
- **证据**：`family_abm/viz/plots.py:70-90`，`cols = state_columns or [c for c in df.columns if c.startswith("state_")]`，`grouped = df.groupby("time")[cols]`，`means/stds` 直接画。
- **实测**：默认 12 条线；成员专属列（health/happiness/stress/energy/education/income）的 mean 在成员子集上计算，Household 专属列（total_income/savings/housing_quality/...）的 mean 在 Household 子集上计算——**同一坐标轴、样本量 5 与 2 混排、图例无区分**。
- **修复建议**：要求显式 `state_columns`，或按 `agent_type` 分面/分组着色，并在标题标注 N。

### VIZ-4 [P2/疑似] `plot_fit_diagnostics` 聚合分支口径混合
- **证据**：`family_abm/viz/plots.py:275-278`
  ```python
  else:
      sub = df.groupby("time").mean(numeric_only=True).reset_index()
  ```
- **实测**：对 `happiness`，绘图曲线与「仅成员均值」数值相同（因为 Household 的 happiness 全 NaN，`mean(skipna)` 自动排除）→ **当前无实际数值错误**；但列命名空间一旦重叠（或 Household 将来也设 happiness），就会静默混合两类总体，且函数不做任何 `agent_type` 过滤与提示。
- **修复建议**：增加 `agent_type: Optional[str] = None` 参数并默认取单一类型，或在混合时 `warnings.warn`。

### VIZ-5 [P2] 输出路径不健壮 + import 期副作用
- **证据**：`plots.py:58-60`（以及 `:94-96, :131-133, :185-187, :251-253, :304-306, :336-338`）`fig.savefig(save_path, dpi=150)`；`examples/fitting_viz_demo.py:16-17` 模块级 `OUTPUT_DIR.mkdir(exist_ok=True)`。
- **实测**：`plot_timeseries(df, save_path=<不存在目录>/a.png)` → `FileNotFoundError [Errno 2]`；`import fitting_viz_demo` 即创建 `examples/output`（副作用，且 `mkdir` 未带 `parents=True`）。
- **修复建议**：`Path(save_path).parent.mkdir(parents=True, exist_ok=True)`；把 `mkdir` 移进 `main()`。

### VIZ-6 [P2] figure 不关闭 + 全局 rcParams 副作用
- **证据**：`plots.py:20-26` import 期 `plt.rcParams.update({...})`（实测 `axes.grid` False→True，进程级全局生效）；全部 `plot_*` 返回 Figure 但**从不 `plt.close`**（文件内 grep `plt.close` = 0 命中）。
- **实测**：连续 3–5 次调用后 `len(plt.get_fignums())` = 5（线性增长）。
- **影响**：长循环（如对每个 agent 出图）会持续占用内存，Agg 下不自动回收。
- **修复建议**：返回前提供 `close: bool = False` 参数或上下文管理器；rcParams 用 `with plt.rc_context(...)` 包裹、或提供 `family_abm.mplstyle`。

### VIZ-7 [P3] 其它 viz 细节
- 未使用 import：`plots.py:11` `GridSpec`、`:13` `Environment`、`:15` `solve_model`、`:269` `import matplotlib.gridspec as gridspec`。
- `plot_phase_portrait` 默认 `x_state="state_happiness"`/`y_state="state_stress"`（`:105-106`）硬编码：Household-only 面板列不存在 → 实测 `KeyError: 'state_happiness'`（建议默认取数据中前两个 `state_` 列并给出清晰错误）。
- `plot_timeseries(df, state_columns=["state_nope"])` → 实测 `KeyError: 'state_nope'`，建议列出可用列。
- 中文字体未配置：默认 `font.family=['sans-serif']`、`font.sans-serif=['DejaVu Sans', ...]`；实测中文标题触发 `UserWarning: Glyph 23478 (\N{CJK UNIFIED IDEOGRAPH-5BB6}) missing from font(s) DejaVu Sans.`（三个 examples 目前全英文标题，故运行期**无**该警告）。
- `plot_niche_space`：未知维度静默取 0（实测 `position.get("unknown_dim", 0)` → 坐标 `[0.5, 0.0]`），>3 维静默忽略，建议报错/警告。
- `plot_family_network` 懒加载 networkx 并给出安装提示（`:200-203`）——这是好的设计；无成员时也能出图（实测 OK）。
- 返回值类型与调用方约定：所有绘图函数返回 `plt.Figure`（与 README 一致）；无一处调用 `plt.show()`，配合 VIZ-1 需在文档中明确「需自行 show/savefig」。

---

## 4. examples 发现与实跑记录

### 4.1 实跑记录（命令、退出码、耗时、警告、产物）

`cwd = F:\GITHUB WORKPLACE\GITHUB ABM\NICHE-sim`，`PYTHONPATH=<repo>`，`PYTHONUTF8=1`：

| 命令 | 退出码 | 耗时 | 警告 | 主要 stdout |
|---|---|---|---|---|
| `python examples/simple_family.py` | **0** | 1.6 s | 无 | `Recorded 600 observations`；20 列（Household 行混入，见下） |
| `python examples/ml_ready.py` | **0** | 1.8 s | 无 | `Panel shape: (1680, 20)`；`X (1680,11) y (1680,)`；`Transition records: 1673`；`Aggregated features per agent` `(7,53)` |
| `python examples/fitting_viz_demo.py` | **0** | 10.1 s | 无 | `Recorded 840 observations across 7 agents`；`[wellbeing] R^2=0.8745`；`[influence] R^2=0.0000`；10 张 PNG |
| `python examples/*.py`（**清空 PYTHONPATH/未安装**） | **1** ×3 | — | — | `ModuleNotFoundError: No module named 'family_abm'` |
| `python -m examples.simple_family`（同上清空） | **0** | — | — | 正常（`-c`/`-m` 会把 cwd 放入 sys.path） |
| `python -c "import family_abm"`（cwd=repo，清空 PYTHONPATH） | **0** | — | — | OK |

**产物写入**：`fitting_viz_demo.py` 本次运行**覆盖重写**了 `examples/output/` 下全部 10 个 PNG（脚本自身行为，允许并在此声明）：
`01_timeseries.png, 02_aggregate.png, 03_phase_portrait.png, 04_comparison.png, 05_niche_3d.png, 06_niche_2d.png, 07_network.png, 08_fit_wellbeing.png, 09_fit_influence.png, 10_forecast.png`。
`ml_ready.py` / `simple_family.py` 不写文件。

**示例面板的结构问题（`simple_family.py` 实测输出）**：`Recorded 600 observations`（5 agents × 120 steps，其中 1 个是 Household）。列含 `state_total_income...state_social_capital`（Household 专属）与 `state_health...state_income`（成员专属），两类行互相 NaN——这正是 ML-3/ML-8 的输入源。时间列范围 **1..120**（无 t=0）。

### 4.2 examples 代码问题

- **EX-1 [P1]** `examples/fitting_viz_demo.py:54` `def demo_basic_plots(df: pd.DataFrame):` —— 文件**没有** `import pandas as pd`（实测 `has __future__ annotations: False`，也无 `import pandas`）。在 Python 3.9–3.13（`setup.py:8` 声明 `python_requires=">=3.9"`）会在**模块 import 时** `NameError: name 'pd' is not defined`；本机 3.14 因 PEP 649 惰性求值而侥幸通过（实测：`exec` 定义成功，访问 `__annotations__` 抛 `NameError: name 'pd' is not defined`）。
  **修复**：加 `import pandas as pd`（或 `from __future__ import annotations`）。
- **EX-2 [P2]** 三个 example 均无 `sys.path` bootstrap，README 的 `python examples/simple_family.py` 在干净环境/未 `pip install` 时直接失败（实测 exit=1）。本机还存在**过期 editable 安装**：`C:\Users\asus\AppData\Roaming\Python\Python314\site-packages\__editable___family_abm_0_1_0_finder.py:9` 的 `MAPPING` 指向 `C:\Users\asus\Desktop\兰彻斯特函数拟合\family_abm`（该目录**已不存在**），因此任何不设 PYTHONPATH 的直接脚本运行都会失败。
  **修复**：example 顶部加 `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`，README 明确 `pip install -e .` 或改用 `python -m examples.simple_family`；并告知用户卸载/重装过期 editable 包。
- **EX-3 [P2]** 无随机种子：`examples/ml_ready.py:45` 用 `Scheduler("random")`（`core/scheduler.py:18` `random.shuffle`），`FamilyMember` 用全局 `random.gauss/uniform`（`family/family_member.py:48,52-56,86,98,110,119,130,142,147`）。实测两次运行 stdout md5 不同（`f4fbc2e6b2` vs `2f18b474bc`），示例输出不可复现。
- **EX-4 [P3]** 无 `try/except` 掩盖错误（三个文件均 `try: False`，这点是**正面**的）；`fitting_viz_demo.py` 的 `OUTPUT_DIR` 用 `Path(__file__).parent`（不依赖 cwd，正面），但 `mkdir` 在模块级（VIZ-5）。
- **EX-5 [P3]** 未使用 import：`examples/ml_ready.py:9` `ResourceBundle`；`examples/fitting_viz_demo.py:7-8` `FeatureExtractor, ResourceBundle`；`fitting_viz_demo.py:181` `sub = df[df["agent_id"] == child_id]...` 计算后从未使用。
- **EX-6 [P3]** 控制台乱码：`fitting_viz_demo.py:227` 的 em dash（`Family ABM — Fitting`）在 cp936 控制台显示为 `Family ABM ?? Fitting`；纯 ASCII 输出或文档要求 `PYTHONUTF8=1` 可解。
- **EX-7 [P3]** `fitting_viz_demo.py:59,217-219` 使用自定义 `plt_close(fig)`（定义在文件末尾）显式关闭 figure —— 行为正确，但说明库本身不 close（VIZ-6），用户必须自己管。

---

## 5. README 声称 vs 实际 差异表

> **前置事实**：仓库根目录**没有 README.md / README.rst / 任何 .md**（实测 `README.md exists: False`，根目录文本文件仅 `requirements.txt`）；也没有 `.git`、没有 `tests/`。因此下列"README 声称"只能按任务给定的条目逐条与代码/实跑对照，**仓库内无法核对原文**。

| # | 声称 | 实际 | 裁定 |
|---|---|---|---|
| 1 | 状态记录 → DataFrame → 特征提取，**可直接对接 sklearn / PyTorch 工作流** | 链路可跑（实跑 exit 0）；但 `FeatureExtractor` 无 `fit/transform/fit_transform`，全库无 sklearn/torch 适配代码（grep 0 命中）；X/y 仅 ndarray；且 y 有 **28.9% 伪造 0**、X 有 **51.9% 伪造 0** | **部分成立（能力声称，非适配实现）**；ML-1/ML-3/ML-10 |
| 2 | `from family_abm import StateRecorder, plot_timeseries, plot_fit_diagnostics` | 实测 import 成功；`family_abm/__init__.py:12,21-25` 有导出 | **成立** |
| 3 | `plot_timeseries(df)`、`plot_fit_diagnostics(df, fitter)` 可直接调用 | 签名成立、返回 `Figure`；但 `plot_timeseries(df)` 多 agent 拼成一条线（VIZ-2），Agg 下不能 `show()`（VIZ-1）；`plot_fit_diagnostics(df, fitter)` 聚合分支混口径（VIZ-4） | **调用成立，语义有缺陷** |
| 4 | 静态可视化：时间序列、相图、生境、网络、拟合诊断 | 7 个函数齐备（`viz/__init__.py:1-15`），networkx 懒加载，Agg 下均可出图并存 PNG | **成立** |
| 5 | examples：simple_family（基础仿真）/ ml_ready（ML 特征提取）/ fitting_viz_demo（拟合+可视化） | 三文件存在且实跑 exit 0；但 `python examples/*.py` 需先装包（未装 → exit 1）；`fitting_viz_demo.py` 在 Python 3.9–3.13 会 import 崩溃 | **存在成立；README 命令与 Python 兼容性不成立**（EX-1/EX-2） |
| 6 | 依赖只有 numpy, pandas, scipy, matplotlib, networkx, fastapi, uvicorn, jinja2 | `requirements.txt:1-8` 与之一致；**但 `setup.py:7` 只有 numpy/pandas**，而 `import family_abm` 强制需要 matplotlib+scipy（实测阻断导入即失败）；sklearn/PyTorch **确非**硬依赖（0 引用） | **requirements 成立；setup.py 不成立（PKG-1）**；sklearn/torch 非硬依赖成立 |
| — | 未提及 | 无 README、无 .git、无 tests；`StateRecorder` 无 parquet；环境级记录无法导出 | 建议补文档与测试 |

---

## 6. 建议改进（按收益排序）

1. **【P1，改动最小、收益最大】重写 `FeatureExtractor.extract_features`**：先 `sort_values(["agent_id","time"]).reset_index(drop=True)`；标签 `shift` 后**丢弃 `notna()==False` 的行**而不是 `fillna(0)`；特征**不做 `fillna(0)`**；默认特征列排除 `attr_*`/`alive`/`target_column` 并按 `agent_type` 分表；删除无效的 `[:len(X)]`。可直接复用 `build_transition_dataset` 的排序逻辑。
2. **不再在库 import 期强制 `Agg`**（`plots.py:8`）；改为探测式兜底或显式 API，并在文档里给出 `plt.show()`/`savefig` 用法。
3. **补依赖与安装路径**：`setup.py` 增加 `scipy>=1.7`、`matplotlib>=3.4`（`networkx`/`fastapi`/`uvicorn`/`jinja2` 放 extras）；example 加 `sys.path` bootstrap 或 README 改为 `pip install -e .` / `python -m examples.*`。
4. **修 `examples/fitting_viz_demo.py`**：加 `import pandas as pd`（3.9–3.13 崩溃）；顺手删掉未使用 import 与 `sub` 死代码。
5. **修 `Simulation.reset()`**：同时 `self.scheduler.time = 0`；新增 `record_initial`/`t=0` 基线录制（修 ML-11 的 `y0` 相位偏移）；并给 `Scheduler`/`Simulation`/`FamilyMember` 加 `seed` 参数，example 固定种子。
6. **`StateRecorder` 增强**：环境级 `to_dataframe(level=...)`/`to_parquet`；`max_steps`/`flush_every` 控制内存（当前 ~1.2 KB/行）；`get_data()` 返回副本；`to_csv` 建父目录。
7. **`plot_timeseries` 按 agent 分组、`plot_aggregate` 显式 `state_columns` 或按 `agent_type` 分面**；`plot_*` 增加 `close` 选项。
8. **文档/字体**：README 补「数据契约（长表、time 从 1 开始且 t=0 不落盘、Household 行混在面板里、fitter 的 `y0` 是 t=1 状态）」；提供中文字体配置片段（`font.sans-serif=["Microsoft YaHei","SimHei"]`）或统一英文标题。
9. **补 `tests/`**：至少覆盖 (a) `extract_features` 的标签语义与无下一步行，(b) `reset()` 时间连续性，(c) `import family_abm` 在仅装 install_requires 的环境下可用，(d) 三个 example 的 smoke test（exit 0 + 无 Warning）。

---

### 附：本次实跑验证全部为只读，仓库唯一改动是本报告

- 未修改任何 `family_abm/**`、`examples/**`、`setup.py`、`requirements.txt` 文件。
- 唯一"写入"是 `examples/fitting_viz_demo.py` 运行时按脚本自身逻辑覆盖了 `examples/output/` 下 10 个 PNG（已在 §4.1 列明）。
- 临时验证脚本位于 `%TEMP%\niche_audit_ml{,2,3,4,5,6,7}.py`，不属于仓库。
