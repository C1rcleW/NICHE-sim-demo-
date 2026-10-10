"""敏感性分析：机制验证的结论对关键参数的依赖程度。

为什么需要
----------
阶段易感性曲线的取值取自埃里克森阶段理论的**含义**，不是实证测量值；阶段年龄
边界同样没有权威精确值。评委必然追问："你的参数是拍的，结论可靠吗？"

本脚本把这条质疑变成一个可回答的问题：扰动这些参数，逐个检验机制验证实验
（`mechanism_validation.py`）的四条结论是否依然成立，并报告结论的成立范围。

被扰动的参数
------------
- ``stage_shift_years``       所有阶段边界整体±N 年（埃里克森未给精确年龄）
- ``susceptibility_scale``    易感性曲线整体缩放（阶段取值未知）
- ``influence_strength``      影响强度（机制强度本身未知）

被检验的结论（来自机制验证实验）
--------------------------------
- P1  易感性呈阶梯下降且边界连续（确定性，只需检验曲线本身）
- P2  效力比随发展阶段单调递减
- P3  易感性 < 0.50 的阶段，影响确实弱于恒定设定
- P4  无边界钳位区间内，剂量-反应单调
- P5  早期影响在成年后仍可分辨

用法
----
    python experiments/sensitivity_analysis.py
    python experiments/sensitivity_analysis.py --seeds 3 --json out.json --plot fig.png
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 复用机制验证实验的仿真与度量，避免两套实现漂移
from experiments.mechanism_validation import (  # noqa: E402
    STEPS,
    e2_stage_profile,
    e3_dose_response,
    e4_lagged_effect,
    susceptibility,
)

# ── 扰动范围 ────────────────────────────────────────────────────────────────

SHIFTS = [-3.0, -2.0, 0.0, 2.0, 3.0]
SCALES = [0.70, 0.85, 1.00, 1.15, 1.30]
STRENGTHS = [1.0, 2.0, 4.0]

# 每条结论的判定阈值
SNR_THRESHOLD = 1.0
CLAMP_LIMIT = 0.01

# P2 需要子代在观测窗口内走完足够多的阶段（见 main 中的护栏）
MIN_STEPS_FOR_STAGE_COVERAGE = 300


def p1_curve_properties(shift: float, scale: float) -> dict:
    """P1：易感性阶梯是否仍单调不增、边界是否仍连续。"""
    ages = np.arange(0.0, 60.0, 0.25)
    curve = np.array([susceptibility(float(a), scale=scale, shift=shift) for a in ages])
    violations = int(np.sum(np.diff(curve) > 1e-12))

    jumps = []
    for boundary in (1.0, 3.0, 6.0, 12.0, 18.0, 40.0):
        # 边界随 shift 平移
        shifted = boundary + shift
        if shifted <= 0.5:
            continue
        left = susceptibility(shifted - 1e-4, scale=scale, shift=shift)
        right = susceptibility(shifted + 1e-4, scale=scale, shift=shift)
        jumps.append(abs(left - right))

    max_jump = max(jumps) if jumps else 0.0
    return {
        "monotone_violations": violations,
        "max_boundary_jump": float(max_jump),
        "max_susceptibility": float(curve.max()),
        "min_susceptibility": float(curve.min()),
        "passed": violations == 0 and max_jump < 1e-3,
    }


def p2_p3_stage_ratios(seeds: list[int], shift: float, scale: float, strength: float) -> dict:
    """P2/P3：效力比是否随阶段单调递减、易感性<0.50 的阶段是否更弱。"""
    params = {"stage_shift_years": shift, "susceptibility_scale": scale}
    e2 = e2_stage_profile(seeds, strength=strength, extra_params=params)
    return {
        "ratios": e2["ratios"],
        "stages": [row["stage"] for row in e2["per_stage"]],
        "openness": [row["staged_openness"] for row in e2["per_stage"]],
        "p2_decreasing": e2["ratio_decreasing"],
        "p3_weaker_below_half": e2["weaker_when_openness_below_half"],
    }


def p4_dose_response(seeds: list[int], shift: float, scale: float) -> dict:
    """P4：无钳位区间内剂量-反应是否单调、可信强度上限是多少。"""
    params = {"stage_shift_years": shift, "susceptibility_scale": scale}
    e3 = e3_dose_response(seeds, [0.0, 0.5, 1.0, 2.0, 4.0, 8.0], extra_params=params)
    best_snr = max((p["snr"] for p in e3["points"]), default=0.0)
    clamped = [p for p in e3["points"] if p["clamped_fraction"] >= CLAMP_LIMIT]
    return {
        "monotone": e3["monotone"],
        "clean_upper_bound": e3["clean_upper_bound"],
        "best_snr": best_snr,
        "first_clamped_strength": clamped[0]["strength"] if clamped else None,
        "passed": bool(e3["monotone"] and best_snr > 2.0),
    }


def p5_lagged(seeds: list[int], shift: float, scale: float, strength: float) -> dict:
    """P5：早期影响在成年后是否仍可分辨。"""
    params = {"stage_shift_years": shift, "susceptibility_scale": scale}
    e4 = e4_lagged_effect(seeds, strength=strength, extra_params=params)
    return {
        "childhood_snr": e4["childhood"]["snr"],
        "adulthood_snr": e4["adulthood"]["snr"],
        "decay_ratio": e4["decay_ratio"],
        "passed": e4["persists_into_adulthood"],
    }


# ── 主流程 ──────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="机制验证结论的敏感性分析")
    parser.add_argument("--seeds", type=int, default=3, help="每个参数组合的种子数")
    parser.add_argument("--steps", type=int, default=STEPS)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args(argv)

    # P2 需要子代在观测窗口内走完足够多的阶段：最年幼成员 4 岁起步，
    # 覆盖学前期→学龄期→青春期→成年早期需要约 300 步（25 年）。
    # 窗口过短时"效力比随阶段递减"本身欠定义，却会产出一份看似"不稳健"的报告，
    # 因此在这里直接拒绝，而不是静默继续。
    if args.steps < MIN_STEPS_FOR_STAGE_COVERAGE:
        raise SystemExit(
            f"--steps 至少需要 {MIN_STEPS_FOR_STAGE_COVERAGE}（当前 {args.steps}）："
            "子代必须走完足够的生命阶段，P2（效力比随阶段递减）才有定义。"
        )

    seeds = [1000 + i for i in range(args.seeds)]
    report: dict = {"seeds": seeds, "steps": args.steps, "runs": []}

    print("=" * 82)
    print("P1  易感性阶梯的曲线性质（确定性，逐参数组合）")
    print("=" * 82)
    print(f"  {'平移(年)':>10}{'缩放':>8}{'单调违例':>10}{'边界跳变':>12}"
          f"{'最大易感性':>12}{'判定':>8}")
    p1_results = []
    for shift, scale in itertools.product(SHIFTS, SCALES):
        result = p1_curve_properties(shift, scale)
        p1_results.append({"shift": shift, "scale": scale, **result})
        print(f"  {shift:>10.1f}{scale:>8.2f}{result['monotone_violations']:>10}"
              f"{result['max_boundary_jump']:>12.2e}{result['max_susceptibility']:>12.3f}"
              f"{'通过' if result['passed'] else '未通过':>8}")
    report["p1"] = p1_results
    p1_all_pass = all(r["passed"] for r in p1_results)

    print()
    print("=" * 82)
    print("P2/P3  效力比的阶段结构（按 平移 × 缩放 扫描，强度=4）")
    print("=" * 82)
    print(f"  {'平移':>6}{'缩放':>7}{'效力比序列':>42}{'P2递减':>8}{'P3更弱':>8}")
    p23_results = []
    for shift, scale in itertools.product(SHIFTS, SCALES):
        result = p2_p3_stage_ratios(seeds, shift, scale, strength=4.0)
        p23_results.append({"shift": shift, "scale": scale, **result})
        ratios = " ".join(f"{r:.3f}" for r in result["ratios"])
        print(f"  {shift:>6.1f}{scale:>7.2f}{ratios:>42}"
              f"{'✓' if result['p2_decreasing'] else '✗':>8}"
              f"{'✓' if result['p3_weaker_below_half'] else '✗':>8}")
    report["p2_p3"] = p23_results
    p2_all_pass = all(r["p2_decreasing"] for r in p23_results)
    p3_all_pass = all(r["p3_weaker_below_half"] for r in p23_results)

    print()
    print("=" * 82)
    print("P4  剂量-反应的单调性与可信强度上限")
    print("=" * 82)
    print(f"  {'平移':>6}{'缩放':>7}{'单调':>8}{'可信上限':>10}{'最佳信噪比':>12}"
          f"{'首个钳位强度':>14}{'判定':>8}")
    p4_results = []
    for shift, scale in itertools.product(SHIFTS, SCALES):
        result = p4_dose_response(seeds, shift, scale)
        p4_results.append({"shift": shift, "scale": scale, **result})
        bound = result["clean_upper_bound"]
        clamp = result["first_clamped_strength"]
        print(f"  {shift:>6.1f}{scale:>7.2f}{'✓' if result['monotone'] else '✗':>8}"
              f"{(f'{bound:.1f}' if bound is not None else '—'):>10}"
              f"{result['best_snr']:>12.2f}"
              f"{(f'{clamp:.1f}' if clamp is not None else '无'):>14}"
              f"{'通过' if result['passed'] else '未通过':>8}")
    report["p4"] = p4_results
    p4_all_pass = all(r["passed"] for r in p4_results)

    print()
    print("=" * 82)
    print("P5  成年后留痕（按 平移 × 缩放 × 强度 扫描）")
    print("=" * 82)
    print(f"  {'平移':>6}{'缩放':>7}{'强度':>7}{'童年信噪比':>12}{'成年信噪比':>12}"
          f"{'衰减比':>10}{'判定':>8}")
    p5_results = []
    for shift, scale, strength in itertools.product(SHIFTS, SCALES, STRENGTHS):
        result = p5_lagged(seeds, shift, scale, strength)
        p5_results.append({"shift": shift, "scale": scale, "strength": strength, **result})
        print(f"  {shift:>6.1f}{scale:>7.2f}{strength:>7.1f}"
              f"{result['childhood_snr']:>12.2f}{result['adulthood_snr']:>12.2f}"
              f"{result['decay_ratio']:>10.4f}"
              f"{'通过' if result['passed'] else '未通过':>8}")
    report["p5"] = p5_results
    p5_pass_rate = sum(1 for r in p5_results if r["passed"]) / max(1, len(p5_results))

    print()
    print("=" * 82)
    print("汇总：结论的稳健性")
    print("=" * 82)
    summary = [
        ("P1 易感性阶梯单调且连续", f"{sum(1 for r in p1_results if r['passed'])}/{len(p1_results)}"),
        ("P2 效力比随阶段单调递减", f"{sum(1 for r in p23_results if r['p2_decreasing'])}/{len(p23_results)}"),
        ("P3 易感性<0.5 阶段影响更弱", f"{sum(1 for r in p23_results if r['p3_weaker_below_half'])}/{len(p23_results)}"),
        ("P4 剂量-反应单调且信噪比>2", f"{sum(1 for r in p4_results if r['passed'])}/{len(p4_results)}"),
        ("P5 成年后留痕", f"{sum(1 for r in p5_results if r['passed'])}/{len(p5_results)}"),
    ]
    for label, tally in summary:
        print(f"  {label:<34}{tally:>10}")

    bounds = sorted({r["clean_upper_bound"] for r in p4_results if r["clean_upper_bound"] is not None})
    print(f"\n  可信强度上限的取值范围: {bounds[0]:.1f} ~ {bounds[-1]:.1f}"
          if bounds else "\n  未测得可信强度上限")

    robust = {
        "p1_all_pass": p1_all_pass,
        "p2_all_pass": p2_all_pass,
        "p3_all_pass": p3_all_pass,
        "p4_all_pass": p4_all_pass,
        "p5_pass_rate": p5_pass_rate,
    }
    report["summary"] = {"robustness": robust, "tallies": dict(summary),
                         "clean_upper_bound_range": bounds}

    print()
    print("=" * 82)
    print("结论")
    print("=" * 82)
    verdicts = [
        (f"P1 在全部 {len(p1_results)} 个参数组合下成立", p1_all_pass),
        (f"P2 在全部 {len(p23_results)} 个参数组合下成立", p2_all_pass),
        (f"P3 在全部 {len(p23_results)} 个参数组合下成立", p3_all_pass),
        (f"P4 在全部 {len(p4_results)} 个参数组合下成立", p4_all_pass),
        (f"P5 在 {p5_pass_rate * 100:.0f}% 的参数组合下成立", p5_pass_rate > 0.9),
    ]
    for label, passed in verdicts:
        print(f"  [{'稳健' if passed else '不稳健'}] {label}")
    report["verdicts"] = [{"claim": label, "robust": bool(passed)} for label, passed in verdicts]

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结构化结果已写入 {args.json}")

    if args.plot:
        _plot(report, args.plot)
        print(f"结果图已写入 {args.plot}")

    return 0


def _plot(report: dict, path: Path) -> None:
    """四张图：P1 通过数、P2 效力比热图、P4 可信上限、P5 通过率。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 4, figsize=(21, 4.6))

    # P1：单调违例数（全部应为 0）
    p1 = report["p1"]
    axes[0].scatter([r["scale"] for r in p1], [r["shift"] for r in p1],
                    c=[r["monotone_violations"] for r in p1], s=90, cmap="OrRd")
    axes[0].set_title("P1  Monotonicity violations")
    axes[0].set_xlabel("susceptibility scale")
    axes[0].set_ylabel("stage shift (years)")

    # P2：效力比热图（最后一阶段，即成年早期）
    p23 = report["p2_p3"]
    scales = sorted({r["scale"] for r in p23})
    shifts = sorted({r["shift"] for r in p23})
    grid = np.full((len(shifts), len(scales)), np.nan)
    for row in p23:
        i = shifts.index(row["shift"])
        j = scales.index(row["scale"])
        grid[i, j] = row["ratios"][-1] if row["ratios"] else np.nan
    image = axes[1].imshow(grid, aspect="auto", cmap="viridis", origin="lower")
    axes[1].set_xticks(range(len(scales)))
    axes[1].set_xticklabels([f"{s:.2f}" for s in scales])
    axes[1].set_yticks(range(len(shifts)))
    axes[1].set_yticklabels([f"{s:+.0f}" for s in shifts])
    axes[1].set_title("P2  Realised ratio, early adulthood")
    axes[1].set_xlabel("susceptibility scale")
    axes[1].set_ylabel("stage shift (years)")
    fig.colorbar(image, ax=axes[1], fraction=0.046)

    # P4：可信强度上限
    p4 = report["p4"]
    axes[2].scatter([r["scale"] for r in p4], [r["shift"] for r in p4],
                    c=[r["clean_upper_bound"] or 0.0 for r in p4], s=90, cmap="Blues")
    axes[2].set_title("P4  Trustworthy strength upper bound")
    axes[2].set_xlabel("susceptibility scale")
    axes[2].set_ylabel("stage shift (years)")

    # P5：通过率（按强度分组）
    p5 = report["p5"]
    strengths = sorted({r["strength"] for r in p5})
    rates = []
    for strength in strengths:
        subset = [r for r in p5 if r["strength"] == strength]
        rates.append(sum(1 for r in subset if r["passed"]) / max(1, len(subset)))
    axes[3].bar([f"{s:.1f}" for s in strengths], rates, color="#55a868")
    axes[3].set_ylim(0, 1.05)
    axes[3].set_title("P5  Pass rate by influence strength")
    axes[3].set_xlabel("influence strength")
    axes[3].set_ylabel("pass rate")

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
