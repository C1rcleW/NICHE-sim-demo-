"""
Simple example: Simulate a single family household over time.
"""
from family_abm import (
    Environment, Simulation, Scheduler,
    FamilyMember, Household, StateRecorder,
)


def main():
    env = Environment()
    # 先建立随机数上下文（seed），这样智能体初始化与后续演化都来自同一条可复现的随机流
    sim = Simulation(env, scheduler=Scheduler("sequential"), seed=42)

    household = Household(name="Smith Family", environment=env)
    env.add_agent(household)

    father = FamilyMember(name="Dad", age=40, gender="male", role_name="parent", environment=env)
    mother = FamilyMember(name="Mom", age=38, gender="female", role_name="parent", environment=env)
    son = FamilyMember(name="Son", age=10, gender="male", role_name="child", environment=env)
    daughter = FamilyMember(name="Daughter", age=8, gender="female", role_name="child", environment=env)

    household.add_member(father)
    household.add_member(mother)
    household.add_member(son)
    household.add_member(daughter)

    recorder = StateRecorder(record_agents=True)
    sim.add_recorder(recorder)

    sim.run(steps=120)

    df = recorder.to_dataframe()
    print("Simulation finished. Recorded", len(df), "observations.")
    print("\nColumns:", list(df.columns))
    print("\nSample data:")
    print(df.head(10))

    print("\n--- Final states ---")
    for agent in env.get_agents():
        if isinstance(agent, FamilyMember):
            s = agent.get_state()
            print(f"  {s['attributes']['name']:>10} | "
                  f"age={s['attributes']['age']:.1f} | "
                  f"role={s['attributes']['role']:>6} | "
                  f"happiness={s['state']['happiness']:.2f} | "
                  f"stress={s['state']['stress']:.2f} | "
                  f"health={s['state']['health']:.2f}")


if __name__ == "__main__":
    main()
