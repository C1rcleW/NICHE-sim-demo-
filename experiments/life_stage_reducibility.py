"""生命阶段可约性实验：常系数 ODE 能否刻画家庭聚合动力学？

研究问题
--------
家庭内的代际影响强度随子代发展阶段下降（"年长成员越来越难影响孩子"）。
这种**影响系数本身随时间变化**的结构，是否会让宏观聚合动力学无法被
单一常系数 ODE 描述？

设计
----
四代结构（祖辈 68 / 父辈 40 / 子代 12 / 幼子 4），使得 240 步内子代跨越
成年阈值、幼子经历多个发展阶段——"代际更新"因此在观测窗口内真实发生。

四种消融条件：

    C0  无影响            影响强度 = 0（基线）
    C1  影响恒定          易感性固定 0.50，与年龄无关
    C2  阶段易感性        易感性随埃里克森阶段下降
    C3  阶段易感性+角色切换  子代成年后转为施加影响

三类度量：

    1. 轨迹偏离：各条件相对 C0 的聚合轨迹偏离（机制是否可见）
    2. 离散度趋势：成员间变异系数随时间的变化（累积优势：差距发散/收敛）
    3. 可约性：用常系数 ODE 拟合聚合轨迹的 R²（全窗口 vs 分段）

预期
----
影响系数在 C1 中近似恒定、在 C2/C3 中随阶段快速变化。
因此 C2/C3 的"全窗口单一 ODE"拟合应比 C1 更差，而分段拟合能部分恢复。

用法
----
    python experiments/life_stage_reducibility.py
    python experiments/life_stage_reducibility.py --steps 240 --json results.json --plot fig.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from family_abm import Environment, FamilyMember, Household, Scheduler, Simulation, StateRecorder  # noqa: E402
from family_abm.fitting.fitter import make_fitter  # noqa: E402

# ── 实验配置 ────────────────────────────────────────────────────────────────

SEED = 42

# 四代结构：让"代际更新"在观测窗口内真实发生
#   Child 12 岁 -> 240 步后 32 岁（跨越成年阈值）
#   Toddler 4 岁 -> 24 岁（完整经历学前期到成年）
FAMILIES = [
    ("Smith", [
        ("Grandfather", 68, "male", "elder"),
        ("Father", 40, "male", "parent"),
        ("Mother", 38, "female", "parent"),
        ("Child", 12, "male", "child"),
        ("Toddler", 4, "female", "child"),
    ]),
    ("Jones", [
        ("Grandmother", 64, "female", "elder"),
        ("Mother2", 34, "female", "parent"),
        ("Daughter", 12, "female", "child"),
    ]),
]

# 影响强度：诊断表明 ~4 时机制效应清晰可见（偏离 0.077）且未饱和
INFLUENCE_STRENGTH = 4.0

CONDITIONS = [
    ("C0", "无影响（基线）", {"influence_strength": 0.0}),
    ("C1", "影响恒定", {"influence_strength": INFLUENCE_STRENGTH,
                        "use_life_stage_susceptibility": 0.0, "role_switch": 0.0}),
    ("C2", "阶段易感性", {"influence_strength": INFLUENCE_STRENGTH,
                          "use_life_stage_susceptibility": 1.0, "role_switch": 0.0}),
    ("C3", "阶段易感性 + 角色切换", {"influence_strength": INFLUENCE_STRENGTH,
                                      "use_life_stage_susceptibility": 1.0, "role_switch": 1.0}),
]

# 阶段窗口（步 = 月），对齐子代的发展阶段：
#   Window A  子代 12->20 岁（青春期，易感性 0.28 快速下降）
#   Window B  子代 20->32 岁（成年，易感性稳定 0.15 且角色反转）
# C1 中易感性恒为 0.50，两窗口的影响系数相同；C2/C3 中两窗口显著不同。
STAGE_WINDOWS = [
    ("A 青春期(12-20岁)", 0, 96),
    ("B 成年后(20-32岁)", 96, 240),
]

STATE_COLUMNS = ["state_happiness", "state_stress"]

# 图表英文标签（图会被单独放进幻灯片，避免字体依赖）
EN_LABELS: dict[str, str] = {
    "A 青春期(12-20岁)": "A adolescence\n(12-20y)",
    "B 成年后(20-32岁)": "B adulthood\n(20-32y)",
    "无影响（基线）": "no influence\n(baseline)",
    "影响恒定": "constant\ninfluence",
    "阶段易感性": "stage\nsusceptibility",
    "阶段易感性 + 角色切换": "stage +\nrole switch",
}


# ── 仿真 ────────────────────────────────────────────────────────────────────


def run_condition(params: dict, steps: int = 240):
    env = Environment()
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=SEED)
    env.params = dict(params)

    for family_name, members in FAMILIES:
        household = Household(name=family_name, household_id=family_name.lower(), environment=env)
        env.add_agent(household)
        for index, (name, age, gender, role) in enumerate(members):
            household.add_member(FamilyMember(
                name=name, age=age, gender=gender, role_name=role,
                agent_id=f"{family_name.lower()}-{index}", environment=env,
            ))

    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)
    sim.run(steps)
    return recorder.to_dataframe()


def aggregate(df, low=0, high=None):
    """家庭聚合轨迹：每时刻成员均值（宏观观测量）。"""
    members = df[df["agent_type"] == "FamilyMember"]
    members = members[members["time"] >= low]
    if high is not None:
        members = members[members["time"] < high]
    grouped = members.groupby("time")[STATE_COLUMNS].mean().dropna()
    grouped = grouped.reset_index()
    grouped.columns = ["time", "happiness", "stress"]
    return grouped


def trajectory_deviation(baseline: "np.ndarray", other: "np.ndarray") -> dict:
    """相对基线的偏离：用基线幅度归一化，便于跨状态量比较。"""
    n = min(len(baseline), len(other))
    delta = other[:n] - baseline[:n]
    scale = max(float(np.abs(baseline[:n]).mean()), 1e-9)
    return {
        "mean_abs": float(np.abs(delta).mean()),
        "max_abs": float(np.abs(delta).max()),
        "normalized": float(np.abs(delta).mean() / scale),
    }


def dispersion(df) -> list[dict]:
    """成员间变异系数随时间的变化——累积优势检验（+ 发散 / − 收敛）。"""
    members = df[df["agent_type"] == "FamilyMember"]
    records = []
    for column in STATE_COLUMNS:
        grouped = members.groupby("time")[column]
        mean = grouped.mean()
        std = grouped.std().fillna(0.0)
        cv = (std / mean.replace(0.0, np.nan)).dropna()
        if len(cv) < 5:
            continue
        slope = float(np.polyfit(cv.index.values.astype(float), cv.values.astype(float), 1)[0])
        records.append({
            "state": column,
            "first": float(cv.iloc[0]),
            "last": float(cv.iloc[-1]),
            "slope": slope,
            "direction": "diverging" if slope > 0 else "converging",
        })
    return records


def influence_intensity(df, low=0, high=None) -> dict:
    """影响系数（强度 × 易感性）的平均水平——"系数是否随时间变化"的直接度量。"""
    members = df[df["agent_type"] == "FamilyMember"]
    members = members[members["time"] >= low]
    if high is not None:
        members = members[members["time"] < high]
    openness = members["state_susceptibility"].astype(float)
    received = members["state_influence_received"].abs().astype(float)
    return {
        "mean_openness": float(openness.mean()),
        "std_openness": float(openness.std()),
        "mean_received": float(received.mean()),
    }


# ── 可约性：常系数 ODE 拟合 ─────────────────────────────────────────────────


def fit_reducibility(df, window=None, model="wellbeing") -> dict:
    """用常系数 ODE 拟合聚合轨迹，返回拟合优度。

    映射：``wellbeing`` 的状态变量是 (happiness, stress)，对应这里的两个聚合观测量。
    """
    low, high = (0, None) if window is None else window
    trajectory = aggregate(df, low, high)
    if len(trajectory) < 12:
        return {"error": "样本点过少", "n": len(trajectory)}
    try:
        fitter = make_fitter(model, state_mapping={"happiness": "happiness", "stress": "stress"})
        fitter.fit_from_dataframe(trajectory)
        summary = fitter.summary_json()
        return {
            "r_squared": float(summary["r_squared"]) if summary.get("r_squared") is not None else None,
            "converged": bool(summary.get("converged")),
            "n": len(trajectory),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "n": len(trajectory)}


# ── 主流程 ──────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生命阶段可约性实验")
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--json", type=Path, help="结构化结果写入 JSON")
    parser.add_argument("--plot", type=Path, help="结果图写入 PNG")
    args = parser.parse_args(argv)

    results = {"steps": args.steps, "seed": SEED, "conditions": {}}
    baseline_series = None

    for key, label, params in CONDITIONS:
        print(f"\n{'=' * 76}")
        print(f"{key}  {label}")
        print(f"  参数: {params}")
        print("=" * 76)

        df = run_condition(params, steps=args.steps)
        happiness = aggregate(df)["happiness"].values

        if baseline_series is None:
            baseline_series = happiness
            deviation = {"mean_abs": 0.0, "max_abs": 0.0, "normalized": 0.0}
        else:
            deviation = trajectory_deviation(baseline_series, happiness)

        full = fit_reducibility(df)
        stages = {}
        for stage_label, low, high in STAGE_WINDOWS:
            if high > args.steps:
                continue
            stages[stage_label] = fit_reducibility(df, (low, high))

        intensity = influence_intensity(df)
        intensity_a = influence_intensity(df, *STAGE_WINDOWS[0][1:]) if len(STAGE_WINDOWS) > 0 else {}
        intensity_b = influence_intensity(df, *STAGE_WINDOWS[1][1:]) if len(STAGE_WINDOWS) > 1 else {}

        print(f"  轨迹偏离基线: 均值={deviation['mean_abs']:.5f}  "
              f"最大={deviation['max_abs']:.5f}  归一化={deviation['normalized']:.4f}")
        print(f"  易感性: 均值={intensity['mean_openness']:.4f} 标准差={intensity['std_openness']:.4f}"
              f"   |  窗口A={intensity_a.get('mean_openness', float('nan')):.4f}"
              f"  窗口B={intensity_b.get('mean_openness', float('nan')):.4f}")
        print(f"  可约性: 全窗口 R²={_fmt(full.get('r_squared'))}"
              + "".join(f"   {lab}={_fmt(stages.get(lab, {}).get('r_squared'))}"
                        for lab, _, _ in STAGE_WINDOWS if lab in stages))

        results["conditions"][key] = {
            "label": label,
            "params": params,
            "deviation": deviation,
            "influence": {"overall": intensity, "window_a": intensity_a, "window_b": intensity_b},
            "reducibility": {"full": full, "stages": stages},
            "dispersion": dispersion(df),
        }

    print(f"\n{'=' * 76}")
    print("汇总")
    print("=" * 76)
    header = (f"{'条件':<30}{'轨迹偏离':>10}{'易感性σ':>10}{'全窗口R²':>11}"
              + "".join(f"{lab[:6]:>10}" for lab, _, _ in STAGE_WINDOWS))
    print(header)
    print("-" * len(header))
    for key, label, _ in CONDITIONS:
        entry = results["conditions"][key]
        influence = entry["influence"]["overall"]
        stages = entry["reducibility"]["stages"]
        row = (f"{key + ' ' + label:<30}"
               f"{entry['deviation']['mean_abs']:>10.5f}"
               f"{influence['std_openness']:>10.4f}"
               f"{_fmt(entry['reducibility']['full'].get('r_squared')):>11}")
        for lab, _, _ in STAGE_WINDOWS:
            row += f"{_fmt(stages.get(lab, {}).get('r_squared')):>10}"
        print(row)

    print("\n成员间离散度趋势:")
    for key, label, _ in CONDITIONS:
        for record in results["conditions"][key]["dispersion"]:
            print(f"  {key} {record['state']:<18} {record['direction']:<11} "
                  f"slope={record['slope']:+.6f}  首={record['first']:.4f} 末={record['last']:.4f}")

    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结构化结果已写入 {args.json}")

    if args.plot:
        _plot(results, args.plot)
        print(f"结果图已写入 {args.plot}")

    return 0


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and not np.isfinite(value):
        return "非有限"
    return f"{value:.4f}"


def _plot(results: dict, path: Path) -> None:
    """三张图：轨迹偏离、易感性的时间变异、分段 R²。

    图表标签一律用英文：中文字形依赖系统字体（DejaVu Sans 无 CJK 字形，
    中文会渲染成方块），而实验图常被单独取出放进幻灯片，不应带上字体依赖。
    中文说明见 README。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    keys = list(results["conditions"])
    labels = [f"{key}\n{EN_LABELS.get(results['conditions'][key]['label'], results['conditions'][key]['label'])}"
              for key in keys]

    fig, axes = plt.subplots(1, 3, figsize=(17, 5))

    axes[0].bar(labels, [results["conditions"][k]["deviation"]["mean_abs"] for k in keys],
                color="#4c72b0")
    axes[0].set_title("Aggregate trajectory deviation (vs C0)")
    axes[0].set_ylabel("Mean absolute deviation")

    windows = [lab for lab, _, _ in STAGE_WINDOWS
               if lab in results["conditions"][keys[0]]["reducibility"]["stages"]]
    width = 0.8 / max(1, len(keys))
    positions = np.arange(len(windows))
    for index, key in enumerate(keys):
        values = [results["conditions"][key]["reducibility"]["stages"][lab]["r_squared"] or 0.0
                  for lab in windows]
        axes[1].bar(positions + index * width, values, width, label=key)
    axes[1].set_xticks(positions + 0.4 - width / 2)
    axes[1].set_xticklabels([EN_LABELS.get(lab, lab) for lab in windows], rotation=10)
    axes[1].set_title("Constant-coefficient ODE fit per life stage")
    axes[1].set_ylabel("R²")
    axes[1].set_ylim(0, 1)
    axes[1].legend(fontsize=8)

    axes[2].bar(labels, [results["conditions"][k]["influence"]["overall"]["std_openness"] for k in keys],
                color="#dd8452")
    axes[2].set_title("Temporal variation of susceptibility")
    axes[2].set_ylabel("Susceptibility std")

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
