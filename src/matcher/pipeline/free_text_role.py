from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

import dspy

from matcher.llm.extract import _parse_json_list
from matcher.llm.modules import QueryParse
from matcher.models.query_spec import SkillCriterion
from matcher.models.role import RequiredSkill, Role
from matcher.observability.telemetry import tap_lm_history
from matcher.pipeline.normalise import normalise_location

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_NEXT_MONTH = re.compile(r"\bnext\s+month\b", re.IGNORECASE)
_END_NEXT_MONTH = re.compile(r"\bend\s+of\s+next\s+month\b", re.IGNORECASE)
_MID_NEXT_MONTH = re.compile(r"\bmid(?:dle)?\s*(?:of\s+)?next\s+month\b", re.IGNORECASE)
_NEXT_WEEK = re.compile(r"\bnext\s+week\b", re.IGNORECASE)
_IN_N_UNITS = re.compile(r"\bin\s+(\d+)\s+(day|week|month)s?\b", re.IGNORECASE)
_ASAP = re.compile(r"\b(asap|immediately|right away|as soon as possible)\b", re.IGNORECASE)
_TODAY = re.compile(r"\btoday\b", re.IGNORECASE)
_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_NOW = re.compile(r"\bnow\b", re.IGNORECASE)
_VALID_SUPPLY_STATES = ("beach", "rolling_off", "new_joiner")


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _next_month_first(today: date) -> date:
    return _add_months(today.replace(day=1), 1)


def resolve_relative_date(phrase: str, today: date) -> date | None:
    phrase = phrase.strip()
    if not phrase:
        return None

    iso = _ISO_DATE.search(phrase)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None

    if _ASAP.search(phrase) or _NOW.search(phrase) or _TODAY.search(phrase):
        return today
    if _TOMORROW.search(phrase):
        return today + timedelta(days=1)
    if _END_NEXT_MONTH.search(phrase):
        first = _next_month_first(today)
        last_day = calendar.monthrange(first.year, first.month)[1]
        return first.replace(day=last_day)
    if _MID_NEXT_MONTH.search(phrase):
        return _next_month_first(today).replace(day=15)
    if _NEXT_MONTH.search(phrase):
        return _next_month_first(today)
    if _NEXT_WEEK.search(phrase):
        return today + timedelta(days=7)

    in_n = _IN_N_UNITS.search(phrase)
    if in_n:
        n, unit = int(in_n.group(1)), in_n.group(2).lower()
        if unit == "day":
            return today + timedelta(days=n)
        if unit == "week":
            return today + timedelta(days=7 * n)
        return _add_months(today, n)

    return None


def _parse_deterministic(
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


def _parse_with_llm(text: str, lm: Any, today: date) -> tuple[Role, list[str]]:
    ambiguities: list[str] = []

    with dspy.context(lm=lm):
        result = dspy.Predict(QueryParse)(query_text=text)
    tap_lm_history(lm, "query_parse")

    title = str(getattr(result, "title", "")).strip() or "Unknown Role"
    if title == "Unknown Role":
        ambiguities.append("title: could not parse a role title")

    criteria: list[SkillCriterion] = []
    for item in _parse_json_list(getattr(result, "skills_json", "[]")):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        polarity = str(item.get("polarity", "require")).strip().lower()
        if not name or polarity not in ("require", "prefer", "exclude"):
            continue
        min_prof_raw = item.get("min_proficiency")
        min_prof = int(min_prof_raw) if isinstance(min_prof_raw, (int, float)) else None
        criteria.append(
            SkillCriterion(name=name, polarity=polarity, min_proficiency=min_prof)  # type: ignore[arg-type]
        )
    if not criteria:
        ambiguities.append("skills: no recognised skills found")

    include_locations = [
        normalise_location(loc)
        for loc in _parse_json_list(getattr(result, "include_locations_json", "[]"))
        if isinstance(loc, str) and loc.strip()
    ]
    exclude_locations = [
        normalise_location(loc)
        for loc in _parse_json_list(getattr(result, "exclude_locations_json", "[]"))
        if isinstance(loc, str) and loc.strip()
    ]
    if not include_locations and not exclude_locations:
        ambiguities.append("location: no recognised location found")

    exclude_supply_states = [
        s
        for s in _parse_json_list(getattr(result, "exclude_supply_states_json", "[]"))
        if s in _VALID_SUPPLY_STATES
    ]

    relative_phrase = str(getattr(result, "relative_start_phrase", "")).strip()
    start_date = resolve_relative_date(relative_phrase, today) if relative_phrase else None
    if not relative_phrase:
        ambiguities.append("start_date: no date found in text")
    elif start_date is None:
        ambiguities.append(f"start_date: could not resolve phrase {relative_phrase!r}")

    required_skills = [
        RequiredSkill(
            name=c.name,
            mandatory=c.polarity == "require",
            required_proficiency=c.min_proficiency,
        )
        for c in criteria
        if c.polarity in ("require", "prefer")
    ]
    exclude_skills = [c.name for c in criteria if c.polarity == "exclude"]

    role = Role(
        id="FREE-TEXT",
        title=title,
        required_skills=required_skills,
        locations=include_locations,
        co_located=bool(include_locations),
        start_date=start_date,
        exclude_skills=exclude_skills,
        exclude_locations=exclude_locations,
        exclude_supply_states=exclude_supply_states,
    )
    return role, ambiguities


def parse(
    text: str,
    known_locations: set[str],
    known_skills: set[str],
    lm: Any = None,
    today: date | None = None,
) -> tuple[Role, list[str]]:
    if lm is not None:
        return _parse_with_llm(text, lm, today or date.today())
    return _parse_deterministic(text, known_locations, known_skills)
