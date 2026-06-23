"""Cross-slice statistics + snapshot harness.

Runs the full match pipeline over every open role on the real workbook,
collects metrics, and writes:

  - analysis/snapshots/<slice>.json   — per-(role, candidate) bands + signals
                                          (the artifact Slice N+1 diffs against)
  - analysis/reports/<slice>-stats.md — human-readable metrics report

The snapshot schema is slice-agnostic, so `compare_slices.py` can diff any two
slices to quantify what changed (bands lit up, ranks moved, gaps closed).

Usage:
    uv run python analysis/slice_stats.py --slice slice1
    uv run python analysis/slice_stats.py --slice slice2   # after Slice 2 ships
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from matcher.config import AppConfig, load_adjacency
from matcher.models.consultant import Consultant
from matcher.models.score import ScoredCandidate
from matcher.pipeline.ingest import (
    ingest_consultants_from_workbook,
    ingest_roles,
)
from matcher.pipeline.match import match_role
from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email
from matcher.scoring.ranker import band

DIMENSIONS = [
    "skill_match",
    "feedback_quality",
    "availability",
    "adaptability",
    "supply_state",
    "performance_trend",
]

# Dimensions that carry real, role-dependent signal in Slice 1.
# The rest are pinned at neutral_baseline (placeholders awaiting Slice 2 LLM).
SLICE1_LIVE_DIMENSIONS = {"skill_match", "availability", "supply_state"}


def _candidate_record(c: ScoredCandidate, cfg: Any) -> dict[str, Any]:
    dims = {d.name: round(d.raw_score, 2) for d in c.dimensions}
    bands = {d.name: band(d.raw_score, cfg) for d in c.dimensions}
    signals_met = sum(1 for b in bands.values() if b == "Strong")
    gaps = [name for name, b in bands.items() if b == "Gap"]
    return {
        "email": c.consultant_email,
        "name": c.consultant_name,
        "rank": c.rank,
        "total_score": c.total_score,
        "data_confidence": c.data_confidence,
        "dimensions": dims,
        "bands": bands,
        "signals_met": signals_met,
        "gaps": gaps,
    }


def run(slice_name: str) -> dict[str, Any]:
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    cfg = config.scoring_config
    adjacency = load_adjacency(Path("config/skill_adjacency.yaml"))
    workbook = config.data_dir / "demand-supply.xlsx"

    roles = ingest_roles(workbook)
    consultants: list[Consultant] = ingest_consultants_from_workbook(workbook)
    consultants = dedup_by_email(canonicalise_locations(consultants))

    supply_breakdown = Counter(c.supply_state for c in consultants)

    per_role: dict[str, Any] = {}
    # Aggregates across every scored (role, candidate) pair.
    dim_band_counts: dict[str, Counter[str]] = {d: Counter() for d in DIMENSIONS}
    signals_hist: Counter[int] = Counter()
    total_scored = 0
    total_filtered = 0

    for role in roles:
        ranked, gaps = match_role(
            role, consultants, adjacency, config.weights, cfg, top_n=len(consultants)
        )
        cand_records = [_candidate_record(c, cfg) for c in ranked]
        for rec in cand_records:
            for d in DIMENSIONS:
                dim_band_counts[d][rec["bands"][d]] += 1
            signals_hist[rec["signals_met"]] += 1
        total_scored += len(cand_records)
        total_filtered += len(gaps)

        per_role[role.id] = {
            "title": role.title,
            "co_located": role.co_located,
            "start_date": role.start_date.isoformat() if role.start_date else None,
            "required_skills": [rs.name for rs in role.required_skills],
            "n_passing": len(ranked),
            "n_filtered_out": len(gaps),
            "candidates": cand_records,
            "filtered_out": [{"name": g.consultant_name, "email": g.consultant_email} for g in gaps],
        }

    # Decidable-signal coverage: share of total weight that can move a band in this slice.
    live_weight = sum(
        getattr(config.weights, d) for d in DIMENSIONS if d in SLICE1_LIVE_DIMENSIONS
    )
    placeholder_weight = round(1.0 - live_weight, 4)

    snapshot = {
        "slice": slice_name,
        "corpus": {
            "n_roles": len(roles),
            "n_consultants": len(consultants),
            "supply_breakdown": dict(supply_breakdown),
        },
        "coverage": {
            "live_dimensions": sorted(SLICE1_LIVE_DIMENSIONS),
            "placeholder_dimensions": sorted(set(DIMENSIONS) - SLICE1_LIVE_DIMENSIONS),
            "live_weight": round(live_weight, 4),
            "placeholder_weight": placeholder_weight,
        },
        "aggregates": {
            "total_scored_pairs": total_scored,
            "total_filtered_pairs": total_filtered,
            "dim_band_counts": {d: dict(dim_band_counts[d]) for d in DIMENSIONS},
            "signals_met_histogram": {str(k): v for k, v in sorted(signals_hist.items())},
        },
        "per_role": per_role,
    }
    return snapshot


def _bar(n: int, total: int, width: int = 24) -> str:
    if total == 0:
        return ""
    filled = round(width * n / total)
    return "█" * filled + "·" * (width - filled)


def write_report(snap: dict[str, Any], path: Path) -> None:
    c = snap["corpus"]
    cov = snap["coverage"]
    agg = snap["aggregates"]
    lines: list[str] = []
    L = lines.append

    L(f"# Slice statistics — `{snap['slice']}`\n")
    L("## Corpus\n")
    L(f"- Open roles: **{c['n_roles']}**")
    L(f"- Consultants (deduped): **{c['n_consultants']}**")
    sb = c["supply_breakdown"]
    L(f"- Supply mix: " + ", ".join(f"{k}={v}" for k, v in sb.items()))
    L("")

    L("## Decision coverage (the headline)\n")
    L(f"- Live dimensions (real signal): **{', '.join(cov['live_dimensions'])}**")
    L(f"- Placeholder dimensions (pinned neutral): **{', '.join(cov['placeholder_dimensions'])}**")
    L(f"- **Live decision weight: {cov['live_weight'] * 100:.0f}%** "
      f"— Placeholder weight: {cov['placeholder_weight'] * 100:.0f}%")
    L("")

    L("## Per-dimension band distribution (all scored pairs)\n")
    total_pairs = agg["total_scored_pairs"]
    L(f"Across {total_pairs} (role, candidate) scored pairs:\n")
    L("| Dimension | Strong | Partial | Gap | Strong-rate |")
    L("|---|---|---|---|---|")
    for d in DIMENSIONS:
        bc = agg["dim_band_counts"][d]
        s, p, g = bc.get("Strong", 0), bc.get("Partial", 0), bc.get("Gap", 0)
        rate = f"{100 * s / total_pairs:.0f}%" if total_pairs else "—"
        L(f"| {d} | {s} | {p} | {g} | {rate} |")
    L("")

    L("## Signals-met distribution\n")
    L("How many of 6 dimensions land in the Strong band, per candidate:\n")
    hist = agg["signals_met_histogram"]
    for k in sorted(hist, key=int):
        v = hist[k]
        L(f"- **{k} of 6 strong**: {v} candidates  `{_bar(v, total_pairs)}`")
    L("")

    L("## Coverage / safety\n")
    L(f"- Scored pairs: **{agg['total_scored_pairs']}**")
    L(f"- Filtered-out pairs (surfaced, never silently dropped — FR-43): "
      f"**{agg['total_filtered_pairs']}**")
    L("")

    L("## Per-role summary\n")
    L("| Role | Title | Co-loc | Passing | Filtered | Top candidate (signals) |")
    L("|---|---|---|---|---|---|")
    for rid, r in snap["per_role"].items():
        top = r["candidates"][0] if r["candidates"] else None
        top_str = f"{top['name']} ({top['signals_met']}/6)" if top else "—"
        L(f"| {rid} | {r['title'][:32]} | {'Y' if r['co_located'] else 'N'} | "
          f"{r['n_passing']} | {r['n_filtered_out']} | {top_str} |")
    L("")

    path.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default="slice1", help="slice label, e.g. slice1")
    args = ap.parse_args()

    snap = run(args.slice)
    snap_path = Path("analysis/snapshots") / f"{args.slice}.json"
    report_path = Path("analysis/reports") / f"{args.slice}-stats.md"
    snap_path.write_text(json.dumps(snap, indent=2, default=str))
    write_report(snap, report_path)
    print(f"snapshot → {snap_path}")
    print(f"report   → {report_path}")
    print(f"roles={snap['corpus']['n_roles']} consultants={snap['corpus']['n_consultants']} "
          f"scored_pairs={snap['aggregates']['total_scored_pairs']} "
          f"live_weight={snap['coverage']['live_weight']}")


if __name__ == "__main__":
    main()
