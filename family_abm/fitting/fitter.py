from __future__ import annotations
from typing import Any, Callable, Optional
import warnings
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import minimize, differential_evolution
from .lanchester import MODEL_REGISTRY, MODEL_PARAM_NAMES, MODEL_STATE_NAMES, solve_model

_STATE_PREFIX = 'state_'
_RTOL = 1e-6
_ATOL = 1e-8
# 失败哨兵：见 P1-2，后续将改为 np.inf 并加发散闸门
_SENTINEL = 1e12
# 积分时间轴缩放上限。L-BFGS-B 的有限差分 eps 是绝对的（默认 1.49e-8），
# 当时间轴横跨 [0,120] 时该步长会引起过大的积分灵敏度，scipy 的 approx_derivative
# 会因扰动点漂出参数边界而抛 "x0 violates bound constraints"（实测 steps=120 必崩）。
# 规范化到 [0,1] 后同一数据可正常收敛，且目标函数值与未缩放时逐位接近（相对差 ~4e-8）。
_SCALE_THRESHOLD = 2.0


class ABMFitter:
    """Fit Lanchester-type ODE models to ABM simulation output.

    Supports multi-start optimization, automatic parameter scaling,
    and convergence diagnostics for robust fitting.
    """

    def __init__(self, model_func: Callable, param_names: list[str],
                 state_names: list[str],
                 state_mapping: Optional[dict[str, str]] = None):
        self.model_func = model_func
        self.param_names = list(param_names)
        self.state_names = list(state_names)
        self.state_mapping = state_mapping or {}
        self.n_params = len(self.param_names)
        self.n_states = len(self.state_names)
        self.fitted_params_: Optional[np.ndarray] = None
        self.fitted_param_dict: dict[str, float] = {}
        self.fit_result: Optional[Any] = None
        self.r_squared: Optional[float] = None
        self._r_squared_raw: Optional[float] = None
        self._t: Optional[np.ndarray] = None
        self._y_true: Optional[np.ndarray] = None
        self._y0: Optional[np.ndarray] = None
        self._resolved_columns: dict[str, str] = {}

    # ── Data ────────────────────────────────────────────────────────────

    def _resolve_col(self, state_name: str) -> str:
        if state_name in self.state_mapping:
            return self.state_mapping[state_name]
        return f'{_STATE_PREFIX}{state_name}'

    def _resolve_state_columns(self, df: pd.DataFrame) -> dict[str, str]:
        """把模型状态解析到 DataFrame 的具体列。

        解析规则（**不做任何猜测**）：
        1. ``state_mapping`` 命中的键直接使用其值；
        2. 否则使用约定名 ``state_<状态名>``；
        3. 若该列不存在，则不再兜底，而是抛出带"可用列 + 建议映射"的 ``ValueError``。

        历史行为是在 Web 层把 ``R1/R2/O1/O2`` 静默映射到任意前 N 个 ``state_`` 列，
        结果 ``influence`` 会被拟到方差为 0 的列上却仍返回 R²=0.878。这里明确禁止。
        """
        available = sorted(c for c in df.columns if isinstance(c, str))
        resolved: dict[str, str] = {}
        missing: list[str] = []

        for state_name in self.state_names:
            column = self._resolve_col(state_name)
            if column in df.columns:
                resolved[state_name] = column
            else:
                missing.append(state_name)

        if missing:
            raise ValueError(self._format_mapping_error(missing, available))

        # 同一个状态不得映射到同一列以外的重复列（语义歧义）
        columns = list(resolved.values())
        duplicates = sorted({c for c in columns if columns.count(c) > 1})
        if duplicates:
            raise ValueError(
                f'状态列存在重复映射：{duplicates}。请为每个状态指定不同列，'
                f'当前映射 {resolved}。'
            )
        self._resolved_columns = resolved
        return resolved

    def _format_mapping_error(self, missing: list[str], available: list[str]) -> str:
        state_columns = [c for c in available if c.startswith(_STATE_PREFIX)]
        expected = [self._resolve_col(s) for s in missing]
        # 按顺序给出"可用列足够时"的一个候选映射，仅供示意，不做任何自动应用
        suggestion = {
            state: (state_columns[i] if i < len(state_columns) else f'{_STATE_PREFIX}{state}')
            for i, state in enumerate(self.state_names)
        }
        parts = [
            f'模型状态 {missing} 找不到对应数据列。',
            f'期望列名：{expected}',
            f'可用状态列：{state_columns}',
            f'请显式传入 state_mapping（示意，需按语义核对）：{suggestion}',
            '抽象状态名（O1/O2/R1/R2/P/Q）与 ABM 具体状态列之间没有默认对应关系，必须由调用方声明语义；'
            '此前 Web 层的自动猜列会把模型拟到无关列上并返回看似合理的 R²。',
        ]
        return '\n'.join(parts)

    def resolve_state_columns(self, df: pd.DataFrame) -> dict[str, str]:
        """公开的状态列解析结果，便于调用方与可视化共享同一套映射。"""
        return self._resolve_state_columns(df)

    def _extract_agent_series(self, df: pd.DataFrame,
                              agent_id: str) -> tuple[np.ndarray, np.ndarray]:
        sub = df[df['agent_id'] == agent_id].sort_values('time')
        if sub.empty:
            available = sorted(str(a) for a in df['agent_id'].unique()) if 'agent_id' in df.columns else []
            raise ValueError(f'数据中没有 agent_id={agent_id!r} 的记录。可用 agent_id：{available}')
        resolved = self._resolve_state_columns(sub)
        t = sub['time'].values.astype(float)
        y = np.column_stack(
            [sub[resolved[s]].values.astype(float) for s in self.state_names]
        )
        return t, y

    def _extract_aggregate_series(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        resolved = self._resolve_state_columns(df)
        grouped = df.groupby('time')
        t = np.array(sorted(grouped.groups.keys()), dtype=float)
        rows = []
        for ti in t:
            g = grouped.get_group(ti)
            rows.append([g[resolved[s]].mean() for s in self.state_names])
        return t, np.array(rows, dtype=float)

    def _validate_data(self, t: np.ndarray, y: np.ndarray) -> None:
        if len(t) < 10:
            raise ValueError(f'Need at least 10 time points, got {len(t)}.')
        if np.any(np.isnan(y)):
            raise ValueError('Data contains NaN values.')
        if np.ptp(y, axis=0).max() < 1e-5:
            warnings.warn('Data has near-zero variance — fitting may be unreliable.')

    # ── Objective ────────────────────────────────────────────────────────

    @staticmethod
    def _integration_scale(t: np.ndarray) -> float:
        """把积分窗口缩放到单位长度，避免长时间轴下的有限差分越界（见 _SCALE_THRESHOLD）。"""
        span = float(t[-1] - t[0]) if len(t) > 1 else 1.0
        return span if span > _SCALE_THRESHOLD else 1.0

    def _solve(self, params: np.ndarray, t: np.ndarray, y0: np.ndarray) -> Optional[np.ndarray]:
        """在缩放过的时间轴上积分模型，返回形状为 (len(t), n_states) 的预测值。"""
        scale = self._integration_scale(t)
        t_scaled = (t - t[0]) / scale
        step = float(np.diff(t_scaled).mean()) if len(t_scaled) > 1 else float(t_scaled[-1] or 1.0)

        def rhs(t_, y_):
            return np.array(self.model_func(t_, list(y_), *params))

        try:
            sol = solve_ivp(rhs, [t_scaled[0], t_scaled[-1]], y0, t_eval=t_scaled,
                            method='RK45', rtol=_RTOL, atol=_ATOL, max_step=step)
        except Exception:
            return None
        if not sol.success:
            return None
        return sol.y.T

    def _objective(self, params: np.ndarray, t: np.ndarray,
                   y_true: np.ndarray, y0: np.ndarray) -> float:
        y_pred = self._solve(params, t, y0)
        if y_pred is None or y_pred.shape != y_true.shape:
            return _SENTINEL
        mse = np.mean((y_pred - y_true) ** 2)
        return float(_SENTINEL if (np.isnan(mse) or np.isinf(mse)) else mse)

    def _r_squared(self, params: np.ndarray, t: np.ndarray,
                   y_true: np.ndarray, y0: np.ndarray) -> Optional[float]:
        """未截断的真实 R²（允许为负）；无法积分时返回 None。

        P1-1 将在 _save_result 中改用本方法，并让 summary_json 同时暴露原始值。
        """
        y_mean = np.mean(y_true, axis=0)
        ss_total = float(np.sum((y_true - y_mean) ** 2))
        if ss_total == 0:
            return 0.0
        y_pred = self._solve(params, t, y0)
        if y_pred is None or y_pred.shape != y_true.shape:
            return None
        ss_res = float(np.sum((y_true - y_pred) ** 2))
        return 1.0 - ss_res / ss_total

    # ── Single-start fit ─────────────────────────────────────────────────

    def fit_from_dataframe(
        self,
        df: pd.DataFrame,
        agent_id: Optional[str] = None,
        p0: Optional[list[float]] = None,
        bounds: Optional[list[tuple[float, float]]] = None,
        method: str = 'L-BFGS-B',
    ) -> Any:
        """Single-start fit.  See fit_robust() for production use."""
        if agent_id is not None:
            t, y_true = self._extract_agent_series(df, agent_id)
        else:
            t, y_true = self._extract_aggregate_series(df)
        self._validate_data(t, y_true)
        self._t, self._y_true, self._y0 = t, y_true, y_true[0]

        n = self.n_params
        if p0 is None:
            p0 = [0.5] * n
        if bounds is None:
            bounds = [(1e-4, 5.0)] * n

        result = minimize(self._objective, p0, args=(t, y_true, y_true[0]),
                          method=method, bounds=bounds,
                          options={'maxiter': 5000, 'ftol': 1e-12})
        self._save_result(result, y_true, t)
        return result

    # ── Multi-start fit (stable) ─────────────────────────────────────────

    def fit_robust(
        self,
        df: pd.DataFrame,
        agent_id: Optional[str] = None,
        bounds: Optional[list[tuple[float, float]]] = None,
        n_starts: int = 8,
        seed: int = 42,
    ) -> Any:
        """Multi-start fitting — tries several random initial guesses, returns the best.

        This is the recommended method for production use.
        """
        if agent_id is not None:
            t, y_true = self._extract_agent_series(df, agent_id)
        else:
            t, y_true = self._extract_aggregate_series(df)
        self._validate_data(t, y_true)
        self._t, self._y_true, self._y0 = t, y_true, y_true[0]

        n = self.n_params
        if bounds is None:
            bounds = [(1e-4, 5.0)] * n

        rng = np.random.RandomState(seed)
        best_result = None
        best_r2 = -np.inf

        for i in range(n_starts):
            p0 = [rng.uniform(b[0], b[1]) for b in bounds]
            result = minimize(self._objective, p0, args=(t, y_true, y_true[0]),
                              method='L-BFGS-B', bounds=bounds,
                              options={'maxiter': 3000, 'ftol': 1e-12})
            r2 = self._r_squared(result.x, t, y_true, y_true[0])
            if r2 is not None and r2 > best_r2:
                best_r2 = r2
                best_result = result

        if best_result is None:
            raise RuntimeError('All fitting attempts failed.')

        self._save_result(best_result, y_true, t)
        return best_result

    def fit_global(
        self,
        df: pd.DataFrame,
        agent_id: Optional[str] = None,
        bounds: Optional[list[tuple[float, float]]] = None,
    ) -> Any:
        """Global optimization via differential evolution (slow but thorough)."""
        if agent_id is not None:
            t, y_true = self._extract_agent_series(df, agent_id)
        else:
            t, y_true = self._extract_aggregate_series(df)
        self._validate_data(t, y_true)
        self._t, self._y_true, self._y0 = t, y_true, y_true[0]

        n = self.n_params
        if bounds is None:
            bounds = [(1e-4, 5.0)] * n

        result = differential_evolution(
            self._objective, bounds, args=(t, y_true, y_true[0]),
            seed=42, maxiter=1000, tol=1e-8, polish=True,
        )
        self._save_result(result, y_true, t)
        return result

    # ── Internals ────────────────────────────────────────────────────────

    def _save_result(self, result: Any, y_true: np.ndarray, t: np.ndarray) -> None:
        self.fitted_params_ = result.x
        self.fitted_param_dict = dict(zip(self.param_names, result.x))
        self.fit_result = result

        # 真实（未截断）R²：保留供 P1-1 的诊断使用；当前对外仍维持原有的
        # max(0.0, .) 行为，避免在阶段 B 改变已发布语义。
        self._r_squared_raw = self._r_squared(result.x, t, y_true, y_true[0])
        if self._r_squared_raw is None:
            self.r_squared = None
        else:
            self.r_squared = max(0.0, self._r_squared_raw)

    # ── Prediction ───────────────────────────────────────────────────────

    def predict(self, t: np.ndarray, y0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.fitted_params_ is None:
            raise RuntimeError('Call fit_*() before predict().')
        return solve_model(self.model_func, y0.tolist(), t,
                           self.fitted_params_.tolist())

    # ── Diagnostics ──────────────────────────────────────────────────────

    @property
    def converged(self) -> bool:
        return (self.fit_result is not None and
                self.fit_result.success and
                self.r_squared is not None and
                self.r_squared > 0.0)

    def summary_json(self) -> dict[str, Any]:
        r2 = None
        if self.r_squared is not None:
            try:
                r2 = round(float(self.r_squared), 6)
            except (TypeError, ValueError):
                r2 = float(self.r_squared)
        fun_val = None
        if self.fit_result is not None:
            try:
                fun_val = float(self.fit_result.fun)
            except (TypeError, ValueError):
                fun_val = None
        params = {}
        for k, v in self.fitted_param_dict.items():
            try:
                params[k] = round(float(v), 6)
            except (TypeError, ValueError):
                params[k] = str(v)
        return {
            'model': getattr(self.model_func, '__name__', 'model'),
            'params': params,
            'r_squared': r2,
            'converged': bool(self.converged),
            'n_params': self.n_params,
            'n_states': self.n_states,
            'state_names': self.state_names,
            'fun': fun_val,
        }

    def summary(self) -> str:
        j = self.summary_json()
        lines = [f'Model: {j["model"]}',
                 f'States: {j["state_names"]}',
                 f'Params: {j["params"]}',
                 f'R^2:    {j["r_squared"]}',
                 f'Converged: {j["converged"]}']
        return '\n'.join(lines)

    def __repr__(self) -> str:
        fitted = self.fitted_params_ is not None
        return f'ABMFitter({self.model_func.__name__}, fitted={fitted})'


# ── Builder ─────────────────────────────────────────────────────────────────

def make_fitter(model_name: str, state_mapping: Optional[dict[str, str]] = None,
                **param_fix: float) -> ABMFitter:
    if model_name not in MODEL_REGISTRY:
        raise KeyError(f'Unknown model "{model_name}". Choose: {list(MODEL_REGISTRY)}')
    all_params = list(MODEL_PARAM_NAMES[model_name])
    state_names = list(MODEL_STATE_NAMES[model_name])
    model_func = MODEL_REGISTRY[model_name]
    for k in param_fix:
        if k in all_params:
            all_params.remove(k)
    if state_mapping is None:
        state_mapping = {}

    if param_fix:
        class _FixedModel:
            def __init__(self, func, fixed):
                self.func = func
                self.fixed = fixed
                self.__name__ = getattr(func, '__name__', 'model')
            def __call__(self, t, y, *free_params):
                merged = {}
                idx = 0
                for p in MODEL_PARAM_NAMES[model_name]:
                    merged[p] = self.fixed[p] if p in self.fixed else free_params[idx]
                    if p not in self.fixed:
                        idx += 1
                return self.func(t, y, **merged)
        wrapped = _FixedModel(model_func, param_fix)
    else:
        wrapped = model_func

    return ABMFitter(wrapped, all_params, state_names, state_mapping)


def compare_models(
    df: pd.DataFrame,
    model_names: list[str],
    agent_id: Optional[str] = None,
    robust: bool = True,
    **fit_kwargs,
) -> dict[str, ABMFitter]:
    results = {}
    for name in model_names:
        fitter = make_fitter(name)
        if robust:
            fitter.fit_robust(df, agent_id=agent_id, **fit_kwargs)
        else:
            fitter.fit_from_dataframe(df, agent_id=agent_id, **fit_kwargs)
        results[name] = fitter
    return results
