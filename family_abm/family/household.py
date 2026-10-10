from __future__ import annotations
from typing import Any, Optional
from ..core.agent import Agent
from .family_member import FamilyMember
from .relationships import Relationship


class Household(Agent):
    def __init__(
        self,
        household_id: Optional[str] = None,
        name: str = "Household",
        environment: Optional[Any] = None,
        **kwargs,
    ):
        """家庭智能体。

        Parameters
        ----------
        environment : Environment, optional
            所属环境。**建议显式传入**，否则 ``add_member()`` 在家庭被
            ``Environment.add_agent()`` 注册之前无法取得环境注入的随机数发生器，
            此时新建关系会退回全局 ``random``，导致带 ``seed`` 的仿真不可复现。
        """
        super().__init__(agent_id=household_id, **kwargs)
        self.set_attribute("name", name)
        self.members: dict[str, FamilyMember] = {}
        self.relationships: dict[tuple[str, str], Relationship] = {}
        if environment is not None:
            self.environment = environment

        self.set_state_value("total_income", 0.0)
        self.set_state_value("savings", 0.0)
        self.set_state_value("housing_quality", 0.5)
        self.set_state_value("neighborhood_quality", 0.5)
        self.set_state_value("cultural_level", 0.5)
        self.set_state_value("social_capital", 0.5)

    def _rng(self) -> Any:
        """取环境注入的随机数发生器；未接入环境时回退全局 ``random``。"""
        import random as _random

        env = self.environment
        rng = getattr(env, "rng", None) if env is not None else None
        return rng if rng is not None else _random

    def add_member(self, member: FamilyMember, relation_to_head: str = "member") -> None:
        self.members[member.id] = member
        rng = self._rng()
        for existing_id in self.members:
            if existing_id != member.id:
                rel = Relationship(
                    agent_a_id=member.id,
                    agent_b_id=existing_id,
                    relation_type=relation_to_head,
                    rng=rng,
                )
                self.relationships[(member.id, existing_id)] = rel
                self.relationships[(existing_id, member.id)] = rel
        if self.environment is not None:
            self.environment.add_agent(member)

    def remove_member(self, member_id: str) -> None:
        if member_id in self.members:
            del self.members[member_id]
            keys_to_remove = [k for k in self.relationships if member_id in k]
            for k in keys_to_remove:
                del self.relationships[k]
            if self.environment is not None:
                self.environment.remove_agent(member_id)

    def get_relationship(self, agent_a: str, agent_b: str) -> Optional[Relationship]:
        return self.relationships.get((agent_a, agent_b))

    def get_member_relationships(self, member_id: str) -> list[Relationship]:
        return [
            rel for (a, _), rel in self.relationships.items()
            if a == member_id
        ]

    def _unique_relationships(self) -> list[Relationship]:
        """按**确定顺序**返回去重后的关系列表。

        每条关系在 ``self.relationships`` 里存了两份（(a,b) 与 (b,a) 指向同一对象），
        因此需要去重。历史实现用 ``set(...)`` 去重，而集合的迭代顺序取决于对象
        哈希（即内存地址），每次运行都不同 —— 这会让 ``update_dynamics()`` 消耗
        随机数的顺序不稳定，导致即使给了 seed 也不可复现。

        这里改为按 (agent_a_id, agent_b_id) 排序，保证顺序只由 id 决定。
        """
        seen: dict[tuple[str, str], Relationship] = {}
        for rel in self.relationships.values():
            seen.setdefault((rel.agent_a_id, rel.agent_b_id), rel)
        return [seen[key] for key in sorted(seen)]

    def step(self) -> None:
        for rel in self._unique_relationships():
            rel.update_dynamics()

        total_income = sum(
            m.get_state_value("income", 0.0)
            for m in self.members.values()
        )
        self.set_state_value("total_income", total_income)

    def get_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": type(self).__name__,
            "attributes": dict(self.attributes),
            "state": dict(self.state),
            "alive": self.alive,
            "member_count": len(self.members),
        }

    def __repr__(self) -> str:
        return f"Household({self.get_attribute('name')}, members={len(self.members)})"
