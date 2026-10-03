"""Family social micro-niche agent-based modeling framework."""

# 单一真源说明：版本号在 pyproject.toml 的 [project].version 中声明。
# 此处重复是为了支持 `family_abm.__version__`（打包验收与用户诊断常用）。
# 两者由 tests/test_packaging.py::test_package_version_matches_pyproject 强制一致。
__version__ = "0.2.0"

from .core.agent import Agent
from .core.environment import Environment
from .core.scheduler import Scheduler
from .core.simulation import Simulation
from .family.family_member import FamilyMember
from .family.household import Household
from .family.relationships import Relationship
from .family.roles import Role, ParentRole, ChildRole, AdultRole, ElderRole
from .niche.resources import Resource, EconomicCapital, CulturalCapital, SocialCapital, EmotionalCapital, ResourceBundle
from .niche.influence import InfluenceRelation
from .niche.micro_niche import MicroNiche
from .ml.recorder import StateRecorder
from .ml.features import FeatureExtractor
from .fitting import (
    ABMFitter, make_fitter, compare_models,
    solve_model, solve_named,
    competition_square_law, competition_linear_law,
    social_influence, wellbeing_balance,
    logistic_growth, lotka_volterra, resource_competition,
)
from .viz import (
    plot_timeseries, plot_phase_portrait, plot_niche_space,
    plot_family_network, plot_fit_diagnostics, plot_aggregate,
    plot_agent_comparison,
)

__all__ = [
    "Agent", "Environment", "Scheduler", "Simulation",
    "FamilyMember", "Household", "Relationship",
    "Role", "ParentRole", "ChildRole", "AdultRole", "ElderRole",
    "Resource", "EconomicCapital", "CulturalCapital", "SocialCapital", "EmotionalCapital", "ResourceBundle",
    "InfluenceRelation", "MicroNiche",
    "StateRecorder", "FeatureExtractor",
    "ABMFitter", "make_fitter", "compare_models",
    "solve_model", "solve_named",
    "competition_square_law", "competition_linear_law",
    "social_influence", "wellbeing_balance",
    "logistic_growth", "lotka_volterra", "resource_competition",
    "plot_timeseries", "plot_phase_portrait", "plot_niche_space",
    "plot_family_network", "plot_fit_diagnostics", "plot_aggregate",
    "plot_agent_comparison",
]
