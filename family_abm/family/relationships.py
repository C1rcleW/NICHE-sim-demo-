from __future__ import annotations

import random
from typing import Any


class Relationship:
    """两个成员之间的关系，携带情感、信任、冲突等关系变量。

    随机数来源（重要）
    -----------------
    若所有关系共用环境的那一条随机流，则"哪条关系先更新"会改变各自抽到的数，
    于是关系状态依赖**迭代顺序**。而迭代顺序又只能按 agent_id 排——agent_id 是
    uuid4()，每次运行都不同，结果就是**同一 seed 也不可复现**。

    因此每条关系持有自己的 ``random.Random``，其种子由
    ``(仿真种子, 双方身份, 关系类型)`` 决定。这样：

    - 关系之间相互独立，迭代顺序不再影响结果；
    - 只要调用方给出稳定的标识（``Household(household_id=...)`` 与
      ``FamilyMember(agent_id=...)``），跨进程、跨机器都能复现。

    未提供环境种子时回退到传入的共享 RNG（或全局 ``random``），行为与旧版一致。
    """

    def __init__(
        self,
        agent_a_id: str,
        agent_b_id: str,
        relation_type: str = "generic",
        rng: Any = None,
        seed: int | None = None,
        identity: tuple[str, str] | None = None,
    ):
        self.agent_a_id = agent_a_id
        self.agent_b_id = agent_b_id
        self.relation_type = relation_type
        self.rng = self._make_rng(rng, seed, identity)

        self.affection: float = self.rng.uniform(0.3, 0.8)
        self.trust: float = self.rng.uniform(0.3, 0.8)
        self.power_dynamics: float = 0.5
        self.communication_quality: float = self.rng.uniform(0.3, 0.7)
        self.conflict: float = self.rng.uniform(0.0, 0.3)

    @staticmethod
    def _make_rng(rng: Any, seed: int | None, identity: tuple[str, str] | None) -> Any:
        """优先使用按身份派生的独立 RNG；否则退回共享 RNG。"""
        if seed is None:
            return rng if rng is not None else random
        label = "|".join(identity or ("", ""))
        return random.Random(f"{seed}|{label}")

    def get_other_id(self, agent_id: str) -> str:
        return self.agent_b_id if agent_id == self.agent_a_id else self.agent_a_id

    def influence_weight(self, from_agent_id: str, domain: str = "general") -> float:
        is_a = from_agent_id == self.agent_a_id
        power = self.power_dynamics if is_a else (1.0 - self.power_dynamics)
        return self.trust * 0.4 + power * 0.4 + self.affection * 0.2

    def update_dynamics(self) -> None:
        self.affection = max(0.0, min(1.0, self.affection + self.rng.uniform(-0.02, 0.02)))
        self.trust = max(0.0, min(1.0, self.trust + self.rng.uniform(-0.01, 0.01)))
        self.conflict = max(0.0, min(1.0, self.conflict + self.rng.uniform(-0.01, 0.01)))

    def get_state(self) -> dict[str, Any]:
        return {
            "agent_a_id": self.agent_a_id,
            "agent_b_id": self.agent_b_id,
            "relation_type": self.relation_type,
            "affection": self.affection,
            "trust": self.trust,
            "power_dynamics": self.power_dynamics,
            "communication_quality": self.communication_quality,
            "conflict": self.conflict,
        }

    def __repr__(self) -> str:
        return f"Relationship({self.agent_a_id[:8]}... <-> {self.agent_b_id[:8]}..., type={self.relation_type})"
