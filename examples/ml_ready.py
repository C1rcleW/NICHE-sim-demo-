"""
Advanced example: Multiple households with ML-ready data recording.
Shows how to extract features for downstream machine learning tasks.
"""
import numpy as np
from family_abm import (
    Environment, Simulation, Scheduler,
    FamilyMember, Household, StateRecorder, FeatureExtractor,
    MicroNiche, ResourceBundle, InfluenceRelation,
)


def create_family(env: Environment, name: str, members_config: list[dict]) -> Household:
    hh = Household(name=f"{name} Household", environment=env)
    env.add_agent(hh)
    for cfg in members_config:
        member = FamilyMember(environment=env, **cfg)
        hh.add_member(member)
    return hh


def main():
    env = Environment()
    # 先建立随机数上下文，使整次仿真（含成员初始化）可复现
    sim = Simulation(env, scheduler=Scheduler("random"), seed=42)

    # Create two households
    create_family(env, "Smith", [
        {"name": "Alice", "age": 35, "gender": "female", "role_name": "parent"},
        {"name": "Bob", "age": 37, "gender": "male", "role_name": "parent"},
        {"name": "Charlie", "age": 9, "gender": "male", "role_name": "child"},
    ])
    create_family(env, "Jones", [
        {"name": "Diana", "age": 32, "gender": "female", "role_name": "parent"},
        {"name": "Eve", "age": 7, "gender": "female", "role_name": "child"},
    ])

    # Micro-niche tracking
    niches: dict[str, MicroNiche] = {}
    for agent in env.get_agents():
        if isinstance(agent, FamilyMember):
            n = MicroNiche(niche_id=agent.id)
            n.update_from_agent_state(agent.state)
            niches[agent.id] = n

    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)

    sim.run(steps=240)

    # --- Feature extraction for ML ---
    extractor = FeatureExtractor(recorder)

    df_panel = extractor.build_agent_panel()
    print("Panel shape:", df_panel.shape)
    print("Columns:", list(df_panel.columns), "\n")

    # Predict next-step happiness (supervised learning target)
    X, y = extractor.extract_features(
        feature_columns=[c for c in df_panel.columns if c.startswith("state_") and c != "state_happiness"],
        target_column="state_happiness",
        lag_steps=1,
    )
    print(f"Feature matrix shape: {X.shape}, target shape: {y.shape if y is not None else 'N/A'}")

    # Transition dataset for Markov / sequence models
    trans_df = extractor.build_transition_dataset(lag=1)
    print(f"Transition records: {len(trans_df)}")
    print(trans_df.head())

    # Aggregated features per agent (for clustering / classification)
    agg_df = extractor.build_network_features()
    print("\nAggregated features per agent:")
    print(agg_df.head())

    # Niche analysis
    print("\n--- Niche analysis ---")
    for agent in env.get_agents():
        if isinstance(agent, FamilyMember) and agent.id in niches:
            n = niches[agent.id]
            n.update_from_agent_state(agent.state)
            print(f"  {agent.get_attribute('name')}: {n.position}")

    if len(niches) >= 2:
        ids = list(niches.keys())
        d = niches[ids[0]].distance_to(niches[ids[1]])
        o = niches[ids[0]].overlap(niches[ids[1]])
        print(f"\nNiche distance between agent {ids[0][:8]} and {ids[1][:8]}: {d:.3f}")
        print(f"Niche overlap: {o:.3f}")


if __name__ == "__main__":
    main()
