from __future__ import annotations

import warnings
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import differential_evolution, minimize

from .lanchester import MODEL_PARAM_NAMES, MODEL_REGISTRY, MODEL_STATE_NAMES, solve_model

_STATE_PREFIX = 'state_'
_RTOL = 1e-6
_ATOL = 1e-8
# 失败哨兵：见 P1-2，后续将改为 np.inf 并加发散闸门
_SENTINEL = 1e12
# 判定参数是否"贴边"的绝对容差
_BOUND_TOL = 1e-6


class ABMFitter:
    """Fit Lanchester-type ODE models to ABM simulation output.

    Supports multi-start optimization, automatic parameter scaling,
    and convergence diagnostics for robust fitting.
    """

    def __init__(self, model_func: Callable, param_names: list[str],
                 state_names: list[str],
                 state_mapping: dict[str, str] | None = None):
        self.model_func = model_func
        self.param_names = list(param_names)
        self.state_names = list(state_names)
        self.state_mapping = state_mapping or {}
        self.n_params = len(self.param_names)
        self.n_states = len(self.state_names)
        self.fitted_params_: np.ndarray | None = None
        self.fitted_param_dict: dict[str, float] = {}
        self.fit_result: Any | None = None
        self.r_squared: float | None = None
        self.bounds: list[tuple[float, float]] = []
        self._bound_params: list[str] = []
        self._t: np.ndarray | None = None
        self._y_true: np.ndarray | None = None
        self._y0: np.ndarray | None = None
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
        parts = [
            f'模型状态 {missing} 找不到对应数据列。',
            f'期望列名：{expected}',
            f'可用状态列：{state_columns}',
            '请显式传入 state_mapping。',
            '注意：本错误信息**不再**给出按字母序的"示意映射"——那样很容易把模型拟到'
            '与语义无关甚至零方差的列上（例如 Household 专属的 state_cultural_level），'
            '从而得到 R²=0.0 却 converged=True 的误导结果。'
            '需要候选建议时请用 Web 端的 GET /api/models（它会按列的时间方差过滤），'
            '但语义对应关系仍须由调用方核对。',
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
            # stacklevel=2 让告警指向调用者，而不是本模块——否则调用方无法定位来源
            warnings.warn('Data has near-zero variance — fitting may be unreliable.', stacklevel=2)

    # ── Objective ────────────────────────────────────────────────────────

    def _solve(self, params: np.ndarray, t: np.ndarray, y0: np.ndarray) -> np.ndarray | None:
        """在**原始时间轴**上积分模型，返回形状为 (len(t), n_states) 的预测值。

        重要：时间自变量必须原样传给模型，**不能**做归一化/缩放。
        把 t 压缩到单位区间在数学上等价于把所有速率参数同乘该区间长度
        （ODE 对时间的缩放会改变解），会让拟合参数随数据窗口漂移。
        实测（5 人 2 户，seed=3）：steps=120 时缩放 R²=0.7065、``r``/``s`` 贴上界；
        steps=240 时 R²=-0.1377；撤销缩放后分别为 0.9661 与 0.9390 且无贴边参数。
        """
        step = float(np.diff(t).mean()) if len(t) > 1 else float(abs(t[-1]) or 1.0)

        def rhs(t_, y_):
            return np.array(self.model_func(t_, list(y_), *params))

        try:
            sol = solve_ivp(rhs, [t[0], t[-1]], y0, t_eval=t,
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
                   y_true: np.ndarray, y0: np.ndarray) -> float | None:
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
        agent_id: str | None = None,
        p0: list[float] | None = None,
        bounds: list[tuple[float, float]] | None = None,
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
        self.bounds = self._normalize_bounds(bounds, n)

        result = minimize(self._objective, p0, args=(t, y_true, y_true[0]),
                          method=method, bounds=self.bounds,
                          options={'maxiter': 5000, 'ftol': 1e-12})
        self._save_result(result, y_true, t)
        return result

    # ── Multi-start fit (stable) ─────────────────────────────────────────

    def fit_robust(
        self,
        df: pd.DataFrame,
        agent_id: str | None = None,
        bounds: list[tuple[float, float]] | None = None,
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
        self.bounds = self._normalize_bounds(bounds, n)
        bounds = self.bounds

        rng = np.random.RandomState(seed)
        best_result = None
        best_r2 = -np.inf

        for _i in range(n_starts):
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
        agent_id: str | None = None,
        bounds: list[tuple[float, float]] | None = None,
    ) -> Any:
        """Global optimization via differential evolution (slow but thorough)."""
        if agent_id is not None:
            t, y_true = self._extract_agent_series(df, agent_id)
        else:
            t, y_true = self._extract_aggregate_series(df)
        self._validate_data(t, y_true)
        self._t, self._y_true, self._y0 = t, y_true, y_true[0]

        n = self.n_params
        self.bounds = self._normalize_bounds(bounds, n)
        bounds = self.bounds

        result = differential_evolution(
            self._objective, bounds, args=(t, y_true, y_true[0]),
            seed=42, maxiter=1000, tol=1e-8, polish=True,
        )
        self._save_result(result, y_true, t)
        return result

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_bounds(bounds: Any, n: int) -> list[tuple[float, float]]:
        """把边界规范化为 list[(lo, hi)]。

        同时接受 ``list[(lo, hi)]``（本库历史用法）与 ``scipy.optimize.Bounds``
        （用户很自然会传）。后者在阶段 B 曾因直接 ``list(bounds)`` 而抛
        TypeError，现在两者都能用。
        """
        if bounds is None:
            return [(1e-4, 5.0)] * n
        if hasattr(bounds, "lb") and hasattr(bounds, "ub"):
            lower = np.atleast_1d(np.asarray(bounds.lb, dtype=float))
            upper = np.atleast_1d(np.asarray(bounds.ub, dtype=float))
            if lower.size == 1:
                lower = np.repeat(lower, n)
            if upper.size == 1:
                upper = np.repeat(upper, n)
            return [(float(lo), float(hi)) for lo, hi in zip(lower, upper)]
        pairs = [(float(lo), float(hi)) for lo, hi in bounds]
        if len(pairs) != n:
            raise ValueError(f'边界数量 ({len(pairs)}) 与参数数量 ({n}) 不一致')
        return pairs

    def _save_result(self, result: Any, y_true: np.ndarray, t: np.ndarray) -> None:
        self.fitted_params_ = result.x
        self.fitted_param_dict = dict(zip(self.param_names, result.x))
        self.fit_result = result

        # 上报**未截断**的真实 R²（允许为负）。
        # 历史实现是 max(0.0, 1 - ss_res/ss_tot)，把"拟合失败"与"拟合极差"抹平成
        # 同一个 0.0，而 converged 又要求 r_squared > 0 —— 两者叠加使负 R² 永远
        # 无法被发现（实测原始 -3.5175 被上报为 0.0）。
        self.r_squared = self._r_squared(result.x, t, y_true, y_true[0])
        self._bound_params = self._parameters_at_bounds(result.x)

    def _parameters_at_bounds(self, params: np.ndarray, tol: float = _BOUND_TOL) -> list[str]:
        """返回贴在上/下界的参数名（**仅用于告警**，不参与 converged 判定）。

        参数贴边可能有正当原因（例如 logistic 的 K、influence 的 target 天然可能落在
        边界），因此它表示"该方向可能不可辨识或边界不合适"，而不是"拟合不可用"。
        """
        hit: list[str] = []
        for name, value, (lower, upper) in zip(self.param_names, params, self.bounds or []):
            if abs(float(value) - float(lower)) <= tol or abs(float(value) - float(upper)) <= tol:
                hit.append(str(name))
        return hit

    def _objective_hit_sentinel(self) -> bool:
        """目标函数是否停在失败哨兵上（说明该解根本没积分成功）。"""
        if self.fit_result is None:
            return True
        try:
            fun = float(self.fit_result.fun)
        except (TypeError, ValueError):
            return True
        return not np.isfinite(fun) or fun >= _SENTINEL

    # ── Prediction ───────────────────────────────────────────────────────

    def predict(self, t: np.ndarray, y0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.fitted_params_ is None:
            raise RuntimeError('Call fit_*() before predict().')
        return solve_model(self.model_func, y0.tolist(), t,
                           self.fitted_params_.tolist())

    # ── Diagnostics ──────────────────────────────────────────────────────

    @property
    def converged(self) -> bool:
        """优化器是否给出了可用解。

        判定条件（**只看优化器**）：
        1. 优化器报告成功（``success`` 为真，即没有超出迭代/函数求值上限）；
        2. 目标函数没有停在失败哨兵上（积分失败时 MSE 无意义）；
        3. R² 可计算（积分能跑通）且为有限值。

        参数"贴边"与负 R² 都**不**在此否决：它们分别表示"该方向可能不可辨识"
        与"拟合确实很差"，是应当如实上报的诊断信息（见 ``params_at_bounds`` /
        ``r_squared``），而不是把一次成功的高 R² 拟合误判为不收敛。
        历史教训：曾把 `r_squared > 0` 与"无贴边参数"塞进 converged，
        导致 R²=0.97–0.99 的正常拟合被判为未收敛。
        """
        if self.fit_result is None or not bool(self.fit_result.success):
            return False
        if self._objective_hit_sentinel():
            return False
        if self.r_squared is None:
            return False
        return bool(np.isfinite(self.r_squared))

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
            'state_columns': dict(self._resolved_columns),
            'fun': fun_val,
            'hit_sentinel': self._objective_hit_sentinel(),
            'params_at_bounds': list(self._bound_params),
            'bounds': [[float(lo), float(hi)] for lo, hi in self.bounds],
        }

    def summary(self) -> str:
        j = self.summary_json()
        lines = [f'Model: {j["model"]}',
                 f'States: {j["state_names"]}',
                 f'Params: {j["params"]}',
                 f'R^2:    {j["r_squared"]}',
                 f'Converged: {j["converged"]}']
        if j['params_at_bounds']:
            lines.append(f'参数被边界钉住: {j["params_at_bounds"]}（该方向不可辨识或边界不合适）')
        if j['hit_sentinel']:
            lines.append('目标函数停在失败哨兵上：该解未成功积分，R² 无意义')
        return '\n'.join(lines)

    def __repr__(self) -> str:
        fitted = self.fitted_params_ is not None
        return f'ABMFitter({self.model_func.__name__}, fitted={fitted})'


# ── Builder ─────────────────────────────────────────────────────────────────

def make_fitter(model_name: str, state_mapping: dict[str, str] | None = None,
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
    agent_id: str | None = None,
    robust: bool = True,
    state_mappings: dict[str, dict[str, str]] | None = None,
    **fit_kwargs,
) -> dict[str, ABMFitter]:
    """依次拟合多个模型并返回结果。

    Parameters
    ----------
    state_mappings : dict[str, dict[str, str]], optional
        按模型名给出各自的 ``state_mapping``。抽象模型（square_law/influence/
        lotka_volterra/resource_competition/logistic）的状态名与 ABM 列名没有默认
        对应关系，必须在此声明；否则这些模型会直接报错（这是刻意的，避免静默
        把模型拟到无关列上）。

        历史实现无法传入映射，导致 7 个模型里 6 个在此函数中完全不可用
        （传 ``state_mapping=`` 会因签名不匹配抛 TypeError）。
    """
    mappings = state_mappings or {}
    unknown = sorted(set(mappings) - set(model_names))
    if unknown:
        raise ValueError(f'state_mappings 含有未请求的模型：{unknown}')

    results: dict[str, ABMFitter] = {}
    for name in model_names:
        fitter = make_fitter(name, state_mapping=mappings.get(name))
        if robust:
            fitter.fit_robust(df, agent_id=agent_id, **fit_kwargs)
        else:
            fitter.fit_from_dataframe(df, agent_id=agent_id, **fit_kwargs)
        results[name] = fitter
    return results
