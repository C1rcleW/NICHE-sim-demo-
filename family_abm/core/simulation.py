from __future__ import annotations
import random
from typing import Any, Callable, Optional
from .environment import Environment
from .scheduler import Scheduler

# 未显式指定 seed 时使用的默认值：保证"不传 seed"也可复现
DEFAULT_SEED = 42


class Simulation:
    def __init__(
        self,
        environment: Environment,
        scheduler: Optional[Scheduler] = None,
        record_initial: bool = True,
        seed: Optional[int] = None,
    ):
        """
        Parameters
        ----------
        environment : Environment
            被步进的环境。
        scheduler : Scheduler, optional
            调度器；默认 sequential。
        record_initial : bool, default True
            在第一次 ``step()`` 之前额外记录一次 ``t=0`` 的初始状态。

            ABM 输出缺基线时，拟合器会取 ``y_true[0]`` 当作初值（那其实是"走完
            第一步之后"的状态），导致整条轨迹相差一步。开启后时间轴为 ``[0..n]``，
            ``recorder`` 的第一行即可直接作为 ODE 的初值。
        seed : int, optional
            随机种子。默认 ``42``（见 :data:`DEFAULT_SEED`），因此**不传 seed 也可复现**。
            仿真始终创建独立的 ``random.Random(seed)`` 并注入 ``environment.rng``，
            不读也不写全局 ``random``，因此不会扰动进程内其它随机数使用。

            **推荐用法**：先建立随机数上下文，再构造智能体，并为需要稳定身份的对象
            提供固定 id（跨运行复现关系初值所需）::

                env = Environment()
                sim = Simulation(env, seed=42)              # 先注入 RNG
                hh = Household(name="Smith", household_id="smith", environment=env)
                env.add_agent(hh)
                hh.add_member(FamilyMember(name="Father", age=40, agent_id="father",
                                           environment=env))

            成员状态的随机数来自环境的这条流，初始化顺序决定取值，因此**先建
            Simulation 再建智能体**才能复现完整的初始状态。关系变量的随机流则按
            ``(seed, 双方身份, 关系类型)`` 派生，互不干扰、也不依赖迭代顺序。
        """
        self.environment = environment
        self.scheduler = scheduler or Scheduler()
        self.record_initial = bool(record_initial)
        self.recorders: list[Any] = []
        self.hooks: dict[str, list[Callable]] = {"pre_step": [], "post_step": []}
        self.current_step = 0

        # 随机数上下文：始终建立独立随机流。
        # 未显式给出 seed 时使用 DEFAULT_SEED，使"不传 seed"也得到可复现结果——
        # 否则智能体初始化会退回全局 random，同一份配置两次运行结果不同，
        # 这对研究用途是不可接受的行为。
        effective_seed = DEFAULT_SEED if seed is None else seed
        environment.rng = random.Random(effective_seed)
        environment.seed = effective_seed
        self.seed = effective_seed
        # 调度器与智能体必须共享同一条随机流，否则无法复现
        self.scheduler.rng = environment.rng

        # 第一个 step 前（以及 reset 之后）需要补记基线
        self._needs_initial_recording = self.record_initial

    def add_recorder(self, recorder: Any) -> None:
        self.recorders.append(recorder)

    def _record_all(self) -> None:
        for recorder in self.recorders:
            recorder.record(self.environment)

    def add_hook(self, stage: str, func: Callable) -> None:
        if stage in self.hooks:
            self.hooks[stage].append(func)

    def _run_hooks(self, stage: str) -> None:
        for hook in self.hooks.get(stage, []):
            hook(self)

    def _prepare_influence(self) -> None:
        """在步进前预计算各家庭成员的"本步接受影响量"。

        必要性：影响量依赖同一步内其它成员的状态。若在各成员 ``step()`` 里边算边用，
        结果会取决于调度顺序（后更新者读到已被更新的兄弟状态）。预计算把影响量固定为
        **步初状态**的函数，使机制与调度顺序解耦，也让效果与"同步更新"一致。

        本方法单独成层，是为了让 core 不必了解 family 层的机制细节：它只调用
        环境暴露的钩子，没有家庭时自动跳过。
        """
        from ..family.family_member import DEFAULT_PARAMS
        from ..family.influence import prepare_received_influence

        params = dict(DEFAULT_PARAMS)
        params.update(getattr(self.environment, "params", None) or {})
        for agent in self.environment.get_agents():
            members = getattr(agent, "members", None)
            if not isinstance(members, dict) or not members:
                continue
            pending = prepare_received_influence(agent, params, rng=self.environment.rng)
            for member in members.values():
                member.set_state_value("influence_received", pending.get(member.id, 0.0))

    def step(self) -> None:
        # 首个步进（或 reset 之后）先落盘初始状态，使时间轴从 0 开始
        if self._needs_initial_recording:
            self._needs_initial_recording = False
            self._record_all()
        self._run_hooks("pre_step")
        self._prepare_influence()
        self.scheduler.step(self.environment)
        self._record_all()
        self._run_hooks("post_step")
        self.current_step += 1

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    def run_until(self, condition: Callable[[Environment], bool], max_steps: int = 1000) -> None:
        for _ in range(max_steps):
            if condition(self.environment):
                break
            self.step()

    def reset(self) -> None:
        """清空记录并回到 t=0。

        注意：本方法当前 **不重置 Scheduler 的内部时钟**，也不回滚智能体状态
        （`environment.time = 0` 之后下一次 `scheduler.step()` 会把 time 覆盖为
        `scheduler.time + 1`）。真正的重跑语义在 P2-3 中统一修正。
        """
        self.environment.time = 0
        self.current_step = 0
        self._needs_initial_recording = self.record_initial
        for recorder in self.recorders:
            recorder.reset()

    def get_results(self) -> dict[str, Any]:
        return {
            "steps": self.current_step,
            "environment": self.environment.get_global_state(),
            "recordings": [r.get_data() for r in self.recorders],
        }
