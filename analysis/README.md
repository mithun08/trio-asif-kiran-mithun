# Cross-slice analysis & presentation

Tools to measure how matching quality improves slice-by-slice, and the deck that tells the story.

## Files

| File | What it does |
|---|---|
| `slice_stats.py` | Runs the full match pipeline over every role on the real workbook; writes a snapshot + a stats report. |
| `compare_slices.py` | Diffs two snapshots → coverage delta, per-dimension Strong-rate delta, signals-met shift, per-role band changes. |
| `snapshots/<slice>.json` | Machine-readable per-candidate bands + signals. The artifact each slice is measured against. |
| `reports/<slice>-stats.md` | Human-readable metrics for one slice. |

The slide decks live in `presentations/` (open `presentations/index.html`). This `analysis/`
folder is the **data tooling** that backs the numbers shown in those decks.

## Workflow

```bash
# After each slice ships, regenerate its snapshot:
uv run python analysis/slice_stats.py --slice slice1
uv run python analysis/slice_stats.py --slice slice2   # once Slice 2 is built

# Quantify the improvement:
uv run python analysis/compare_slices.py slice1 slice2
```

## The metrics that drive the story

1. **Decision coverage** — share of total scoring weight that carries real (non-placeholder) signal. Slice 1 = **55%** (skill + availability + supply); the other 45% (feedback, adaptability, trend) is pinned at neutral 50 until Slice 2's LLM extraction.
2. **Per-dimension Strong-rate** — how often each dimension reaches the Strong band. The three placeholder dimensions sit at **0%** in Slice 1 by construction.
3. **Signals-met histogram** — distribution of "N of 6 strong". Slice 1 caps at **3 of 6** because three dimensions can never exceed Partial.
4. **Reproducibility** — Slice 1 is byte-deterministic; Slice 2+ targets band/signal stability under caching + temperature 0.

## Slice 1 headline numbers (real data)

- 8 roles · 35 consultants · 135 scored (role, candidate) pairs · 0 LLM calls
- Live decision weight: 55% · placeholder weight: 45%
- skill Strong-rate 5% · availability 95% · supply 53% · feedback/adaptability/trend 0%
- Worked example: **Aarav Krishnan vs ROLE-01** — Slice 1 ranks him #17 at **0 of 6 strong**; Slice 2 target is **5 of 6 strong** (only availability remains a flagged gap).
