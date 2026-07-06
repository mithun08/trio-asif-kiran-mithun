from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from matcher.config import OCRConfig
from matcher.models.consultant import Consultant
from matcher.pipeline.ingest import (
    _EMAIL_KEY_PATTERN,
    _derive_name_from_pdf_stem,
    _extract_pdf_text_cached,
    _parse_feedback_sections,
)

# The workbook is the primary supply roster, but a person absent from it can
# still be admitted when a valid profile AND valid feedback corroborate the same
# identity (exact full-name match). Admitted people carry no supply/availability
# data, so they enter at reduced data_confidence (banded "Low") and flagged.
# Ambiguous names and single-source records are quarantined, never ranked.

_EXTERNAL_CONFIDENCE_FACTOR = 0.45
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_FEEDBACK_NAME_RE = re.compile(r"^#\s*Feedback\s*-\s*(.+)$", re.MULTILINE | re.IGNORECASE)


class ReconcileResult(BaseModel):
    admitted: list[str] = Field(default_factory=list)
    quarantined: list[str] = Field(default_factory=list)
    unlinkable_feedback: list[str] = Field(default_factory=list)


def _canon(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", name.casefold())).strip()


def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _valid_name(name: str) -> bool:
    return len(re.findall(r"[a-zA-Z]", name)) >= 2


def reconcile_external_people(
    consultants: list[Consultant],
    profiles_dir: Path,
    feedback_dir: Path,
    ocr_config: OCRConfig | None = None,
    cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Consultant], ReconcileResult]:
    log = logging.getLogger(__name__)
    result = ReconcileResult()

    existing_emails = {c.email.casefold() for c in consultants}
    existing_names = {_canon(c.name) for c in consultants}

    # Non-workbook profiles keyed by exact canonical name. A name shared by two
    # profiles is ambiguous -> mapped to None so it can never corroborate.
    profile_by_name: dict[str, Path | None] = {}
    if profiles_dir.exists():
        for prof_pdf in sorted(profiles_dir.glob("*.pdf")):
            cn = _canon(_derive_name_from_pdf_stem(prof_pdf.stem))
            if cn in existing_names:
                continue
            profile_by_name[cn] = None if cn in profile_by_name else prof_pdf

    new_consultants: list[Consultant] = []
    used_profiles: set[str] = set()
    if feedback_dir.exists():
        for md in sorted(feedback_dir.glob("*.md")):
            content = md.read_text(encoding="utf-8")
            em = _EMAIL_KEY_PATTERN.search(content)
            email = em.group(1).casefold() if em else ""
            if email and email in existing_emails:
                continue  # already linked to a workbook person by ingest_feedback

            nm = _FEEDBACK_NAME_RE.search(content)
            name = nm.group(1).strip() if nm else ""
            sections = _parse_feedback_sections(content)
            cn = _canon(name)

            if not _valid_email(email):
                result.quarantined.append(f"{md.name} (feedback) - invalid/missing email {email!r}")
                result.unlinkable_feedback.append(md.name)
                continue
            if not _valid_name(name):
                result.quarantined.append(f"{md.name} (feedback) - implausible name {name!r}")
                result.unlinkable_feedback.append(md.name)
                continue
            if not sections:
                result.quarantined.append(f"{md.name} (feedback) - no parseable feedback sections")
                result.unlinkable_feedback.append(md.name)
                continue

            matched_pdf = profile_by_name.get(cn)
            if matched_pdf is None:
                reason = (
                    "ambiguous profile name"
                    if cn in profile_by_name
                    else "no corroborating profile"
                )
                result.quarantined.append(f"{md.name} (feedback) - {reason}")
                result.unlinkable_feedback.append(md.name)
                continue

            raw_text, gaps, conf = _extract_pdf_text_cached(matched_pdf, ocr_config, cache)
            if not raw_text:
                result.quarantined.append(
                    f"{md.name} + {matched_pdf.name} - profile unreadable, cannot corroborate"
                )
                result.unlinkable_feedback.append(md.name)
                continue

            used_profiles.add(cn)
            new_consultants.append(
                Consultant(
                    email=email,
                    name=name,
                    raw_profile_text=raw_text,
                    feedback_text=sections,
                    data_confidence=round(conf * _EXTERNAL_CONFIDENCE_FACTOR, 3),
                    data_gaps=[*gaps, "admitted_external", "no_workbook_record"],
                )
            )
            result.admitted.append(f"{name} <{email}>")

    for cn, leftover_pdf in profile_by_name.items():
        if leftover_pdf is not None and cn not in used_profiles:
            result.quarantined.append(f"{leftover_pdf.name} (profile) - no corroborating feedback")

    if result.admitted:
        log.info("Admitted %d external consultants via corroboration", len(result.admitted))
    return [*consultants, *new_consultants], result
