from __future__ import annotations

from typing import Any


class InfluenceRelation:
    def __init__(
        self,
        source_id: str,
        target_id: str,
        strength: float = 0.5,
        domain: str = "general",
    ):
        self.source_id = source_id
        self.target_id = target_id
        self.strength = strength
        self.domain = domain
        self.method: str = "linear"

    def apply(self, target_state: dict[str, float], source_state: dict[str, float]) -> dict[str, float]:
        new_state = dict(target_state)
        for key in source_state:
            if key in target_state:
                if self.method == "linear":
                    delta = (source_state[key] - target_state[key]) * self.strength
                    new_state[key] = max(0.0, min(1.0, target_state[key] + delta))
                elif self.method == "threshold":
                    if abs(source_state[key] - target_state[key]) > 0.2:
                        delta = (source_state[key] - target_state[key]) * self.strength * 0.5
                        new_state[key] = max(0.0, min(1.0, target_state[key] + delta))
        return new_state

    def get_state(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "strength": self.strength,
            "domain": self.domain,
        }

    def __repr__(self) -> str:
        return f"Influence({self.source_id[:8]} -> {self.target_id[:8]}, strength={self.strength:.2f})"
