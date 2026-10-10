from __future__ import annotations
from typing import Any, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from ..niche.micro_niche import MicroNiche


# ── Global style ────────────────────────────────────────────────────────────

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ═══════════════════════════════════════════════════════════════════════════
# 1. Time Series
# ═══════════════════════════════════════════════════════════════════════════

def plot_timeseries(
    df: pd.DataFrame,
    state_columns: Optional[list[str]] = None,
    agent_id: Optional[str] = None,
    title: str = "Agent State Time Series",
    figsize: tuple[float, float] = (10, 5),
    save_path: Optional[str] = None,
) -> plt.Figure:
    if agent_id is not None:
        df = df[df["agent_id"] == agent_id].copy()

    cols = state_columns or [c for c in df.columns if c.startswith("state_")]
    df = df.sort_values("time")

    fig, ax = plt.subplots(figsize=figsize)
    for col in cols:
        label = col.replace("state_", "")
        ax.plot(df["time"].values, df[col].values, label=label, lw=1.5)

    ax.set_xlabel("Time step")
    ax.set_ylabel("Value")
    ax.set_title(title)
    ax.legend(fontsize=9)
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_aggregate(
    df: pd.DataFrame,
    state_columns: Optional[list[str]] = None,
    title: str = "Population Aggregate Statistics",
    figsize: tuple[float, float] = (12, 5),
    save_path: Optional[str] = None,
) -> plt.Figure:
    cols = state_columns or [c for c in df.columns if c.startswith("state_")]
    grouped = df.groupby("time")[cols]

    fig, axes = plt.subplots(1, 2, figsize=figsize)

    means = grouped.mean()
    stds = grouped.std()
    t = means.index.values

    for col in cols:
        label = col.replace("state_", "")
        axes[0].plot(t, means[col].values, label=label, lw=1.5)
        axes[1].plot(t, stds[col].values, label=label, lw=1.5, ls="--")

    axes[0].set_title("Mean")
    axes[0].set_xlabel("Time step")
    axes[0].legend(fontsize=8)

    axes[1].set_title("Std Dev")
    axes[1].set_xlabel("Time step")
    axes[1].legend(fontsize=8)

    fig.suptitle(title, y=1.02)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# 2. Phase Portrait
# ═══════════════════════════════════════════════════════════════════════════

def plot_phase_portrait(
    df: pd.DataFrame,
    x_state: str = "state_happiness",
    y_state: str = "state_stress",
    agent_id: Optional[str] = None,
    title: str = "Phase Portrait",
    figsize: tuple[float, float] = (6, 6),
    save_path: Optional[str] = None,
) -> plt.Figure:
    if agent_id is not None:
        df = df[df["agent_id"] == agent_id].copy()

    df = df.sort_values("time")
    fig, ax = plt.subplots(figsize=figsize)

    x = df[x_state].values
    y = df[y_state].values

    ax.plot(x, y, "o-", ms=3, lw=1, alpha=0.7)
    ax.scatter(x[0], y[0], c="green", s=100, zorder=5, label="Start", marker="o")
    ax.scatter(x[-1], y[-1], c="red", s=100, zorder=5, label="End", marker="s")

    ax.set_xlabel(x_state.replace("state_", ""))
    ax.set_ylabel(y_state.replace("state_", ""))
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# 3. Niche Space
# ═══════════════════════════════════════════════════════════════════════════

def plot_niche_space(
    niches: dict[str, MicroNiche],
    dims: Optional[list[str]] = None,
    labels: Optional[dict[str, str]] = None,
    title: str = "Social Micro-Niche Space",
    figsize: tuple[float, float] = (8, 6),
    save_path: Optional[str] = None,
) -> plt.Figure:
    dims = dims or ["economic", "cultural", "social"]

    n_dims = len(dims)
    if n_dims == 2:
        fig, ax = plt.subplots(figsize=figsize)
        for nid, niche in niches.items():
            x = niche.position.get(dims[0], 0)
            y = niche.position.get(dims[1], 0)
            label = labels.get(nid, nid[:8]) if labels else nid[:8]
            ax.scatter(x, y, s=120, alpha=0.8)
            ax.annotate(label, (x, y), fontsize=8, alpha=0.8)
        ax.set_xlabel(dims[0])
        ax.set_ylabel(dims[1])
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.05, 1.05)
        ax.set_title(title)
        ax.set_aspect("equal")

    elif n_dims >= 3:
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111, projection="3d")
        for nid, niche in niches.items():
            x = niche.position.get(dims[0], 0)
            y = niche.position.get(dims[1], 0)
            z = niche.position.get(dims[2], 0)
            label = labels.get(nid, nid[:8]) if labels else nid[:8]
            ax.scatter(x, y, z, s=80, alpha=0.8)
            ax.text(x, y, z, label, fontsize=7, alpha=0.7)
        ax.set_xlabel(dims[0])
        ax.set_ylabel(dims[1])
        ax.set_zlabel(dims[2])
        ax.set_title(title)

    else:
        raise ValueError("Need at least 2 dimensions to plot.")

    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# 4. Family Relationship Network
# ═══════════════════════════════════════════════════════════════════════════

def plot_family_network(
    household: Any,
    title: str = "Family Relationship Network",
    figsize: tuple[float, float] = (8, 6),
    save_path: Optional[str] = None,
) -> plt.Figure:
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("plot_family_network requires networkx. Run: pip install networkx")

    G = nx.Graph()
    for mid, member in household.members.items():
        name = member.get_attribute("name") or mid[:8]
        role = member.get_attribute("role")
        G.add_node(mid, name=name, role=role)

    for (a, b), rel in household.relationships.items():
        if a < b:
            G.add_edge(a, b,
                       weight=rel.affection,
                       conflict=rel.conflict,
                       trust=rel.trust)

    fig, ax = plt.subplots(figsize=figsize)
    pos = nx.spring_layout(G, seed=42, k=1.5)

    role_colors = {"parent": "#e74c3c", "adult": "#f39c12",
                   "child": "#3498db", "elder": "#2ecc71", "member": "#95a5a6"}
    node_colors = []
    for n in G.nodes():
        role = G.nodes[n].get("role", "member")
        node_colors.append(role_colors.get(role, "#95a5a6"))

    edge_widths = [max(0.5, G[u][v].get("weight", 0.5) * 4) for u, v in G.edges()]
    edge_colors = [G[u][v].get("conflict", 0) for u, v in G.edges()]

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                           node_size=800, edgecolors="white", linewidths=1.5)
    nx.draw_networkx_edges(G, pos, ax=ax, width=edge_widths,
                           edge_color=edge_colors, edge_cmap=plt.cm.RdYlGn_r,
                           edge_vmin=0, edge_vmax=1, alpha=0.7)

    nx.draw_networkx_labels(G, pos, ax=ax,
                            labels={n: G.nodes[n].get("name", n[:8]) for n in G.nodes()},
                            font_size=10, font_weight="bold")

    legend_elements = [
        mpatches.Patch(color=c, label=r, alpha=0.7)
        for r, c in role_colors.items()
        if any(G.nodes[n].get("role") == r for n in G.nodes())
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# 5. Fit Diagnostics
# ═══════════════════════════════════════════════════════════════════════════

def plot_fit_diagnostics(
    df: pd.DataFrame,
    fitter: Any,
    agent_id: Optional[str] = None,
    state_names: Optional[list[str]] = None,
    title: str = "ODE Fit Diagnostics",
    figsize: tuple[float, float] = (12, 4),
    save_path: Optional[str] = None,
) -> plt.Figure:

    state_names = state_names or fitter.state_names
    n_states = len(state_names)

    if agent_id is not None:
        sub = df[df["agent_id"] == agent_id].sort_values("time")
    else:
        sub = df.groupby("time").mean(numeric_only=True).reset_index()

    def _resolve_col(s):
        if hasattr(fitter, "state_mapping") and s in fitter.state_mapping:
            return fitter.state_mapping[s]
        return f"state_{s}"

    t = sub["time"].values.astype(float)
    y_true = np.column_stack([sub[_resolve_col(s)].values.astype(float) for s in state_names])
    y0 = y_true[0]

    t_pred = np.linspace(t[0], t[-1], 200)
    _, y_pred = fitter.predict(t_pred, y0)

    fig, axes = plt.subplots(1, n_states, figsize=figsize, squeeze=False)

    for i, (ax, sn) in enumerate(zip(axes[0], state_names)):
        ax.plot(t, y_true[:, i], "o", ms=4, label="ABM data", alpha=0.6)
        ax.plot(t_pred, y_pred[i], "-", lw=2, label="ODE fit")
        ax.set_xlabel("Time step")
        ax.set_ylabel(sn)
        ax.set_title(f"{sn}")
        ax.legend(fontsize=8)

    fig.suptitle(title, y=1.02)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# 6. Agent Comparison
# ═══════════════════════════════════════════════════════════════════════════

def plot_agent_comparison(
    df: pd.DataFrame,
    state: str = "state_happiness",
    agent_ids: Optional[list[str]] = None,
    title: str = "Agent Comparison",
    figsize: tuple[float, float] = (10, 5),
    save_path: Optional[str] = None,
) -> plt.Figure:
    if agent_ids is None:
        agent_ids = df["agent_id"].unique().tolist()

    fig, ax = plt.subplots(figsize=figsize)
    for aid in agent_ids:
        sub = df[df["agent_id"] == aid].sort_values("time")
        label = sub["attr_name"].iloc[0] if "attr_name" in sub.columns else aid[:8]
        ax.plot(sub["time"].values, sub[state].values, label=label, lw=1.5)

    ax.set_xlabel("Time step")
    ax.set_ylabel(state.replace("state_", ""))
    ax.set_title(title)
    ax.legend(fontsize=9)
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
