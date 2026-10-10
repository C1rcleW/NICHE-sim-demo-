from __future__ import annotations


class Role:
    def __init__(self, name: str, privileges: dict[str, float] | None = None, norms: list[str] | None = None):
        self.name = name
        self.privileges = privileges or {}
        self.norms = norms or []

    def get_decision_weight(self, domain: str = "general") -> float:
        return self.privileges.get(domain, self.privileges.get("general", 0.5))

    def __repr__(self) -> str:
        return f"Role({self.name})"


class ParentRole(Role):
    def __init__(self):
        super().__init__(
            name="parent",
            privileges={"general": 0.8, "finance": 0.9, "education": 0.8, "daily_life": 0.7},
            norms=["provide_care", "set_boundaries", "nurture", "teach", "protect"],
        )


class ChildRole(Role):
    def __init__(self):
        super().__init__(
            name="child",
            privileges={"general": 0.2, "finance": 0.0, "education": 0.2, "daily_life": 0.3},
            norms=["obey", "learn", "respect", "cooperate"],
        )


class AdultRole(Role):
    def __init__(self):
        super().__init__(
            name="adult",
            privileges={"general": 0.6, "finance": 0.6, "education": 0.5, "daily_life": 0.5},
            norms=["contribute", "maintain", "cooperate"],
        )


class ElderRole(Role):
    def __init__(self):
        super().__init__(
            name="elder",
            privileges={"general": 0.7, "finance": 0.5, "education": 0.7, "daily_life": 0.4},
            norms=["wisdom", "guidance", "support"],
        )


ROLE_REGISTRY: dict[str, type[Role]] = {
    "parent": ParentRole,
    "child": ChildRole,
    "adult": AdultRole,
    "elder": ElderRole,
}
