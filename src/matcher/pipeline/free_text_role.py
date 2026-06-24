from __future__ import annotations

import re
from datetime import date

from matcher.models.role import RequiredSkill, Role
from matcher.pipeline.normalise import normalise_location

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_NEXT_MONTH = re.compile(r"\bnext\s+month\b", re.IGNORECASE)


def parse(
    text: str,
    known_locations: set[str],
    known_skills: set[str],
) -> tuple[Role, list[str]]:
    ambiguities: list[str] = []

    title_match = re.search(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,4})\b", text)
    title = title_match.group(1) if title_match else "Unknown Role"
    if title == "Unknown Role":
        ambiguities.append("title: could not parse a capitalised phrase")

    locations = [
        normalise_location(loc)
        for loc in known_locations
        if re.search(re.escape(loc), text, re.IGNORECASE)
    ]
    if not locations:
        ambiguities.append("location: no recognised location found")

    required_skills = [
        RequiredSkill(name=skill, mandatory=True)
        for skill in known_skills
        if re.search(r"\b" + re.escape(skill) + r"\b", text, re.IGNORECASE)
    ]
    if not required_skills:
        ambiguities.append("skills: no recognised skills found")

    start_date: date | None = None
    dm = _ISO_DATE.search(text)
    if dm:
        try:
            start_date = date.fromisoformat(dm.group(1))
        except ValueError:
            ambiguities.append(f"start_date: {dm.group(1)!r} not a valid ISO date")
    elif _NEXT_MONTH.search(text):
        ambiguities.append("start_date: 'next month' not parseable as ISO date")
    else:
        ambiguities.append("start_date: no date found in text")

    role = Role(
        id="FREE-TEXT",
        title=title,
        required_skills=required_skills,
        locations=locations,
        start_date=start_date,
    )
    return role, ambiguities
