from __future__ import annotations
from typing import Any, Optional
import random


class Relationship:
    def __init__(
        self,
        agent_a_id: str,
        agent_b_id: str,
        relation_type: str = "generic",
        rng: Any = None,
    ):
        self.agent_a_id = agent_a_id
        self.agent_b_id = agent_b_id
        self.relation_type = relation_type
        # 由 Household 传入环境注入的 RNG；单独使用本类时回退全局 random
        self.rng = rng if rng is not None else random

        self.affection: float = self.rng.uniform(0.3, 0.8)
        self.trust: float = self.rng.uniform(0.3, 0.8)
        self.power_dynamics: float = 0.5
        self.communication_quality: float = self.rng.uniform(0.3, 0.7)
        self.conflict: float = self.rng.uniform(0.0, 0.3)

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
