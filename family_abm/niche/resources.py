from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Resource:
    name: str
    value: float = 0.0
    capacity: float = float("inf")

    def add(self, amount: float) -> float:
        added = min(amount, self.capacity - self.value) if self.capacity != float("inf") else amount
        self.value += added
        return added

    def remove(self, amount: float) -> float:
        removed = min(amount, self.value)
        self.value -= removed
        return removed

    def transfer_to(self, other: Resource, amount: float) -> float:
        removed = self.remove(amount)
        other.add(removed)
        return removed

    def __repr__(self) -> str:
        return f"{self.name}: {self.value:.3f}"


class EconomicCapital(Resource):
    def __init__(self, value: float = 0.0):
        super().__init__(name="economic_capital", value=value, capacity=float("inf"))


class CulturalCapital(Resource):
    def __init__(self, value: float = 0.0):
        super().__init__(name="cultural_capital", value=value, capacity=1.0)


class SocialCapital(Resource):
    def __init__(self, value: float = 0.0):
        super().__init__(name="social_capital", value=value, capacity=1.0)


class EmotionalCapital(Resource):
    def __init__(self, value: float = 0.0):
        super().__init__(name="emotional_capital", value=value, capacity=1.0)


class ResourceBundle:
    def __init__(self, economic: float = 0.0, cultural: float = 0.0, social: float = 0.0, emotional: float = 0.0):
        self.economic = EconomicCapital(economic)
        self.cultural = CulturalCapital(cultural)
        self.social = SocialCapital(social)
        self.emotional = EmotionalCapital(emotional)

    def get(self, resource_type: str) -> Resource:
        mapping = {
            "economic": self.economic,
            "cultural": self.cultural,
            "social": self.social,
            "emotional": self.emotional,
        }
        return mapping.get(resource_type, self.economic)

    def to_dict(self) -> dict[str, float]:
        return {
            "economic": self.economic.value,
            "cultural": self.cultural.value,
            "social": self.social.value,
            "emotional": self.emotional.value,
        }

    def __repr__(self) -> str:
        return f"ResourceBundle({self.to_dict()})"
