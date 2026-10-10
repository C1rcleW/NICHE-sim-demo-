from __future__ import annotations

import uuid
from typing import Any


class Agent:
    def __init__(
        self,
        agent_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
    ):
        self.id = agent_id or str(uuid.uuid4())
        self.attributes = attributes or {}
        self.state = state or {}
        self.environment: Any = None
        self.alive = True

    def step(self) -> None:
        raise NotImplementedError

    def get_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": type(self).__name__,
            "attributes": dict(self.attributes),
            "state": dict(self.state),
            "alive": self.alive,
        }

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def get_attribute(self, key: str, default: Any = None) -> Any:
        return self.attributes.get(key, default)

    def set_state_value(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_state_value(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)
