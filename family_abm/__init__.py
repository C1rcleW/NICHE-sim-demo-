"""Family social micro-niche agent-based modeling framework."""

# 单一真源说明：版本号在 pyproject.toml 的 [project].version 中声明。
# 此处重复是为了支持 `family_abm.__version__`（打包验收与用户诊断常用）。
# 两者由 tests/test_packaging.py::test_package_version_matches_pyproject 强制一致。
__version__ = "0.1.0"

from .core.agent import Agent
from .core.environment import Environment
from .core.scheduler import Scheduler
from .core.simulation import Simulation
from .family.family_member import FamilyMember
from .family.household import Household
from .family.relationships import Relationship
from .family.roles import AdultRole, ChildRole, ElderRole, ParentRole, Role
from .fitting import (
    ABMFitter,
    compare_models,
    competition_linear_law,
    competition_square_law,
    logistic_growth,
    lotka_volterra,
    make_fitter,
    resource_competition,
    social_influence,
    solve_model,
    solve_named,
    wellbeing_balance,
)
from .ml.features import FeatureExtractor
from .ml.recorder import StateRecorder
from .niche.influence import InfluenceRelation
from .niche.micro_niche import MicroNiche
from .niche.resources import (
    CulturalCapital,
    EconomicCapital,
    EmotionalCapital,
    Resource,
    ResourceBundle,
    SocialCapital,
)
from .viz import (
    plot_agent_comparison,
    plot_aggregate,
    plot_family_network,
    plot_fit_diagnostics,
    plot_niche_space,
    plot_phase_portrait,
    plot_timeseries,
)

__all__ = [
    "ABMFitter",
    "AdultRole",
    "Agent",
    "ChildRole",
    "CulturalCapital",
    "EconomicCapital",
    "ElderRole",
    "EmotionalCapital",
    "Environment",
    "FamilyMember",
    "FeatureExtractor",
    "Household",
    "InfluenceRelation",
    "MicroNiche",
    "ParentRole",
    "Relationship",
    "Resource",
    "ResourceBundle",
    "Role",
    "Scheduler",
    "Simulation",
    "SocialCapital",
    "StateRecorder",
    "compare_models",
    "competition_linear_law",
    "competition_square_law",
    "logistic_growth",
    "lotka_volterra",
    "make_fitter",
    "plot_agent_comparison",
    "plot_aggregate",
    "plot_family_network",
    "plot_fit_diagnostics",
    "plot_niche_space",
    "plot_phase_portrait",
    "plot_timeseries",
    "resource_competition",
    "social_influence",
    "solve_model",
    "solve_named",
    "wellbeing_balance",
]
