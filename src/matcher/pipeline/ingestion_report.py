from __future__ import annotations

import re
from pathlib import Path

from matcher.models.consultant import Consultant
from matcher.models.ingestion_report import IngestionReport
from matcher.models.role import Role
from matcher.pipeline.reconcile import ReconcileResult

_EMAIL_KEY_PATTERN = re.compile(r"\*\*Email \(key\):\*\*\s*(\S+)", re.IGNORECASE)


def build(
    roles: list[Role],
    consultants: list[Consultant],
    feedback_dir: Path,
    warnings: list[str],
    reconcile: ReconcileResult | None = None,
) -> IngestionReport:
    profiles_parsed = sum(1 for c in consultants if c.raw_profile_text.strip())
    profiles_low_confidence = [c.email for c in consultants if c.data_confidence < 1.0]
    supply_without_profile = [
        c.email for c in consultants if "profile_pdf_unmatched" in c.data_gaps
    ]

    feedback_matched = 0
    feedback_unmatched: list[str] = []
    if feedback_dir.exists():
        emails = {c.email.casefold() for c in consultants}
        for md_path in sorted(feedback_dir.glob("*.md")):
            content = md_path.read_text(encoding="utf-8")
            m = _EMAIL_KEY_PATTERN.search(content)
            if m and m.group(1).casefold() in emails:
                feedback_matched += 1
            else:
                feedback_unmatched.append(md_path.name)

    return IngestionReport(
        profiles_parsed=profiles_parsed,
        profiles_low_confidence=profiles_low_confidence,
        feedback_matched=feedback_matched,
        feedback_unmatched=feedback_unmatched,
        supply_without_profile=supply_without_profile,
        admitted_external=list(reconcile.admitted) if reconcile else [],
        quarantined_records=list(reconcile.quarantined) if reconcile else [],
        warnings=list(warnings),
    )
