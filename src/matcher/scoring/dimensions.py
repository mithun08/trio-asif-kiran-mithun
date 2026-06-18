from __future__ import annotations

from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import DimensionScore


def score_skill_match(consultant: Consultant, role: Role) -> DimensionScore:
    """Score skill match (weight 0.35): exact → synonym → vector similarity layers."""
    raise NotImplementedError


def score_feedback_quality(consultant: Consultant) -> DimensionScore:
    """Score feedback quality (weight 0.25)."""
    raise NotImplementedError


def score_availability(consultant: Consultant, role: Role) -> DimensionScore:
    """Score availability (weight 0.15)."""
    raise NotImplementedError


def score_adaptability(consultant: Consultant) -> DimensionScore:
    """Score adaptability (weight 0.15)."""
    raise NotImplementedError


def score_supply_state(consultant: Consultant) -> DimensionScore:
    """Score supply state signal (weight 0.05)."""
    raise NotImplementedError


def score_performance_trend(consultant: Consultant) -> DimensionScore:
    """Score performance trend (weight 0.05)."""
    raise NotImplementedError
