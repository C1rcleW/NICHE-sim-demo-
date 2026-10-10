from __future__ import annotations
from typing import Any, Optional
import math
import random
from ..core.agent import Agent

PERSONALITY_DIMENSIONS = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]

# ── Default simulation parameters ──────────────────────────────────────────
#
# 量级说明（0.2.0 校准）：
#   health_* —— 月度衰减。base + age*age_coef 在 40 岁时约 1.1e-3/月 ≈ 1.3%/年，
#               使健康状况在数十年的仿真尺度上缓慢下降而不是触底；
#               旧值 (0.002 + 0.00015·age) 在 40 岁时约 6.8e-3/月 ≈ 7.8%/年，
#               会在约 10 年内把健康打到下限 0.01。
#   stress_* —— 压力按"朝均衡点松弛"演化，均衡值 = (base + work)·(1 + sens·neuro) / decay。
#               默认参数下成年人 ≈ 0.31、儿童 ≈ 0.17，保证神经质人格在整个区间内
#               都能产生可分辨的差异（旧参数均衡值 > 1 会被钳位饱和）。
DEFAULT_PARAMS: dict[str, float] = {
    "education_rate": 0.008,
    "income_base": 0.10,
    "income_edu_boost": 0.40,
    "income_age_peak": 45,
    "income_age_spread": 18,
    "health_floor": 0.35,
    "health_decay_rate": 0.0020,
    "health_edu_protection": 0.30,
    "stress_base": 0.012,
    "stress_work_add": 0.008,
    "stress_decay": 0.06,
    "stress_neuro_sensitivity": 0.30,
    "happiness_baseline": 0.35,
    "happiness_health_weight": 0.20,
    "happiness_income_weight": 0.25,
    "happiness_edu_weight": 0.10,
    "happiness_stress_penalty": 0.30,
    "happiness_recovery": 0.08,
    "randomness": 0.02,
}


class FamilyMember(Agent):
    def __init__(
        self,
        name: str = "",
        age: float = 25.0,
        gender: str = "other",
        personality: Optional[dict[str, float]] = None,
        role_name: str = "adult",
        environment: Optional[Any] = None,
        **kwargs,
    ):
        """家庭成员智能体。

        Parameters
        ----------
        environment : Environment, optional
            所属环境。**传入后初始化随机数才来自该环境的 RNG**（即
            ``Simulation(seed=...)`` 注入的独立随机流）。

            若不传，成员在自身构造期间 ``self.environment`` 仍为 ``None``
            （要等 ``Household.add_member()`` 把它注册进环境才设置），
            此时初始化会退回全局 ``random``，导致带 seed 的仿真**不可复现**。
            推荐写法::

                env = Environment()
                sim = Simulation(env, seed=42)
                hh = Household(name="Smith", environment=env)
                env.add_agent(hh)
                hh.add_member(FamilyMember(name="Father", age=40, environment=env))
        """
        super().__init__(**kwargs)
        if environment is not None:
            self.environment = environment
        rng = self._rng()
        self.set_attribute("name", name)
        self.set_attribute("age", age)
        self.set_attribute("gender", gender)
        self.set_attribute("personality", personality or {
            k: max(0.0, min(1.0, rng.gauss(0.5, 0.15))) for k in PERSONALITY_DIMENSIONS
        })
        self.set_attribute("role", role_name)

        self.set_state_value("health", max(0.3, min(1.0, 1.0 - age * 0.003 + rng.gauss(0, 0.05))))
        self.set_state_value("happiness", rng.uniform(0.4, 0.7))
        self.set_state_value("stress", rng.uniform(0.15, 0.4))
        self.set_state_value("energy", rng.uniform(0.6, 1.0))
        self.set_state_value("education", max(0.0, min(1.0, age * 0.012 + rng.gauss(0, 0.05))))
        self.set_state_value("income", 0.0)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _rng(self) -> Any:
        """取随机数发生器：优先用环境注入的独立实例，否则回退全局 ``random``。

        由 ``Simulation(seed=...)`` 注入的 RNG 使仿真可复现；直接使用全局
        ``random`` 时调用方需自行播种。
        """
        env = self.environment
        rng = getattr(env, "rng", None) if env is not None else None
        return rng if rng is not None else random

    def _p(self, key: str, default: float = 0.0) -> float:
        """Read a parameter from environment config, with fallback."""
        if self.environment is not None:
            env_params = getattr(self.environment, "params", None) or {}
            return float(env_params.get(key, DEFAULT_PARAMS.get(key, default)))
        return float(DEFAULT_PARAMS.get(key, default))

    def _role_at_age(self, age: float) -> str:
        if age < 6:     return "preschool"
        elif age < 18:   return "child"
        elif age < 22:   return "student"
        elif age < 65:   return "adult"
        else:           return "elder"

    def age_increment(self, years: float = 1 / 12) -> None:
        new_age = self.get_attribute("age") + years
        self.set_attribute("age", new_age)
        self.set_attribute("role", self._role_at_age(new_age))

    # ── Main step ────────────────────────────────────────────────────────

    def step(self) -> None:
        age = self.get_attribute("age")
        role = self.get_attribute("role")
        personality = self.get_attribute("personality")
        rng = self._rng().gauss

        dt_months = self._p("dt_months", 1.0)
        noise = self._p("randomness", 0.02)

        # ── Education (peaks early, plateaus) ──
        edu = self.get_state_value("education")
        edu_rate = self._p("education_rate", 0.008)
        age_edu_factor = max(0.05, 1.0 - age / 60)
        edu_gain = edu_rate * age_edu_factor * (1 - edu)
        if age < 6:
            edu_gain *= 0.3
        edu += (edu_gain + rng(0, noise * 0.3)) * dt_months
        self.set_state_value("education", max(0.0, min(1.0, edu)))

        # ── Income (education × age curve × role) ──
        base = self._p("income_base", 0.10)
        edu_boost = self._p("income_edu_boost", 0.4) * edu
        peak = self._p("income_age_peak", 45)
        spread = self._p("income_age_spread", 18)
        age_factor = math.exp(-((age - peak) ** 2) / (2 * spread ** 2))
        role_mul = {"preschool": 0.0, "child": 0.0, "student": 0.15,
                    "adult": 1.0, "elder": 0.35}.get(role, 0.2)
        income = base * (1 + edu_boost) * age_factor * role_mul
        income += rng(0, noise * base)
        self.set_state_value("income", max(0.0, income))

        # ── Health (decays toward a floor, accelerated by age, buffered by education) ──
        #
        # 结构说明（0.2.0 重写）：
        #   纯线性衰减没有下界，长时间仿真必然把健康压到 0.01 —— 等于用"死亡"代替
        #   "衰老"，健康维度会失去区分度。改为朝下限渐近：
        #       h ← floor + (h - floor) · exp(-k·dt)，
        #   k = rate · edu_factor · age_factor，其中 age_factor = max(1, age/50)²
        #   表达"年龄越大衰减越快"。这样既有年龄曲线，又不会无限下坠。
        #
        #   同时 edu_protect 作用在**总衰减**上（旧实现只乘在年龄项，教育几乎无效果）。
        hp = self.get_state_value("health")
        floor = self._p("health_floor", 0.35)
        rate = self._p("health_decay_rate", 0.0020)
        age_factor = max(1.0, age / 50.0) ** 2
        edu_protect = min(1.0, self._p("health_edu_protection", 0.30) * edu)
        k = rate * age_factor * (1 - edu_protect)
        hp = floor + (hp - floor) * math.exp(-k * dt_months)
        hp += rng(0, noise * 0.3)
        self.set_state_value("health", max(0.01, min(1.0, hp)))

        # ── Stress (relaxes toward an equilibrium, scaled by neuroticism) ──
        st = self.get_state_value("stress")
        st_base = self._p("stress_base", 0.012)
        st_work = self._p("stress_work_add", 0.008) if role in ("adult", "student") else 0.005
        st_decay = self._p("stress_decay", 0.06)
        neuro = personality.get("neuroticism", 0.5)
        neuro_sens = self._p("stress_neuro_sensitivity", 0.30)
        st_change = (st_base + st_work) * (1 + neuro_sens * neuro) - st_decay * st
        st_change += rng(0, noise * 0.5) * (st + 0.1)
        self.set_state_value("stress", max(0.0, min(1.0, st + st_change)))

        # ── Happiness (target-based, mean-reverting) ──
        ha = self.get_state_value("happiness")
        h_base = self._p("happiness_baseline", 0.35)
        h_health = self._p("happiness_health_weight", 0.20) * hp
        h_income = self._p("happiness_income_weight", 0.25) * min(1.0, income * 3)
        h_edu = self._p("happiness_edu_weight", 0.10) * edu
        h_stress_pen = self._p("happiness_stress_penalty", 0.30) * st
        target = max(0.0, min(1.0, h_base + h_health + h_income + h_edu - h_stress_pen))
        recovery = self._p("happiness_recovery", 0.08)
        ha += (target - ha) * recovery + rng(0, noise * 0.5)
        self.set_state_value("happiness", max(0.0, min(1.0, ha)))

        # ── Energy (simple cycle) ──
        en = self.get_state_value("energy")
        en = en * 0.92 + 0.06 + rng(0, noise * 0.2)
        self.set_state_value("energy", max(0.0, min(1.0, en)))

        # ── Age ──
        self.age_increment(years=dt_months / 12)

    def __repr__(self) -> str:
        return f"FamilyMember({self.get_attribute('name')}, age={self.get_attribute('age'):.1f}, role={self.get_attribute('role')})"
