from __future__ import annotations
from typing import Any, Callable, Optional
from .environment import Environment
from .scheduler import Scheduler


class Simulation:
    def __init__(
        self,
        environment: Environment,
        scheduler: Optional[Scheduler] = None,
        record_initial: bool = True,
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
        """
        self.environment = environment
        self.scheduler = scheduler or Scheduler()
        self.record_initial = bool(record_initial)
        self.recorders: list[Any] = []
        self.hooks: dict[str, list[Callable]] = {"pre_step": [], "post_step": []}
        self.current_step = 0
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

    def step(self) -> None:
        # 首个步进（或 reset 之后）先落盘初始状态，使时间轴从 0 开始
        if self._needs_initial_recording:
            self._needs_initial_recording = False
            self._record_all()
        self._run_hooks("pre_step")
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
