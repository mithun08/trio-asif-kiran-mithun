from __future__ import annotations

from datetime import date

from matcher.models.role import Role


def check(role: Role, today: date) -> list[str]:
    if role.start_date is None:
        return []
    if role.start_date < today:
        return [f"role {role.id} start_date {role.start_date} is in the past"]
    return []
