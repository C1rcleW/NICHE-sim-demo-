from __future__ import annotations
from typing import Callable
import numpy as np
from scipy.integrate import solve_ivp


# ─── Lanchester-style Social Dynamics Models ───────────────────────────────

def competition_square_law(t: float, y: list[float], alpha: float, beta: float,
                           eps1: float = 0.0, eps2: float = 0.0) -> list[float]:
    """
    Square Law analog for social competition.
    dR1/dt = -alpha * R2 + eps1    (resource/status of group 1)
    dR2/dt = -beta * R1 + eps2     (resource/status of group 2)
    """
    R1, R2 = y
    return [-alpha * R2 + eps1, -beta * R1 + eps2]


def competition_linear_law(t: float, y: list[float], alpha: float, beta: float) -> list[float]:
    """
    Linear Law analog: competition proportional to interaction.
    dR1/dt = -alpha * R1 * R2
    dR2/dt = -beta  * R1 * R2
    """
    R1, R2 = y
    return [-alpha * R1 * R2, -beta * R1 * R2]


def social_influence(t: float, y: list[float], gamma: float, delta: float,
                     target1: float = 1.0, target2: float = 0.0) -> list[float]:
    """
    Opinion/behavior influence between two agents/groups.
    dO1/dt = -gamma * (O1 - O2) + delta * (target1 - O1)
    dO2/dt = -gamma * (O2 - O1) + delta * (target2 - O2)
    """
    O1, O2 = y
    return [
        -gamma * (O1 - O2) + delta * (target1 - O1),
        -gamma * (O2 - O1) + delta * (target2 - O2),
    ]


def wellbeing_balance(t: float, y: list[float], p: float, q: float,
                      r: float, s: float, income: float = 0.5) -> list[float]:
    """
    Happiness-Stress balance as a mixed Lanchester system.
    dH/dt = p * income - q * S * H      (happiness: boosted by income, eroded by stress)
    dS/dt = r * H * (1 - S) - s * S       (stress: fueled by happiness saturation, natural decay)
    """
    H, S = y
    return [p * income - q * S * H, r * H * (1 - S) - s * S]


def logistic_growth(t: float, y: list[float], r: float, K: float) -> list[float]:
    """
    Logistic growth (single population).
    dP/dt = r * P * (1 - P / K)
    """
    P = y[0]
    return [r * P * (1 - P / K)]


def lotka_volterra(t: float, y: list[float], a: float, b: float,
                   c: float, d: float) -> list[float]:
    """
    Classic predator-prey (e.g., work demands vs. family time).
    dP/dt = a * P - b * P * Q
    dQ/dt = c * P * Q - d * Q
    """
    P, Q = y
    return [a * P - b * P * Q, c * P * Q - d * Q]


def resource_competition(t: float, y: list[float], r1: float, k1: float,
                         r2: float, k2: float, alpha: float, beta: float) -> list[float]:
    """
    Two-species competition with logistic growth + Lanchester cross-term.
    dR1/dt = r1 * R1 * (1 - R1/K1) - alpha * R2
    dR2/dt = r2 * R2 * (1 - R2/K2) - beta  * R1
    """
    R1, R2 = y
    return [
        r1 * R1 * (1 - R1 / k1) - alpha * R2,
        r2 * R2 * (1 - R2 / k2) - beta * R1,
    ]


# ─── Solver ─────────────────────────────────────────────────────────────────

MODEL_REGISTRY: dict[str, Callable] = {
    "square_law": competition_square_law,
    "linear_law": competition_linear_law,
    "influence": social_influence,
    "wellbeing": wellbeing_balance,
    "logistic": logistic_growth,
    "lotka_volterra": lotka_volterra,
    "resource_competition": resource_competition,
}

MODEL_PARAM_NAMES: dict[str, list[str]] = {
    "square_law": ["alpha", "beta", "eps1", "eps2"],
    "linear_law": ["alpha", "beta"],
    "influence": ["gamma", "delta", "target1", "target2"],
    "wellbeing": ["p", "q", "r", "s", "income"],
    "logistic": ["r", "K"],
    "lotka_volterra": ["a", "b", "c", "d"],
    "resource_competition": ["r1", "k1", "r2", "k2", "alpha", "beta"],
}

MODEL_STATE_NAMES: dict[str, list[str]] = {
    "square_law": ["R1", "R2"],
    "linear_law": ["R1", "R2"],
    "influence": ["O1", "O2"],
    "wellbeing": ["happiness", "stress"],
    "logistic": ["population"],
    "lotka_volterra": ["prey", "predator"],
    "resource_competition": ["R1", "R2"],
}


def solve_model(model_func: Callable, y0: list[float], t_eval: np.ndarray,
                params: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """Solve an ODE model and return (time_points, state_trajectories)."""
    def wrapped(t, y):
        return model_func(t, y, *params)

    sol = solve_ivp(wrapped, [t_eval[0], t_eval[-1]], y0,
                    t_eval=t_eval, method="RK45", rtol=1e-6, atol=1e-8)

    if not sol.success:
        raise RuntimeError(f"ODE solver failed: {sol.message}")

    return sol.t, sol.y


def solve_named(model_name: str, y0: list[float], t_eval: np.ndarray,
                params: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """Look up a model by name and solve it."""
    if model_name not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model '{model_name}'. Available: {list(MODEL_REGISTRY)}")
    return solve_model(MODEL_REGISTRY[model_name], y0, t_eval, params)
