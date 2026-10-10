from __future__ import annotations

from typing import Any

import pandas as pd

from ..core.environment import Environment


class StateRecorder:
    def __init__(self, record_agents: bool = True, record_environment: bool = True):
        self.record_agents = record_agents
        self.record_environment = record_environment
        self.history: list[dict[str, Any]] = []
        self.agent_history: list[dict[str, Any]] = []

    def record(self, env: Environment) -> None:
        step_data: dict[str, Any] = {
            "time": env.time,
            "population": len(env.agents),
        }
        if self.record_environment:
            step_data["environment"] = env.get_global_state()
        self.history.append(step_data)

        if self.record_agents:
            for agent in env.get_agents():
                agent_state = agent.get_state()
                record: dict[str, Any] = {
                    "time": env.time,
                    "agent_id": agent.id,
                    "agent_type": agent_state["type"],
                    "alive": agent_state["alive"],
                }
                for attr_key, attr_val in agent_state.get("attributes", {}).items():
                    if isinstance(attr_val, (str, int, float, bool)):
                        record[f"attr_{attr_key}"] = attr_val
                for state_key, state_val in agent_state.get("state", {}).items():
                    if isinstance(state_val, (int, float)):
                        record[f"state_{state_key}"] = state_val
                self.agent_history.append(record)

    def get_data(self) -> dict[str, Any]:
        return {"environment": self.history, "agents": self.agent_history}

    def to_dataframe(self) -> pd.DataFrame:
        """宽表形式的历史记录。

        **契约（重要）**：缺失值保持为 ``NaN``，不填充。

        不同 agent 类型的状态键本来就不同（Household 没有 ``state_happiness``，
        FamilyMember 没有 ``state_total_income``），因此宽度对齐后必然出现 NaN。
        这些 NaN 表达的是"该 agent 没有这个状态"，**不是数值 0**：

        - 拟合器依赖 ``groupby('time').mean()`` 逐列跳过 NaN，从而让每个状态列只
          在"真正拥有该状态的 agent 子集"上聚合；
        - 一旦在 API 层 ``fillna(0)``，成员状态的均值会被 Household 行拖低，
          图表与拟合目标就不再是同一条序列（历史实测偏低 28.6%）。

        人看的表格视图请用 :meth:`to_statistics_dataframe`。
        """
        if self.agent_history:
            return pd.DataFrame(self.agent_history)
        return pd.DataFrame()

    def to_statistics_dataframe(self) -> pd.DataFrame:
        """按 agent 类型分组的统计视图（丢弃缺失值）。

        返回长表，列为 ``agent_type`` / ``column`` / ``n`` / ``mean`` / ``std`` /
        ``min`` / ``max``。与 :meth:`to_dataframe` 的区别是：这里刻意**丢弃 NaN**
        （每个单元格的 ``n`` 明确给出有效样本数），因此不会把"不存在"误读为 0。
        """
        df = self.to_dataframe()
        columns = ["agent_type", "column", "n", "mean", "std", "min", "max"]
        if df.empty:
            return pd.DataFrame(columns=columns)

        numeric = df.select_dtypes(include="number")
        # 身份/派生字段不是状态量，避免混入统计
        numeric = numeric.drop(columns=[c for c in ("time", "alive") if c in numeric.columns], errors="ignore")

        records: list[dict[str, Any]] = []
        for agent_type, group in df.groupby("agent_type", sort=True):
            subset = numeric.loc[group.index]
            for column in sorted(subset.columns):
                series = subset[column].dropna()
                if series.empty:
                    continue
                records.append({
                    "agent_type": str(agent_type),
                    "column": column,
                    "n": int(series.size),
                    "mean": float(series.mean()),
                    "std": float(series.std(ddof=0)),
                    "min": float(series.min()),
                    "max": float(series.max()),
                })
        return pd.DataFrame(records, columns=columns)

    def to_csv(self, filepath: str, level: str = "agent") -> None:
        """导出 CSV。

        Parameters
        ----------
        level : {"agent", "statistics", "environment"}
            - ``agent``：:meth:`to_dataframe` 的宽表（缺失值为空字段，不写 0）
            - ``statistics``：:meth:`to_statistics_dataframe` 的分组统计
            - ``environment``：环境级历史（``history``，只有记录环境时才有内容）
        """
        if level == "agent":
            df = self.to_dataframe()
        elif level == "statistics":
            df = self.to_statistics_dataframe()
        elif level == "environment":
            df = pd.DataFrame(self.history)
        else:
            raise ValueError(f"未知 level={level!r}，可选：agent / statistics / environment")
        df.to_csv(filepath, index=False)

    def reset(self) -> None:
        self.history.clear()
        self.agent_history.clear()
