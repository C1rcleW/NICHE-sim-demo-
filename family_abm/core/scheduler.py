from __future__ import annotations

import random
from typing import Any

from .agent import Agent
from .environment import Environment


class Scheduler:
    """决定每个时间步"哪些 agent、以什么顺序"被更新。

    ``rng`` 由 :class:`Simulation` 注入，与智能体共享同一条随机流；
    单独使用本类时回退到全局 ``random``。
    """

    def __init__(self, method: str = "sequential", rng: Any = None):
        self.method = method
        self.time = 0
        self.rng = rng if rng is not None else random

    def schedule(self, environment: Environment) -> list[Agent]:
        agents = environment.get_agents()
        if self.method == "sequential":
            return agents
        elif self.method == "random":
            shuffled = list(agents)
            self.rng.shuffle(shuffled)
            return shuffled
        elif self.method == "random_activation":
            shuffled = list(agents)
            self.rng.shuffle(shuffled)
            n = self.rng.randint(1, max(1, len(shuffled)))
            return shuffled[:n]
        else:
            raise ValueError(f"Unknown scheduler method: {self.method}")

    def step(self, environment: Environment) -> None:
        for agent in self.schedule(environment):
            if agent.alive:
                agent.step()
        self.time += 1
        environment.time = self.time
