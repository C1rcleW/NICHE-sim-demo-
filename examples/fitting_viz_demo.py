"""
Comprehensive demo: run ABM, fit Lanchester-type ODE models, visualize results.
"""
import numpy as np
from family_abm import (
    Environment, Simulation, Scheduler,
    FamilyMember, Household, StateRecorder, FeatureExtractor,
    MicroNiche, ResourceBundle,
    make_fitter, wellbeing_balance, solve_model,
    plot_timeseries, plot_phase_portrait, plot_niche_space,
    plot_family_network, plot_fit_diagnostics, plot_aggregate,
    plot_agent_comparison,
)
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def build_household(env: Environment, name: str, members: list[dict]) -> Household:
    hh = Household(name=f"{name} Household", environment=env)
    env.add_agent(hh)
    for cfg in members:
        hh.add_member(FamilyMember(environment=env, **cfg))
    return hh


def run_simulation(steps: int = 120) -> tuple[Simulation, StateRecorder]:
    env = Environment()
    # 先建立随机数上下文，使整次仿真可复现
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=42)

    # Household A — two parents, one child
    build_household(env, "Zhang", [
        {"name": "Father", "age": 42, "gender": "male", "role_name": "parent"},
        {"name": "Mother", "age": 40, "gender": "female", "role_name": "parent"},
        {"name": "Child",  "age": 12, "gender": "male", "role_name": "child"},
    ])

    # Household B — single parent, one child
    build_household(env, "Li", [
        {"name": "Mom",   "age": 35, "gender": "female", "role_name": "parent"},
        {"name": "Daughter", "age": 8, "gender": "female", "role_name": "child"},
    ])

    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)
    sim.run(steps)
    return sim, recorder


# ═══════════════════════════════════════════════════════════════════════════
# 1. BASIC TIME SERIES VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════
def demo_basic_plots(df: pd.DataFrame):
    print("[1/5] Basic time series & aggregate plots ...")

    fig = plot_timeseries(df, title="All Agents — Happiness")
    fig.savefig(str(OUTPUT_DIR / "01_timeseries.png"), dpi=150)
    plt_close(fig)

    fig = plot_aggregate(df, title="Population Aggregate")
    fig.savefig(str(OUTPUT_DIR / "02_aggregate.png"), dpi=150)
    plt_close(fig)

    # Phase portrait for one agent
    child_id = df[df["attr_name"] == "Child"]["agent_id"].iloc[0]
    fig = plot_phase_portrait(df, agent_id=child_id,
                              title=f"Child — Happiness vs Stress")
    fig.savefig(str(OUTPUT_DIR / "03_phase_portrait.png"), dpi=150)
    plt_close(fig)

    # Agent comparison
    fig = plot_agent_comparison(df, state="state_happiness",
                                title="Happiness Comparison")
    fig.savefig(str(OUTPUT_DIR / "04_comparison.png"), dpi=150)
    plt_close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 2. NICHE SPACE VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════
def demo_niche_plots(env: Environment, df: pd.DataFrame):
    print("[2/5] Niche space visualization ...")

    niches: dict[str, MicroNiche] = {}
    for agent in env.get_agents():
        if isinstance(agent, FamilyMember):
            n = MicroNiche(niche_id=agent.id,
                           dimensions=["economic", "cultural", "social", "emotional"])
            # Grab final state from the last record
            rec = df[df["agent_id"] == agent.id].iloc[-1]
            agent_state = {
                "income": rec.get("state_income", 0),
                "education": rec.get("state_education", 0.5),
                "social_capital": rec.get("state_social_capital", 0.5),
                "happiness": rec.get("state_happiness", 0.5),
            }
            n.update_from_agent_state(agent_state)
            niches[agent.id] = n

    labels = {}
    for agent in env.get_agents():
        if isinstance(agent, FamilyMember):
            labels[agent.id] = agent.get_attribute("name")

    fig = plot_niche_space(niches, dims=["economic", "cultural", "social"],
                           labels=labels, title="Social Micro-Niche Positions")
    fig.savefig(str(OUTPUT_DIR / "05_niche_3d.png"), dpi=150)
    plt_close(fig)

    fig = plot_niche_space(niches, dims=["economic", "emotional"],
                           labels=labels, title="Economic vs Emotional Niche")
    fig.savefig(str(OUTPUT_DIR / "06_niche_2d.png"), dpi=150)
    plt_close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 3. FAMILY NETWORK
# ═══════════════════════════════════════════════════════════════════════════
def demo_network_plot(env: Environment):
    print("[3/5] Family relationship network ...")

    for agent in env.get_agents():
        if isinstance(agent, Household):
            fig = plot_family_network(agent, title=f"{agent.get_attribute('name')} Network")
            fig.savefig(str(OUTPUT_DIR / "07_network.png"), dpi=150)
            plt_close(fig)
            break


# ═══════════════════════════════════════════════════════════════════════════
# 4. ODE FITTING — Lanchester-type models
# ═══════════════════════════════════════════════════════════════════════════
def demo_fitting(df: pd.DataFrame):
    print("[4/5] ODE fitting with Lanchester-type models ...")

    # Pick the Child agent to fit
    child_id = df[df["attr_name"] == "Child"]["agent_id"].iloc[0]
    print(f"  Fitting to agent: Child ({child_id[:8]}...)")

    # —— Model A: wellbeing_balance (happiness-stress Lanchester system) ——
    fitter_wb = make_fitter("wellbeing")
    fitter_wb.fit_from_dataframe(
        df, agent_id=child_id,
        p0=[0.3, 0.5, 0.4, 0.2, 0.5],
        bounds=[(0, 5), (0, 5), (0, 5), (0, 5), (0, 2)],
    )
    print(f"  [wellbeing]  params={fitter_wb.fitted_param_dict}")
    print(f"  [wellbeing]  R^2={fitter_wb.r_squared:.4f}")

    fig = plot_fit_diagnostics(df, fitter_wb, agent_id=child_id,
                               title="Wellbeing Model — Child")
    fig.savefig(str(OUTPUT_DIR / "08_fit_wellbeing.png"), dpi=150)
    plt_close(fig)

    # —— Model B: social_influence (opinion dynamics) ——
    # Map ODE states O1/O2 to actual ABM columns
    fitter_inf = make_fitter("influence",
                             state_mapping={"O1": "state_happiness", "O2": "state_stress"})
    fitter_inf.fit_from_dataframe(
        df, agent_id=child_id,
        p0=[0.3, 0.1],
        bounds=[(0, 5), (0, 5)],
    )
    print(f"  [influence]  params={fitter_inf.fitted_param_dict}")
    print(f"  [influence]  R^2={fitter_inf.r_squared:.4f}")

    fig = plot_fit_diagnostics(df, fitter_inf, agent_id=child_id,
                               title="Influence Model — Child")
    fig.savefig(str(OUTPUT_DIR / "09_fit_influence.png"), dpi=150)
    plt_close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 5. SOLVE ODE FORWARD / WHAT-IF SCENARIO
# ═══════════════════════════════════════════════════════════════════════════
def demo_forecast(df: pd.DataFrame):
    print("[5/5] Forward simulation of fitted model ...")

    child_id = df[df["attr_name"] == "Child"]["agent_id"].iloc[0]
    sub = df[df["agent_id"] == child_id].sort_values("time")
    t = np.linspace(0, 50, 200)

    # Scenario A: low income (0.3)
    y0 = [0.7, 0.3]
    t_a, y_a = solve_model(wellbeing_balance, y0, t,
                           params=[0.3, 0.5, 0.4, 0.2, 0.3])

    # Scenario B: high income (0.9)
    t_b, y_b = solve_model(wellbeing_balance, y0, t,
                           params=[0.3, 0.5, 0.4, 0.2, 0.9])

    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)

    axes[0].plot(t_a, y_a[0], label="Happiness", lw=2)
    axes[0].plot(t_a, y_a[1], label="Stress", lw=2, ls="--")
    axes[0].set_title("Low Income (0.3) — What-if")
    axes[0].set_xlabel("Time")
    axes[0].legend()

    axes[1].plot(t_b, y_b[0], label="Happiness", lw=2)
    axes[1].plot(t_b, y_b[1], label="Stress", lw=2, ls="--")
    axes[1].set_title("High Income (0.9) — What-if")
    axes[1].set_xlabel("Time")
    axes[1].legend()

    fig.suptitle("Wellbeing Model — What-if Scenario Analysis", y=1.02)
    fig.tight_layout()
    fig.savefig(str(OUTPUT_DIR / "10_forecast.png"), dpi=150)
    plt_close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def plt_close(fig):
    import matplotlib.pyplot as plt
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 55)
    print("  Family ABM — Fitting & Visualization Demo")
    print("=" * 55)

    print("\nRunning ABM simulation (120 steps) ...")
    sim, recorder = run_simulation(steps=120)
    df = recorder.to_dataframe()
    print(f"  Recorded {len(df)} observations across {df['agent_id'].nunique()} agents\n")

    demo_basic_plots(df)
    demo_niche_plots(sim.environment, df)
    demo_network_plot(sim.environment)
    demo_fitting(df)
    demo_forecast(df)

    print(f"\n{'=' * 55}")
    print(f"  All outputs saved to: {OUTPUT_DIR}")
    print(f"  Files:")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        print(f"    {f.name}")
    print("=" * 55)


if __name__ == "__main__":
    main()
