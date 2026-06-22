from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl

from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill, Role
from matcher.pipeline.normalise import normalise_location

_PROFICIENCY_MAP: dict[str, int] = {
    "expert": 5,
    "working": 3,
    "experienced": 3,
    "proficient": 3,
    "beginner": 1,
    "learning": 1,
}

_SUPPLY_STATE_MAP: dict[str, str] = {
    "Beach": "beach",
    "Rolling Off": "rolling_off",
    "New Joiners": "new_joiner",
}


def _parse_date(val: object) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        return date.fromisoformat(str(val).strip())
    except (ValueError, TypeError):
        return None


def _parse_required_skill(token: str) -> RequiredSkill:
    token = token.strip()
    match = re.match(r"^(.+?)\s*\((\w+)\)$", token)
    if match:
        name, prof_text = match.group(1).strip(), match.group(2).casefold()
        proficiency = _PROFICIENCY_MAP.get(prof_text)
        return RequiredSkill(name=name, required_proficiency=proficiency)
    return RequiredSkill(name=token)


def _build_header_map(ws: Any, header_row: int = 2) -> dict[str, int]:
    row = next(ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True))
    return {str(cell): idx for idx, cell in enumerate(row) if cell is not None}


def ingest_roles(xlsx_path: Path) -> list[Role]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Open Roles"]
    headers = _build_header_map(ws, header_row=2)

    required_columns = {"Role ID", "Title", "Required Skills", "Location"}
    missing = required_columns - headers.keys()
    if missing:
        raise ValueError(f"Open Roles sheet missing columns: {missing}")

    roles: list[Role] = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        role_id = row[headers["Role ID"]]
        if not role_id:
            continue

        skills_raw = row[headers.get("Required Skills", -1)] or ""
        required_skills = [
            _parse_required_skill(t) for t in str(skills_raw).split(";") if t.strip()
        ]

        loc_raw = str(row[headers.get("Location", -1)] or "")
        locations = [normalise_location(p.strip()) for p in loc_raw.split("/") if p.strip()]

        co_located = str(row[headers.get("Co-location", -1)] or "").strip().casefold() == "yes"
        start_date = _parse_date(row[headers.get("Start", -1)])
        description = str(row[headers.get("Notes / Constraints", -1)] or "")

        roles.append(
            Role(
                id=str(role_id),
                title=str(row[headers["Title"]] or ""),
                description=description,
                required_skills=required_skills,
                locations=locations,
                co_located=co_located,
                start_date=start_date,
            )
        )
    return roles


def _parse_skills(raw: object) -> list[Skill]:
    if not raw:
        return []
    return [
        Skill(name=s.strip(), proficiency=3, years_experience=0.0)
        for s in str(raw).split(",")
        if s.strip()
    ]


def ingest_consultants_from_workbook(xlsx_path: Path) -> list[Consultant]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    result: list[Consultant] = []

    for sheet_name, supply_state in _SUPPLY_STATE_MAP.items():
        ws = wb[sheet_name]
        headers = _build_header_map(ws, header_row=2)

        required_columns = {"Name", "Email", "Grade", "Location"}
        missing = required_columns - headers.keys()
        if missing:
            raise ValueError(f"{sheet_name} sheet missing columns: {missing}")

        skills_col = next(
            (k for k in headers if k.startswith("Key Skills")),
            None,
        )

        for row in ws.iter_rows(min_row=3, values_only=True):
            name = row[headers["Name"]]
            if not name:
                continue

            skills_raw = row[headers[skills_col]] if skills_col else None

            available_from: date | None = None
            rolloff_confidence = "high"

            if supply_state == "rolling_off":
                available_from = _parse_date(row[headers.get("Roll-off Date", -1)])
                rolloff_confidence = str(row[headers.get("Confidence", -1)] or "high").casefold()
            elif supply_state == "new_joiner":
                available_from = _parse_date(row[headers.get("Join Date", -1)])

            result.append(
                Consultant(
                    name=str(name),
                    email=str(row[headers["Email"]] or ""),
                    grade=str(row[headers["Grade"]] or ""),
                    location=str(row[headers["Location"]] or ""),
                    skills=_parse_skills(skills_raw),
                    raw_profile_text=str(row[headers.get("Notes", -1)] or ""),
                    available_from=available_from,
                    supply_state=supply_state,  # type: ignore[arg-type]
                    rolloff_confidence=rolloff_confidence,  # type: ignore[arg-type]
                )
            )

    return result


def ingest_consultants(profiles_dir: Path) -> list[Consultant]:
    raise NotImplementedError


def ingest_feedback(feedback_dir: Path, consultants: list[Consultant]) -> list[Consultant]:
    raise NotImplementedError
