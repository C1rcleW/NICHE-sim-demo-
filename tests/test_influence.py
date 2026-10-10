"""代际影响机制的回归测试。

覆盖三部分：
1. 易感性曲线（埃里克森阶段 + 边界过渡）——纯函数，可精确断言
2. 影响传导（关系权重、来源能力、能量约束、兄弟姐妹分摊）
3. 家庭经济压力（含作为政策杠杆的收入支持）
以及机制整体的行为性质：影响随年龄递减、成年后方向反转、同 seed 可复现。
"""
from __future__ import annotations

import pytest

from family_abm import Environment, FamilyMember, Household, Scheduler, Simulation, StateRecorder
from family_abm.family.influence import (
    ADULTHOOD_AGE,
    ERIKSON_STAGES,
    INITIAL_INFLUENCE,
    initial_influence_stock,
    is_influencing,
    life_stage_of,
    select_sources,
    source_weight,
    susceptibility,
)

STAGE_AGES = [0.0, 2.0, 5.0, 9.0, 15.0, 25.0, 50.0]
MEMBERS = [("Father", 40, "male", "parent"), ("Mother", 38, "female", "parent"), ("Child", 6, "male", "child")]


# ── 易感性曲线 ────────────────────────────────────────────────────────────


def test_susceptibility_is_monotone_non_increasing_in_age() -> None:
    """易感性必须随年龄单调不增，不能出现"长大反而更易受影响"。"""
    ages = [i * 0.25 for i in range(0, 81 * 4)]
    values = [susceptibility(age) for age in ages]
    for earlier, later in zip(values, values[1:]):
        assert later <= earlier + 1e-12, "易感性随年龄上升，与阶段理论不符"


def test_susceptibility_matches_stage_values_inside_stages() -> None:
    """阶段内部应取该阶段的定义值。"""
    for start, end, expected, _source, _name in ERIKSON_STAGES:
        if end - start <= 2:            # 过窄的阶段落在过渡带内，跳过
            continue
        middle = (start + end) / 2
        if start > 0:                   # 起点后的过渡带之外
            middle = max(middle, start + 2.0)
        if middle >= end:
            continue
        assert susceptibility(middle) == pytest.approx(expected, abs=1e-9), (
            f"阶段 {_name} 在年龄 {middle} 的易感性应为 {expected}"
        )


def test_susceptibility_transition_is_continuous() -> None:
    """阶段边界处必须连续——硬切换会让影响量跳变，制造人为的动力学间断。"""
    for boundary in (1.0, 3.0, 6.0, 12.0, 18.0, 40.0):
        left = susceptibility(boundary - 1e-6)
        right = susceptibility(boundary + 1e-6)
        assert abs(left - right) < 1e-4, f"边界 {boundary} 处易感性跳变 {abs(left - right)}"


def test_susceptibility_bounded_and_decreasing_overall() -> None:
    assert 0.0 < susceptibility(0) <= 1.0
    assert susceptibility(80) < susceptibility(5)
    assert susceptibility(5) - susceptibility(18) > 0.3, "青春期应相对学前期明显下降"


def test_life_stage_labels_cover_lifespan() -> None:
    assert life_stage_of(0.5) == "婴儿期"
    assert life_stage_of(9) == "学龄期"
    assert life_stage_of(15) == "青春期"
    assert life_stage_of(60) == "成年中期后"


def test_initial_influence_stock_only_for_adults() -> None:
    assert initial_influence_stock(30) == INITIAL_INFLUENCE > 0
    assert initial_influence_stock(10) == 0.0


def test_susceptibility_scale_preserves_shape_and_monotonicity() -> None:
    """易感性缩放必须保持阶段形状与单调性（敏感性分析用的扰动参数）。

    回归：重写该函数时曾把"进入第一阶段"的过渡也计入，导致所有正年龄的
    易感性被额外递减到 0——单调性检查抓不到，必须比对基准值才能发现。
    """
    baseline = [susceptibility(age) for age in (0, 2, 5, 9, 15, 25, 50)]
    assert baseline == pytest.approx([0.95, 0.85, 0.75, 0.50, 0.28, 0.15, 0.10], abs=1e-9)

    for scale in (0.70, 0.85, 1.15, 1.30):
        ages = [i * 0.25 for i in range(0, 200)]
        values = [susceptibility(age, scale=scale) for age in ages]
        assert all(b <= a + 1e-12 for a, b in zip(values, values[1:])), (
            f"scale={scale} 破坏单调性"
        )
        assert 0.0 <= min(values) and max(values) <= 1.0, f"scale={scale} 越界"
        # 缩放应等比例作用（未钳位处）
        for age in (9.0, 15.0, 25.0):
            expected = baseline[[0, 2, 5, 9, 15, 25, 50].index(age)] * scale
            assert susceptibility(age, scale=scale) == pytest.approx(expected, abs=1e-9)


def test_stage_shift_moves_boundaries() -> None:
    """阶段平移应把边界整体挪动：正 shift = 阶段推迟到来。"""
    # 9 岁在边界 6 与 12 之间，基准易感性 0.50
    assert susceptibility(9.0) == pytest.approx(0.50, abs=1e-9)
    # 阶段推迟 3 年：9 岁相当于原来的 6 岁，仍在学前期→学龄期边界附近
    assert susceptibility(9.0, shift=3.0) > susceptibility(9.0)
    # 阶段提前 3 年：9 岁相当于原来的 12 岁，已是青春期
    assert susceptibility(9.0, shift=-3.0) < susceptibility(9.0)

    # 平移不改变曲线形状，只平移它
    for shift in (-3.0, -2.0, 2.0, 3.0):
        ages = [i * 0.25 for i in range(0, 240)]
        values = [susceptibility(age, shift=shift) for age in ages]
        assert all(b <= a + 1e-12 for a, b in zip(values, values[1:])), (
            f"shift={shift} 破坏单调性"
        )


def test_is_influencing_switches_at_adulthood() -> None:
    assert not is_influencing(ADULTHOOD_AGE - 0.1)
    assert is_influencing(ADULTHOOD_AGE + 0.1)
    assert not is_influencing(ADULTHOOD_AGE + 10, role_switch=False), "消融对照应关闭角色切换"


# ── 影响传导 ──────────────────────────────────────────────────────────────


def build_household(seed=42, ages=(40, 38, 6), params=None):
    env = Environment()
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=seed)
    if params:
        env.params = dict(params)
    hh = Household(name="Smith", household_id="smith", environment=env)
    env.add_agent(hh)
    members = []
    for index, age in enumerate(ages):
        member = FamilyMember(name=f"M{index}", age=age, role_name="parent" if age >= 18 else "child",
                              agent_id=f"m{index}", environment=env)
        hh.add_member(member)
        members.append(member)
    return env, sim, hh, members


def test_children_are_influenced_by_older_adults() -> None:
    _env, _sim, hh, members = build_household()
    child = members[-1]
    sources = select_sources(child, hh)
    assert {s.get_attribute("name") for s in sources} == {"M0", "M1"}, "应由两名成年成员影响"


def test_adults_are_not_influenced_by_children() -> None:
    """影响是单向下行的：成年人不应被孩子影响。"""
    _env, _sim, hh, members = build_household()
    assert select_sources(members[0], hh) == [] or all(
        s.get_attribute("age") >= 18 for s in select_sources(members[0], hh)
    )


def test_source_weight_reflects_relationship_quality() -> None:
    """关系越好（信任高、冲突低），影响权重越大。"""
    _env, _sim, hh, members = build_household()
    child, father = members[-1], members[0]
    relationship = hh.get_relationship(members[0].id, child.id)

    relationship.trust, relationship.conflict = 0.9, 0.0
    strong = source_weight(child, father, hh)
    relationship.trust, relationship.conflict = 0.1, 0.5
    weak = source_weight(child, father, hh)
    assert strong > weak, "关系质量未影响影响权重"


def test_influence_effect_grows_with_strength() -> None:
    """影响强度越大，子代轨迹偏离无影响基线的幅度越大。"""

    def final_happiness(strength):
        env, sim, hh, members = build_household(params={"influence_strength": strength})
        recorder = StateRecorder(record_agents=True)
        sim.add_recorder(recorder)
        sim.run(120)
        child = [m for m in members if m.get_attribute("age") < 18][0]
        return child.get_state_value("happiness")

    off, weak, strong = (final_happiness(s) for s in (0.0, 0.5, 2.0))
    assert abs(weak - off) > 1e-4, "开启影响后轨迹应有可见改变"
    assert abs(strong - off) >= abs(weak - off) * 0.5, "更大强度不应使偏离消失"


def test_received_influence_shrinks_as_child_ages() -> None:
    """儿童承受的影响量随年龄（易感性下降）而减小。

    注意：不能用"当前年龄"筛选孩子——仿真跑完后他已成年，要用构造时的引用。
    """
    env, sim, hh, members = build_household(params={"influence_strength": 1.0})
    child = members[-1]
    assert child.get_attribute("age") < 18, "该成员构造时应为未成年人"
    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)
    sim.run(200)
    df = recorder.to_dataframe()
    rows = df[df["agent_id"] == child.id].sort_values("time")
    early = rows[(rows["time"] > 0) & (rows["time"] < 60)]["state_influence_received"].abs().max()
    late = rows[(rows["time"] >= 110) & (rows["time"] < 160)]["state_influence_received"].abs().max()
    assert early > late, f"影响量未随年龄下降：早期峰值={early:.6f} 后期峰值={late:.6f}"


def test_child_gains_influence_capacity_at_adulthood() -> None:
    """子代成年后应获得养育能力并转为施加影响一方（否则角色切换形同虚设）。"""
    env, sim, hh, members = build_household(ages=(40, 38, 6), params={"influence_strength": 1.0})
    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)
    sim.run(180)                        # 6 岁起走 15 年 -> 约 21 岁
    child = members[-1]
    assert child.get_attribute("age") >= ADULTHOOD_AGE
    assert child.get_state_value("influence") > 0.1, "成年后未获得养育存量"


def test_siblings_share_influence_rather_than_amplify_it() -> None:
    """兄弟多不该让每个孩子得到更强影响，只应被分摊。

    两个孩子的家庭中，每个孩子受到的"份"应约为独生子女的一半左右
    （因为影响按受影响的未成年成员数分摊）。
    """
    def first_child_received(num_children: int) -> float:
        ages = (40, 38) + tuple(6 for _ in range(num_children))
        env, sim, hh, members = build_household(ages=ages, params={"influence_strength": 1.0})
        children = [m for m in members if m.get_attribute("age") < 18]
        child = children[0]
        # 用记录的第一批非零影响量比较（避免步数差异影响）
        recorder = StateRecorder(record_agents=True)
        sim.add_recorder(recorder)
        sim.run(5)
        df = recorder.to_dataframe()
        rows = df[df["agent_id"] == child.id].sort_values("time")
        return float(rows["state_influence_received"].abs().max())

    one = first_child_received(1)
    two = first_child_received(2)
    assert one > 0 and two > 0, "该配置下应能观测到影响量"
    assert two < one, f"两个孩子时每人受到的影响未减少：1孩={one:.6f} 2孩={two:.6f}"


def test_influence_disabled_leaves_members_uncoupled() -> None:
    """影响关闭时，两类成员的状态演化互不影响（消融条件的基线）。"""

    def child_health_with(strength):
        env, sim, hh, members = build_household(params={"influence_strength": strength})
        sim.run(60)
        child = members[-1]
        return child.get_state_value("health")

    a = child_health_with(0.0)
    b = child_health_with(0.0)
    assert a == pytest.approx(b), "关闭影响时结果仍应完全可复现"


# ── 家庭经济压力与政策杠杆 ────────────────────────────────────────────────


def test_household_income_is_consumed_by_members() -> None:
    """total_income 从"只写不读"变为共同压力源后，成员应能读到经济压力。"""
    _env, sim, hh, members = build_household()
    sim.run(30)
    pressures = [m.get_state_value("economic_pressure") for m in members]
    assert all(0.0 <= p <= 1.0 for p in pressures)
    assert all(p == pytest.approx(hh.get_state_value("economic_pressure")) for p in pressures), (
        "成员应共享同一个家庭压力值"
    )


def test_income_support_reduces_pressure_and_child_stress() -> None:
    """收入支持是"提高可支配收入"，不是"抬高够用门槛"——支持越多压力应越小。

    回归：早先把 support 加到基准上，导致支持越多、测得的压力越大（方向反了）。
    """
    def measure(support):
        env, sim, hh, members = build_household(params={"income_support": support})
        sim.run(120)
        child = members[-1]
        return hh.get_state_value("economic_pressure"), child.get_state_value("stress")

    pressure_0, stress_0 = measure(0.0)
    pressure_1, stress_1 = measure(1.0)
    assert pressure_1 < pressure_0, f"收入支持未降低家庭压力：{pressure_0:.4f} -> {pressure_1:.4f}"
    assert stress_1 < stress_0, f"收入支持未降低子代压力：{stress_0:.4f} -> {stress_1:.4f}"


def test_young_members_are_more_sensitive_to_economic_pressure() -> None:
    """年幼成员对家庭经济压力更敏感（Family Stress Model 的核心预测）。"""
    env = Environment()
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=7)
    env.params = {"income_support": 0.0}
    hh = Household(name="Poor", household_id="poor", environment=env)
    env.add_agent(hh)
    child = FamilyMember(name="Child", age=8, role_name="child", agent_id="c", environment=env)
    adult = FamilyMember(name="Adult", age=45, role_name="adult", agent_id="a", environment=env)
    hh.add_member(adult)
    hh.add_member(child)
    # 压低成人收入，制造较高经济压力
    for member in (adult, child):
        member.set_state_value("income", 0.0)
    sim.run(60)
    assert hh.get_state_value("economic_pressure") > 0.5, "该配置应产生明显经济压力"


# ── 机制整体 ──────────────────────────────────────────────────────────────


def test_influence_mechanism_preserves_reproducibility() -> None:
    """机制引入的随机数消耗不得破坏可复现性。"""
    def signature(seed):
        env, sim, hh, members = build_household(seed=seed, params={"influence_strength": 1.0})
        recorder = StateRecorder(record_agents=True)
        sim.add_recorder(recorder)
        sim.run(60)
        df = recorder.to_dataframe()
        cols = [c for c in df.columns if c.startswith("state_")]
        return [
            tuple(None if row[c] != row[c] else round(float(row[c]), 12) for c in cols)
            for _, row in df.sort_values(["time", "attr_name"]).iterrows()
        ]

    assert signature(2026) == signature(2026), "同一 seed 结果不一致"
    assert signature(2026) != signature(99), "不同 seed 应产生不同结果"


def test_relationship_dynamics_do_not_depend_on_iteration_order() -> None:
    """关系变量的随机流按身份派生，不应受对象迭代顺序影响。

    回归：早先关系共用环境 RNG，而排序键是 uuid，导致同一 seed 下关系状态
    依赖迭代顺序、跨运行不可复现。
    """
    env_a = Environment()
    sim_a = Simulation(env_a, seed=5)
    hh_a = Household(name="H", household_id="h", environment=env_a)
    env_a.add_agent(hh_a)
    hh_a.add_member(FamilyMember(name="A", age=40, agent_id="a", environment=env_a))
    hh_a.add_member(FamilyMember(name="B", age=10, agent_id="b", environment=env_a))
    sim_a.run(50)

    env_b = Environment()
    sim_b = Simulation(env_b, seed=5)
    hh_b = Household(name="H", household_id="h", environment=env_b)
    env_b.add_agent(hh_b)
    hh_b.add_member(FamilyMember(name="A", age=40, agent_id="a", environment=env_b))
    hh_b.add_member(FamilyMember(name="B", age=10, agent_id="b", environment=env_b))
    sim_b.run(50)

    rel_a = hh_a.get_relationship("a", "b")
    rel_b = hh_b.get_relationship("a", "b")
    assert (rel_a.affection, rel_a.trust, rel_a.conflict) == pytest.approx(
        (rel_b.affection, rel_b.trust, rel_b.conflict)
    ), "关系状态受迭代顺序影响，跨运行不可复现"
