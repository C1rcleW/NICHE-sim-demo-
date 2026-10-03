"""阶段 C 验收测试：数据契约（NaN 语义）与拟合失败的上报诚实性。

回归对象：
- P1-4：API 层 `fillna(0)` 把"该 agent 没有这个状态"伪造成数值 0，
  使前端聚合比真实值低约 28.6%，并与 fitter 使用的 NaN 跳过均值不是同一序列。
- P1-1：`r_squared = max(0.0, ...)` 把负 R² 抹成 0，而 `converged` 又要求 R²>0，
  导致"拟合失败"与"拟合极差"不可区分。
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from family_abm import Environment, FamilyMember, Household, Scheduler, Simulation, StateRecorder
from family_abm.fitting.fitter import make_fitter

STEPS = 30


def _seed(value: int = 424242) -> None:
    random.seed(value)
    np.random.seed(value)


def build_df(*, steps: int = STEPS) -> pd.DataFrame:
    _seed()
    env = Environment()
    household = Household(name="Smith Household")
    env.add_agent(household)
    household.add_member(FamilyMember(name="Father", age=40, gender="male", role_name="parent"))
    household.add_member(FamilyMember(name="Child", age=10, gender="male", role_name="child"))

    recorder = StateRecorder(record_agents=True)
    sim = Simulation(env, scheduler=Scheduler("sequential"), record_initial=True)
    sim.add_recorder(recorder)
    sim.run(steps)
    return recorder.to_dataframe()


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return build_df()


# ── P1-4：NaN 语义 ────────────────────────────────────────────────────────


def test_to_dataframe_preserves_nan_instead_of_filling_zero(raw_df: pd.DataFrame) -> None:
    """宽表必须保留 NaN：Household 没有成员状态列，成员没有 Household 状态列。"""
    household_rows = raw_df[raw_df["agent_type"] == "Household"]
    member_rows = raw_df[raw_df["agent_type"] == "FamilyMember"]

    assert household_rows["state_happiness"].isna().all(), "Household 不应有 state_happiness"
    assert member_rows["state_total_income"].isna().all(), "成员不应有 state_total_income"
    # 关键反例：不得出现"被填成 0"
    assert (household_rows["state_happiness"].fillna(-1) == -1).all()
    assert not (household_rows["state_happiness"] == 0).any()
    assert not (member_rows["state_total_income"] == 0).any()


def test_aggregate_is_computed_on_the_right_subset(raw_df: pd.DataFrame) -> None:
    """逐列均值只能在拥有该列的 agent 子集上聚合（这正是 fitter 依赖的语义）。"""
    at_time = raw_df[raw_df["time"] == 5]
    member_mean = at_time[at_time["agent_type"] == "FamilyMember"]["state_happiness"].mean()
    pooled = at_time["state_happiness"].mean()
    assert pooled == pytest.approx(member_mean), "pandas 应跳过 NaN 而不是当成 0"

    polluted = at_time["state_happiness"].fillna(0).mean()
    assert polluted < member_mean, "若按旧 API 的 fillna(0)，均值会被 Household 行拖低"


def test_statistics_dataframe_is_grouped_and_drops_missing(raw_df: pd.DataFrame) -> None:
    recorder_columns = {"agent_type", "column", "n", "mean", "std", "min", "max"}

    _seed()
    env = Environment()
    household = Household(name="H")
    env.add_agent(household)
    household.add_member(FamilyMember(name="A", age=40, role_name="parent"))
    recorder = StateRecorder(record_agents=True)
    sim = Simulation(env, scheduler=Scheduler("sequential"))
    sim.add_recorder(recorder)
    sim.run(5)

    stats = recorder.to_statistics_dataframe()
    assert set(stats.columns) == recorder_columns
    assert set(stats["agent_type"]) == {"FamilyMember", "Household"}
    assert not stats.isna().any().any(), "统计视图不应含 NaN（缺失值被丢弃而非填 0）"

    member_happiness = stats[(stats["agent_type"] == "FamilyMember") & (stats["column"] == "state_happiness")]
    assert len(member_happiness) == 1
    assert member_happiness.iloc[0]["n"] == 6, "t=0..5 共 6 个有效样本"

    # Household 不该出现在 state_happiness 的统计里
    assert "state_happiness" not in set(stats[stats["agent_type"] == "Household"]["column"])


def test_statistics_dataframe_has_columns_when_empty() -> None:
    stats = StateRecorder().to_statistics_dataframe()
    assert list(stats.columns) == ["agent_type", "column", "n", "mean", "std", "min", "max"]
    assert stats.empty


def test_to_csv_levels(tmp_path: Path, raw_df: pd.DataFrame) -> None:
    _seed()
    env = Environment()
    household = Household(name="H")
    env.add_agent(household)
    household.add_member(FamilyMember(name="A", age=40, role_name="parent"))
    recorder = StateRecorder(record_agents=True, record_environment=True)
    sim = Simulation(env, scheduler=Scheduler("sequential"))
    sim.add_recorder(recorder)
    sim.run(3)

    for level in ("agent", "statistics", "environment"):
        path = tmp_path / f"{level}.csv"
        recorder.to_csv(str(path), level=level)
        assert path.is_file() and path.stat().st_size > 0, f"{level} 导出为空"

    with pytest.raises(ValueError, match="level"):
        recorder.to_csv(str(tmp_path / "bad.csv"), level="nope")


def test_web_api_preserves_null_instead_of_zero() -> None:
    """API 必须传 null，不能把缺失值伪造成 0。"""
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from family_abm.web.app import app

    client = fastapi_testclient.TestClient(app)
    assert client.post("/api/run", json={"steps": 20}).status_code == 200
    payload = client.get("/api/data").json()

    assert "statistics" in payload and payload["statistics"], "应回传分组统计"

    household_rows = [row for row in payload["data"] if row["agent_type"] == "Household"]
    assert household_rows, "应有 Household 行"
    assert all(row["state_happiness"] is None for row in household_rows), (
        "Household 的 state_happiness 必须是 null，而不是被填成 0"
    )
    member_rows = [row for row in payload["data"] if row["agent_type"] == "FamilyMember"]
    assert all(row["state_total_income"] is None for row in member_rows), (
        "成员的 state_total_income 必须是 null"
    )


# ── P1-1：上报诚实性 ─────────────────────────────────────────────────────


def test_negative_r_squared_is_reported_not_clamped(raw_df: pd.DataFrame) -> None:
    """负 R² 必须如实上报（旧实现的 max(0.0, .) 会把它抹成 0.0）。"""
    member_id = raw_df[raw_df["agent_type"] == "FamilyMember"]["agent_id"].iloc[0]
    fitter = make_fitter("wellbeing")
    # 极窄的边界把优化逼到很差的结果上
    fitter.fit_from_dataframe(raw_df, agent_id=member_id, p0=[5.0, 5.0, 5.0, 5.0, 5.0],
                              bounds=[(1e-4, 1e-3)] * 5)
    assert fitter.r_squared is not None
    assert fitter.r_squared < 0.0, f"应上报负 R²，实际 {fitter.r_squared}"
    assert fitter.summary_json()["r_squared"] < 0.0


def test_converged_requires_no_bound_parameters(raw_df: pd.DataFrame) -> None:
    fitter = make_fitter("wellbeing")
    fitter.fit_from_dataframe(raw_df)
    summary = fitter.summary_json()
    assert "params_at_bounds" in summary and "hit_sentinel" in summary
    if summary["params_at_bounds"]:
        assert summary["converged"] is False, "存在贴边参数时不应判定为可信收敛"


def test_summary_reports_state_columns_and_bounds(raw_df: pd.DataFrame) -> None:
    fitter = make_fitter("wellbeing")
    fitter.fit_from_dataframe(raw_df)
    summary = fitter.summary_json()
    assert summary["state_columns"] == {"happiness": "state_happiness", "stress": "state_stress"}
    assert len(summary["bounds"]) == fitter.n_params
    assert summary["hit_sentinel"] is False
    assert "R^2:" in fitter.summary()


def test_sentinel_solution_is_flagged() -> None:
    """目标函数停在失败哨兵上时，converged 必须为 False（即使 success=True）。"""
    fitter = make_fitter("wellbeing")
    fitter.bounds = [(1e-4, 5.0)] * fitter.n_params
    fitter.fit_result = type("R", (), {"success": True, "fun": 1e12, "x": np.array([0.5] * 5)})()
    fitter.fitted_params_ = fitter.fit_result.x
    fitter._bound_params = []
    assert fitter.converged is False

    fitter.fit_result = type("R", (), {"success": True, "fun": 0.01, "x": np.array([0.5] * 5)})()
    assert fitter.converged is True
