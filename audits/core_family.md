# core + family 审查报告

- 审查范围：`family_abm/core/{agent,environment,scheduler,simulation,__init__}.py`、`family_abm/family/{family_member,household,relationships,roles,__init__}.py`，并交叉核对 `family_abm/__init__.py`、`setup.py`、`web/app.py`、`web/static/js/dashboard.js`、`ml/recorder.py`（仅作证据引用，未改动）。
- 审查方式：只读阅读 + 在临时目录写验证脚本执行（**未修改仓库任何文件**；唯一写入的是本报告）。
- 环境：CPython 3.14.3（Windows），`PYTHONPATH` 指向仓库根，`python <TEMP>\audit_core_family{,2,3,4}.py`。
- 严重度：P1 = 正确性错误 / 会导致错误结论或崩溃；P2 = 明显设计缺陷 / 健壮性风险；P3 = 可读性、风格、小优化。
- 复现说明：每条「证据」都可用文末【附录 B】的脚本复现；报告内数字均为实测输出。

> **前置事实**：仓库内**不存在 README.md（也不存在任何 `.md`/`.rst` 文档，且不是 git 仓库）**。
> 因此第 3 节的「README 声称」是按任务书给出的声称文本逐条核对，无法核对 README 原文措辞。这本身记为 **PK-2（P2）**。

---

## 1. 结论摘要（最关键问题）

1. **【P1｜健康数值崩溃】** 默认参数下健康衰减速度不合理：30 岁成年人在 **41.8 岁**就跌到硬下限 0.01（20 岁 → 34.6 岁，40 岁 → 50.3 岁）。任何 ≥20 年的模拟里，所有成年人的健康都恒为 0.01，健康维度彻底失去区分度，幸福也随之下沉到 0.2 附近。证据：`family_member.py:113-120` + `DEFAULT_PARAMS` `family_member.py:16-18`；实测见【附录 A H2】。
2. **【P1｜压力被截断在边界】** 压力更新是「朝均衡点松弛」，默认均衡点 = `(0.03+0.02)(1+0.30·neuro)/0.06`：neuro=0.5 时 **0.958**，neuro≥0.667 时解析均衡 **>1.0 被 clamp 截断**。实测 neuro=0.75 与 neuro=1.0 的稳态压力**完全相同（都是 1.0000）**——神经质人格参数在 0.7 以上完全失效。证据：`family_member.py:122-131`；实测【附录 A H4】。
3. **【P1｜可从仪表板触发的崩溃】** 仪表板「Age Spread」输入框 `min="0"`，且空值会被 `parseFloat(v)||0` 变成 0；`income_age_spread=0` 使 `math.exp(-(...)/(2*spread**2))` 抛 `ZeroDivisionError`（`/api/run` 无 try/except → 500）。参数为 `None`/非数字字符串同样 `TypeError/ValueError`；参数为 `NaN` 则被 `max/min` 静默转成 1.0/0.0（实测 health=1.0、happiness=1.0）。证据：`family_member.py:104-106`、`family_member.py:61-66`、`web/app.py:90`、`dashboard.js:255,266`；实测【附录 A E9/E10】。
4. **【P1｜角色与年龄脱钩】** `role` 在构造时被直接写成 `role_name`（默认 `"adult"`），**不按年龄推导**：`FamilyMember(age=0.2)` 的第一步用 adult 角色乘数 1.0 计收入（实测 0.001606 vs 正确 preschool 的 0.001156，**高估 39%**）；`role_name="parent"`（README 示例与仪表板都用它）在第一步落进 `role_mul` 兜底值 0.2，之后又被 `age_increment` 无条件覆盖为成人。证据：`family_member.py:40,50,78,107-108`；实测【附录 A H1/E8】。
5. **【P1｜不可复现】** 仿真链路完全没有种子入口：`family_member.py:48,52-56,86,110,119,130,142,147`、`relationships.py:17-21,32-34`、`scheduler.py:17-23` 全部直接用全局 `random`。同一份输入、同一套参数，两次 `POST /api/run` 得到不同 KPI（实测 run1 happiness=0.415131、run2=0.383532），因此仪表板上「改参数 → 比结果」的结论被随机性混淆。证据同上；实测【附录 A E11】。
6. **【P1/P2｜安装即崩 + 家庭层是空壳】** `import family_abm` 会连带导入 `scipy`（`fitting/fitter.py:6`）与 `matplotlib`（`viz/plots.py:7-8`），但 `setup.py:7` 只声明 `numpy,pandas` → `pip install .` 后 `import family_abm` 必然 ModuleNotFoundError。另外**家庭耦合层不产生任何因果**：`Relationship` 状态与 `Household.total_income` 没有任何模块读取，关系演进是纯随机游走，`roles.py` 的角色类从未被实例化（`ROLE_REGISTRY` 在 `web/app.py:17` 被导入却未使用）。证据：`setup.py:7`、`family_abm/__init__.py:14,21`、`household.py:54-62`、`relationships.py:31-34`、`roles.py:5-59`。

> **Lead 线索复核**：Lead 提供的 7 条线索（Scheduler 方法缺失、`total_income` 滞后一步、19 参数与 `dt_months`/energy 步长不一致、无种子、幸福用旧 `hp`+教育只护年龄项、roles/influence_weight 死代码、`agent.py` 字典别名）经独立实测**全部证实**（仅线索 3 的行号区间 121-148 需细化为三段）；Lead 遗留的钩子语义问题确认为**不自洽**（`post_step` 内 `current_step` 与 `env.time` 差 1、recorder 先于 `post_step`）。逐条证据见 **§5**。新增 P2 发现两条：**AG-3**（`attributes or {}` 别名共享）、**SI-5 升级为 P2**（钩子语义不自洽）。

---

## 2. 逐文件发现

### 2.1 `family_abm/core/agent.py`

**AG-1（P3）`get_state()` 只做浅拷贝，嵌套属性可被外部别名修改**
- 证据：`agent.py:22-29` `"attributes": dict(self.attributes)`；`family_member.py:47-49` 把 `personality` 这个 **dict** 存进 attributes。`StateRecorder` 只挑标量（`recorder.py:32-34`）所以暂时不会落盘，但任何调用方 `agent.get_state()["attributes"]["personality"]["neuroticism"] = 0` 会直接改掉智能体内部状态。
- 影响：隐式共享可变状态，调试困难。
- 建议：`copy.deepcopy` 或让 `get_state()` 明确返回只读视图；`personality` 用 `MappingProxyType`/冻结 dataclass。

**AG-2（P3）缺少 `__init__` 参数校验与 `agent_id` 唯一性约束**
- 证据：`agent.py:13` `self.id = agent_id or str(uuid.uuid4())`，重复 id 不报错，注册时静默覆盖（见 EN-1）。
- 建议：在 `Environment.add_agent` 处做重复检测（见 EN-1），`Agent` 本身可加 `agent_id` 类型断言。

**AG-3（P2）`attributes or {}` / `state or {}` 直接持有调用方传入的字典（别名共享，非拷贝）** —— Lead 线索 7，**证实**
- 证据：`agent.py:14-15`
  ```python
  self.attributes = attributes or {}   # agent.py:14
  self.state = state or {}             # agent.py:15
  ```
  无 `dict(...)`/`copy`。实测：传入非空 dict 时 `a.attributes is shared_attr → True`；外部 `shared_attr["k"]=999` 后 `agent.attributes == {'k': 999}`。`FamilyMember` 走 `**kwargs` 透传（`family_member.py:43` `super().__init__(**kwargs)`），因此 `FamilyMember(attributes=d)` 同样别名（实测外部改写 `d["p"]=42` 后 `m.get_attribute("p")==42`）。更隐蔽的是 `or {}` 的语义：传入**空** dict 时会被替换为新 dict（`b.attributes is empty → False`），即「非空则别名、空则拷贝」，行为取决于内容，难以预期。
- 影响：`Agent(...)`/`FamilyMember(attributes=...)` 的调用方共享可变状态；批量构造（如从同一模板 dict 生成一族成员）会让所有智能体共享 personality/属性，出现「改一个全员变」的幽灵 bug；与 AG-1 的 `get_state()` 浅拷贝叠加放大风险。
- 建议：`self.attributes = dict(attributes) if attributes else {}`（同理 `state`），并对嵌套值（`personality`）做 `deepcopy`；或在 docstring 明确「传入字典会被此对象接管，调用方不得再修改」。
- 附注：`attributes or {}` 与 `state or {}` 还丢失了「调用方显式传入空容器」的意图，若未来要区分 `None`/`{}` 需改为 `is None` 判断。

---

### 2.2 `family_abm/core/environment.py`

**EN-1（P2）重复 `agent_id` 静默覆盖**
- 证据：`environment.py:14-15`
  ```python
  def add_agent(self, agent, x=None, y=None):
      self.agents[agent.id] = agent
  ```
  同 id 再注册会覆盖旧对象，旧对象仍持有 `environment` 引用（`agent.environment = self` 只在注册时设置），形成「幽灵智能体」。
- 影响：`Household(household_id="H")` 或显式 `agent_id` 场景下静默丢 agent，人口统计错误且无日志。
- 建议：`if agent.id in self.agents: raise ValueError(...)`（或返回 bool 并由调用方决定）；`remove_agent` 已正确把 `environment` 置 None（`environment.py:22-26`），保持一致。

**EN-2（P2）`Environment.step()` 与 `Scheduler.step()` 双时钟冲突，会让时间倒流**
- 证据：`environment.py:37-41` 自增 `self.time`；`scheduler.py:28-33` 在自增自己的 `self.time` 后 **覆盖** `environment.time = self.time`。实测：`sim.run(5)` 后 `env.time=5`，调用一次 `env.step()` → 6，再 `sim.step()` → **env.time 回到 6 而不是 7**（`Scheduler.time` 仍是 5）。
- 影响：任何混用（或第三方扩展）都会产生非单调的记录时间列，`StateRecorder`/`fitter` 的时间轴不再可信；同时存在两套语义等价的步进实现，容易走岔。
- 建议：只保留一个时钟——让 `Environment` 持有 time，`Scheduler.step` 只负责选择与调用，删掉 `Environment.step()`（或让它委托给 scheduler）；`Simulation` 与 `Environment` 二者只能有一条步进入口。

**EN-3（P3）`width/height/properties/x/y` 是死参数**
- 证据：全仓库 grep `\.width|\.height|get_attribute("x"|\.properties` 只命中定义处 `environment.py:10-12,47` 与 `household.py:71`；`add_agent(x=,y=)` 写入的 `x/y` 属性无人读取。
- 影响：README/API 暗示存在空间环境，实际无空间模型，误导使用者。
- 建议：要么实现空间（邻域、距离），要么从签名与文档中删除。

**EN-4（P3）`params` 是隐式约定属性**
- 证据：`Environment.__init__`（`environment.py:7`）没有 `params`；`web/app.py:90` 靠 `env.params = cfg.params` 注入，`family_member.py:64` 靠 `getattr(self.environment, "params", None)` 读取。
- 影响：参数层约定不显式、无类型、无校验（直接导致 FM-3 崩溃）。
- 建议：`Environment(params: Optional[Mapping[str,float]] = None)`，与 `DEFAULT_PARAMS` 合并 + 校验（见第 4 节改进①）。

---

### 2.3 `family_abm/core/scheduler.py`

**SC-1（P2）未实现 `parallel` / `simultaneous` 语义，且 `sequential` 事实上是「按注册序的 Gauss-Seidel」**
- 证据：`scheduler.py:12-26` 仅支持 `sequential`（返回注册序列表）、`random`、`random_activation`；实测 `Scheduler("parallel")` / `Scheduler("simultaneous")` 抛 `ValueError: Unknown scheduler method: parallel/simultaneous`。【附录 A E12】
- 影响：(1) 文档/使用者预期的并发或同步更新语义不存在；(2) 「边更新边读取」的顺序依赖无法被消除。当前 `FamilyMember.step()` 不读其他智能体，所以成员之间暂时顺序无关，但 `Household.step()` 读成员收入（见 HH-1），顺序敏感已经真实存在。
- 建议：新增 `simultaneous`：两阶段提交（先对所有 agent 调 `collect_next_state()` 到快照，再统一 `commit()`）；`sequential` 明确命名为 `gauss_seidel` 并在 docstring 说明因果泄漏方向；`parallel` 若指真并行需说明对共享 RNG/环境的约束。

**SC-2（P3）`method` 延迟校验，构造时不报错**
- 证据：`scheduler.py:8-10` 构造函数不校验；错误只在第一次 `schedule()` 抛出（`scheduler.py:25-26`），且异常文本不列出可用取值。实测 `Scheduler("totally_bogus")` 构造成功。
- 建议：构造时白名单校验并列出合法值；顺便给出 `Scheduler.__repr__`。

**SC-3（P3）`random*` 复用全局 RNG，与智能体噪声流耦合**
- 证据：`scheduler.py:2,17-23` 直接 `random.shuffle/randint`。
- 影响：调度顺序的随机数消耗会平移后续 `random.gauss()` 的流，使「只改调度方式」也改变所有状态轨迹，实验设计无法隔离变量；而且没有 `seed` 参数（见 FM-5）。
- 建议：给 `Scheduler` 注入独立的 `random.Random(seed)`。

**SC-4（P3）`random_activation` 的激活数量含 Household**
- 证据：`scheduler.py:23` `random.randint(1, max(1, len(shuffled)))`，而 `shuffled` 包含 Household 智能体。实测 5 个 agent（1 户 + 4 成员）时激活数为 1..5，可能出现「只激活 Household、所有成员本步都不更新」的 tick。
- 影响：随机激活的语义（按人口比例？按智能体？）不清，且会让 recorder 里出现整步无成员更新的静默期。
- 建议：明确激活单位（人 vs 户），或按比例参数 `activation_rate` 抽样并文档化。

---

### 2.4 `family_abm/core/simulation.py`

**SI-1（P2）`reset()` 不重置 `Scheduler.time`，重置后再跑时间轴断裂**
- 证据：`simulation.py:48-52` 只重置 `environment.time` 与 `current_step`（以及 recorder）；`scheduler.py:32-33` 的 `self.time` 无人重置。实测：`run(3)` → `reset()` → `run(3)`，记录时间列为 **[4,5,6]**（应为 [1,2,3]），且智能体状态并未回滚。
- 影响：任何「多情景复用同一 Simulation」的流程都得到错位的时间索引；与 `fitter` 的 t 轴、`plot_*` 的 x 轴全部错配。
- 建议：新增 `Scheduler.reset()`，`Simulation.reset()` 同时重置两套时钟；若要支持真正的重跑，还需对 `Environment` 做状态快照/深拷贝。

**SI-2（P2）没有记录 t=0 初始状态**
- 证据：`simulation.py:30-36` 顺序为 `scheduler.step()` → `recorder.record()`，`run(3)` 记录时间为 [1,2,3]。实测【附录 A F5】。
- 影响：时序数据缺基线；`ABMFitter._extract_*` 取 `y_true[0]` 当 `y0`（`fitter.py:112,145,199`）实际是一步之后的状态，所有拟合都存在 1 步相位偏移；`plot_*` 也画不出初始点。
- 建议：在 `run()` 开始前调用一次 `recorder.record(env)`（时间标记 0），或在 `Simulation.__init__` 里做基线记录。

**SI-3（P3）`add_hook` 静默丢弃未知 stage**
- 证据：`simulation.py:22-24` `if stage in self.hooks: append`，拼错 `"post_step_typo"` 不会报错也不会执行。实测【附录 A F7】。
- 建议：`else: raise KeyError(...)`。

**SI-4（P3）`run_until` 返回 None、静默放弃**
- 证据：`simulation.py:42-46`：条件在步进前判定（条件初始为真则 0 步），耗尽 `max_steps` 时既无异常也无返回值。实测【附录 A F6】。
- 建议：返回 `bool`（是否因条件满足而停止）或抛 `TimeoutError`，并明确条件判定时机。

**SI-5（P2）钩子语义不自洽：`current_step` 与 `env.time` 在 `post_step` 内不一致，且 `post_step` 的写入当步不可见** —— Lead 遗留问题，**证实（语义不自洽）**
- 证据：`simulation.py:30-36`
  ```python
  self._run_hooks("pre_step")            # :31
  self.scheduler.step(self.environment)  # :32  ← 内部把 environment.time 自增（scheduler.py:32）
  for recorder in self.recorders: recorder.record(self.environment)  # :33-34
  self._run_hooks("post_step")           # :35
  self.current_step += 1                 # :36  ← 在 post_step 之后才自增
  ```
  实测（3 tick，在每个钩子里打印 `(sim.current_step, env.time, 成员 age, env.properties)`）：
  - `pre_step`：`(0,0,30.0)`、`(1,1,30.083)`、`(2,2,30.167)` → 时钟一致，看到的是**本 tick 更新前**的状态；
  - `post_step`：`(0,1,30.083)`、`(1,2,30.167)`、`(2,3,30.250)` → 看到的是**更新后**的状态，但 **`current_step` 比 `env.time` 小 1**（同一钩子内两个时钟不自洽）；
  - recorder 在 `post_step` 之前执行：`post_step` 把 `env.properties["stage"]="post_step"` 后，记录里 3 个 tick 全是 `'pre_step'`；`post_step` 写入的 `income=12345` 在 2 个 tick 的记录中都**未出现**（`income` 每步被 `family_member.py:109-111` 重算覆盖，因此永远不会被记录）。【附录 A HOOK】
- 影响：
  1. 钩子若用 `sim.current_step` 打时间戳、而 recorder/`env.time` 用另一个基准，会得到差 1 的时间轴（与 SI-1 的重置错位叠加后更难排查）；
  2. 在 `post_step` 里写聚合量/指标（最自然的用法，例如家庭总收入）**不会进入本步记录**，且对每步重算的状态永远不可见——用户会以为钩子没生效；
  3. `pre_step` 却会进入本步记录（`env.properties` 被记为 `'pre_step'`），即两个阶段的可见性相反且未文档化。
- 建议：统一为「先 `current_step += 1` 再跑钩子」，并把顺序固定为 `pre_step → step → post_step → record`（或 `record` 放最后并加 `record_pre/post` 选项）；在 `Simulation` docstring 写明每个阶段能看到的状态、`env.time`/`current_step` 的取值；`add_hook` 未知 stage 报错（SI-3）。
- 另注：钩子签名是 `hook(self)`（收到 `Simulation`），而 recorder 是 `record(environment)`（收到 `Environment`），两套约定并存，容易在钩子里误用 `env` 参数（`simulation.py:26-28` vs `recorder.py:14`）。

**SI-6（P3）`Simulation` 不接收 `seed`，也不负责参数层**
- 证据：`simulation.py:8-17` 只有 `environment` 与 `scheduler`。
- 建议：`Simulation(environment, scheduler=None, seed=None)`，统一给 scheduler 与所有 agent 注入 RNG（见 FM-5）。

---

### 2.5 `family_abm/core/__init__.py`

**CI-1（P3）导出与 README 一致，但没有 `__version__`、没有 `Agent` 之外的别名**
- 证据：`core/__init__.py:1-6` 导出 `Agent/Environment/Scheduler/Simulation` 且 `__all__` 一致。
- 影响：无。仅提示 `family_abm/__init__.py` 未导出 `__version__`（`PKG-INFO:3` 有 0.1.0），无法在运行时核对版本。
- 建议：`__version__ = "0.1.0"` 并加 `from importlib.metadata import version` 兜底。

---

### 2.6 `family_abm/family/family_member.py`

> 该文件是全部 P1 数值问题的集中地。默认参数见 `family_member.py:10-30`（共 **19** 个 key，非 README 声称的 18）。

**FM-1（P1）健康衰减参数校准错误，成年人在中年即触底 0.01**
- 证据：`family_member.py:113-120`
  ```python
  base_decay = self._p("health_decay_base", 0.002)          # family_member.py:115
  age_decay  = self._p("health_decay_age", 0.00015) * age   # family_member.py:116
  hp_change  = -(base_decay + age_decay * (1 - edu_protect)) * dt_months
  ```
  默认 `health_decay_base=0.002`、`health_decay_age=0.00015`（`family_member.py:16-17`）。月度损失：age=25 时 0.0052/月 ≈ **0.062/年**；age=45 时 0.0077/月 ≈ **0.093/年**；age=60 时 0.116/年。
  实测（randomness=0）：起始 20 岁 → **34.6 岁**到 0.01；30 岁 → **41.8 岁**；40 岁 → 50.3 岁；50 岁 → 58.2 岁；之后恒定 0.0100。【附录 A H2】
  实测常规场景（README 式 4 人家庭、120 步=10 年）：Dad 40→50 岁 health 掉到 **0.11**，Mom 0.01，孩子 0.35/0.55。
- 影响：这是**结论级错误**——健康维度在 20 年尺度上饱和到下限，`happiness_health_weight` 项恒为 0.002 左右（见 FM-6 的分解），任何「健康影响幸福」「教育保护健康」的对比都会被地板效应吞掉；`education protection` 名义 30% 实际只作用在年龄项（且 edu=0.5 时只有 15% 减免），无法补偿。
- 建议：把衰减改为相对量纲并重标定，例如
  `hp -= hp * (health_decay_base + health_decay_age * age) * (1 - edu_protect) * dt_months`，
  并把 `health_decay_age` 从 1.5e-4 降到 ~1e-5 量级，使 70 岁健康落在 0.5-0.8；加回归测试 `assert 0.4 <= health(age=70) <= 0.85`。

**FM-2（P1）压力均衡点超出 [0,1]，被 clamp 截断导致人格参数失效**
- 证据：`family_member.py:122-131`
  ```python
  st_change = (st_base + st_work) * (1 + neuro_sens * neuro) - st_decay * st   # :129
  self.set_state_value("stress", max(0.0, min(1.0, st + st_change)))           # :131
  ```
  解析均衡 `st* = (st_base+st_work)(1+neuro_sens·neuro)/st_decay`。默认下成人 `(0.03+0.02)·(1+0.3·neuro)/0.06`：neuro=0 → 0.833，0.5 → 0.958，**≥0.667 → >1.0**。
  实测（randomness=0，360 步=30 年，年龄 30→60 保持 adult）：neuro=0.75 → 1.0000，neuro=1.00 → **1.0000**（与 0.75 完全同值）；无噪声成人实测 0.99-1.00，300 步内有 2 次贴到 0.9999 以上。【附录 A H4/F1】
- 影响：神经质在 0.67 以上**完全无效**（人格→压力映射被天花板压平）；`happiness_stress_penalty` 的 0.3×1.0=0.30 变成所有成年人的固定扣分，幸福对人格/收入的敏感性被压缩（H3：stress=-0.297，占目标各项绝对值之和的 37%）。
- 建议：把「目标值 + 松弛」显式化并保证目标 < 1：
  `st_target = clamp((st_base + st_work) * (1 + neuro_sens * neuro) / st_decay, 0, 0.8)`；
  或把 `stress_decay` 提到 0.12（均衡 0.48）并让 `stress_base` 承担水平。加不变量测试：默认参数下所有生命阶段的稳态压力 < 0.8，且 neuro 单调可分辨（0.1 与 1.0 的稳态差 > 0.15）。

**FM-3（P1）参数无校验：`income_age_spread=0` 崩溃；`None`/非数字抛异常；`NaN` 静默变边界值**
- 证据：
  - `family_member.py:104-106`
    ```python
    spread = self._p("income_age_spread", 18)
    age_factor = math.exp(-((age - peak) ** 2) / (2 * spread ** 2))
    ```
    `spread=0` → `ZeroDivisionError`。实测：`env.params={"income_age_spread":0.0}` + 一次 `step()` → `ZeroDivisionError: division by zero`。【附录 A E9】
  - `family_member.py:61-66` `float(env_params.get(key, ...))`：`None` → `TypeError`；`"abc"` → `ValueError`。实测【附录 A E10】。
  - `NaN` 参数不会抛错，而是被 `max(0.0, min(1.0, x))`（`family_member.py:99,111,120,131,143,148`）静默改写：实测 `randomness=nan` → `health=1.0, happiness=1.0, income=0.0`（因 `max(0.0,nan)=0.0`、`min(1.0,nan)=1.0`）。
  - 触发路径是公开 UI：`dashboard.js:255` `<input ... step="0.001" min="0" max="5">`（允许 0），`dashboard.js:266` `parseFloat(inp.value) || 0`（清空即 0），`web/app.py:90` `env.params = cfg.params`，`web/app.py:86-111` 的 `/api/run` 无 try/except → 500。
- 影响：P1 级可用性/正确性问题；NaN 路径更危险——不报错但结果被钉在量程边界，属于静默错误结论。
- 建议：在参数入口做一次 schema 校验（pydantic 或手写 `MathParams` dataclass）：类型、`isfinite`、取值域（`income_age_spread >= 1e-3`、`stress_decay > 0` 等）；`_p` 改为读取已校验的 `self._params`（同时解决性能，见 FM-10）；`/api/run` 包 try/except 返回 4xx。

**FM-4（P1）构造时角色不按年龄推导，且 `role_name` 在第一步后即失效**
- 证据：`family_member.py:40,50`
  ```python
  role_name: str = "adult", ...            # :40
  self.set_attribute("role", role_name)    # :50  ← 不调用 _role_at_age
  ```
  而 `_role_at_age`（`family_member.py:68-73`）只在 `age_increment`（`:75-78`）里被调用，即**第一步结束时**。
  实测：`FamilyMember(age=0.5/3/10/17/100)` 构造后 role 全是 `'adult'`；0.2 岁婴儿第一步收入 0.001606（role=adult, `role_mul=1.0`），同一婴儿显式设为 `preschool` 时 0.001156 → **高估 39%**；`role_name="parent"` 不在 `role_mul` 表（`family_member.py:107-108`）→ 第一步兜底 0.2，第二步被覆盖为 adult。【附录 A H1/E8】
- 影响：(a) Python API 默认路径下每个非成人成员第一步收入错误；(b) 公开参数 `role_name`（README 示例、仪表板下拉框 `dashboard.js:304-309` 都在用）是**一次性且会被静默丢弃**的假参数；(c) 两套角色词汇（`preschool/child/student/adult/elder` vs `roles.py:54-59` 的 `parent/child/adult/elder`）并存且互不认识。
- 建议：`__init__` 里 `self.set_attribute("role", self._role_at_age(age))`；把 `role_name` 明确定义为「角色覆盖」并单独存 `role_override`，或干脆删除该参数；统一角色词汇表并把 `role_mul` 抽成 `roles.py` 的注册表（`Role.income_multiplier`），让 `ROLE_REGISTRY` 真正被使用。

**FM-5（P1）全链路无随机种子，仿真不可复现**
- 证据：构造期 `family_member.py:48,52-56`（`random.gauss/uniform`），步进期 `:86,110,119,130,142,147`（6 次抽样），`relationships.py:17-21,32-34`（关系初值与演化），`scheduler.py:17-23`（乱序），全部使用**模块级全局 `random`**；`Simulation`/`Environment`/`FamilyMember` 均无 `seed`/`rng` 参数。
- 实测：同一段脚本两次运行 happiness=0.415131 vs 0.383532（`random.seed(123)` 后为 0.383532）【附录 A E11】；`Scheduler('random')` 的顺序只能通过 `random.seed` 间接控制【附录 A E18】。
- 影响：仪表板同样输入点击两次得到不同 KPI，用户会把随机差异当成参数效应；论文/报告数字无法复现；`fitting` 侧却有 `seed=42`（`fitter.py:135,151,207`），前后不一致。
- 建议：`Simulation(seed=...)` → 创建 `random.Random(seed)` 并注入 `Environment`/`Scheduler`/每个 `FamilyMember`（`self.rng = rng or random`），所有抽样改走 `self.rng`；`StateRecorder` 记录 seed 元数据。

**FM-6（P2）步内「边更新边读」：幸福目标混用了新值与旧值**
- 证据：`family_member.py:92-142`。education 在第 98-99 行写回（局部变量 `edu` 已更新），income 在第 109-111 行计算（局部 `income` 更新），但 happiness 目标在 `:136-139` 同时使用 **旧 `hp`**（第 114 行读、第 120 行已写回 state）与 **旧 `st`**（第 123 行读、第 131 行已写回），以及 **新 `edu`/新 `income`**：
  ```python
  h_health = self._p("happiness_health_weight", 0.20) * hp          # 旧 health :136
  h_income = self._p("happiness_income_weight", 0.25) * min(1.0, income*3)  # 新 income :137
  h_edu    = self._p("happiness_edu_weight", 0.10) * edu             # 新 education :138
  h_stress_pen = self._p("happiness_stress_penalty", 0.30) * st      # 旧 stress :139
  ```
  实测同一状态下的目标值：纯显式 Euler（全旧）= **0.47951**，代码的混合版 = **0.56632**，纯 Gauss-Seidel（全新）= 0.55404 → 混合方案与两种一致方案都不同（相差 0.087，占 0-1 量程的 18%）。【附录 A F2】
- 影响：更新范式不明确（既不是 Jacobi/simultaneous 也不是一致的 Gauss-Seidel），任何「同一步内应该看到什么」的分析都无定论；这正是 SC-1 所述因果泄漏的微观版本；参数敏感性分析会受实现顺序污染。
- 建议：`step()` 开头 `prev = dict(self.state)`，所有公式只用 `prev` 计算增量，最后统一提交（显式 Euler）；或明确采用 Gauss-Seidel 并把顺序写进 docstring。这也让「simultaneous」调度器变得可实现。

**FM-7（P2）`dt_months` 只作用于 education/health/age，stress/happiness/energy 是「每次调用」而非「每单位时间」**
- 证据：应用了 `dt_months` 的：education `:98`、health `:118`、age `:151`；**未应用**的：stress `:129`、happiness `:142`、energy `:147`（`dt_months` 本身在 `:88` 读取）。Lead 线索 3 所称的 121-148 行区间正是这三段（stress `:122-131`、happiness `:133-143`、energy `:145-148`），逐行核对后确认**三段全都没有乘 `dt_months`**，而 `dt_months` 只出现在 `:88`（读取）、`:98`、`:118`、`:151`。
- 实测：`dt_months=12` 走 1 步 vs `dt_months=1` 走 12 步（同一 1 年）：age 都是 31.00、education 0.5040 vs 0.4840、health 0.8459 vs 0.8530（接近），但 **stress 0.3862 vs 0.6373、happiness 0.5912 vs 0.4869、energy 0.6460 vs 0.6849**（差 65%/21%）。【附录 A E3】
- 影响：量纲不一致；把步长从「月」改成「年」会系统性改变压力/幸福/精力的动力学，模拟结果依赖步长这一实现细节，属于典型的离散化错误。（`dt_months` 还是**未文档化的隐藏参数**，不在 `DEFAULT_PARAMS`，见 RO/PK 相关条目。）
- 建议：要么删除 `dt_months`（固定 dt=1 个月并写进文档），要么对所有状态统一乘 dt；对松弛型方程用精确解避免步长不稳定：`st += (st_eq - st) * (1 - math.exp(-st_decay * dt))`。

**FM-8（P2）幸福公式与 README 不一致：收入项被 ×3 缩放并截断**
- 证据：`family_member.py:137` `min(1.0, income * 3)`；README 声称「收入权重×收入」的线性项。默认参数下收入上限 `0.10*(1+0.40*1)*1*1 = 0.14`，故 `min(1,0.14*3)=0.42` → 收入项最多 `0.25*0.42 = 0.105`，即**权重 0.25 只兑现 42%**。实测默认收入 0.124 → 收入项 0.0930（名义 0.25 的 37%）；`income_base≥0.5` 时直接钉在 0.25 饱和（仪表板允许到 5）。【附录 A F4/H6】
- 影响：收入→幸福映射非线性、未文档化、两端都失真：低收入区间斜率被放大 3 倍，高收入区间完全饱和；跨情景比较收入效应会得到与参数名义值不符的结论。
- 建议：统一量纲——对收入做显式归一化 `income_norm = income / income_ref`（`income_ref` 作为参数），文档化并移除魔法数字 3；`income_base` 的取值范围与 `income_ref` 绑定校验。

**FM-9（P2）人格仅 neuroticism 生效；人格值不校验（非 dict 直接崩、越界值被接受）**
- 证据：5 维定义 `family_member.py:7`，随机生成并 clamp `:47-49`，但 `step()` 中只读 `neuroticism`（`:127`）；openness/conscientiousness/extraversion/agreeableness 无任何引用（grep 全仓库仅命中定义/构造）。显式传入的 personality **不做 clamp/类型校验**：`personality=[1,2]` → `AttributeError: 'list' object has no attribute 'get'`；`{'neuroticism':'high'}` → `TypeError`；`{'neuroticism':50}` → 第一步压力直接 1.0。【附录 A G4/E17】
- 影响：(a) README「每人拥有独立人格」名不副实，4/5 维是纯装饰数据列；(b) 越界值污染结果且无告警。
- 建议：校验为 `dict[str, float]` 且每个维度 clamp 到 [0,1]；把另外 4 维接入模型（如 conscientiousness→`education_rate`、extraversion→社交资本/关系质量、agreeableness→关系冲突、openness→新行为采纳），否则从构造与文档中删除。

**FM-10（P2，性能）每智能体每步重复读取参数 20 次，占单步耗时约 27%**
- 证据：`family_member.py:61-66` 的 `_p` 每调用一次做 `getattr` + `dict.get` + `float()`；`step()` 内 `self._p(` 共 **20 处**（行号 88,89,93,102,103,104,105,115,116,117,124,125,126,128,135,136,137,138,139,141）。
- 实测：2000 成员 × 200 步 = 440k agent-steps，6.59s（≈15 µs/agent-step）。cProfile（100 户×10 成员 × 100 步）：总 7.39s，`_p` 调用 **1,957,535 次**，tottime 1.263s / cumtime 1.996s（≈27%），`dict.get` 5,115,270 次 0.753s，`getattr` 1,957,535 次 0.232s；`Relationship.update_dynamics` 450,000 次 0.829s（正好是 100 户 C(10,2)=45 × 100 步 × 100 户，即 O(n²)）。
- 影响：参数读取成为第一大热点；规模上去后（10^4-10^5 智能体）不可接受。
- 建议：参数合并/校验一次并缓存为 `self._params`（或冻结 dataclass，属性直读）→ 预计整体提速 25-35%；进一步见第 4 节性能项。

**FM-11（P2）教育永不衰减、终身单调增长，学龄阶段因子有未文档的下限**
- 证据：`family_member.py:91-99`：`age_edu_factor = max(0.05, 1.0 - age / 60)`，`edu += (edu_rate*age_edu_factor*(1-edu) + 噪声) * dt_months`，`(1-edu)` 恒 >0 → 单调不减、永不停滞。
- 实测（randomness=0，1200 步=100 年）：起始 6 岁 → 106 岁 edu=**0.925**；起始 30 岁 → 130 岁 edu=0.762；常规 120 步场景里 8 岁孩子 edu 从 0.10 涨到 0.15、40 岁父亲 0.57。【附录 A F3/E1/E14】
- 影响：教育被建模成「终身累积且不折旧」的存量，老年人教育水平可高于青年；`max(0.05, ...)` 的 0.05 下限意味着 60 岁以后仍在稳定增长（配合 FM-1 的健康归零，会得到「高龄、零健康、高教育、零收入」的失真画像）。
- 建议：按生命阶段冻结/折旧（`if role in ("adult","elder"): gain=0` 或 `edu -= edu_decay`），把下限常量提为参数并文档化；加测试「edu 在 25 岁后年增量 < 0.005」。

**FM-12（P3）未使用的状态 `energy` 是死变量且不是「恢复-消耗循环」**
- 证据：`family_member.py:145-148` `en = en * 0.92 + 0.06 + 噪声` → AR(1)，解析不动点 `0.06/0.08 = 0.75`，与 stress/health/role/人格**完全无关**；全仓库无任何方程读取 `energy`（grep `state_energy|energy` 仅命中本文件三处：`:55,146,148`）。
- 实测：randomness=0 跑 200 步 → energy=**0.750000**（与解析值一致），而此时 stress=1.0、health=0.01。【附录 A H5】
- 影响：README 的「简单的恢复-消耗循环」不成立（无消耗项、无恢复项、无耦合）；该状态只增加记录体积。
- 建议：接入真实循环（如 `en += (rest_rate*(1-stress) - work_rate*st_work) * dt`），或删除该状态与文档描述。

**FM-13（P3）年龄边界无上限、`role` 切换滞后一步、异常年龄不校验**
- 证据：`family_member.py:68-73` 阈值 `<6/<18/<22/<65/else`，无上界；`age_increment` 在 `step()` 末尾调用（`:151`），所以跨阈值的当月仍用旧角色计收入（一致性可接受，但需明示）；`age=None`/`"x"` → `TypeError`，`age=-5` 被接受（`_role_at_age(-5)="preschool"`）。
- 实测：age 从 64.9 加 0.5 年后 role 才变 `elder`；`age=1e6` 不报错。【附录 A G5】
- 影响：超高龄（>100）无死亡/退出机制时，agent 永久存活并持续老化（见 HH-4）；非法年龄静默通过。
- 建议：`0 <= age <= 120` 校验；补 `mortality`/`age_out` 机制或在文档明确「无死亡」；阈值集中为 `LIFE_STAGE_BOUNDS` 常量。

---

### 2.7 `family_abm/family/household.py`

**HH-1（P2）`total_income` 永远滞后一步，且受注册顺序支配**
- 证据：`household.py:54-62`
  ```python
  def step(self):
      for rel in set(self.relationships.values()): rel.update_dynamics()
      total_income = sum(m.get_state_value("income", 0.0) for m in self.members.values())
      self.set_state_value("total_income", total_income)
  ```
  而注册顺序是 `env.add_agent(hh)` 先、`hh.add_member(m)` 后（`household.py:33-34` 把成员注册进环境），`Scheduler.schedule` 用 `environment.get_agents()`（`environment.py:28-29`）按 dict 插入序返回 → **Household 永远先于成员步进**。
- 实测：t=1 时 `total_income=0.000000` 而成员收入之和 0.113725（差 -0.1137）；t=2 时 total_income=0.113725 恰为 t=1 的和。【附录 A E4】
- 影响：记录中的家庭总收入整体错位一步；若未来有人把 Household 注册在成员之后（例如中途新增家庭），同一仿真内会出现两种时序语义；`/api/data`、`plot_*`、`MicroNiche` 读取的都是这个滞后量。
- 建议：把聚合改为「步后计算」——在 `Simulation.step` 的 `post_step` 阶段调用 `household.aggregate()`，或在 `Household.get_state()` 里按需即时求和（`total_income` 不入 state，改为属性）。

**HH-2（P2）成员未注册时静默失联（顺序陷阱）**
- 证据：`household.py:22-34` 的 `add_member` 只在 `self.environment is not None` 时把成员注册进环境（`:33-34`），没有告警也没有延迟注册。
- 实测：先 `h2.members[...]=member` 再 `env.add_agent(h2)` → 环境中只有 1 个 agent，**该成员永不步进、也永不被记录**。【附录 A E5】
- 影响：用户（或未来重构）把 `add_member` 放在 `add_agent` 之前时，仿真「跑得动、结果看着正常」，实际少算了整个成员——最危险的一类静默错误。
- 建议：`add_member` 在 `environment is None` 时 `warnings.warn` 或抛错；更稳妥的是让 `Household` 记录待注册成员，并在 `Environment.add_agent(household)` 时自动注册（或在 `Household.step()` 中兜底注册）。

**HH-3（P2）`Household.step()` 不检查 `alive`，死亡/迁出成员仍被计入总收入**
- 证据：`household.py:58-61` 求和时无 `alive` 过滤；`alive` 仅在 `scheduler.py:30`/`environment.py:39` 阻止 `step()`。
- 实测：把成员 `alive=False` 后它不再步进，但 `Household.total_income` 仍包含它最后一步的收入 0.118，且 `member_count` 仍为 1。【附录 A G6】
- 影响：一旦引入死亡/迁出，家庭收入与规模会永久保留幽灵成员；`remove_member`（`:36-43`）才是唯一清账路径，而它不会被自动调用。
- 建议：聚合时 `if m.alive` 过滤；提供 `Household.reap_dead()`；或让 `Simulation` 在 `post_step` 统一同步成员表。

**HH-4（P2）死亡/迁出机制完全缺失，`alive` 永远为 True**
- 证据：全仓库 grep `alive` 只出现在 `agent.py:17,28`（初始化/导出）、`scheduler.py:30`、`environment.py:39`（作为门控读取）、`recorder.py:30`（记录）、`household.py:70`；**没有任何地方把 `alive` 置为 False**。实测 95 岁跑 240 步到 115 岁仍 `alive=True`、role=elder、household 成员数不变。【附录 A E15】
- 影响：`生命阶段…老年` 没有出口；长程仿真里智能体无限老化（配合 FM-1 全部变成 health=0.01、income≈0 的幽灵），人口结构随时间为单调老龄化的伪像。
- 建议：加入死亡率模型（如 Gompertz：`p_death = exp((age-a)/b)`）与迁出事件，或至少在文档与 API 中明确「本模型不含死亡」，并把 `alive` 的语义（只作外部开关）写清。

**HH-5（P3）`add_member` 重复添加会重掷已有关系的属性**
- 证据：`household.py:24-32` 对每个 existing 成员**新建** `Relationship` 并写入两个方向的 key；同一成员再次 `add_member` 时，该成员与所有人的关系对象会被整体替换（`random.uniform` 重掷 affection/trust/conflict，`relationships.py:17-21`）。
- 影响：重复添加/批量重建成员会静默丢失关系历史。
- 建议：存在即早退；或提供 `rebuild_relationships=False` 选项。

**HH-6（P3）`relation_to_head` 被套用到所有成员对，且其默认值 `"member"` 不属于任何角色词表**
- 证据：`household.py:22` `def add_member(self, member, relation_to_head: str = "member")`；`:24-32` 把该值写进**新成员与每一个已存在成员**之间的 `Relationship.relation_type`（`relationships.py:11`）。而 `ROLE_REGISTRY` 的键是 `parent/child/adult/elder`（`roles.py:54-59`），`_role_at_age` 的取值是 `preschool/child/student/adult/elder`（`family_member.py:68-73`）——**两套词表都不含 `"member"`**，也就是说默认调用产生的 `relation_type` 与角色体系完全对不上（`examples/simple_family.py:21-24` 与仪表板 `dashboard.js:338-345` 都走默认值或 `role_name`，从未传 `relation_to_head`）。`Household` 也没有 head 字段。
- 影响：`relation_type` 当前无消费者（见 RL-2），所以暂无错误结果；但一旦按关系类型驱动影响权重（RL-2/改进⑤），默认值会让所有家庭关系落进「未知类型」兜底分支。
- 建议：统一词表（把 `member` 改为显式枚举或必填），引入 `head_id` 与逐对 `relation` 参数（如 `{member_id: relation}`）。

**HH-7（P3）`get_state()` 的 `member_count` 不会被 recorder 记录**
- 证据：`household.py:64-72` 在 `get_state()` 里加 `member_count`，但 `recorder.py:32-37` 只遍历 `attributes` 与 `state` → `member_count` 被丢弃。
- 建议：放进 `self.state`，或让 recorder 支持额外字段。

**HH-8（P3，性能）`set(self.relationships.values())` 每步重建 O(n²) 集合**
- 证据：`household.py:55`：`relations` 字典有 `n(n-1)` 个 key（每对关系存两个方向，`household.py:31-32`），成员 n=10 时每步构造 90 元素集合、去重后 45 个对象。实测 8 成员 → 28 个唯一对象（= C(8,2)，去重正确）【附录 A E13】；顺序依赖对象身份哈希，两次独立进程实测顺序一致（未证明为不确定性 bug，但依赖分配序，属脆弱设计）。
- 建议：额外维护 `self._unique_relationships: list[Relationship]`（`add_member`/`remove_member` 同步维护），直接遍历列表；`relationships` 仅作索引。

---

### 2.8 `family_abm/family/relationships.py`

**RL-1（P2）关系动力学是纯随机游走，与任何智能体状态无关 → 家庭耦合层无因果**
- 证据：`relationships.py:31-34`
  ```python
  self.affection = clamp(self.affection + random.uniform(-0.02, 0.02))
  self.trust     = clamp(self.trust + random.uniform(-0.01, 0.01))
  self.conflict  = clamp(self.conflict + random.uniform(-0.01, 0.01))
  ```
  不接受任何成员状态/事件输入；同时全仓库**没有任何代码读取 relationship 的 affection/trust/conflict** 用于成员状态更新（grep `relationships` 仅命中 family/`__init__`、household、web/app.py:235、viz/plots.py:211——全是序列化/可视化）。
- 影响：家庭结构对成员的幸福、压力、健康无影响；「家庭 ABM」实际退化为 N 个互不相干的单智能体独立随机过程 + 装饰性网络图。README 所暗示的家庭机制不成立（属结论级设计缺陷）。
- 建议：把关系量接入成员方程（如 `happiness += support_weight*(affection+trust) - conflict_penalty*conflict`、`stress -= family_buffer*affection`），并让关系受互动事件/人格/压力驱动（如冲突随双方 stress 上升）。

**RL-2（P3）`influence_weight` / `power_dynamics` / `domain` / `communication_quality` 是死 API**
- 证据：`relationships.py:19` `power_dynamics = 0.5` 常量、`:26-29` `influence_weight(from_agent_id, domain="general")` 里 `domain` **从未使用**，:20 `communication_quality` 初始化后从不更新；全仓库无 `influence_weight` 调用点（grep 仅命中定义/`get_state`）。实测两个方向权重完全相同（0.467293/0.467293），传 `domain="finance"` 结果不变。【附录 A E13】
- 影响：接口承诺的方向性影响/权力不对称不存在；`power_dynamics=0.5` 使 `is_a` 分支退化为恒等。
- 建议：要么实现（由 `Role.get_decision_weight` 驱动 `power_dynamics`、用 `domain` 查权限、按关系类型更新 `communication_quality`），要么删除。

**RL-3（P3）`agent_a_id` 由「后加入者」决定，方向语义随插入顺序变化**
- 证据：`household.py:26-27` 新建时 `agent_a_id=member.id`（新成员）→ 实测 `rel.agent_a_id == 后加入者`。【附录 A E13】
- 影响：`influence_weight` 的 `is_a` 分支含义取决于加人顺序，而非家庭角色；一旦 `power_dynamics` 不再恒为 0.5，就会产生难解释的方向性偏差。
- 建议：按稳定序（如创建时间/id 排序）固定 a/b，或显式保存 `head_id`/`child_id` 语义；`power_dynamics` 从角色派生。

**RL-4（P3）关系初值与更新无种子（同 FM-5）**
- 证据：`relationships.py:17-21,32-34` 使用全局 `random`。
- 建议：由 `Household`/`Environment` 注入 RNG。

---

### 2.9 `family_abm/family/roles.py`

**RO-1（P2）`Role` 体系完全未接入仿真，两套角色词汇并存**
- 证据：`roles.py:5-59` 定义 `Role/ParentRole/ChildRole/AdultRole/ElderRole` 与 `ROLE_REGISTRY`；全仓库**没有任何实例化**（grep 仅命中定义、`family/__init__.py:4,6` 导出、`web/app.py:17` 导入）。实测 `FamilyMember` 的 `role` 是字符串，取值来自 `_role_at_age`（`preschool/child/student/adult/elder`），与 registry 的 `parent/child/adult/elder` 词汇表不一致（少了 `preschool/student`，多了 `parent`）。
- 影响：(a) `get_decision_weight` 的决策权重、`norms` 都不影响任何计算；(b) `role_mul` 的 income 乘数硬编码在 `family_member.py:107-108`，与 `roles.py` 平行，改一处必然忘另一处；(c) `web/app.py:17` 是无用导入（且有循环导入隐患）。
- 建议：把 `income_multiplier`、`stress_work_add` 系数、`role_mul` 等搬进 `Role`，`FamilyMember` 持有 `Role` 实例；`_role_at_age` 返回 registry key；清理 `web/app.py:17`。

---

### 2.10 `family_abm/family/__init__.py`

**FI-1（P3）导出完整但未导出 `DEFAULT_PARAMS` / `PERSONALITY_DIMENSIONS` / `ROLE_REGISTRY`**
- 证据：`family/__init__.py:1-6` 仅导出 `FamilyMember/Household/Relationship/Role/ParentRole/ChildRole/AdultRole/ElderRole`；`DEFAULT_PARAMS` 只能从 `family_abm.family.family_member` 深导入（`web/app.py:70` 正是这么做的）。
- 影响：参数层缺乏稳定公开入口，用户无法从 `family_abm.family` 拿到默认参数做覆盖。
- 建议：导出 `DEFAULT_PARAMS`、`PERSONALITY_DIMENSIONS`、`ROLE_REGISTRY`、`LIFE_STAGE_BOUNDS` 并纳入 `__all__`。

---

### 2.11 跨文件：`family_abm/__init__.py` 与打包（PK）

**PK-1（P1）`import family_abm` 强依赖 scipy/matplotlib，但 `setup.py` 只声明 numpy+pandas**
- 证据：`family_abm/__init__.py:14-20` `from .fitting import ...` → `fitting/fitter.py:6` `from scipy.integrate import solve_ivp`、`fitting/lanchester.py:4`；`family_abm/__init__.py:21-25` `from .viz import ...` → `viz/plots.py:7-8` `import matplotlib; matplotlib.use("Agg")`。而 `setup.py:7` `install_requires=["numpy>=1.21.0", "pandas>=1.3.0"]`；`PKG-INFO:5-6` 同样只有 numpy/pandas。`requirements.txt:1-8` 是正确的（含 scipy/matplotlib/networkx/fastapi/uvicorn/jinja2），但 `setup.py` 未使用。
- 影响：`pip install .` 后 `import family_abm`、README 示例、`python examples/simple_family.py` 全部 ModuleNotFoundError。`networkx` 只在 `viz/plots.py:201-203` 惰性导入并有清晰报错，处理得当，可与 scipy/matplotlib 的区别对待作为对照。
- 建议：`install_requires` 对齐 `requirements.txt`（web 依赖可放 `extras_require={"web": [...]}`）；更彻底的做法是把 `viz`/`fitting` 改为惰性导入（`__getattr__`），让 `from family_abm import FamilyMember` 只依赖 numpy/pandas——但注意 `recorder.py:3` 已依赖 pandas。

**PK-2（P2）仓库没有任何 README/文档，README 声称无法核对**
- 证据：`glob **/*.md` 无结果；`Get-ChildItem -Recurse -Include *.md,*.rst` 为空；目录下只有 `examples/ family_abm/ family_abm.egg-info/ requirements.txt setup.py`；非 git 仓库（无 `.git`），`SOURCES.txt` 里也没有 README。
- 影响：第 3 节的核对只能依据任务书转述的声称；用户/评审无法从仓库自证 API 与公式。
- 建议：补 `README.md`（把第 3 节表格中「形式符合但数值不符」的项一并修正），并把公式与默认参数表放进去。

**PK-3（P3）README 声称的其它 API 均存在且签名兼容**
- 证据：`family_abm/__init__.py:1-42` 导出 `FamilyMember/Household/Environment/Simulation/Scheduler/StateRecorder/make_fitter/wellbeing_balance/solve_model/plot_timeseries/plot_fit_diagnostics/Relationship/Role` 等；实测 `hasattr` 全部为 True，签名见【附录 B】。
- 提示：`wellbeing_balance`（`lanchester.py:44-52`）是 ODE 模型 `dH/dt=p·income-q·S·H`、`dS/dt=r·H(1-S)-s·S`，与 `FamilyMember.step` 的离散更新式（`family_member.py:129,140-142`）**不是同一个模型**，而 `make_fitter('wellbeing')` + `/api/fit` 默认就用它去拟合 ABM 的 happiness/stress（`web/app.py:53,161`）→ 拟合优度衡量的是代理模型失配程度，不是 ABM 校准质量（属跨模块问题，此处仅记录以免误读拟合结果）。

---

## 3. README 声称 vs 实际实现 差异表

| README 说法 | 实际实现（证据） | 判定 |
|---|---|---|
| 家庭包含多个成员智能体，每人拥有独立的人格、年龄轨迹、教育、收入、健康、情绪状态 | 状态齐全（`family_member.py:52-57`）；但人格 5 维只有 `neuroticism` 生效（`:127`），其余 4 维从不被读取 | **部分符合**（人格维度失效，P2） |
| 18 个动力学参数可在仪表板实时调整 | `DEFAULT_PARAMS` 有 **19** 个 key（`family_member.py:10-30`，实测 `len==19`），`web/app.py:71-78` 分组也是 19 个；此外还读取隐藏参数 `dt_months`（`:88`）→ 共 20 个可调项。参数随 `POST /api/run` 一次性提交并同步跑完（`web/app.py:86-104`），UI 无中途调整通道；引擎层 `env.params` 确实每步实时读取（实测 F8） | **不符合**（数量 18→19/20；「实时」仅引擎层成立） |
| 生命阶段：学龄前 → 儿童 → 学生 → 成人 → 老年 | `_role_at_age` 五段齐全（`family_member.py:68-73`）；但构造时 role 恒为默认 `'adult'`，与年龄无关（实测 0.5/3/10/17/100 岁全是 adult），`roles.py` 的 Role 体系与 `ROLE_REGISTRY` 完全未接入 | **部分符合**（P1 见 FM-4，P2 见 RO-1） |
| 收入 = 基础值 × (1 + 教育加成 × 受教育水平) × 年龄曲线 × 角色乘数 | `family_member.py:102-111` 与之逐项一致（`base*(1+income_edu_boost*edu)*exp(-(age-peak)²/2σ²)*role_mul`） | **符合**（公式一致；但 `role_mul` 由 FM-4 的角色错误污染） |
| 健康 = 基础衰减 + 年龄加速衰减，受教育水平减缓 | 公式 `-(base_decay + age_decay·age·(1-edu_protect))`（`family_member.py:115-118`）形式一致；数学上「衰减率随年龄线性增长 → 健康二次下降」符合「加速」；但教育只减缓年龄项不影响基础项，且默认量级使 30 岁在 41.8 岁触底 0.01（实测 H2） | **形式符合，校准不符合**（P1 见 FM-1） |
| 压力 = 基础压力 + 工作负荷，受神经质人格放大，自然衰减 | 形式一致（`family_member.py:129`）；但均衡值 `(0.03+0.02)(1+0.3·neuro)/0.06` = 0.833…1.083，neuro≥0.667 起被 clamp 到 1.0，实测 neuro=0.75 与 1.0 稳态完全相同（H4） | **形式符合，数值饱和**（P1 见 FM-2） |
| 幸福 = 均值回归：目标值 = 基底 + 健康权重×健康 + 收入权重×收入 + 教育权重×教育 − 压力惩罚×压力 | 目标项名称齐备（`family_member.py:135-140`），均值回归 `ha += (target-ha)*recovery` 正确（`:142`）；但收入项实为 `min(1, income*3)`，未文档化的 ×3 缩放 + 截断，默认下最多兑现权重的 42%（实测收入项 0.105/0.25） | **部分符合**（P2 见 FM-8） |
| 精力 = 简单的恢复-消耗循环 | 实为 AR(1) `en*0.92+0.06`，不动点恒为 0.75，无消耗项、无恢复耦合，且无任何方程读取 `energy`（实测 0.750000，H5） | **不符合**（P3 见 FM-12） |
| Python API 用法示例（Environment/Household/FamilyMember/StateRecorder/Simulation/Scheduler 组合） | `examples/simple_family.py` 与 README 式组合均可跑通（实测 600 条记录、角色随年龄推进）；`examples/fitting_viz_demo.py`、`examples/ml_ready.py` 存在（未运行，因其写 `examples/output/*.png`） | **符合** |
| `from family_abm import ... FamilyMember, Household, StateRecorder, make_fitter, wellbeing_balance, solve_model, plot_timeseries, plot_fit_diagnostics` | 全部存在且可导入，签名见【附录 B】；但导入 `family_abm` 会连带要求 scipy+matplotlib，而 `setup.py:7` 未声明 → 干净安装后导入即失败 | **存在性符合；安装声明不符合**（P1 见 PK-1） |
| （README 文件本身） | 仓库无 README.md / 任何 .md / 非 git 仓库 | **无法核对原文**（P2 见 PK-2） |

---

## 4. 建议的算法/结构改进（按收益排序）

1. **建立显式参数层（最高优先）**：`@dataclass(frozen=True) SimulationParams`，含类型/范围/有限性校验，`Environment(params=...)` 合并 `DEFAULT_PARAMS`，`FamilyMember` 持引用。
   - 理由：一次性消灭 FM-3 崩溃类、FM-10 的 20 次/步 dict 查找（实测 27% 运行时间）、`dt_months` 隐藏参数、README 参数数量不一致。
   - 预期：整体提速 25-35%；非法参数在入口报错而非在某一帧静默变 1.0/崩溃。

2. **统一随机源与可复现性**：`Simulation(seed=...)` → `numpy.random.Generator`/`random.Random` 注入 `Environment`/`Scheduler`/每个 `FamilyMember`/`Relationship`；recorder 记录 seed 与参数快照。
   - 理由：修 FM-5、SC-3、RL-4；让仪表板 A/B 对比有意义（当前同输入不同输出）。
   - 预期：任何实验可用一行 seed 复现；参数敏感性分析可做统计检验。

3. **重标定健康/压力/幸福，并用不变量测试锁死**：健康改相对衰减（`hp -= hp·rate(age)`），压力改「目标+松弛」并保证目标 <0.8，收入项量纲归一化。
   - 理由：修 FM-1、FM-2、FM-8——这三个问题会让「健康/压力/收入如何影响幸福」的结论全部失真。
   - 预期：70 岁健康落在 0.5-0.8；所有生命阶段稳态压力 <0.8 且 neuro 单调可分；收入权重按名义值线性生效。测试如 `test_health_lifecourse`、`test_stress_equilibrium_bounded`、`test_income_monotone_in_happiness`。

4. **两种明确的更新语义（Jacobi / Gauss-Seidel）**：`FamilyMember.step()` 改为「快照 → 计算增量 → 提交」，`Scheduler` 增加 `simultaneous`（两阶段提交），`sequential` 更名 `gauss_seidel` 并注明因果泄漏方向。
   - 理由：修 FM-6（实测目标值差 0.087/18%）、SC-1、SC-2；使「同步更新」成为可选项，而这也是把关系/家庭耦合（见 5）引入后避免顺序依赖的前提。
   - 预期：同一步内所有公式基于同一状态，结果与实现顺序无关；可复现的并行/同步实验。

5. **让家庭层真正产生因果**：关系量接入成员方程（支持 → 幸福/压力缓冲，冲突 → 压力）；`power_dynamics` 由 `Role.get_decision_weight` 派生；聚合量（`total_income`、`member_count`）改为 `post_step` 阶段的步后聚合并过滤 `alive`；`energy` 与 stress/health 耦合；引入死亡/迁出。
   - 理由：修 RL-1、RL-2、RO-1、HH-1、HH-3、HH-4、FM-12——当前「家庭」对成员状态零影响，家庭 ABM 名不副实。
   - 预期：Household 规模/关系质量能解释成员幸福方差；长寿仿真不再全是「健康 0.01 的 130 岁幽灵」。

6. **步长一致性**：删除 `dt_months` 或对所有状态一致应用 dt，松弛项用精确解 `st += (st_eq-st)·(1-exp(-k·dt))`。
   - 理由：修 FM-7（dt=12/1 步在同一 1 年内 stress 差 0.3862 vs 0.6373）。
   - 预期：结果不随步长选择漂移，支持年/月/周多分辨率实验。

7. **数据层分离与基线**：`StateRecorder` 分类型建表（`to_dataframe(agent_type=...)`），`run()` 前记录 t=0。
   - 理由：修 SI-2 与「Household 行与成员行混在同一张表」（实测 600 行中第 0 行是 Household，`state_education=NaN`，任何 `groupby('time').mean()` 都把 Household 平均进去）。
   - 预期：`fitter`/`plot_*`/`/api/data` 不再混入非人类行，拟合去掉 1 步相位偏移。

8. **向量化与算法复杂度**：每步一次性生成噪声矩阵（`np.random.Generator.normal(size=(n,k))`）而非每智能体 13 次标量抽样；状态更新批量 numpy 化；关系更新用矩阵化或把 `Household.step` 的 `set()` 去重（HH-8）换成维护好的唯一列表；大批家庭用 `numpy` 分块。
   - 理由：实测 15 µs/agent-step、`_p` 27%、`update_dynamics` O(n²) 占 11%；关系更新本质是 `n(n-1)/2` 次独立抽样，天然可向量化。
   - 预期：10^4-10^5 智能体规模下 20-100× 提速（纯 Python 标量 → 数组批量）。

9. **工程收尾（低风险、高省心）**：`setup.py` 对齐依赖（PK-1）；`v1.0 API` 卫生——重复 id 报错（EN-1）、`add_hook` 未知阶段报错（SI-3）、`Scheduler` 构造期校验（SC-2）、`Simulation.reset` 重置双时钟（SI-1）、`add_member` 未注册告警（HH-2）、导出 `DEFAULT_PARAMS`（FI-1）、补 `README.md`（PK-2）、`__version__`（CI-1）。
   - 预期：消除一类「静默错误」和「装完即崩」，并把文档与实现重新对齐。

---

## 5. Lead 线索复核（逐条证实/证伪）

| # | Lead 线索 | 判定 | 关键证据（文件:行） | 报告交叉引用 |
|---|---|---|---|---|
| 1 | Scheduler 只实现 sequential/random/random_activation；`parallel`/`simultaneous` 直接 ValueError | **证实** | `scheduler.py:14-26`；实测 `ValueError: Unknown scheduler method: parallel/simultaneous`（E12） | SC-1、SC-2 |
| 2 | Household 与成员同在 `env.agents`，sequential 下 Household 先 step → `total_income` 滞后一步；且无「家庭→成员」反馈 | **证实** | `environment.py:28-29`（插入序）+ `household.py:54-62` + `household.py:33-34`；实测 t=1 `0.0` vs 成员和 `0.113725`，t=2 恰为 t=1 的和（E4） | HH-1、RL-1 |
| 3 | `DEFAULT_PARAMS` 19 键；`:88` 读 `dt_months` 但该键不在 `DEFAULT_PARAMS`（靠 `_p` 的 default=1.0）；energy（121-148）未乘 `dt_months` | **证实（并修正行号范围）** | `family_member.py:10-30`（实测 `len==19`）、`:88`、`:98,118,151` vs `:129,142,147` | FM-7、PK/README 表 |
| 4 | 随机性来自全局 `random`，`Simulation` 无 `seed`，跨运行不可复现；web 多请求共享全局 RNG | **证实** | `family_member.py:48,52-56,86,110,119,130,142,147`、`relationships.py:17-21,32-34`、`scheduler.py:2,17-23`、`simulation.py:8-17`；全包 grep `random.seed|Random(|default_rng` 仅命中 `fitter.py:207`（scipy 内部 seed）与 `plots.py:219`（networkx 布局），**无一处为仿真链路播种** | FM-5、SC-3、RL-4 |
| 5 | 幸福用更新前的 `hp`；教育只削减年龄加速衰减，基础衰减不受影响 | **证实** | `family_member.py:114`（读 hp）→ `:120`（写 health）→ `:136`（happiness 仍用旧 hp）；`:115`（base_decay）与 `:116-118`（edu_protect 只乘 age_decay） | FM-6、FM-1 |
| 6 | `roles.py` 的 Role 体系与 `influence_weight` 在引擎中完全未被调用；`add_member` 传 `relation_type="member"` 而注册表只有 parent/child/adult/elder | **证实（并补一处词表冲突）** | `roles.py:5-59` 无实例化；`relationships.py:26-29` 无调用点；`household.py:22` 默认 `"member"` vs `roles.py:54-59`；另 `_role_at_age` 用的是 `preschool/…/student`（`family_member.py:68-73`）→ **三套词表互不相通** | RO-1、RL-2、HH-6 |
| 7 | `agent.py` 用 `state or {}` / `attributes or {}` 持有调用方同一个字典（别名共享，非拷贝） | **证实（附行为细节）** | `agent.py:14-15`；实测非空 dict `is` 同一对象、外部改写可见；**空 dict 会被 `or {}` 换成新对象**（「非空别名、空拷贝」的隐式分支）；`FamilyMember(**kwargs)`（`family_member.py:43`）同样透传别名 | AG-3、AG-1 |
| 附 | `Simulation.add_hook` 传 `self`，而 recorder 在 hook 之前调用，pre/post_step 语义是否自洽 | **证实不自洽** | `simulation.py:26-36`；实测 `post_step` 内 `current_step` 比 `env.time` 小 1（(0,1)/(1,2)/(2,3)），recorder 记录的 `env.properties` 恒为 `pre_step`，`post_step` 写入当步不可见 | SI-5 |

### 5.1 逐条补充说明

**线索 2 的数值与本次实测不同但不矛盾。** Lead 实测 step1 `成员 0.0236 / 家庭 0.0`、step2 `成员 0.1180 / 家庭 0.0236`；本次实测为 step1 `0.113725 / 0.000000`。差异只来自 RNG 流状态（成员年龄、`income` 的 `random.gauss` 抽样不同），**滞后关系完全相同**：`total_income(t) == Σ member_income(t-1)`，且 t=1 时家庭收入恒为 0.0。根因是注册顺序 + dict 插入序（`environment.py:28-29`、`household.py:33-34`），不是随机性。Lead 所述「环境里没有任何『家庭→成员』的反馈通道」也已独立证实：全仓库对 `relationships` 的读取只出现在 `household.step` 内部更新（`household.py:55`）、`web/app.py:235`、`viz/plots.py:211`（均为可视化/序列化），`total_income` 无任何消费者。

**线索 3 的行号修正。** `dt_months` 的应用点只有三处（`:98` 教育、`:118` 健康、`:151` 年龄）；未应用的三段是 stress `family_member.py:122-131`、happiness `:133-143`、energy `:145-148`（Lead 所写的 121-148 区间覆盖了这三段）。另外 `DEFAULT_PARAMS` 确实没有 `dt_months`（19 键实测），因此 `_p("dt_months", 1.0)` 恒为 1.0，除非调用方通过 `env.params` 注入——这与 `web/app.py:90` 的任意 `params` 透传结合，就能出现 FM-7 的量纲不一致（实测 `dt=12` 时 stress 0.3862 vs `dt=1`×12 步 0.6373）。

**线索 4 的 web 端放大效应。** `web/app.py:85-104` 每次 `POST /api/run` 只重建 `Environment`/`Members`，**从不调用任何播种函数**（全包仅 `fitter.py:207`、`plots.py:219` 出现 seed，且都不影响仿真链路）。因此同一进程内所有请求共享同一个全局 `random` 状态流：连续两次相同请求结果不同（E11），并且**第 N 次请求的结果取决于此前所有请求累计消耗的随机数**（顺序耦合）。补充说明：`/api/run` 是 `async def` 内同步跑完（`web/app.py:86,101`），会阻塞事件循环，因此单 worker 下请求实际串行——问题主要是「请求间共享 RNG 流」而非交错执行；一旦换成多 worker/线程池或把阻塞调用移出事件循环，还会叠加真正的交错不确定性。另建议该路由改为同步 `def`（FastAPI 会放入线程池）或 `run_in_threadpool`，避免阻塞健康检查与其它接口。

**线索 5 的量级提醒。** 「教育减缓健康衰减」在形式上成立（`edu_protect = 0.30*edu`，`family_member.py:117`），但 `base_decay=0.002` 不受教育影响，且 edu=0.5 时年龄项只被削减 15%；配合 FM-1 的失控量级（30 岁在 41.8 岁触底 0.01），教育保护在结果上不可观测。

**线索 6 的补强。** 除 Lead 指出的「`roles.py`/`influence_weight` 未被调用」「`relation_type='member'` 不在注册表」外，实测 `influence_weight` 两个方向返回完全相同（0.467293/0.467293，因 `power_dynamics` 恒为 0.5，`relationships.py:19,28`），`domain` 形参被完全忽略（`relationships.py:26`）；`FamilyMember.role` 是字符串且取值集合（`preschool/child/student/adult/elder`）与 `ROLE_REGISTRY`（`parent/child/adult/elder`）不同 → 共三套互不相通的角色词表。

**线索 附（钩子语义）的结论**：`pre_step` 语义自洽（看到本 tick 更新前状态，且 `current_step == env.time`）；`post_step` 不自洽——它与 `env.time` 差 1（`scheduler.py:32` 已在 recorder 之前自增，而 `simulation.py:36` 的 `current_step += 1` 在钩子之后），且 recorder 先于 `post_step`，导致 `post_step` 的写入当步不可见、对每步重算的状态（income/health/education 等）永远不可见。详见 SI-5。

---

## 附录 A：关键实测输出（可复现）

验证脚本（临时目录，均在仓库外创建；运行方式 `cd 仓库根; $env:PYTHONPATH=<仓库根>; python <脚本>`）：
`C:\Users\asus\AppData\Local\Temp\audit_core_family.py`、`audit_core_family2.py`、`audit_core_family3.py`、`audit_core_family4.py`、`audit_core_family5.py`。

- **HOOK**（`audit_core_family5.py`）`pre_step` 日志 `(current_step, env.time, age) = (0,0,30.0)/(1,1,30.083)/(2,2,30.167)`；`post_step` 日志 `(0,1,30.083)/(1,2,30.167)/(2,3,30.250)`；recorder 记录的 `env.properties` 3 个 tick 全为 `{'stage':'pre_step'}`；`post_step` 写入的 `income=12345` 在两 tick 记录中均未出现（记录值 0.0812/0.0823）。
- **AG-3** 同脚本：非空 dict 传入 → `a.attributes is shared_attr == True`，外部改写后 `{'k': 999}` 可见；空 dict 传入 → `b.attributes is empty == False`；`FamilyMember(attributes=d)` 后 `d["p"]=42` → `m.get_attribute("p") == 42`。

- **E9** `env.params={"income_age_spread":0.0}` + 1 步 → `ZeroDivisionError: division by zero`。
- **E10** `{"randomness": None}` → `TypeError`；`{"randomness":"abc"}` → `ValueError`；`{"randomness": nan}` → 无异常，`health=1.0 happiness=1.0 income=0.0`；`max(0.0,nan)=0.0`、`min(1.0,nan)=1.0`（CPython 实测）。
- **E4** t=1：`total_income=0.000000` vs 成员收入之和 `0.113725`；t=2：`0.113725` vs `0.110667` → 恰好滞后一步。
- **E5** 成员先加入、家户后注册 → `agents in env: 1`，成员未注册。
- **E6** `run(3)`→`reset()`→`run(3)`：记录时间 **[4,5,6]**（`scheduler.time` 未重置）。
- **E7** `sim.run(5)`→`env.step()`→`sim.step()`：`env.time` 从 6 回到 6（倒退）。
- **E3** 同 1 年：`dt=12`×1 步 → stress 0.3862 / happy 0.5912；`dt=1`×12 步 → stress 0.6373 / happy 0.4869（age 均为 31.00）。
- **E11** 同输入两次运行：happiness `0.415131` vs `0.383532`。
- **E12** `parallel`/`simultaneous` → `ValueError: Unknown scheduler method`；`Scheduler("totally_bogus")` 构造不报错。
- **E13** 4 成员：relationships key=12、唯一对象=6（=C(4,2)，去重正确）；`influence_weight` 两方向同值 0.467293；`domain` 参数无效；`remove_member` 后 key=6（正确）。
- **H1** 构造 role：0.5/3/10/17/100 岁全部 `'adult'`；0.2 岁婴儿首步收入 0.001606（role=adult）vs 0.001156（role=preschool）。
- **H2** 健康触底 0.01 的年龄：起始 20→34.6、30→41.8、40→50.3、50→58.2；月度损失 age=45 时 0.00774/月。
- **H3** 40 岁 10 年后：health=0.0108、stress=0.9900、income=0.1165、edu=0.5997、happiness=0.2542；目标各项 `{baseline 0.35, health 0.0022, income 0.0874, edu 0.06, stress −0.297}`。
- **H4** neuro 0.00/0.25/0.50/0.75/1.00 → 稳态 stress 0.8333/0.8958/0.9583/**1.0000**/**1.0000**（解析均衡 0.8333/0.8958/0.9583/1.0208/1.0833）。
- **H5** randomness=0 跑 200 步 → energy=`0.750000`（不动点 0.06/0.08），此时 stress=1.0、health=0.01。
- **F2** 同一状态幸福目标：全旧 0.47951 / 代码混合 0.56632 / 全新 0.55404。
- **F5** `run(3)` → 记录时间 [1,2,3]，无 t=0。
- **F8** 运行中改 `env.params={"education_rate":1.0}` → 下一步 edu 从 0.32698 → 0.65304（参数实时读取成立）。
- **性能** 2000 成员×200 步 = 6.59s（约 15 µs/agent-step，66.8k agent-steps/s）；cProfile：`_p` 1,957,535 次（cumtime 1.996s / 7.391s ≈27%）、`dict.get` 5,115,270 次、`update_dynamics` 450,000 次（O(n²)）。

## 附录 B：README 声称 API 的存在性与签名（实测 `inspect.signature`）

```
FamilyMember      (name='', age=25.0, gender='other', personality=None, role_name='adult', **kwargs)
Household         (household_id=None, name='Household', **kwargs)
Environment       (width=100, height=100)
Simulation        (environment, scheduler=None)
Scheduler         (method='sequential')
StateRecorder     (record_agents=True, record_environment=True)
Relationship      (agent_a_id, agent_b_id, relation_type='generic')
Role              (name, privileges=None, norms=None)
make_fitter       (model_name, state_mapping=None, **param_fix) -> ABMFitter
wellbeing_balance (t, y, p, q, r, s, income=0.5) -> list[float]
solve_model       (model_func, y0, t_eval, params) -> (np.ndarray, np.ndarray)
plot_timeseries   (df, state_columns=None, agent_id=None, title=..., figsize=(10,5), save_path=None)
plot_fit_diagnostics(df, fitter, agent_id=None, state_names=None, title=..., figsize=(12,4), save_path=None)
```
全部存在，均可从 `family_abm` 顶层导入；`Environment`/`Simulation`/`Scheduler` 的构造签名不含 `seed`/`params`（见 FM-5、EN-4）。

## 附录 C：审查边界与未确证项

- 本次未运行 `examples/fitting_viz_demo.py`、`examples/ml_ready.py`（会覆写 `examples/output/*.png`，属仓库文件）；`examples/simple_family.py` 只打印、已运行通过。
- `Household.step` 中 `set(...)` 的迭代顺序：**已实测两次独立进程顺序一致**，故只记为脆弱设计（HH-8，P3），**未**列为不确定性 bug。
- `_p` 对 `env.params` 的实时读取意味着「模型可在运行中改参数」——这是能力而非缺陷；缺陷在于缺少校验与稳定的公开参数入口。
- `web/`、`ml/`、`niche/`、`fitting/`、`viz/` 不在本次逐文件审查范围，仅在与 core/family 的耦合点（参数注入、时间轴、记录表、拟合 y0）处引用为证据。
