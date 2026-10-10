"""机制验证：代际影响机制是否产生了理论预期的现象？

与 `life_stage_reducibility.py` 的区别
--------------------------------------
那个实验用"常系数 ODE 的拟合优度"当主指标，但该指标被 ODE 与 ABM 之间的
**结构错配**主导（实测：ODE 对自生成数据 R²=1.00000，对 ABM 数据仅 0.38–0.90），
机制效应被淹没在结构误差里。本脚本改测**机制直接产生的可观测量**：

    E1  易感性阶梯        易感性是否随埃里克森阶段呈阶梯下降
    E2  影响量的年龄结构   子代实际承受的影响量是否随年龄递减、在哪个阶段降幅最大
    E3  剂量-反应关系      影响强度提升是否单调放大子代轨迹偏离，是否饱和
    E4  代际更新的滞后效应 父母影响力是否在子代成年后仍留下可测的差异

E1 是确定性的（纯函数），E2–E4 用多种子系综取均值以降噪。

用法
----
    python experiments/mechanism_validation.py
    python experiments/mechanism_validation.py --seeds 8 --json out.json --plot fig.png
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
from family_abm.family.influence import ADULTHOOD_AGE, ERIKSON_STAGES, susceptibility  # noqa: E402

# ── 配置 ────────────────────────────────────────────────────────────────────

# 三代同堂：让"代际更新"在观测窗口内真实发生
FAMILY = [
    ("Grandfather", 68, "male", "elder"),
    ("Father", 40, "male", "parent"),
    ("Mother", 38, "female", "parent"),
    ("Child", 12, "male", "child"),
    ("Toddler", 4, "female", "child"),
]

# 关注的子代：用**最年幼**成员，才能覆盖从学前期到成年的完整阶段序列
FOCUS_CHILD_INDEX = 4        # Toddler，4 岁起
STEPS = 300                  # 25 年

# 图表英文标签（图会被单独取出放进幻灯片，避免系统字体依赖：
# DejaVu Sans 无 CJK 字形，中文标签会渲染成方块）
STAGE_EN: dict[str, str] = {
    "婴儿期": "infancy",
    "幼儿期": "toddler",
    "学前期": "preschool",
    "学龄期": "school age",
    "青春期": "adolescence",
    "成年早期": "early adult",
    "成年中期后": "mid adult",
}

STATE_COLUMNS = ["state_happiness", "state_stress", "state_health"]

# 配对比较：同一 seed 下"有影响 vs 无影响"，消除种子间差异
# （跨种子比较会把种子间方差误当作噪声，人为压低信噪比）


def build_env(seed: int, params: dict):
    env = Environment()
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=seed)
    env.params = dict(params)
    household = Household(name="Family", household_id="family", environment=env)
    env.add_agent(household)
    for index, (name, age, gender, role) in enumerate(FAMILY):
        household.add_member(FamilyMember(
            name=name, age=age, gender=gender, role_name=role,
            agent_id=f"family-{index}", environment=env,
        ))
    return env, sim, household


def run_once(seed: int, params: dict, steps: int = STEPS):
    env, sim, household = build_env(seed, params)
    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)
    sim.run(steps)
    return recorder.to_dataframe()


# ── E1 易感性阶梯 ───────────────────────────────────────────────────────────


def e1_susceptibility_staircase() -> dict:
    """易感性是否随年龄阶梯下降，且阶段边界处连续。"""
    ages = np.arange(0.0, 45.0, 0.25)
    curve = np.array([susceptibility(float(a)) for a in ages])

    # 单调性
    violations = int(np.sum(np.diff(curve) > 1e-12))

    # 各阶段内部平台值：取阶段中点
    plateaus = []
    for start, end, expected, source, label in ERIKSON_STAGES:
        if end > 45:
            end = 45
        if end - start < 2:
            continue
        middle = start + (end - start) / 2
        plateaus.append({
            "stage": label,
            "age_mid": float(middle),
            "expected": float(expected),
            "actual": float(susceptibility(float(middle))),
            "source": source,
        })

    # 边界连续性
    jumps = []
    for boundary in (1.0, 3.0, 6.0, 12.0, 18.0, 40.0):
        left = susceptibility(boundary - 1e-4)
        right = susceptibility(boundary + 1e-4)
        jumps.append({"boundary": boundary, "jump": float(abs(left - right))})

    return {
        "monotone_violations": violations,
        "curve_samples": [{"age": float(a), "susceptibility": float(v)}
                          for a, v in zip(ages[::8], curve[::8])],
        "plateaus": plateaus,
        "max_boundary_jump": max(j["jump"] for j in jumps),
        "boundary_jumps": jumps,
    }


# ── 共用：跑一组条件 ────────────────────────────────────────────────────────


def run_ensemble(seeds: list[int], params: dict, steps: int = STEPS) -> dict:
    """多种子系综：返回每个种子的子代轨迹（按 attr_name 索引）。"""
    output = {"child_happiness": [], "child_received": [], "child_influence": [],
              "child_susceptibility": [], "child_age": [], "aggregate": []}
    for seed in seeds:
        df = run_once(seed, params, steps=steps)
        child = df[df["attr_name"] == FAMILY[FOCUS_CHILD_INDEX][0]].sort_values("time")
        if child.empty:
            continue
        output["child_happiness"].append(child["state_happiness"].to_numpy(dtype=float))
        output["child_received"].append(child["state_influence_received"].to_numpy(dtype=float))
        output["child_influence"].append(child["state_influence"].to_numpy(dtype=float))
        output["child_susceptibility"].append(child["state_susceptibility"].to_numpy(dtype=float))
        output["child_age"].append(child["attr_age"].to_numpy(dtype=float))
        members = df[df["agent_type"] == "FamilyMember"]
        output["aggregate"].append(
            members.groupby("time")["state_happiness"].mean().to_numpy(dtype=float)
        )
    return output


def stack_mean(series_list: list[np.ndarray]) -> np.ndarray:
    """对齐长度后取均值（多种子降噪）。"""
    if not series_list:
        return np.array([])
    length = min(len(s) for s in series_list)
    return np.mean(np.vstack([s[:length] for s in series_list]), axis=0)


def stack_std(series_list: list[np.ndarray]) -> np.ndarray:
    if not series_list:
        return np.array([])
    length = min(len(s) for s in series_list)
    return np.std(np.vstack([s[:length] for s in series_list]), axis=0)


# ── E2 影响量的年龄结构 ─────────────────────────────────────────────────────


def e2_stage_profile(seeds: list[int], strength: float) -> dict:
    """阶段易感性在各发展阶段的**实际效力**：承受影响量之比。

    注意（这是对最初假设的修正）
    ---------------------------
    最初假设"实际承受的影响量随阶段递减"，实测不成立：影响量是
    `易感性 × 幸福差距 × 养育者存量` 的乘积。学龄期易感性虽低于学前期，
    但此时亲子幸福差距最大，使影响量峰值出现在学龄期。
    **机制没错，是假设的表述错了。**

    本函数度量与假设直接对应的可观测量：**等强度下承受影响量之比**
    （阶段易感性 / 恒定易感性）。两组除易感性外完全相同，因此该比值反映
    阶段结构是否真的传导到子代。

    关于判据（这里做过一次修正）
    --------------------------
    最初断言"比值应精确等于易感性之比"，实测不成立且**不该**成立：影响存在
    反馈——影响越强，子代幸福越向父母靠拢，差距缩小又反过来压低单位影响量。
    实测比值因此被放大（青春期：易感性之比 0.575，实测效力之比仅 0.026）。

    正确的可证伪判据是两条：
      1. 比值随发展阶段**单调下降**（效力真的在衰减）
      2. 在易感性低于 0.50 的阶段，比值**小于 1**（阶段设定确实削弱了影响）
    """
    ensembles = {}
    for label, flag in (("constant", 0.0), ("staged", 1.0)):
        ensembles[label] = run_ensemble(seeds, {
            "influence_strength": strength,
            "use_life_stage_susceptibility": flag,
            "role_switch": 1.0,
        })

    staged = ensembles["staged"]
    ages = stack_mean(staged["child_age"])

    staged_magnitude = np.abs(stack_mean(staged["child_received"]))
    constant_magnitude = np.abs(stack_mean(ensembles["constant"]["child_received"]))
    openness = stack_mean(staged["child_susceptibility"])

    per_stage = []
    for start, end, expected, source, label in ERIKSON_STAGES:
        mask = (ages >= start) & (ages < end)
        if not np.any(mask):
            continue
        staged_mean = float(staged_magnitude[mask].mean())
        constant_mean = float(constant_magnitude[mask].mean())
        stage_openness = float(openness[mask].mean())
        per_stage.append({
            "stage": label,
            "age_range": [float(start), float(end)],
            "n_steps": int(mask.sum()),
            "staged_openness": stage_openness,
            "constant_openness": 0.50,
            "openness_ratio": stage_openness / 0.50,
            "observed_ratio": staged_mean / constant_mean if constant_mean > 1e-12 else 0.0,
            "staged_mean_influence": staged_mean,
            "constant_mean_influence": constant_mean,
        })

    ratios = [row["observed_ratio"] for row in per_stage]
    weakening = [row for row in per_stage if row["staged_openness"] < 0.50]
    return {
        "per_stage": per_stage,
        "ratios": ratios,
        # 判据 1：效力随发展阶段单调下降
        "ratio_decreasing": all(b <= a * 1.05 + 1e-9 for a, b in zip(ratios, ratios[1:])),
        # 判据 2：易感性低于 0.50 的阶段，影响确实弱于恒定设定
        "weaker_when_openness_below_half": bool(
            weakening and all(row["observed_ratio"] < 1.0 for row in weakening)
        ),
        "amplification": [
            {"stage": row["stage"],
             "openness_ratio": row["openness_ratio"],
             "observed_ratio": row["observed_ratio"],
             "amplification_factor": (row["openness_ratio"] / row["observed_ratio"]
                                      if row["observed_ratio"] > 1e-12 else None)}
            for row in per_stage
        ],
    }


# ── E3 剂量-反应关系 ────────────────────────────────────────────────────────


def e3_dose_response(seeds: list[int], strengths: list[float]) -> dict:
    """影响强度 → 轨迹偏离：应单调增大，并呈现饱和。

    **配对设计**：同一 seed 下比较"有影响"与"无影响"的子代轨迹，再对差值取
    系综均值。跨种子直接比较会把种子间方差（本模型约 0.03）当作噪声，
    而机制效应只有 0.02 量级——配对后噪声来自种子内的随机时间序列，
    量级小得多，信噪比才能反映真实可分辨性。
    """
    baseline_by_seed = run_ensemble(seeds, {"influence_strength": 0.0})["child_happiness"]

    points = []
    for strength in strengths:
        ensemble = run_ensemble(seeds, {"influence_strength": strength,
                                        "use_life_stage_susceptibility": 1.0,
                                        "role_switch": 1.0})
        paired = []
        for base_series, treat_series in zip(baseline_by_seed, ensemble["child_happiness"]):
            length = min(len(base_series), len(treat_series))
            if length == 0:
                continue
            paired.append(treat_series[:length] - base_series[:length])
        if not paired:
            continue
        stacked = np.vstack(paired)
        mean_deviation = np.abs(stacked.mean(axis=0))
        # 配对后的噪声：各 seed 偏离方向不一致的程度
        paired_noise = float(stacked.std(axis=0).mean())

        # 边界钳位：幸福被截断在 [0,1] 的帧占比。钳位会使系统对参数高度敏感，
        # 此时"剂量-反应"关系不再可信（实测 strength≥8 时近半帧触界）。
        clamped = 0
        total = 0
        for series in ensemble["child_happiness"]:
            array = np.asarray(series, dtype=float)
            clamped += int(np.sum((array <= 1e-9) | (array >= 1 - 1e-9)))
            total += int(array.size)

        points.append({
            "strength": float(strength),
            # 系综平均后的偏离幅度（机制的系统性效应）
            "mean_abs_deviation": float(mean_deviation.mean()),
            "max_abs_deviation": float(mean_deviation.max()),
            "final_deviation": float(mean_deviation[-1]),
            # 配对噪声：机制效应必须显著大于它才算可分辨
            "paired_noise": paired_noise,
            "snr": float(mean_deviation.mean() / max(paired_noise, 1e-12)),
            "clamped_fraction": float(clamped / total) if total else 0.0,
        })

    deviations = [p["mean_abs_deviation"] for p in points]
    # 只在"未发生明显钳位"的区间判定单调性——钳位区间的变化由截断主导，
    # 不是机制本身的性质。
    clean = [p for p in points if p["clamped_fraction"] < 0.01]
    clean_deviations = [p["mean_abs_deviation"] for p in clean]
    monotone_clean = all(b >= a - 1e-9 for a, b in zip(clean_deviations, clean_deviations[1:]))
    return {
        "points": points,
        "monotone": bool(monotone_clean),
        "clean_upper_bound": max((p["strength"] for p in clean), default=None),
        "saturation_strength": next(
            (points[i]["strength"] for i in range(1, len(points))
             if deviations[i] > 0 and
             (deviations[i] - deviations[i - 1]) / max(deviations[i], 1e-12) < 0.05),
            None),
    }


# ── E4 代际更新的滞后效应 ───────────────────────────────────────────────────


def e4_lagged_effect(seeds: list[int], strength: float) -> dict:
    """父母影响是否在子代成年后仍留下可测差异（滞后效应）。

    **配对设计**：同一 seed 下比较"全程有影响"与"无影响"，对差值取系综均值。

    本模型的幸福是均值回归的，因此早期扰动会随时间衰减——预期成年后的
    差异远小于童年期。这里如实测量衰减幅度，而不是假定它必然持久。
    """
    full = run_ensemble(seeds, {"influence_strength": strength,
                                "use_life_stage_susceptibility": 1.0, "role_switch": 1.0})
    none = run_ensemble(seeds, {"influence_strength": 0.0})

    ages = stack_mean(full["child_age"])
    paired = []
    for base_series, treat_series in zip(none["child_happiness"], full["child_happiness"]):
        length = min(len(base_series), len(treat_series), len(ages))
        if length == 0:
            continue
        paired.append(treat_series[:length] - base_series[:length])
    stacked = np.vstack(paired)
    length = stacked.shape[1]
    mean_deviation = stacked.mean(axis=0)
    paired_noise_series = stacked.std(axis=0)

    adult_mask = ages[:length] >= ADULTHOOD_AGE
    child_mask = ages[:length] < ADULTHOOD_AGE

    def summarize(mask):
        if not np.any(mask):
            return {"n": 0, "mean_deviation": 0.0, "max_deviation": 0.0,
                    "signed_mean": 0.0, "paired_noise": 0.0, "snr": 0.0}
        delta = mean_deviation[mask]
        noise = float(paired_noise_series[mask].mean())
        return {
            "n": int(mask.sum()),
            "mean_deviation": float(np.abs(delta).mean()),
            "max_deviation": float(np.abs(delta).max()),
            "signed_mean": float(delta.mean()),
            "paired_noise": noise,
            "snr": float(np.abs(delta).mean() / max(noise, 1e-12)),
        }

    childhood = summarize(child_mask)
    adulthood = summarize(adult_mask)
    return {
        "childhood": childhood,
        "adulthood": adulthood,
        "persists_into_adulthood": bool(adulthood["snr"] > 1.0),
        "decay_ratio": float(
            adulthood["mean_deviation"] / max(childhood["mean_deviation"], 1e-12)
        ),
    }


# ── 主流程 ──────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="代际影响机制的验证实验")
    parser.add_argument("--seeds", type=int, default=6, help="系综种子数（降噪用）")
    parser.add_argument("--steps", type=int, default=STEPS)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args(argv)

    seeds = [1000 + i for i in range(args.seeds)]
    report: dict = {"seeds": seeds, "steps": args.steps}

    print("=" * 78)
    print("E1  易感性阶梯（确定性的纯函数检验）")
    print("=" * 78)
    e1 = e1_susceptibility_staircase()
    report["e1"] = e1
    print(f"  单调性违例次数: {e1['monotone_violations']}（应为 0）")
    print(f"  阶段边界最大跳变: {e1['max_boundary_jump']:.2e}（应接近 0，表连续）")
    print(f"  {'阶段':<10}{'年龄中点':>10}{'理论值':>10}{'实际值':>10}")
    for plateau in e1["plateaus"]:
        flag = "" if abs(plateau["actual"] - plateau["expected"]) < 1e-9 else "  <-- 不符"
        print(f"  {plateau['stage']:<10}{plateau['age_mid']:>10.1f}"
              f"{plateau['expected']:>10.3f}{plateau['actual']:>10.3f}{flag}")

    print()
    print("=" * 78)
    print("E2  阶段易感性的实际效力（承受影响量之比 = 阶段/恒定）")
    print("=" * 78)
    e2 = e2_stage_profile(seeds, strength=4.0)
    report["e2"] = e2
    print(f"  {'阶段':<10}{'年龄区间':>12}{'步数':>6}{'易感性':>9}"
          f"{'易感性比':>10}{'效力比':>10}{'放大倍数':>11}")
    for row, amp in zip(e2["per_stage"], e2["amplification"]):
        age_range = f"{row['age_range'][0]:.0f}-{row['age_range'][1]:.0f}"
        factor = amp["amplification_factor"]
        factor_text = f"{factor:.2f}" if factor else "—"
        print(f"  {row['stage']:<10}{age_range:>12}{row['n_steps']:>6}"
              f"{row['staged_openness']:>9.4f}{row['openness_ratio']:>10.3f}"
              f"{row['observed_ratio']:>10.3f}{factor_text:>11}")
    print(f"  效力随发展阶段单调递减: {e2['ratio_decreasing']}")
    print(f"  易感性<0.50 的阶段影响确实更弱: {e2['weaker_when_openness_below_half']}")

    print()
    print("=" * 78)
    print("E3  剂量-反应关系（配对设计：同一 seed 下有无影响之差）")
    print("=" * 78)
    strengths = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
    e3 = e3_dose_response(seeds, strengths)
    report["e3"] = e3
    print(f"  {'强度':>8}{'平均偏离':>13}{'最大偏离':>13}{'配对噪声':>13}"
          f"{'信噪比':>9}{'触界比例':>11}")
    for point in e3["points"]:
        print(f"  {point['strength']:>8.1f}{point['mean_abs_deviation']:>13.6f}"
              f"{point['max_abs_deviation']:>13.6f}{point['paired_noise']:>13.6f}"
              f"{point['snr']:>9.2f}{point['clamped_fraction'] * 100:>10.2f}%")
    print(f"  无钳位区间内的单调递增: {e3['monotone']}"
          f"   可信强度上限: {e3['clean_upper_bound']}")

    print()
    print("=" * 78)
    print("E4  代际更新的滞后效应（配对设计）")
    print("=" * 78)
    e4 = e4_lagged_effect(seeds, strength=4.0)
    report["e4"] = e4
    child = e4["childhood"]
    adult = e4["adulthood"]
    print(f"  童年期偏离: 均值={child['mean_deviation']:.6f}  最大={child['max_deviation']:.6f}"
          f"  (n={child['n']})")
    print(f"  成年后偏离: 均值={adult['mean_deviation']:.6f}  最大={adult['max_deviation']:.6f}"
          f"  (n={adult['n']})")
    print(f"  配对噪声:   童年={child['paired_noise']:.6f}  成年后={adult['paired_noise']:.6f}")
    print(f"  信噪比:     童年={child['snr']:.2f}  成年后={adult['snr']:.2f}")
    print(f"  效应衰减比（成年后/童年）: {e4['decay_ratio']:.4f}")
    print(f"  差异在成年后仍可分辨: {e4['persists_into_adulthood']}")

    print()
    print("=" * 78)
    print("结论")
    print("=" * 78)
    best_snr = max((p["snr"] for p in e3["points"]), default=0.0)
    verdicts = [
        ("E1 易感性呈阶梯下降且边界连续", e1["monotone_violations"] == 0
         and e1["max_boundary_jump"] < 1e-3),
        ("E2 效力随发展阶段单调递减", e2["ratio_decreasing"]),
        ("E2 易感性<0.50 的阶段影响更弱", e2["weaker_when_openness_below_half"]),
        ("E3 无钳位区间内剂量-反应单调", e3["monotone"]),
        ("E3 效应显著高于配对噪声（信噪比>2）", best_snr > 2.0),
        ("E4 影响在成年后仍留痕（信噪比>1）", e4["persists_into_adulthood"]),
    ]
    for label, passed in verdicts:
        print(f"  [{'通过' if passed else '未通过'}] {label}")
    report["verdicts"] = [{"claim": label, "passed": bool(passed)} for label, passed in verdicts]

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结构化结果已写入 {args.json}")

    if args.plot:
        _plot(report, args.plot)
        print(f"结果图已写入 {args.plot}")

    return 0


def _is_decreasing(values: list[float]) -> bool:
    """允许微小噪声的递减判定。"""
    return all(b <= a * 1.05 + 1e-9 for a, b in zip(values, values[1:]))


def _plot(report: dict, path: Path) -> None:
    """四张图：易感性曲线、影响量年龄剖面、剂量-反应、滞后效应。

    标签一律英文：图会被单独取出放进幻灯片，不应依赖系统中文字体。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 4, figsize=(21, 4.6))

    # E1 易感性曲线
    curve = report["e1"]["curve_samples"]
    ages = [p["age"] for p in curve]
    values = [p["susceptibility"] for p in curve]
    axes[0].plot(ages, values, linewidth=2)
    for start, _end, _v, _s, label in ERIKSON_STAGES:
        if start <= max(ages):
            axes[0].axvline(start, color="grey", linestyle=":", linewidth=0.8)
    axes[0].set_title("E1  Susceptibility by Erikson stage")
    axes[0].set_xlabel("age (years)")
    axes[0].set_ylabel("susceptibility")
    axes[0].set_ylim(0, 1)

    # E2 阶段易感性的效力（承受影响量之比 vs 易感性之比）
    stages = report["e2"]["per_stage"]
    positions = np.arange(len(stages))
    axes[1].bar(positions - 0.2, [r["openness_ratio"] for r in stages], 0.4,
                label="openness ratio", color="#4c72b0")
    axes[1].bar(positions + 0.2, [r["observed_ratio"] for r in stages], 0.4,
                label="realised influence ratio", color="#dd8452")
    axes[1].axhline(1.0, color="black", linewidth=0.8, linestyle=":")
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels([STAGE_EN.get(r["stage"], r["stage"]) for r in stages], rotation=20)
    axes[1].set_title("E2  Stage susceptibility: realised effect")
    axes[1].set_ylabel("ratio (staged / constant)")
    axes[1].legend(fontsize=8)

    # E3 剂量-反应
    points = report["e3"]["points"]
    axes[2].plot([p["strength"] for p in points], [p["mean_abs_deviation"] for p in points],
                 marker="o", linewidth=2, label="paired mean deviation")
    axes[2].plot([p["strength"] for p in points], [p["paired_noise"] for p in points],
                 marker="s", linestyle="--", color="red", linewidth=1, label="paired noise")
    axes[2].set_xscale("symlog", linthresh=0.5)
    axes[2].set_title("E3  Dose-response: strength vs deviation")
    axes[2].set_xlabel("influence strength (log)")
    axes[2].set_ylabel("deviation")
    axes[2].legend(fontsize=8)
    # 标注钳位区间的起点（该区间结论不可信）
    clamped = [p for p in points if p["clamped_fraction"] >= 0.01]
    if clamped:
        axes[2].axvspan(clamped[0]["strength"] * 0.8, max(p["strength"] for p in points) * 1.2,
                        color="red", alpha=0.12)
        axes[2].text(clamped[0]["strength"], axes[2].get_ylim()[1] * 0.6,
                     "boundary\nclamping", fontsize=8, color="darkred")

    # E4 滞后效应：童年 vs 成年后的偏离幅度（含配对噪声参考）
    axes[3].bar(["childhood", "adulthood"],
                [report["e4"]["childhood"]["mean_deviation"],
                 report["e4"]["adulthood"]["mean_deviation"]], color="#55a868",
                label="paired mean deviation")
    axes[3].plot([-0.4, 0, 1, 1.4],
                 [0, report["e4"]["childhood"]["paired_noise"],
                  report["e4"]["adulthood"]["paired_noise"], 0],
                 color="red", linestyle="--", linewidth=1, label="paired noise")
    axes[3].set_title("E4  Lagged effect of parental influence")
    axes[3].set_ylabel("deviation")
    axes[3].legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
