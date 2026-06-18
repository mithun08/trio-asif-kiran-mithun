from __future__ import annotations

from matcher.models.role import Role
from matcher.models.score import ScoredCandidate


def generate_explanations(
    candidates: list[ScoredCandidate],
    role: Role,
) -> list[ScoredCandidate]:
    """Generate NL explanations for each candidate via DSPy → OpenRouter."""
    raise NotImplementedError
