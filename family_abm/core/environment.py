from __future__ import annotations

import random
from typing import Any

from .agent import Agent


class Environment:
    """智能体的容器与共享上下文。

    除注册智能体外，它还承载两类共享状态：

    - ``params``：动力学参数（`FamilyMember._p()` 会读取，缺省时回退到 DEFAULT_PARAMS）
    - ``rng``：随机数发生器。默认是全局 ``random`` 模块；当由 :class:`Simulation`
      以 ``seed`` 创建时会换成独立实例，使仿真可复现且不影响进程内的其它随机数使用。
      智能体应通过 ``environment.rng`` 取随机数，而不是直接调用全局 ``random``。
    - ``seed``：仿真种子。需要"按身份派生独立随机流"的组件（如 ``Relationship``）
      用它获得确定性种子，从而摆脱对对象迭代顺序的依赖。
    """

    def __init__(self, width: int = 100, height: int = 100):
        self.agents: dict[str, Agent] = {}
        self.time: int = 0
        self.width = width
        self.height = height
        self.properties: dict[str, Any] = {}
        self.params: dict[str, float] = {}
        self.rng: Any = random
        self.seed: int | None = None

    def add_agent(self, agent: Agent, x: float | None = None, y: float | None = None) -> None:
        self.agents[agent.id] = agent
        agent.environment = self
        if x is not None:
            agent.set_attribute("x", x)
        if y is not None:
            agent.set_attribute("y", y)

    def remove_agent(self, agent_id: str) -> None:
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.environment = None
            del self.agents[agent_id]

    def get_agents(self) -> list[Agent]:
        return list(self.agents.values())

    def get_agent_by_id(self, agent_id: str) -> Agent | None:
        return self.agents.get(agent_id)

    def get_agents_by_type(self, agent_type: type) -> list[Agent]:
        return [a for a in self.agents.values() if isinstance(a, agent_type)]

    def step(self) -> None:
        for agent in self.get_agents():
            if agent.alive:
                agent.step()
        self.time += 1

    def get_global_state(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "population": len(self.agents),
            "properties": dict(self.properties),
        }
