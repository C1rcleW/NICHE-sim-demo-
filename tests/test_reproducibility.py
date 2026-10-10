"""可复现性与校准的回归测试。

这两件事此前都是缺失的：
- 仿真完全没有种子入口，同一份输入跑两次结果不同 → 研究结论不可信
- 健康衰减是真实人类衰老速度的 20–30 倍，10 年就把健康打到下限 0.01；
  压力平衡点 > 1 被钳位饱和，神经质人格在高区间完全失效
"""
from __future__ import annotations

import random

from family_abm import Environment, FamilyMember, Household, Scheduler, Simulation, StateRecorder
from family_abm.family.family_member import DEFAULT_PARAMS

FAMILIES = [
    ("Smith", [("Father", 40, "male", "parent"), ("Mother", 38, "female", "parent"), ("Child", 10, "male", "child")]),
    ("Jones", [("Mom", 35, "female", "parent"), ("Daughter", 8, "female", "child")]),
]
STATE_COLS = ["state_health", "state_stress", "state_happiness", "state_income", "state_education", "state_energy"]


def build(seed=None, steps=120):
    """按推荐顺序构建：先注入 RNG，再建智能体（含 environment）。"""
    env = Environment()
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=seed)
    for name, members in FAMILIES:
        hh = Household(name=name, environment=env)
        env.add_agent(hh)
        for n, a, g, r in members:
            hh.add_member(FamilyMember(name=n, age=a, gender=g, role_name=r, environment=env))
    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)
    sim.run(steps)
    return recorder.to_dataframe()


def signature(df):
    """与 uuid 无关的确定性签名：按 (time, attr_name) 对齐后取状态列。"""
    ordered = df.sort_values(["time", "attr_name"]).reset_index(drop=True)
    rows = []
    for _, row in ordered.iterrows():
        values = tuple(None if row[c] != row[c] else round(float(row[c]), 12) for c in STATE_COLS)
        rows.append((int(row["time"]), str(row["agent_type"]), str(row.get("attr_name")), *values))
    return rows


# ── 可复现性 ──────────────────────────────────────────────────────────────


def test_same_seed_gives_identical_trajectories() -> None:
    """同一 seed 的运行必须逐点一致（含 t=0 的初始化状态）。"""
    a, b, c = (signature(build(seed=2026)) for _ in range(3))
    assert a == b == c, "同一 seed 的仿真结果不可复现"


def test_different_seed_gives_different_trajectories() -> None:
    a = signature(build(seed=1))
    b = signature(build(seed=2))
    assert a != b, "不同 seed 应产生不同结果"


def test_reproducibility_is_independent_of_global_rng() -> None:
    """注入的 RNG 必须与全局 random 隔离。

    否则调用方在别处使用 random 就会污染仿真结果——这正是此前不可复现的根因之一。
    """
    random.seed(11111)
    a = signature(build(seed=2026))
    random.seed(99999)
    random.random()
    b = signature(build(seed=2026))
    assert a == b, "仿真结果受全局 random 状态影响"


def test_seed_isolation_does_not_perturb_global_rng() -> None:
    """反过来，仿真也不应推进全局 random（避免影响调用方）。"""
    random.seed(7)
    expected = [random.random() for _ in range(3)]

    random.seed(7)
    build(seed=2026)
    actual = [random.random() for _ in range(3)]
    assert actual == expected, "仿真消耗了全局 random，会干扰调用方"


def test_t0_state_is_reproducible() -> None:
    """t=0 的初始状态也必须可复现（成员初始化要用注入的 RNG）。

    注意：Household 行没有成员状态列，取值是 NaN，而 NaN != NaN，
    因此在构造签名时必须先把 NaN 规整为 None，否则比较恒为 False。
    """
    def t0(seed):
        df = build(seed=seed, steps=1)
        first = df[df["time"] == 0].sort_values("attr_name")
        rows = []
        for row in first[STATE_COLS].values:
            rows.append(tuple(None if v != v else round(float(v), 12) for v in row))
        return rows

    assert t0(2026) == t0(2026)
    assert t0(2026) != t0(99)


def test_without_seed_falls_back_to_global_random() -> None:
    """不给 seed 时保持旧行为（依赖全局 random），但显式播种后仍可复现。"""
    random.seed(5)
    a = signature(build(seed=None, steps=40))
    random.seed(5)
    b = signature(build(seed=None, steps=40))
    assert a == b, "无 seed 时显式播种全局 random 也应可复现"


# ── 校准 ──────────────────────────────────────────────────────────────────


def test_health_stays_informative_over_long_simulation() -> None:
    """健康不应在仿真尺度内触底：长仿真里仍要有区分度。

    回归：旧参数在 40 岁时约 7.8%/年衰减，约 10 年就把健康压到下限 0.01。
    """
    df = build(seed=42, steps=600)          # 600 个月 = 50 年
    health = df[(df["agent_type"] == "FamilyMember") & (df["time"] == 600)]["state_health"]
    assert health.min() > 0.2, f"50 年后健康已退化到 {health.min():.4f}，失去区分度"
    assert health.std() > 0.0, "个体健康应存在差异"

    # 40 岁成年人在 10 年后不应触底
    father = df[(df["attr_name"] == "Father")].sort_values("time")
    at_120 = father[father["time"] == 120]["state_health"].iloc[0]
    assert at_120 > 0.5, f"40 岁成年人 10 年后健康仅 {at_120:.4f}"


def test_health_decays_slowly_and_monotonically_in_expectation() -> None:
    """健康应缓慢下降，而不是断崖式下跌。"""
    df = build(seed=42, steps=240)
    father = df[df["attr_name"] == "Father"].sort_values("time")
    t0 = father[father["time"] == 0]["state_health"].iloc[0]
    t240 = father[father["time"] == 240]["state_health"].iloc[0]
    decline = t0 - t240
    # 20 年下降幅度应在合理区间（不是 10 年归零）
    assert 0.01 < decline < 0.5, f"20 年健康变化 {decline:.4f}，量级不合理"


def test_stress_does_not_saturate() -> None:
    """压力不应长期贴在上限：旧参数平衡点 > 1，整个仿真都在饱和区。"""
    df = build(seed=42, steps=600)
    stress = df[(df["agent_type"] == "FamilyMember")]["state_stress"]
    assert stress.max() < 0.95, f"压力达到 {stress.max():.4f}，已进入饱和区"

    tail = df[(df["agent_type"] == "FamilyMember") & (df["time"] >= 500)]["state_stress"]
    assert tail.mean() < 0.7, f"后段平均压力 {tail.mean():.4f} 偏高"


def test_neuroticism_is_effective_across_full_range() -> None:
    """神经质人格在整个 [0,1] 区间都应产生可分辨的差异（不再被钳位抹平）。"""
    means = []
    for neuro in (0.0, 0.25, 0.5, 0.75, 1.0):
        env = Environment()
        sim = Simulation(env, scheduler=Scheduler("sequential"), seed=7)
        hh = Household(name="H", environment=env)
        env.add_agent(hh)
        personality = {k: 0.5 for k in
                       ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")}
        personality["neuroticism"] = neuro
        hh.add_member(FamilyMember(name="X", age=40, role_name="parent",
                                   personality=personality, environment=env))
        sim.run(300)
        means.append(hh.members[list(hh.members)[0]].get_state_value("stress"))

    assert means == sorted(means), f"稳态压力未随神经质单调增加：{means}"
    assert means[-1] - means[0] > 0.02, f"神经质的影响过小，几乎不可分辨：{means}"
    assert len(set(round(m, 6) for m in means)) == len(means), f"存在被钳位抹平的取值：{means}"


def test_education_protects_total_health_decay() -> None:
    """教育保护必须作用在总衰减上（旧实现只乘在年龄项，教育几乎无作用）。"""
    def end_health(education_hint: float, seed: int = 3) -> float:
        env = Environment()
        sim = Simulation(env, scheduler=Scheduler("sequential"), seed=seed)
        hh = Household(name="H", environment=env)
        env.add_agent(hh)
        m = FamilyMember(name="X", age=50, role_name="adult", environment=env)
        hh.add_member(m)
        m.set_state_value("education", education_hint)
        # 每步把教育固定在目标水平，隔离"教育本身会变化"的干扰
        original_step = m.step

        def step_with_fixed_education():
            original_step()
            m.set_state_value("education", education_hint)

        m.step = step_with_fixed_education
        sim.run(120)
        return m.get_state_value("health")

    low = end_health(0.0)
    high = end_health(1.0)
    assert high > low + 0.01, f"高教育未减缓健康衰减（低={low:.4f}，高={high:.4f}）"


def test_parameters_still_exposed_and_typed() -> None:
    """校准只应改数值/命名，不应改变参数个数与类型。"""
    assert len(DEFAULT_PARAMS) == 19
    assert all(isinstance(v, (int, float)) for v in DEFAULT_PARAMS.values())
    for key in ("health_floor", "health_decay_rate", "health_edu_protection",
                "stress_base", "stress_work_add"):
        assert key in DEFAULT_PARAMS
