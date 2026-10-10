from __future__ import annotations

from typing import Any

from ..core.agent import Agent
from .family_member import FamilyMember
from .relationships import Relationship


class Household(Agent):
    def __init__(
        self,
        household_id: str | None = None,
        name: str = "Household",
        environment: Any | None = None,
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
        seed = getattr(self.environment, "seed", None) if self.environment is not None else None
        for existing_id in self.members:
            if existing_id != member.id:
                # 关系身份用**家庭名 + 成员在家庭中的加入序号**，而不是 uuid：
                # uuid 每次运行都不同，会让按 id 排序的关系顺序变化，
                # 进而导致同一 seed 下关系状态不可复现。
                rel = Relationship(
                    agent_a_id=member.id,
                    agent_b_id=existing_id,
                    relation_type=relation_to_head,
                    rng=rng,
                    seed=seed,
                    identity=(self._member_label(member), self._member_label(existing_id)),
                )
                self.relationships[(member.id, existing_id)] = rel
                self.relationships[(existing_id, member.id)] = rel
        if self.environment is not None:
            self.environment.add_agent(member)

    def _member_label(self, member_id: str) -> str:
        """成员的稳定标签：家庭名 + 加入序号（与 uuid 无关）。"""
        order = list(self.members).index(member_id) if member_id in self.members else -1
        name = getattr(self, "name", "") or getattr(self, "attributes", {}).get("name", "")
        return f"{name}#{order}"

    @property
    def name(self) -> str:
        return str(self.get_attribute("name") or "")

    def remove_member(self, member_id: str) -> None:
        if member_id in self.members:
            del self.members[member_id]
            keys_to_remove = [k for k in self.relationships if member_id in k]
            for k in keys_to_remove:
                del self.relationships[k]
            if self.environment is not None:
                self.environment.remove_agent(member_id)

    def get_relationship(self, agent_a: str, agent_b: str) -> Relationship | None:
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

    def _p(self, key: str, default: float = 0.0) -> float:
        """读取环境参数（家庭层与成员层共用同一套参数）。"""
        env = self.environment
        env_params = getattr(env, "params", None) if env is not None else None
        from .family_member import DEFAULT_PARAMS

        return float((env_params or {}).get(key, DEFAULT_PARAMS.get(key, default)))

    def step(self) -> None:
        for rel in self._unique_relationships():
            rel.update_dynamics()

        # 政策杠杆：收入支持直接提高家庭可支配收入（例如儿童津贴），
        # 而不是抬高"够用"的门槛——后者会让支持越多、测得的压力越大。
        support = self._p("income_support", 0.0)
        total_income = sum(
            (m.get_state_value("income", 0.0) or 0.0)
            for m in self.members.values()
        ) * (1.0 + support)
        self.set_state_value("total_income", total_income)

        # ── 家庭经济压力 ──
        # 此前 total_income 只写不读：家庭算出了聚合量却无人消费，使"家庭"在
        # 动力学上等同于一个命名空间。这里把它变成共同压力源：人均收入低于
        # 基准时产生压力，由成员各自读取（Family Stress Model 的入口）。
        baseline = self._p("income_baseline", 0.08)
        perceived = total_income / max(1, len(self.members))
        pressure = 0.0 if baseline <= 0 else max(0.0, (baseline - perceived) / baseline)
        self.set_state_value("economic_pressure", pressure)
        for member in self.members.values():
            member.set_state_value("economic_pressure", pressure)

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
