from __future__ import annotations

from typing import Any

import numpy as np

from .resources import ResourceBundle


class MicroNiche:
    def __init__(self, niche_id: str, dimensions: list[str] | None = None):
        self.niche_id = niche_id
        self.dimensions = dimensions or ["economic", "cultural", "social", "emotional"]
        self.position: dict[str, float] = {d: 0.5 for d in self.dimensions}
        self.resources = ResourceBundle()
        self.boundary_permeability: dict[str, float] = {d: 0.5 for d in self.dimensions}

    def set_position(self, dimension: str, value: float) -> None:
        if dimension in self.dimensions:
            self.position[dimension] = max(0.0, min(1.0, value))

    def get_position_vector(self) -> np.ndarray:
        return np.array([self.position[d] for d in self.dimensions])

    def distance_to(self, other: MicroNiche, metric: str = "euclidean") -> float:
        v1 = self.get_position_vector()
        v2 = other.get_position_vector()
        if metric == "euclidean":
            return float(np.linalg.norm(v1 - v2))
        elif metric == "manhattan":
            return float(np.sum(np.abs(v1 - v2)))
        elif metric == "cosine":
            norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
            if norm_product == 0:
                return 1.0
            return float(1.0 - np.dot(v1, v2) / norm_product)
        return float(np.linalg.norm(v1 - v2))

    def overlap(self, other: MicroNiche) -> float:
        dist = self.distance_to(other)
        return max(0.0, 1.0 - dist / np.sqrt(len(self.dimensions)))

    def resource_exchange_efficiency(self, other: MicroNiche) -> float:
        overlap = self.overlap(other)
        avg_permeability = float(np.mean([self.boundary_permeability[d] for d in self.dimensions]))
        return overlap * avg_permeability

    def update_from_agent_state(self, agent_state: dict[str, float], mapping: dict[str, str] | None = None) -> None:
        mapping = mapping or {
            "income": "economic",
            "education": "cultural",
            "social_capital": "social",
            "happiness": "emotional",
        }
        for agent_key, niche_key in mapping.items():
            if agent_key in agent_state and niche_key in self.dimensions:
                self.set_position(niche_key, float(agent_state[agent_key]))

    def get_state(self) -> dict[str, Any]:
        return {
            "niche_id": self.niche_id,
            "position": dict(self.position),
            "resources": self.resources.to_dict(),
            "boundary_permeability": dict(self.boundary_permeability),
        }

    def __repr__(self) -> str:
        return f"MicroNiche({self.niche_id}, pos={self.position})"
