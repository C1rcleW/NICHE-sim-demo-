"""阶段 B 验收测试：记录 t=0 基线 + 拟合输入显式化。

回归对象：
- P1-5：`Simulation` 先 step 后 record，导致时间轴只有 [1..n]，拟合器把
  "走完第一步后的状态"当成 t=0 初值，整条轨迹相差一步。
- P1-3：`/api/fit` 在列名不匹配时把 O1/O2/R1/R2 静默映射到任意前 N 个 state_ 列，
  把模型拟到无关列（甚至方差为 0 的列）上并返回看似合理的 R²。
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from family_abm import Environment, FamilyMember, Household, Scheduler, Simulation, StateRecorder
from family_abm.fitting.fitter import ABMFitter, make_fitter
from family_abm.fitting.lanchester import MODEL_PARAM_NAMES, MODEL_REGISTRY, MODEL_STATE_NAMES

STEPS = 15


def _seed(value: int = 20260101) -> None:
    random.seed(value)
    np.random.seed(value)


def build_recorder(*, record_initial: bool, steps: int = STEPS) -> tuple[StateRecorder, Simulation]:
    _seed()
    env = Environment()
    household = Household(name="Smith Household")
    env.add_agent(household)
    household.add_member(FamilyMember(name="Father", age=40, gender="male", role_name="parent"))
    household.add_member(FamilyMember(name="Child", age=10, gender="male", role_name="child"))

    recorder = StateRecorder(record_agents=True)
    sim = Simulation(env, scheduler=Scheduler("sequential"), record_initial=record_initial)
    sim.add_recorder(recorder)
    sim.run(steps)
    return recorder, sim


# ── P1-5：t=0 基线 ────────────────────────────────────────────────────────


def test_records_t0_baseline_by_default() -> None:
    recorder, sim = build_recorder(record_initial=True)
    df = recorder.to_dataframe()
    assert sorted(df["time"].unique()) == list(range(0, STEPS + 1)), "时间轴应为 [0..steps]"
    assert len(df) == (STEPS + 1) * 3, "每个时间点应记录 1 个 Household + 2 个成员"
    assert sim.current_step == STEPS


def test_t0_row_equals_initial_agent_state() -> None:
    """t=0 那一行必须是"未被步进过"的初始状态，而不是第一步之后的状态。"""
    _seed()
    env = Environment()
    household = Household(name="Smith Household")
    env.add_agent(household)
    member = FamilyMember(name="Father", age=40, gender="male", role_name="parent")
    household.add_member(member)

    before = {k: v for k, v in member.get_state()["state"].items()}
    recorder = StateRecorder(record_agents=True)
    sim = Simulation(env, scheduler=Scheduler("sequential"), record_initial=True)
    sim.add_recorder(recorder)
    sim.run(1)

    df = recorder.to_dataframe()
    row = df[(df["time"] == 0) & (df["agent_id"] == member.id)].iloc[0]
    for key, value in before.items():
        assert row[f"state_{key}"] == pytest.approx(value), f"t=0 的 {key} 应等于步进前的初始值"

    # 反向验证：t=1 的状态必须已经变化，否则说明 t=0 记录的是步进后的状态
    row1 = df[(df["time"] == 1) & (df["agent_id"] == member.id)].iloc[0]
    assert row1["state_education"] != pytest.approx(before["education"]), "第一步后教育应发生变化"


def test_record_initial_can_be_disabled() -> None:
    recorder, sim = build_recorder(record_initial=False)
    df = recorder.to_dataframe()
    assert sorted(df["time"].unique()) == list(range(1, STEPS + 1)), "关闭后时间轴应为 [1..steps]"
    assert len(df) == STEPS * 3


def test_reset_re_records_baseline() -> None:
    """reset() 之后应重新记录一次基线行。

    注意：本阶段**不**修复 reset 的完整语义——`Scheduler` 内部时钟没有重置，
    所以后续时间轴会接着往下走（下面断言用 >= 表达）。完整的重跑语义（时钟统一
    + 状态回滚）属于计划中的 P2-3，届时本测试的 `>=` 会收紧为 `== [0, 1, 2]`。
    """
    recorder, sim = build_recorder(record_initial=True)
    sim.reset()
    assert sim.current_step == 0
    sim.run(2)
    df = recorder.to_dataframe()
    assert (df["time"] == 0).any(), "reset 后应重新出现基线行"
    assert sorted(df["time"].unique())[0] == 0
    assert len(df[df["time"] == 0]) == 3, "基线行应重新记录每个 agent"
    # 已知问题 P2-3：时间轴不会从 1 重新开始
    assert max(df["time"]) >= 2


def test_formatter_error_message_is_actionable() -> None:
    _seed()
    env = Environment()
    household = Household(name="H")
    env.add_agent(household)
    household.add_member(FamilyMember(name="A", age=40, role_name="parent"))
    recorder = StateRecorder(record_agents=True)
    sim = Simulation(env, scheduler=Scheduler("sequential"))
    sim.add_recorder(recorder)
    sim.run(10)
    df = recorder.to_dataframe()

    fitter = make_fitter("influence")  # 状态为 O1/O2，与 ABM 列名无对应关系
    with pytest.raises(ValueError) as excinfo:
        fitter.fit_from_dataframe(df)
    message = str(excinfo.value)
    assert "state_mapping" in message, "错误信息应给出修正方式"
    assert "state_happiness" in message, "错误信息应列出可用的状态列"


# ── P1-3：拟合输入显式化 ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def sim_df() -> pd.DataFrame:
    recorder, _ = build_recorder(record_initial=True, steps=40)
    return recorder.to_dataframe()


def test_abstract_model_does_not_silently_pick_arbitrary_columns(sim_df: pd.DataFrame) -> None:
    """抽象状态名不得被静默映射：默认约定找不到列时必须报错。"""
    for model_name in ("square_law", "linear_law", "influence", "logistic", "lotka_volterra", "resource_competition"):
        fitter = make_fitter(model_name)
        with pytest.raises(ValueError):
            fitter.fit_from_dataframe(sim_df)


def test_default_naming_still_works(sim_df: pd.DataFrame) -> None:
    """wellbeing 的状态名 happiness/stress 能对上 state_happiness/state_stress，应正常拟合。"""
    fitter = make_fitter("wellbeing")
    fitter.fit_from_dataframe(sim_df)
    assert fitter.resolve_state_columns(sim_df) == {"happiness": "state_happiness", "stress": "state_stress"}
    assert fitter.r_squared is not None


def test_explicit_mapping_is_honoured(sim_df: pd.DataFrame) -> None:
    mapping = {"R1": "state_happiness", "R2": "state_stress"}
    fitter = make_fitter("square_law", state_mapping=mapping)
    resolved = fitter.resolve_state_columns(sim_df)
    assert resolved == mapping


def test_duplicate_mapping_rejected(sim_df: pd.DataFrame) -> None:
    fitter = make_fitter("square_law", state_mapping={"R1": "state_happiness", "R2": "state_happiness"})
    with pytest.raises(ValueError, match="重复映射"):
        fitter.resolve_state_columns(sim_df)


def test_unknown_agent_id_reports_available_ids(sim_df: pd.DataFrame) -> None:
    fitter = make_fitter("wellbeing")
    with pytest.raises(ValueError) as excinfo:
        fitter.fit_from_dataframe(sim_df, agent_id="not-an-agent")
    assert "not-an-agent" in str(excinfo.value)


def test_long_horizon_fit_does_not_crash_on_bounds() -> None:
    """长积分窗口（steps>=120）必须能拟合。

    回归：scipy 的 L-BFGS-B 有限差分 eps 是绝对步长，时间轴横跨 [0,120] 时扰动点
    会漂出参数边界，抛 ``ValueError: `x0` violates bound constraints``。
    修复方式是把积分时间轴缩放到单位长度（见 fitter._integration_scale）。
    """
    recorder, _ = build_recorder(record_initial=True, steps=120)
    df = recorder.to_dataframe()
    fitter = make_fitter("wellbeing")
    result = fitter.fit_from_dataframe(df)  # 修复前此处抛 ValueError
    assert result.success
    assert fitter.r_squared is not None


def test_integration_scale_only_kicks_in_for_long_windows() -> None:
    """缩放阈值：跨度 <= 2 时不做缩放；更长窗口按跨度归一。"""
    tiny = np.array([0.0, 1.0, 2.0])
    assert ABMFitter._integration_scale(tiny) == pytest.approx(1.0)

    long = np.arange(0.0, 120.0, 1.0)
    assert ABMFitter._integration_scale(long) == pytest.approx(119.0)

    # 跨度为 0 的退化输入不应除零
    assert ABMFitter._integration_scale(np.array([5.0, 5.0, 5.0])) == pytest.approx(1.0)


def test_web_fit_returns_400_with_hint_for_unmappable_model(sim_df: pd.DataFrame) -> None:
    """Web 端点对无法映射的模型返回 400（而不是 500 或伪成功）。"""
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from family_abm.web.app import app as web_app

    client = fastapi_testclient.TestClient(web_app)
    assert client.post("/api/run", json={"steps": 30}).status_code == 200

    bad = client.post("/api/fit", json={"model_name": "square_law", "robust": False})
    assert bad.status_code == 400, bad.text
    assert "state_mapping" in bad.json()["error"]

    good = client.post("/api/fit", json={"model_name": "wellbeing", "robust": False})
    assert good.status_code == 200, good.text
