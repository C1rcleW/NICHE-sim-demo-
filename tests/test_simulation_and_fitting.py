"""阶段 B 验收测试：记录 t=0 基线 + 拟合输入显式化。

回归对象：
- P1-5：`Simulation` 先 step 后 record，导致时间轴只有 [1..n]，拟合器把
  "走完第一步后的状态"当成 t=0 初值，整条轨迹相差一步。
- P1-3：`/api/fit` 在列名不匹配时把 O1/O2/R1/R2 静默映射到任意前 N 个 state_ 列，
  把模型拟到无关列（甚至方差为 0 的列）上并返回看似合理的 R²。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from family_abm import Environment, FamilyMember, Household, Scheduler, Simulation, StateRecorder
from family_abm.fitting.fitter import ABMFitter, compare_models, make_fitter
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


def test_long_horizon_fit_recovers_known_parameters() -> None:
    """长窗口（120 步）拟合必须恢复出已知参数。

    回归背景：曾把 ODE 时间轴按窗口长度缩放到 [0,1]。这在数学上等价于把所有速率
    参数同乘窗口长度，因此"拟合成功"却得到被整体缩放过的参数——120 步实测
    R² 从 0.9661 退化到 0.7065、240 步退化到 -0.1377。
    本测试用已知 (r, K) 合成 logistic 数据再拟合，若时间轴被缩放则 r 会被
    系统性乘/除窗口长度，断言必然失败。
    """
    from scipy.integrate import solve_ivp

    from family_abm.fitting.lanchester import logistic_growth

    true_r, true_k = 0.35, 1.2
    t = np.arange(0.0, 120.0, 1.0)
    solution = solve_ivp(lambda tt, y: logistic_growth(tt, y, true_r, true_k),
                         [t[0], t[-1]], [1e-3], t_eval=t, method="RK45", rtol=1e-8, atol=1e-10)
    assert solution.success

    df = pd.DataFrame({
        "time": t,
        "agent_id": "synthetic",
        "state_population": solution.y[0],
    })

    fitter = make_fitter("logistic")
    fitter.fit_from_dataframe(df)
    recovered_r = fitter.fitted_param_dict["r"]
    recovered_k = fitter.fitted_param_dict["K"]

    assert recovered_r == pytest.approx(true_r, rel=0.15), (
        f"恢复的 r={recovered_r} 与真值 {true_r} 偏差过大——时间轴可能被缩放"
    )
    assert recovered_k == pytest.approx(true_k, rel=0.15), f"恢复的 K={recovered_k} 与真值 {true_k} 偏差过大"
    assert fitter.r_squared > 0.99, f"R²={fitter.r_squared} 过低"


def test_fit_accepts_scipy_bounds_object() -> None:
    """bounds 同时接受 list[(lo,hi)] 与 scipy.optimize.Bounds。"""
    from scipy.optimize import Bounds

    recorder, _ = build_recorder(record_initial=True, steps=40)
    df = recorder.to_dataframe()

    fitter = make_fitter("wellbeing")
    fitter.fit_from_dataframe(df, bounds=Bounds(lb=[1e-4] * 5, ub=[5.0] * 5))
    assert fitter.bounds == [(1e-4, 5.0)] * 5
    assert fitter.r_squared is not None

    with pytest.raises(ValueError, match="边界数量"):
        make_fitter("wellbeing").fit_from_dataframe(df, bounds=[(0.0, 1.0)] * 3)


def test_compare_models_accepts_state_mappings() -> None:
    """compare_models 必须能为抽象模型传入映射（此前传 state_mapping= 会 TypeError）。"""
    recorder, _ = build_recorder(record_initial=True, steps=40)
    df = recorder.to_dataframe()

    results = compare_models(
        df,
        ["wellbeing", "square_law"],
        robust=False,
        state_mappings={"square_law": {"R1": "state_happiness", "R2": "state_stress"}},
    )
    assert set(results) == {"wellbeing", "square_law"}
    assert results["square_law"]._resolved_columns == {"R1": "state_happiness", "R2": "state_stress"}

    with pytest.raises(ValueError, match="未请求的模型"):
        compare_models(df, ["wellbeing"], robust=False, state_mappings={"square_law": {}})


def test_web_fit_accepts_explicit_state_mapping(sim_df: pd.DataFrame) -> None:
    """Web /api/fit 支持显式 state_mapping，抽象模型不再永远 400。"""
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from family_abm.web.app import app as web_app

    client = fastapi_testclient.TestClient(web_app)
    assert client.post("/api/run", json={"steps": 40}).status_code == 200

    models = client.get("/api/models").json()
    by_name = {m["name"]: m for m in models["models"]}
    assert by_name["wellbeing"]["directly_fittable"] is True
    assert by_name["square_law"]["directly_fittable"] is False
    assert by_name["square_law"]["missing_states"] == ["R1", "R2"]

    unmapped = client.post("/api/fit", json={"model_name": "square_law", "robust": False})
    assert unmapped.status_code == 400

    mapped = client.post("/api/fit", json={
        "model_name": "square_law",
        "robust": False,
        "state_mapping": {"R1": "state_happiness", "R2": "state_stress"},
    })
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["state_columns"] == {"R1": "state_happiness", "R2": "state_stress"}


def test_api_models_excludes_constant_columns_from_suggestions() -> None:
    """候选映射必须排除零方差列。

    回归：按字母序取前 N 个 state_ 列会选中 Household 专属常量列
    （state_cultural_level，ptp=0），把模型拟到常数列上会得到 R²=0.0 却
    converged=True —— 比"静默猜列"更糟的误导。
    """
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from family_abm.web.app import app as web_app

    client = fastapi_testclient.TestClient(web_app)
    assert client.post("/api/run", json={"steps": 20}).status_code == 200
    payload = client.get("/api/models").json()

    assert "state_cultural_level" in payload["constant_state_columns"], "应识别出 Household 常量列"
    assert "state_happiness" in payload["usable_state_columns"]
    for column in payload["usable_state_columns"]:
        assert column not in payload["constant_state_columns"]

    for model in payload["models"]:
        suggestion = model["suggested_mapping"]
        if suggestion:
            for column in suggestion.values():
                assert column not in payload["constant_state_columns"], (
                    f"{model['name']} 的建议映射包含零方差列 {column}"
                )


def test_api_fit_returns_400_when_all_starts_fail() -> None:
    """多起点全部失败必须返回 400（可预期）而不是 500（服务端故障）。"""
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from family_abm.web.app import app as web_app

    client = fastapi_testclient.TestClient(web_app)
    # 恰好 10 个时间点：满足拟合下限，但对 6 参数模型几乎没有约束力
    assert client.post("/api/run", json={"steps": 10}).status_code == 200

    response = client.post("/api/fit", json={
        "model_name": "resource_competition",
        "robust": True,
        "state_mapping": {"R1": "state_income", "R2": "state_education"},
    })
    assert response.status_code == 400, f"应为 400，实际 {response.status_code}: {response.text[:300]}"
    body = response.json()
    assert body.get("status") in {"all_starts_failed", "model_not_applicable"}
    assert "error" in body


def test_web_fit_maps_sentinel_solution_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """优化停在哨兵上必须映射为 400（带 status=model_not_applicable），而非 500。

    这里用确定性桩替换 fitter：靠真实模型"必然失败"来做断言是不可靠的
    （实测 square_law 在某些列组合上也能找到 R²=0.74 的可用解）。
    """
    import asyncio
    import importlib

    # 注意：`from family_abm.web import app` / `import family_abm.web.app as m`
    # 都会拿到 FastAPI 实例（web/__init__.py 暴露了同名属性），必须显式取子模块。
    web_app_module = importlib.import_module("family_abm.web.app")

    class _SentinelFitter:
        n_states = 2
        _t = None
        _y0 = None
        fitted_param_dict = {"alpha": 0.5}
        state_names = ["R1", "R2"]

        def fit_from_dataframe(self, df, agent_id=None):
            return type("R", (), {"success": True, "fun": 1e12})()

        def summary_json(self):
            return {"hit_sentinel": True, "r_squared": None, "converged": False}

    monkeypatch.setattr(web_app_module, "make_fitter", lambda *a, **k: _SentinelFitter())
    monkeypatch.setattr(web_app_module, "_sim_df", pd.DataFrame({"time": [0, 1], "state_happiness": [0.1, 0.2]}))

    response = asyncio.run(web_app_module.api_fit(web_app_module.FitRequest(model_name="square_law", robust=False)))
    assert response.status_code == 400
    payload = json.loads(response.body)
    assert payload["status"] == "model_not_applicable"
    assert "哨兵" in payload["error"]


def test_web_fit_maps_all_starts_failure_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """多起点全部失败抛出的 RuntimeError 必须映射为 400。"""
    import asyncio
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")

    class _FailingFitter:
        n_states = 2
        _t = None
        _y0 = None
        state_names = ["R1", "R2"]

        def fit_robust(self, df, agent_id=None):
            raise RuntimeError("All fitting attempts failed.")

        def summary_json(self):
            return {"hit_sentinel": True}

    monkeypatch.setattr(web_app_module, "make_fitter", lambda *a, **k: _FailingFitter())
    monkeypatch.setattr(web_app_module, "_sim_df", pd.DataFrame({"time": [0, 1], "state_happiness": [0.1, 0.2]}))

    response = asyncio.run(web_app_module.api_fit(web_app_module.FitRequest(model_name="resource_competition", robust=True)))
    assert response.status_code == 400
    assert json.loads(response.body)["status"] == "all_starts_failed"


def test_converged_reflects_optimizer_state_not_bound_hits() -> None:
    """突变测试：converged 只看优化器状态，不看参数是否贴边。

    历史问题（两次）：先是把 `r_squared > 0` 塞进 converged 导致负 R² 不可见；
    后又把"无贴边参数"塞进去，导致 R²=0.97–0.99 的正常拟合被判为未收敛。
    本测试同时钉住两个方向。
    """
    fitter = make_fitter("wellbeing")
    fitter.bounds = [(1e-4, 5.0)] * fitter.n_params
    fitter.fit_result = type("R", (), {"success": False, "fun": 0.01, "x": np.array([1e-4] * 5)})()
    assert fitter.converged is False, "优化器未成功时不得判为收敛"

    # 优化器成功 + 目标有限 + R² 有限 -> 收敛为真；参数贴边仅作告警
    fitter.fit_result = type("R", (), {"success": True, "fun": 0.01, "x": np.array([1e-4] * 5)})()
    fitter.fitted_params_ = fitter.fit_result.x
    fitter.r_squared = 0.97
    assert fitter.converged is True, "高 R² 的成功拟合不应因参数贴边被判为未收敛"
    assert fitter._parameters_at_bounds(fitter.fit_result.x) == fitter.param_names, "贴边仍应被检出并告警"


def test_high_r_squared_fit_is_not_reported_as_unconverged() -> None:
    """真实数据上的高 R² 拟合必须被判定为已收敛（此前贴边误判使 R²=0.97 报 False）。"""
    recorder, _ = build_recorder(record_initial=True, steps=120)
    df = recorder.to_dataframe()
    fitter = make_fitter("wellbeing")
    fitter.fit_from_dataframe(df)
    summary = fitter.summary_json()
    assert summary["r_squared"] > 0.8, summary["r_squared"]
    assert summary["converged"] is True, (
        f"R²={summary['r_squared']} 的高质量拟合被判为未收敛；贴边参数={summary['params_at_bounds']}"
    )


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
