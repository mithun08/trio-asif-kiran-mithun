from __future__ import annotations

import hashlib
from pathlib import Path

import typer

from matcher.config import AppConfig, load_adjacency
from matcher.llm.cache import configure_dspy_cache
from matcher.llm.client import configure_lm
from matcher.models.output import DataQualityReport, RunOutput
from matcher.pipeline.explain import generate_explanations
from matcher.pipeline.extract import extract_signals
from matcher.pipeline.gap import build_gap_report
from matcher.pipeline.ingest import (
    ingest_consultants,
    ingest_consultants_from_workbook,
    ingest_feedback,
    ingest_roles,
)
from matcher.pipeline.match import match_role
from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email, scrub_pii
from matcher.render.json import render_json
from matcher.render.text import print_results
from matcher.scoring.confidence import attach_confidence_levels
from matcher.scoring.info_flags import attach_info_flags

app = typer.Typer(name="dsm", help="Demand-Supply Matcher CLI")


@app.command()
def match(
    role_id: str = typer.Argument(..., help="Role ID (e.g. ROLE-01)"),
    top_n: int = typer.Option(5, "--top", "-n", help="Number of candidates to return"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Skip LLM extraction; run deterministic scoring only"
    ),
    no_explanations: bool = typer.Option(
        False, "--no-explanations", help="Skip LLM explanation generation"
    ),
) -> None:
    """Rank consultants for a given role ID."""
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))

    if not no_llm:
        configure_dspy_cache(config.cache_dir)
        configure_lm(config)

    workbook = config.data_dir / "demand-supply.xlsx"
    roles = ingest_roles(workbook)
    role = next((r for r in roles if r.id == role_id), None)
    if role is None:
        typer.echo(f"Role {role_id!r} not found.", err=True)
        raise typer.Exit(code=1)

    consultants = ingest_consultants_from_workbook(workbook)
    consultants = ingest_consultants(config.data_dir / "profiles", consultants)
    consultants = ingest_feedback(config.data_dir / "project_feedback", consultants)
    consultants = canonicalise_locations(consultants)
    consultants = dedup_by_email(consultants)
    consultants = scrub_pii(consultants)

    if not no_llm:
        consultants = extract_signals(consultants, config.scoring_config)

    ranked, gaps = match_role(
        role, consultants, adjacency_map, config.weights, config.scoring_config, top_n=top_n
    )

    ranked = attach_confidence_levels(ranked, consultants, config.scoring_config)
    ranked = attach_info_flags(ranked, consultants, role, config.scoring_config)

    if not no_llm and not no_explanations:
        ranked = generate_explanations(ranked, role, consultants, config)

    gap_report = build_gap_report(
        role,
        consultants,
        ranked,
        gaps,
        adjacency_map,
        config.weights,
        config.scoring_config,
        config,
    )

    stat = workbook.stat()
    snapshot_id = hashlib.sha256(f"{stat.st_mtime}{stat.st_size}".encode()).hexdigest()[:16]

    output = RunOutput(
        snapshot_id=snapshot_id,
        role_id=role_id,
        candidates=ranked,
        gap_report=gap_report,
        role_snapshot=role,
        data_quality=DataQualityReport(total_consultants_ingested=len(consultants)),
    )

    if output_json:
        typer.echo(render_json(output))
    else:
        print_results(ranked, gaps, config.scoring_config, gap_report=gap_report)


@app.command()
def ingest(
    data_dir: str = typer.Option("data/", "--data-dir", help="Directory containing source files"),
    force: bool = typer.Option(False, "--force", help="Force re-ingest even if index is current"),
) -> None:
    """Ingest source files and rebuild the vector index."""
    typer.echo(f"Ingesting from {data_dir!r} (force={force})")


if __name__ == "__main__":
    app()
