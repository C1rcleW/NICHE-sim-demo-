from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .recorder import StateRecorder


class FeatureExtractor:
    def __init__(self, recorder: StateRecorder):
        self.recorder = recorder

    def build_agent_panel(self) -> pd.DataFrame:
        return self.recorder.to_dataframe()

    def build_agent_trajectories(self, agent_id: str | None = None) -> pd.DataFrame:
        df = self.build_agent_panel()
        if agent_id is not None:
            df = df[df["agent_id"] == agent_id]
        return df.sort_values(["agent_id", "time"])

    def extract_features(
        self,
        feature_columns: list[str] | None = None,
        target_column: str | None = None,
        lag_steps: int = 1,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        df = self.build_agent_panel()
        if df.empty:
            return np.array([]), None

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if "time" in numeric_cols:
            numeric_cols.remove("time")
        feature_cols = feature_columns or numeric_cols

        X = df[feature_cols].fillna(0).values
        y = None
        if target_column and target_column in df.columns:
            y = df.groupby("agent_id")[target_column].shift(-lag_steps).fillna(0).values[:len(X)]
            X = X[:len(y)]

        return X, y

    def build_transition_dataset(
        self,
        state_columns: list[str] | None = None,
        lag: int = 1,
    ) -> pd.DataFrame:
        df = self.build_agent_panel()
        if df.empty:
            return pd.DataFrame()

        state_cols = state_columns or [c for c in df.columns if c.startswith("state_")]
        records = []
        for agent_id, group in df.groupby("agent_id"):
            group = group.sort_values("time")
            for i in range(len(group) - lag):
                source = group.iloc[i]
                target = group.iloc[i + lag]
                row: dict[str, Any] = {}
                for col in state_cols:
                    row[f"{col}_t"] = source[col]
                    row[f"{col}_t+{lag}"] = target[col]
                row["agent_id"] = agent_id
                row["time"] = source["time"]
                records.append(row)
        return pd.DataFrame(records)

    def build_network_features(self, agent_id: str | None = None) -> pd.DataFrame:
        df = self.build_agent_panel()
        if df.empty:
            return pd.DataFrame()
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if "time" in numeric_cols:
            numeric_cols.remove("time")
        grouped = df.groupby("agent_id")[numeric_cols].agg(["mean", "std", "min", "max"])
        grouped.columns = ["_".join(col).strip() for col in grouped.columns.values]
        return grouped.reset_index()
