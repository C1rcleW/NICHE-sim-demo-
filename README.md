# Family ABM — 家庭社会小生境智能体建模框架

> **版本 0.2.0** ｜ 一个模块化、可复用的**智能体建模（Agent-Based Model）框架**，用于模拟家庭社会小生境（Social Micro-Niches）。集成兰彻斯特型 ODE 拟合、交互式 Web 仪表板，面向计算社会学与交叉科学研究。

---

## 核心功能

- **多层次仿真** — 家庭包含多个成员智能体，每人拥有独立的人格、年龄轨迹、教育、收入、健康、情绪状态
- **交互式仪表板** — FastAPI + Plotly.js，内置中英文双语，在浏览器中完成仿真配置、运行、拟合、可视化全流程
- **ODE 拟合** — 7 种内置兰彻斯特型社会动力学模型，支持多起点鲁棒优化与差分进化全局搜索
- **机器学习接口** — 状态记录 → DataFrame → 特征提取，输出可直接接入 sklearn / PyTorch 工作流
- **小生境模型** — 将智能体映射到四维社会空间（经济 / 文化 / 社会 / 情感），计算生境距离与重叠度
- **参数可调** — 19 个动力学参数（学习速率、收入曲线、压力敏感度等）在 Setup 标签页中配置

> ⚠️ **关于"小生境"的现状**：四维空间中 `social` 维度依赖 `social_capital` 状态，而目前只有 `Household` 拥有该状态（成员为 NaN → 被钳到 1.0），`economic` 直接取收入值。因此该空间在当前版本中**维度信息不完整**，详见[已知限制](#已知限制)。

---

## 快速开始

### 安装

```bash
# 标准安装（推荐；wheel 已包含 Web 前端资源）
pip install .

# 开发模式（可编辑安装，便于改代码）
pip install -e ".[dev]"
```

依赖由 `pyproject.toml` 统一声明，`requirements.txt` 是同一份清单的镜像（有测试强制二者一致）。

### 启动 Web 仪表板

```bash
python -m family_abm.web
# → http://127.0.0.1:8520  （启动后自动打开浏览器）
```

### 从命令行运行示例

```bash
python examples/simple_family.py        # 基础仿真
python examples/ml_ready.py             # ML 特征提取
python examples/fitting_viz_demo.py     # 拟合 + 可视化（会写入 examples/output/*.png）
```

> 示例脚本以"包已安装"为前提；若未安装，请先 `pip install .` 或设置 `PYTHONPATH` 指向仓库根。

---

## 使用指南

### Web 仪表板

| 标签页 | 功能 |
|--------|------|
| **Setup（设置）** | 配置家庭与成员、仿真步数、以及 19 个动力学参数。点击 *Run Simulation* 运行。 |
| **Charts（图表）** | 交互式时间序列图 + 社会生境空间散点图。 |
| **Fitting（拟合）** | 选择 ODE 模型，拟合仿真数据，查看 R²、参数估计值与诊断告警。 |
| **Network（网络）** | 家庭关系网络图（情感、信任、冲突可视化）。 |

右上角 ⚙ 按钮切换 **English / 简体中文**。

<img width="2531" height="1264" alt="image" src="https://github.com/user-attachments/assets/d9c9b193-79bd-4528-a2a1-df1b5b90dbc5" />

**拟合页的诚实性设计**（0.2.0 新增）：

- R² 允许为负——负值表示"模型结构不适合这些状态列"，不会被悄悄抹成 0
- `Converged` 只表示**优化器跑完了**，不等于模型适用；界面上会并列显示
- 命中失败哨兵（解未成功积分）或参数被边界钉住时，会显示黄色告警条并列出参数名
- 抽象模型（`square_law` / `influence` / …）的状态名与 ABM 列名没有默认对应关系，
  下拉中会标注"（需映射）"并自动带上候选映射；候选不足的模型直接置灰不可选

### Python API

```python
from family_abm import (
    Environment, Simulation, Scheduler,
    FamilyMember, Household, StateRecorder,
    make_fitter, wellbeing_balance, solve_model,
    plot_timeseries, plot_fit_diagnostics,
)

# 构建仿真
env = Environment()
hh = Household(name="张")
env.add_agent(hh)
hh.add_member(FamilyMember(name="父亲", age=35, role_name="parent"))
hh.add_member(FamilyMember(name="儿子", age=8, role_name="child"))

# 运行（默认额外记录 t=0 基线，使拟合初值不偏移）
recorder = StateRecorder(record_agents=True)
sim = Simulation(env, scheduler=Scheduler("sequential"))
sim.add_recorder(recorder)
sim.run(120)

df = recorder.to_dataframe()      # 宽表；缺失值保持 NaN（不同 agent 类型的状态列不同）
stats = recorder.to_statistics_dataframe()   # 按 agent_type 分组的统计视图（丢弃缺失）

# 拟合幸福-压力模型
fitter = make_fitter("wellbeing")
fitter.fit_robust(df)
print(fitter.summary())
print(fitter.summary_json()["params_at_bounds"])   # 被边界钉住的参数（告警，不是错误）

# 可视化（不传 save_path 时返回 Figure）
fig = plot_timeseries(df)
plot_fit_diagnostics(df, fitter)
```

### 数据契约（重要）

`StateRecorder.to_dataframe()` 返回**宽表且保留 NaN**：`Household` 没有成员的
`state_happiness` 等列，成员也没有 `state_total_income`，这些 NaN 表示"该 agent 没有这个状态"，
**不是数值 0**。拟合器与绘图依赖这个语义（逐列跳过 NaN）。

需要"给人看"的表格时请用 `to_statistics_dataframe()` 或 `to_csv(level="statistics")`。

---

## 项目结构

```
family_abm/
├── core/              # 核心引擎：Agent, Environment, Scheduler, Simulation
├── family/            # 家庭模型：FamilyMember, Household, Relationship, Roles
├── niche/             # 生境模型：MicroNiche, ResourceBundle, InfluenceRelation
├── ml/                # ML 集成：StateRecorder, FeatureExtractor
├── fitting/           # 7 种兰彻斯特型 ODE 模型 + ABMFitter
│   ├── lanchester.py  #   模型定义 + 求解器
│   └── fitter.py      #   ABMFitter（fit_robust / fit_global）、make_fitter、compare_models
├── viz/               # 静态可视化（matplotlib）：时间序列、相图、生境、网络、拟合诊断
├── web/               # FastAPI 仪表板 + Plotly.js
│   ├── __main__.py    #   启动入口：python -m family_abm.web
│   ├── app.py         #   REST API（run / data / fit / models / niche / network / params）
│   ├── templates/     #   HTML（data-i18n 双语支持）
│   └── static/        #   CSS + JS
└── __init__.py
baseline/              # 行为基线锚点（JSON，纳入版本控制）
tests/                 # pytest 测试套件
tools/                 # baseline.py、verify_install.py、check_dashboard_behavior.js
```

---

## 智能体动力学

每个 `FamilyMember` 经历 **学龄前 → 儿童 → 学生 → 成人 → 老年** 五个生命阶段（按年龄自动推进）。内部状态每步更新：

| 变量 | 驱动机制 |
|------|---------|
| **教育** | 年龄依赖的学习速率，饱和于 1.0 |
| **收入** | `基础值 × (1 + 教育加成 × 受教育水平) × 年龄曲线 × 角色乘数` |
| **健康** | 基础衰减 + 年龄加速衰减，受教育水平减缓 |
| **压力** | 基础压力 + 工作负荷，受神经质人格放大，自然衰减 |
| **幸福** | 均值回归：`目标值 = 基底 + 健康权重×健康 + 收入权重×收入 + 教育权重×教育 − 压力惩罚×压力` |
| **精力** | 恢复-消耗循环 |

19 个动力学参数按组暴露：Education 1 ／ Income 4 ／ Health 3 ／ Stress 4 ／ Happiness 6 ／ Noise 1。
它们从 `Environment.params` 读取并回退到 `DEFAULT_PARAMS`。

> **注意**：参数在 Setup 标签页**配置后于 Run 时生效**，不是运行中的实时调整。
> 另有两个隐藏量：`dt_months`（默认 1.0，仅影响教育/健康/年龄三段更新）与 `randomness`（噪声强度）。

---

## ODE 模型（兰彻斯特型）

| 模型 | 状态变量 | 参数 | 社会类比 |
|------|---------|------|---------|
| `square_law` | R₁, R₂ | α, β, ε₁, ε₂ | 群体竞争（相互消耗） |
| `linear_law` | R₁, R₂ | α, β | 交互驱动竞争 |
| `influence` | O₁, O₂ | γ, δ, T₁, T₂ | 意见/行为影响（收敛到目标） |
| `wellbeing` | H, S | p, q, r, s, income | 幸福-压力平衡 |
| `logistic` | P | r, K | 单群体增长 |
| `lotka_volterra` | P, Q | a, b, c, d | 工作 vs 家庭时间 |
| `resource_competition` | R₁, R₂ | r₁, k₁, r₂, k₂, α, β | 逻辑斯蒂 + 兰彻斯特 |

拟合使用 `scipy.optimize.minimize`（多起点鲁棒优化 `fit_robust`）与
`scipy.optimize.differential_evolution`（全局搜索 `fit_global`）。

**模型适用性提示**：

- `square_law` 的系数矩阵特征值为 `±√(αβ)`，无自限项，在较大 α/β 下会发散；
  `eps>0` 只在长时间下保留常激励，并非收敛保证
- `wellbeing` 中 `p` 与 `income` 只以乘积 `p·income` 出现，二者**严格不可辨识**
  （同一乘积给出完全相同的拟合结果），解读参数值时请只把它们当作一个整体
- 抽象模型必须显式声明 `state_mapping`，否则直接报错——这是刻意设计，
  避免把模型静默拟到无关甚至零方差的列上

---

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/run` | 按配置运行仿真 |
| `GET` | `/api/data` | 宽表数据（缺失值为 `null`）+ 分组统计 |
| `GET` | `/api/models` | 模型清单、状态名、可映射性与候选映射；支持 `?agent_id=` 按单个 agent 评估 |
| `POST` | `/api/fit` | 拟合；请求体支持 `state_mapping` |
| `GET` | `/api/niche` | 各 agent 的生境位置 |
| `GET` | `/api/network` | 家庭关系网络 |
| `GET` | `/api/params` | 参数默认值与分组 |

`/api/fit` 的所有错误都返回**结构化 JSON**（不再有纯文本 500）：

| status | HTTP | 触发条件 |
|--------|------|---------|
| `ok` | 200 | 正常拟合 |
| `model_not_applicable` | 200 | 命中失败哨兵（解未成功积分）；返回 `warning` 且跳过预测轨迹 |
| `invalid_mapping` | 400 | `state_mapping` 指向非数值列 |
| `invalid_input` | 400 | 状态列无法解析、数据不足、参数边界不合法 |
| `invalid_dataframe` | 400 | 数据缺少 `time` / `agent_id` 必需列 |
| `unknown_model` | 400 | 未知模型名 |
| `optimizer_failed` | 400 | 优化器未收敛（`success=False`） |
| `all_starts_failed` | 400 | 多起点拟合全部失败 |
| `runtime_error` | 400 | 其它运行期错误（拟合实现体内冒泡的 `RuntimeError`） |
| `fitting_error` | 500 | 未预期异常（保留结构化信息以便排障） |
| `prediction_failed` | 500 | 拟合成功但预测轨迹生成失败 |

---

## 可复现性与验证

### 当前状态：仿真是**未播种**的

`FamilyMember.__init__`、`Relationship`、`Scheduler` 使用全局 `random` 模块，
而 `Simulation` 尚无 `seed` 参数——**同一份输入连续跑两次会得到不同结果**。
如需在脚本中复现，请自行在构建环境前调用 `random.seed(...)` 与 `np.random.seed(...)`；
`tools/baseline.py` 即采用这种做法。为每个 run 注入独立 RNG 已列入后续计划。

### 基线锚点

`baseline/default_seed42.json` 是纳入版本控制的行为基线。任何校准/结构改动之后：

```bash
python -X utf8 tools/baseline.py --check baseline/default_seed42.json
# 若改动是有意的：重新固化并在提交信息中说明行为变化
python -X utf8 tools/baseline.py --out baseline/default_seed42.json
```

### 测试

```bash
pip install -e ".[dev]"
python -X utf8 -m pytest tests/ -q          # 64 项
```

覆盖范围包括：打包（构建 wheel → 干净安装 → 启动服务）、时间轴与 t=0 基线、
拟合输入显式化、NaN 语义、R²/收敛上报、Web API 契约，
以及由 Node 执行的仪表板行为测试（`tools/check_dashboard_behavior.js`，无 node 时该项跳过）。

### 安装冒烟

```bash
python -X utf8 tools/verify_install.py --import-only   # 校验当前环境
# 或指向隔离安装目录：
python -X utf8 tools/verify_install.py <install-target>
```

---

## 依赖

**运行时**（`pyproject.toml` 声明）：

```
numpy>=1.21.0   pandas>=1.3.0    scipy>=1.7.0
matplotlib>=3.4.0   fastapi>=0.100.0   uvicorn>=0.23.0
jinja2>=3.1.0   pydantic>=2.0.0
```

**可选**：

- `[dev]` — pytest、build、httpx（`httpx` 是 `fastapi.testclient` 的必需依赖，安装冒烟会用到）
- `[viz]` — networkx（仅 `plot_family_network()` 惰性导入）

Python 要求：`>=3.9`。

---

## 已知限制

以下问题已在当前版本中**确认存在**，尚未修复；README 如实列出，避免使用者误用：

| 领域 | 问题 | 影响 |
|------|------|------|
| 校准 | 默认参数下健康在 10–15 年内触底 0.01；压力在神经质 > 0.67 区间被钳位饱和 | 长仿真中健康维度失去区分度 |
| 仿真 | 无全局种子（见上文） | 结果不可复现，参数比较失去意义 |
| 拟合 | `wellbeing` 的 `p` 与 `income` 不可辨识 | 参数估计值不能单独解读 |
| 拟合 | `square_law` 结构性发散 | 大 α/β 下发散，拟合可能落在无意义分支 |
| ML | `FeatureExtractor.extract_features` 对标签与特征做 `fillna(0)` | 缺失被伪造成 0，监督学习目标失真 |
| 小生境 | `social` 维度恒为 1.0、`economic` 无归一化 | 四维空间实际维度信息不完整 |
| Web | `/api/run`、`/api/fit` 在 `async` 路由内同步执行；仿真状态为模块级单例 | 长拟合会阻塞其它请求；并发会话会相互覆盖 |
| 打包 | 仓库无 `LICENSE` 文件 | 使用前请与作者确认授权 |

详细的审查记录（含逐条 `文件:行` 证据与复现命令）位于 [`audits/`](audits/)；
分层修复路线图见 [`audits/remediation_plan.md`](audits/remediation_plan.md)。

---

## 引用与许可

本仓库当前**未附带 LICENSE 文件**。在补充授权声明之前，请视为保留所有权利；
如需在研究中引用或复用，请先联系作者。
