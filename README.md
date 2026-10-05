# Family ABM — 家庭社会小生境智能体建模框架

一个模块化、可复用的**智能体建模（Agent-Based Model）框架**，用于模拟家庭社会小生境（Social Micro-Niches）。集成兰彻斯特型 ODE 拟合、交互式 Web 仪表板，面向计算社会学与交叉科学研究。

---

## 核心功能

- **多层次仿真** — 家庭包含多个成员智能体，每人拥有独立的人格、年龄轨迹、教育、收入、健康、情绪状态
- **交互式仪表板** — FastAPI + Plotly.js，内置中英文双语，在浏览器中完成仿真配置、运行、拟合、可视化全流程
- **ODE 拟合** — 7 种内置兰彻斯特型社会动力学模型（竞争、影响、幸福-压力平衡等），支持多起点鲁棒优化和差分进化全局搜索
- **机器学习接口** — 状态记录 → DataFrame → 特征提取，输出可直接对接 sklearn / PyTorch 工作流
- **小生境模型** — 将智能体映射到四维社会空间（经济 / 文化 / 社会 / 情感），计算生境距离与重叠度
- **参数可调** — 19 个动力学参数（学习速率、收入曲线、压力敏感度等）在仪表板中配置

---

## 快速开始

```bash
# 1. 安装
pip install .

# 2. 启动 Web 仪表板（自动打开浏览器）
python -m family_abm.web

# 3. 或从命令行运行示例
python examples/simple_family.py        # 基础仿真
python examples/ml_ready.py             # ML 特征提取
python examples/fitting_viz_demo.py     # 拟合 + 可视化
```

开发模式请用 `pip install -e ".[dev]"`（可编辑安装，含测试依赖）。

---

## 使用指南

### Web 仪表板

```bash
python -m family_abm.web
# → http://127.0.0.1:8520
```

| 标签页 | 功能 |
|--------|------|
| **Setup（设置）** | 配置家庭与成员、仿真步数、以及 19 个动力学参数。点击 *Run Simulation* 运行。 |
| **Charts（图表）** | 交互式时间序列图 + 社会生境空间散点图。 |
| **Fitting（拟合）** | 选择 ODE 模型，拟合仿真数据，查看 R² 与参数估计值。 |
| **Network（网络）** | 家庭关系网络图（情感、信任、冲突可视化）。|

右上角 ⚙ 按钮切换 **English / 简体中文**

<img width="2531" height="1264" alt="image" src="https://github.com/user-attachments/assets/d9c9b193-79bd-4528-a2a1-df1b5b90dbc5" />

拟合页的几点说明：

- 抽象模型（`square_law`、`influence` 等）的状态名与 ABM 列名没有默认对应关系，
  需要显式指定 `state_mapping`；界面上会自动填入候选映射
- `R²` 允许为负（表示模型结构不适合当前状态列），`Converged` 只表示优化器正常结束
- 参数被边界钉住或解未能成功积分时，页面会给出告警

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

# 运行
recorder = StateRecorder(record_agents=True)
sim = Simulation(env, scheduler=Scheduler("sequential"))
sim.add_recorder(recorder)
sim.run(120)

df = recorder.to_dataframe()

# 拟合幸福-压力模型
fitter = make_fitter("wellbeing")
fitter.fit_robust(df)
print(fitter.summary())

# 可视化
plot_timeseries(df)
plot_fit_diagnostics(df, fitter)
```

`to_dataframe()` 返回宽表，缺失值保持为 `NaN`——不同 agent 类型拥有的状态列不同
（`Household` 没有 `state_happiness`，成员没有 `state_total_income`），
这些 NaN 表示"该 agent 没有这个状态"，拟合与绘图都会逐列跳过它们。
需要聚合表格时用 `recorder.to_statistics_dataframe()`。

---

## 项目结构

```
family_abm/
├── core/              # 核心引擎：Agent, Environment, Scheduler, Simulation
├── family/            # 家庭模型：FamilyMember, Household, Relationship, Roles
├── niche/             # 生境模型：MicroNiche, ResourceBundle, InfluenceRelation
├── ml/                # ML 集成：StateRecorder, FeatureExtractor
├── fitting/           # 7 种兰彻斯特型 ODE 模型 + ABMFitter
│   ├── lanchester.py  #   模型定义与求解器
│   └── fitter.py      #   ABMFitter（fit_robust / fit_global）、make_fitter
├── viz/               # 静态可视化（matplotlib）：时间序列、相图、生境、网络、拟合诊断
├── web/               # FastAPI 仪表板 + Plotly.js
│   ├── __main__.py    #   启动入口：python -m family_abm.web
│   ├── app.py         #   REST API
│   ├── templates/     #   HTML（data-i18n 双语支持）
│   └── static/        #   CSS + JS
└── __init__.py
```

---

## 智能体动力学

每个 `FamilyMember` 经历 **学龄前 → 儿童 → 学生 → 成人 → 老年** 五个生命阶段。内部状态每步更新：

| 变量 | 驱动机制 |
|------|---------|
| **教育** | 年龄依赖的学习速率，饱和于 1.0 |
| **收入** | `基础值 × (1 + 教育加成 × 受教育水平) × 年龄曲线 × 角色乘数` |
| **健康** | 基础衰减 + 年龄加速衰减，受教育水平减缓 |
| **压力** | 基础压力 + 工作负荷，受神经质人格放大，自然衰减 |
| **幸福** | 均值回归：`目标值 = 基底 + 健康权重×健康 + 收入权重×收入 + 教育权重×教育 − 压力惩罚×压力` |
| **精力** | 恢复-消耗循环 |

19 个动力学参数按组暴露：Education 1 ／ Income 4 ／ Health 3 ／ Stress 4 ／ Happiness 6 ／ Noise 1，
在 Setup 标签页配置后于 Run 时生效。

---

## ODE 模型（兰彻斯特型）

| 模型 | 状态变量 | 参数 | 社会类比 |
|------|---------|------|---------|
| `square_law` | R₁, R₂ | α, β, ε₁, ε₂ | 群体竞争 |
| `linear_law` | R₁, R₂ | α, β | 交互驱动竞争 |
| `influence` | O₁, O₂ | γ, δ, T₁, T₂ | 意见/行为影响 |
| `wellbeing` | H, S | p, q, r, s, income | 幸福-压力平衡 |
| `logistic` | P | r, K | 单群体增长 |
| `lotka_volterra` | P, Q | a, b, c, d | 工作 vs 家庭时间 |
| `resource_competition` | R₁, R₂ | r₁, k₁, r₂, k₂, α, β | 逻辑斯蒂 + 兰彻斯特 |

拟合使用 `scipy.optimize.minimize`，支持多起点鲁棒优化（`fit_robust`）和差分进化全局搜索（`fit_global`）。

使用时注意两点：

- `square_law` 的系数矩阵特征值为 `±√(αβ)`，没有自限项，在较大 α/β 下会发散
- `wellbeing` 中 `p` 与 `income` 只以乘积 `p·income` 出现，二者无法分别确定，
  请把它们的乘积当作一个整体来解读

---

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/run` | 按配置运行仿真 |
| `GET` | `/api/data` | 宽表数据（缺失值为 `null`）+ 分组统计 |
| `GET` | `/api/models` | 模型清单、状态名与候选映射，支持 `?agent_id=` |
| `POST` | `/api/fit` | 拟合（请求体支持 `state_mapping`） |
| `GET` | `/api/niche` | 各 agent 的生境位置 |
| `GET` | `/api/network` | 家庭关系网络 |
| `GET` | `/api/params` | 参数默认值与分组 |

---

## 依赖

```
numpy, pandas, scipy, matplotlib
fastapi, uvicorn, jinja2, pydantic
```

可选：`networkx`（家庭关系网络图，`pip install "family_abm[viz]"`）。
Python 版本要求：`>=3.9`。
---

## 说明与限制

- **仿真未固定随机种子**：同一组输入连续运行两次结果会不同。如需复现，请在构建环境前
  自行设置 `random.seed()` 与 `np.random.seed()`。
- **小生境空间维度不完整**：`social` 维度依赖 `social_capital`，目前只有 `Household` 拥有该状态；
  `economic` 直接取收入值，未做归一化。
- **`FeatureExtractor` 的缺失值处理**：当前会用 0 填充，用于监督学习前请自行处理缺失。
- **默认参数下的长期校准**：长时间仿真中健康会衰减到下限、压力趋于饱和。
- 仓库暂未附带 LICENSE 文件，使用前请与作者确认授权。

---

## 引用

如在研究中使用本框架，欢迎联系作者交流。
