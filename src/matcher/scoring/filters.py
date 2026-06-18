from __future__ import annotations

from matcher.models.consultant import Consultant
from matcher.models.role import Role


def apply_hard_filters(consultants: list[Consultant], role: Role) -> list[Consultant]:
    """Remove consultants that fail location or availability hard constraints."""
    raise NotImplementedError
