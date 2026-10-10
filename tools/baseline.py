"""基线快照：固定种子跑一次仿真，导出可比较的统计摘要。

用途（P0-3）：
- 任何"校准/结构"改动之后，用 `--check` 对比基线，把不可见的行为变化显式暴露出来；
- 仿真通过 `Simulation(seed=...)` 注入独立 RNG（0.2.0 起），因此同一 seed
  跨进程、跨机器都可复现，无需调用方手动播种全局 `random`。

用默认模型参数（DEFAULT_PARAMS）与默认家庭结构，保证跨机器可复现。

用法：
    python tools/baseline.py --out baseline/default_seed42.json
    python tools/baseline.py --check baseline/default_seed42.json

`baseline/default_seed42.json` 是**纳入版本控制的锚点**，用于在任何校准/结构改动
之后显式暴露不可见的行为变化。若改动是有意的，重新固化并在提交信息里说明：

    python -X utf8 tools/baseline.py --out baseline/default_seed42.json

退出码：0 = 成功/一致，1 = 与基线不一致或发生错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许直接以脚本方式运行（python tools/baseline.py）而无需先安装
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from family_abm import (
    Environment,
    FamilyMember,
    Household,
    Scheduler,
    Simulation,
    StateRecorder,
)

DEFAULT_SEED = 42
DEFAULT_STEPS = 120
DEFAULT_FAMILIES = [
    ("Smith", [("Father", 40, "male", "parent"), ("Mother", 38, "female", "parent"), ("Child", 10, "male", "child")]),
    ("Jones", [("Mom", 35, "female", "parent"), ("Daughter", 8, "female", "child")]),
]


def build_environment(env: Environment) -> Environment:
    for household_name, members in DEFAULT_FAMILIES:
        household = Household(name=f"{household_name} Household", environment=env)
        env.add_agent(household)
        for name, age, gender, role_name in members:
            household.add_member(FamilyMember(name=name, age=age, gender=gender,
                                              role_name=role_name, environment=env))
    return env


def _round(value: float, digits: int = 6) -> float:
    return float(round(float(value), digits))


def collect_stats(recorder: StateRecorder) -> dict:
    """按 agent_type 分组，统计每个数值列的 mean/std/min/max。"""
    df = recorder.to_dataframe()
    stats: dict[str, dict] = {}
    for agent_type, group in df.groupby("agent_type", sort=True):
        numeric = group.select_dtypes(include=[np.number]).drop(columns=["time"], errors="ignore")
        columns: dict[str, dict] = {}
        for column in sorted(numeric.columns):
            series = numeric[column].dropna()
            if series.empty:
                continue
            columns[column] = {
                "n": int(series.size),
                "mean": _round(series.mean()),
                "std": _round(series.std(ddof=0)),
                "min": _round(series.min()),
                "max": _round(series.max()),
            }
        stats[str(agent_type)] = {"rows": len(group), "columns": columns}
    return {
        "rows": len(df),
        "time_min": int(df["time"].min()) if not df.empty else None,
        "time_max": int(df["time"].max()) if not df.empty else None,
        "agents": stats,
    }


def run(seed: int, steps: int) -> dict:
    env = Environment()
    # 先注入 RNG，再建智能体：这样初始化与演化都来自同一条可复现随机流
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=seed)
    build_environment(env)
    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)
    sim.run(steps)
    return collect_stats(recorder)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="family_abm 基线快照")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--out", type=Path, help="写出基线 JSON")
    parser.add_argument("--check", type=Path, help="与既有基线 JSON 对比")
    args = parser.parse_args(argv)

    if not args.out and not args.check:
        args.out = Path("baseline/default_seed42.json")
        print(f"未指定 --out/--check，默认写入 {args.out}")

    try:
        summary = run(args.seed, args.steps)
    except Exception as exc:
        print(f"[FAIL] 仿真执行失败：{type(exc).__name__}: {exc}")
        return 1

    payload = {"seed": args.seed, "steps": args.steps, "summary": summary}
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded + "\n", encoding="utf-8")
        print(f"[OK] 基线已写入 {args.out}（rows={summary['rows']}, time=[{summary['time_min']}..{summary['time_max']}]）")

    if args.check:
        if not args.check.is_file():
            print(f"[FAIL] 基线文件不存在：{args.check}")
            return 1
        expected = json.loads(args.check.read_text(encoding="utf-8"))
        if expected == payload:
            print(f"[OK] 与基线一致：{args.check}")
            return 0
        print(f"[FAIL] 与基线不一致：{args.check}")
        _report_diff(expected.get("summary", {}), summary)
        return 1

    return 0


def _report_diff(expected: dict, actual: dict, max_items: int = 10) -> None:
    shown = 0
    exp_cols = expected.get("agents", {})
    act_cols = actual.get("agents", {})
    for agent_type in sorted(set(exp_cols) | set(act_cols)):
        exp = exp_cols.get(agent_type, {}).get("columns", {})
        act = act_cols.get(agent_type, {}).get("columns", {})
        for column in sorted(set(exp) | set(act)):
            if exp.get(column) != act.get(column):
                print(f"  - {agent_type}.{column}")
                print(f"      baseline: {exp.get(column)}")
                print(f"      current : {act.get(column)}")
                shown += 1
                if shown >= max_items:
                    print(f"  ...（仅显示前 {max_items} 项）")
                    return


if __name__ == "__main__":
    raise SystemExit(main())
