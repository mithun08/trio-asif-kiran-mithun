from __future__ import annotations

from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate


def match_role(
    role: Role,
    consultants: list[Consultant],
    top_n: int = 5,
) -> list[ScoredCandidate]:
    """Apply hard filters, score 6 dimensions, rank, and return top-N candidates."""
    raise NotImplementedError
