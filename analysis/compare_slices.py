"""Diff two slice snapshots to quantify quality improvement.

Reads analysis/snapshots/<a>.json and <b>.json (produced by slice_stats.py)
and reports what changed between slices:

  - decision coverage delta (live vs placeholder weight)
  - per-dimension Strong-rate delta (which dimensions "lit up")
  - signals-met shift (candidates moving to higher signal counts)
  - per-candidate band changes for a focus role (default ROLE-01)

Usage:
    uv run python analysis/compare_slices.py slice1 slice2
    uv run python analysis/compare_slices.py slice1 slice2 --role ROLE-01
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DIMENSIONS = [
    "skill_match",
    "feedback_quality",
    "availability",
    "adaptability",
    "supply_state",
    "performance_trend",
]


def _load(name: str) -> dict[str, Any]:
    return json.loads((Path("analysis/snapshots") / f"{name}.json").read_text())


def _strong_rate(snap: dict[str, Any], dim: str) -> float:
    agg = snap["aggregates"]
    total = agg["total_scored_pairs"] or 1
    return 100 * agg["dim_band_counts"][dim].get("Strong", 0) / total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--role", default="ROLE-01")
    args = ap.parse_args()

    a, b = _load(args.a), _load(args.b)

    print(f"=== Coverage: {args.a} → {args.b} ===")
    print(f"live weight:        {a['coverage']['live_weight']:.2f} → {b['coverage']['live_weight']:.2f}")
    print(f"placeholder weight: {a['coverage']['placeholder_weight']:.2f} → "
          f"{b['coverage']['placeholder_weight']:.2f}")

    print(f"\n=== Per-dimension Strong-rate ===")
    print(f"{'dimension':<20}{args.a:>10}{args.b:>10}{'Δ':>10}")
    for d in DIMENSIONS:
        ra, rb = _strong_rate(a, d), _strong_rate(b, d)
        print(f"{d:<20}{ra:>9.0f}%{rb:>9.0f}%{rb - ra:>+9.0f}%")

    print(f"\n=== Signals-met histogram ===")
    ha = a["aggregates"]["signals_met_histogram"]
    hb = b["aggregates"]["signals_met_histogram"]
    for k in sorted(set(ha) | set(hb), key=int):
        print(f"  {k} of 6 strong: {ha.get(k, 0):>4} → {hb.get(k, 0):>4}")

    print(f"\n=== Band changes for {args.role} ===")
    ra = {c["email"]: c for c in a["per_role"].get(args.role, {}).get("candidates", [])}
    rb = {c["email"]: c for c in b["per_role"].get(args.role, {}).get("candidates", [])}
    for email in sorted(set(ra) & set(rb)):
        ca, cb = ra[email], rb[email]
        changed = [
            f"{d}: {ca['bands'][d]}→{cb['bands'][d]}"
            for d in DIMENSIONS
            if ca["bands"][d] != cb["bands"][d]
        ]
        if changed:
            print(f"  {cb['name']} (signals {ca['signals_met']}→{cb['signals_met']}, "
                  f"rank {ca['rank']}→{cb['rank']}): {'; '.join(changed)}")


if __name__ == "__main__":
    main()
