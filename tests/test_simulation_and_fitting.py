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
import re
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
        # 默认映射命中但该列为常量时，不得再声称可直接拟合
        if model["directly_fittable"]:
            for column in model["expected_columns"].values():
                assert column in payload["usable_state_columns"]


def test_models_endpoint_marks_needs_manual_mapping_when_candidates_run_out() -> None:
    """候选列不足时必须 needs_manual_mapping=True 且不给建议（此前零覆盖）。"""
    import asyncio
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")
    # 只有 1 个有变化的 state_ 列，而 two-state 模型需要 2 个
    frame = pd.DataFrame({
        "time": [0, 1, 2, 3],
        "state_only_changing": [0.1, 0.3, 0.5, 0.7],
        "state_pinned": [1.0, 1.0, 1.0, 1.0],
    })
    original = web_app_module._sim_df
    web_app_module._sim_df = frame
    try:
        payload = asyncio.run(web_app_module.api_models())
        body = json.loads(payload.body)
    finally:
        web_app_module._sim_df = original

    assert body["usable_state_columns"] == ["state_only_changing"]
    assert body["constant_state_columns"] == ["state_pinned"]

    wellbeing = next(m for m in body["models"] if m["name"] == "wellbeing")
    # 默认映射 state_happiness/state_stress 都不存在
    assert wellbeing["directly_fittable"] is False
    assert set(wellbeing["missing_states"]) == {"happiness", "stress"}
    # 只有 1 个候选而需要 2 个 -> 不能给建议，必须标记人工指定
    assert wellbeing["needs_manual_mapping"] is True, wellbeing
    assert not wellbeing["suggested_mapping"]

    logistic = next(m for m in body["models"] if m["name"] == "logistic")
    # 需要 1 个状态、有 1 个候选 -> 可以给出建议
    assert logistic["needs_manual_mapping"] is False
    assert logistic["suggested_mapping"] == {"population": "state_only_changing"}


def test_variance_report_uses_time_aggregated_target_not_pooled_span() -> None:
    """方差判据必须针对拟合目标序列（按 time 聚合），而不是全表 pooled 跨度。

    回归：pooled min/max 会把"每个 agent 各自恒定、但不同 agent 取值不同"的列
    误判为有变化，而拟合用的恰恰是按 time 聚合后的序列。
    """
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")
    frame = pd.DataFrame({
        "time": [0, 1, 2, 0, 1, 2],
        # 每个 agent 在时间上恒定，但两个 agent 取值不同 -> pooled 跨度很大
        "state_per_agent_constant": [0.1, 0.1, 0.1, 0.9, 0.9, 0.9],
        # 真正随时间变化
        "state_time_varying": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        # 完全常量
        "state_flat": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    })

    usable, constant, unverifiable = web_app_module._column_variance_report(frame)
    assert usable == ["state_time_varying"], f"usable={usable}"
    assert set(constant) == {"state_flat", "state_per_agent_constant"}, f"constant={constant}"
    assert unverifiable == []

    # pooled 跨度确实很大，证明"用 pooled 判据"会把它误判为可用
    assert frame["state_per_agent_constant"].max() - frame["state_per_agent_constant"].min() > 0.7


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


def test_web_fit_returns_200_with_warning_for_sentinel_solution(monkeypatch: pytest.MonkeyPatch) -> None:
    """哨兵解返回 200 + status=model_not_applicable + warning。

    设计取舍（经复核指出后修正）：此前的实现一旦命中哨兵就返回 400，而前端对任何
    ``res.error`` 都提前 return，导致 dashboard.js 里的"命中哨兵告警条"成为永不执行的
    死代码。诊断信息必须能到达界面，因此哨兵解走 200 路径并在 UI 上以告警条呈现。

    这里用确定性桩替换 fitter：靠真实模型"必然失败"来做断言不可靠
    （实测 square_law 在某些列组合上也能得到 R²=0.74）。
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
        _resolved_columns = {"R1": "state_a", "R2": "state_b"}
        fitted_param_dict = {"alpha": 0.5}
        state_names = ["R1", "R2"]

        def fit_from_dataframe(self, df, agent_id=None):
            return type("R", (), {"success": True, "fun": 1e12})()

        def summary_json(self):
            return {"hit_sentinel": True, "r_squared": None, "converged": False, "params_at_bounds": []}

    monkeypatch.setattr(web_app_module, "make_fitter", lambda *a, **k: _SentinelFitter())
    monkeypatch.setattr(web_app_module, "_sim_df", pd.DataFrame({"time": [0, 1], "state_happiness": [0.1, 0.2]}))

    response = asyncio.run(web_app_module.api_fit(web_app_module.FitRequest(model_name="square_law", robust=False)))
    assert response.status_code == 200, response.body
    payload = json.loads(response.body)
    assert payload["status"] == "model_not_applicable"
    assert payload["warning"] and "哨兵" in payload["warning"]
    assert payload["summary"]["hit_sentinel"] is True
    # 哨兵解不生成预测轨迹：既省算力，也避免 predict 失败把结论颠倒
    assert payload["predict_trace"] == []
    assert payload["prediction_skipped"] is True


def test_sentinel_check_precedes_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    """哨兵命中时不得调用 predict：真实场景 resource_competition+robust=false
    的 predict 必然失败，若先 predict 会把"模型不适用"错报成 500 prediction_failed。
    """
    import asyncio
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")

    class _SentinelWithFailingPredict:
        n_states = 2
        _y0 = np.array([0.5, 0.3])
        _resolved_columns = {"R1": "state_a", "R2": "state_b"}
        state_names = ["R1", "R2"]
        predict_called = False

        def __init__(self):
            self._t = np.array([0.0, 1.0])

        def fit_from_dataframe(self, df, agent_id=None):
            return type("R", (), {"success": True, "fun": 1e12})()

        def predict(self, t, y0):
            type(self).predict_called = True
            raise RuntimeError("predict would fail")

        def summary_json(self):
            return {"hit_sentinel": True, "r_squared": None, "converged": False, "params_at_bounds": []}

    stub = _SentinelWithFailingPredict()
    monkeypatch.setattr(web_app_module, "make_fitter", lambda *a, **k: stub)
    monkeypatch.setattr(web_app_module, "_sim_df", pd.DataFrame({"time": [0, 1], "state_happiness": [0.1, 0.2]}))

    response = asyncio.run(web_app_module.api_fit(web_app_module.FitRequest(model_name="square_law", robust=False)))
    assert response.status_code == 200, response.body
    assert stub.predict_called is False, "哨兵命中时不应调用 predict"


def test_missing_time_or_agent_column_reports_invalid_dataframe(monkeypatch: pytest.MonkeyPatch) -> None:
    """数据缺必需列时必须报 invalid_dataframe，而不是被误诊成"未知模型名"。

    回归：`except KeyError` 曾包住整个流程，df 缺 time 列时返回
    400 unknown_model（"未知模型名 'time'"）。
    """
    import asyncio
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")

    for frame in (
        pd.DataFrame({"agent_id": ["a"], "state_happiness": [0.1]}),          # 缺 time
        pd.DataFrame({"time": [0], "state_happiness": [0.1]}),                # 缺 agent_id（按 agent 拟合时）
    ):
        monkeypatch.setattr(web_app_module, "_sim_df", frame)
        request = web_app_module.FitRequest(model_name="wellbeing", robust=False)
        if "agent_id" not in frame.columns:
            request.agent_id = "a"
        response = asyncio.run(web_app_module.api_fit(request))
        assert response.status_code == 400, response.body
        body = json.loads(response.body)
        assert body["status"] == "invalid_dataframe", body
        assert "必需列" in body["error"]


def test_web_fit_maps_optimizer_failure_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """优化器自身失败（success=False）映射为 400 + status=optimizer_failed。"""
    import asyncio
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")

    class _FailedOptimizerFitter:
        n_states = 2
        _t = None
        _y0 = None
        state_names = ["R1", "R2"]

        def fit_from_dataframe(self, df, agent_id=None):
            return type("R", (), {"success": False, "fun": 0.01})()

        def summary_json(self):
            return {"hit_sentinel": False, "r_squared": 0.0, "converged": False}

    monkeypatch.setattr(web_app_module, "make_fitter", lambda *a, **k: _FailedOptimizerFitter())
    monkeypatch.setattr(web_app_module, "_sim_df", pd.DataFrame({"time": [0, 1], "state_happiness": [0.1, 0.2]}))

    response = asyncio.run(web_app_module.api_fit(web_app_module.FitRequest(model_name="wellbeing", robust=False)))
    assert response.status_code == 400
    assert json.loads(response.body)["status"] == "optimizer_failed"


def test_web_fit_maps_all_starts_failure_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """多起点全部失败抛出的 RuntimeError 必须映射为 400（仅拟合阶段的异常）。"""
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


def test_web_fit_does_not_mask_prediction_failure_as_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """拟合成功但 predict() 抛 RuntimeError 时必须暴露为 500，而不是误诊成 all_starts_failed。

    回归：此前 `except RuntimeError` 包住了整个流程，predict() 的 RuntimeError
    被改写成 400 all_starts_failed（诊断错误且丢失 summary）。
    """
    import asyncio
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")

    class _PredictFailsFitter:
        n_states = 2
        fitted_param_dict = {"p": 0.5}
        state_names = ["happiness", "stress"]
        _resolved_columns = {"happiness": "state_happiness", "stress": "state_stress"}
        _y0 = np.array([0.5, 0.3])

        def __init__(self):
            self._t = np.array([0.0, 1.0])

        def fit_from_dataframe(self, df, agent_id=None):
            return type("R", (), {"success": True, "fun": 0.01})()

        def predict(self, t, y0):
            raise RuntimeError("predict exploded")

        def summary_json(self):
            return {"hit_sentinel": False, "r_squared": 0.9, "converged": True, "params_at_bounds": []}

    monkeypatch.setattr(web_app_module, "make_fitter", lambda *a, **k: _PredictFailsFitter())
    monkeypatch.setattr(web_app_module, "_sim_df", pd.DataFrame({"time": [0, 1], "state_happiness": [0.1, 0.2]}))

    response = asyncio.run(web_app_module.api_fit(web_app_module.FitRequest(model_name="wellbeing", robust=False)))
    assert response.status_code == 500
    assert json.loads(response.body)["status"] == "prediction_failed"


def test_web_fit_unknown_model_returns_400() -> None:
    """未知 model_name 必须返回 400（而不是让 KeyError 落到 500）。"""
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from family_abm.web.app import app as web_app

    client = fastapi_testclient.TestClient(web_app)
    assert client.post("/api/run", json={"steps": 20}).status_code == 200

    response = client.post("/api/fit", json={"model_name": "no_such_model", "robust": False})
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["status"] == "unknown_model"
    assert "wellbeing" in body["error"]


def test_frontend_warns_on_non_positive_r_squared() -> None:
    """即使没命中哨兵，R²<=0 也必须有可见告警（converged=True 只说明优化器跑完了）。

    回归：square_law 在 UI 实际使用的 robust=true 下可得到 R²=-14.35/-94265.68
    且 converged=True，此前界面上没有任何提示。
    """
    dashboard = Path(__file__).resolve().parent.parent / "family_abm" / "web" / "static" / "js" / "dashboard.js"
    source = dashboard.read_text(encoding="utf-8")
    assert "fitting.warn_r2_nonpositive" in source, "缺少 R² 非正告警"
    assert "s.r_squared <= 0" in source, "缺少触发 R² 非正告警的条件"
    # 双语字典都要有该键（各自以 'fitting.warn_r2_nonpositive': 形式出现一次）
    assert source.count("fitting.warn_r2_nonpositive':") == 2, "该 i18n 键应同时存在于中英文字典"


def test_fit_diagnostics_do_not_expose_alphabetical_mapping_suggestion() -> None:
    """fitter 的错误信息不得再按字母序给出"示意映射"。

    回归：按字母序取列会把 state_cultural_level（Household 常量列）当作建议，
    把模型拟到零方差列上得到 R²=0.0 却 converged=True。
    """
    from family_abm.fitting.fitter import ABMFitter
    from family_abm.fitting.lanchester import MODEL_PARAM_NAMES, MODEL_REGISTRY, MODEL_STATE_NAMES

    fitter = ABMFitter(
        MODEL_REGISTRY["influence"],
        MODEL_PARAM_NAMES["influence"],
        MODEL_STATE_NAMES["influence"],
    )
    message = fitter._format_mapping_error(["O1", "O2"], ["time", "state_cultural_level", "state_happiness"])
    # 不应内嵌任何实际映射字典（形如 {'O1': 'state_...'}）
    assert not re.search(r"\{\s*'?O1'?\s*:\s*'?state_", message), f"不应再内嵌示意映射：{message}"
    assert "state_cultural_level" not in message.split("可用状态列")[0], "不应把常量列当作建议列"
    assert "/api/models" in message, "应指向带方差过滤的候选接口"
    assert "state_mapping" in message


def test_build_fit_chart_does_not_shadow_i18n_function() -> None:
    """buildFitChart 内不得再声明名为 t 的变量。

    回归（既有 bug）：`const t = Object.keys(byTime)...` 遮蔽了 i18n 函数 t()，
    导致每次成功拟合都在绘图阶段抛 `TypeError: t is not a function`，
    状态永远停在"拟合中…"。复核指出该修复当时零测试覆盖，故这里用源码形状断言守住。
    """
    dashboard = Path(__file__).resolve().parent.parent / "family_abm" / "web" / "static" / "js" / "dashboard.js"
    source = dashboard.read_text(encoding="utf-8")

    start = source.index("function buildFitChart")
    end = source.index("\nfunction ", start + 1)
    body = source[start:end]

    assert not re.search(r"\b(?:const|let|var)\s+t\s*=", body), "buildFitChart 内不得声明名为 t 的变量（会遮蔽 i18n）"
    assert "const timeKeys" in body, "应使用不冲突的变量名承载时间轴"
    assert "t('fitting.data_suffix')" in body, "i18n 调用必须仍然有效"


def test_models_endpoint_respects_agent_subset() -> None:
    """/api/models 支持按 agent 子集评估：整体有变化但该 agent 恒定的列应判为常量。"""
    import asyncio
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")
    frame = pd.DataFrame({
        "time": [0, 1, 2, 0, 1, 2],
        "agent_id": ["A", "A", "A", "B", "B", "B"],
        # 整体随时间变化，但 agent A 恒定
        "state_happiness": [0.5, 0.5, 0.5, 0.1, 0.5, 0.9],
        "state_stress": [0.2, 0.4, 0.6, 0.2, 0.4, 0.6],
    })
    original = web_app_module._sim_df
    web_app_module._sim_df = frame
    try:
        pooled = json.loads(asyncio.run(web_app_module.api_models()).body)
        subset = json.loads(asyncio.run(web_app_module.api_models(agent_id="A")).body)
    finally:
        web_app_module._sim_df = original

    assert "state_happiness" in pooled["usable_state_columns"], "整体看 happiness 有变化"
    assert "state_happiness" in subset["constant_state_columns"], "agent A 的 happiness 恒定"
    wellbeing_subset = next(m for m in subset["models"] if m["name"] == "wellbeing")
    assert wellbeing_subset["directly_fittable"] is False, "该 agent 子集下 happiness 为常量，不应声称可直接拟合"


def test_variance_report_treats_single_group_as_unverifiable() -> None:
    """只有一个有效时间分组的列无法验证方差，应归入 unverifiable 而不是 usable。"""
    import importlib

    web_app_module = importlib.import_module("family_abm.web.app")
    frame = pd.DataFrame({
        "time": [0, 0, 1, 1],
        "state_only_one_group": [0.1, 0.2, None, None],
        "state_normal": [0.1, 0.2, 0.3, 0.4],
    })
    usable, constant, unverifiable = web_app_module._column_variance_report(frame)
    assert "state_only_one_group" in unverifiable, f"unverifiable={unverifiable}"
    assert "state_normal" in usable


def test_frontend_blocks_fit_when_no_model_is_selectable() -> None:
    """全禁用时必须禁用拟合按钮并给出原因，且拒绝发起拟合。"""
    dashboard = Path(__file__).resolve().parent.parent / "family_abm" / "web" / "static" / "js" / "dashboard.js"
    source = dashboard.read_text(encoding="utf-8")
    assert "fitSectionBlocked" not in source  # 防止误命名
    assert "fitSelectionBlocked" in source
    assert "btn.disabled = !anySelectable" in source
    assert "'fitting.none_available'" in source
    assert source.count("fitting.none_available':") == 2, "该 i18n 键应中英双语齐全"

    template = Path(__file__).resolve().parent.parent / "family_abm" / "web" / "templates" / "index.html"
    html = template.read_text(encoding="utf-8")
    assert 'id="fitRunBtn"' in html, "拟合按钮需要 id 才能被禁用"


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
