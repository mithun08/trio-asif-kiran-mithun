from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path

import typer

from matcher.config import AppConfig, load_adjacency
from matcher.llm.cache import configure_dspy_cache
from matcher.llm.client import configure_lm
from matcher.models.errors import IngestionError
from matcher.models.output import DataQualityReport, RunOutput
from matcher.observability import telemetry as _telemetry
from matcher.observability.run_log import configure_log_sink, log_data_quality, log_run_start
from matcher.observability.timing import stage_timer
from matcher.pipeline import stale_date
from matcher.pipeline.explain import generate_explanations
from matcher.pipeline.extract import extract_signals
from matcher.pipeline.free_text_role import parse as parse_free_text_role
from matcher.pipeline.gap import build_gap_report
from matcher.pipeline.ingest import (
    ingest_consultants,
    ingest_consultants_from_workbook,
    ingest_feedback,
    ingest_roles,
)
from matcher.pipeline.ingestion_report import build as build_ingestion_report
from matcher.pipeline.match import match_role
from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email, scrub_pii
from matcher.render.json import render_json
from matcher.render.text import print_results
from matcher.scoring.confidence import attach_confidence_levels
from matcher.scoring.info_flags import attach_info_flags

app = typer.Typer(name="dsm", help="Demand-Supply Matcher CLI")


@app.command()
def match(
    role_id: str | None = typer.Argument(None, help="Role ID (e.g. ROLE-01)"),
    top_n: int = typer.Option(5, "--top", "-n", help="Number of candidates to return"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Skip LLM extraction; run deterministic scoring only"
    ),
    no_explanations: bool = typer.Option(
        False, "--no-explanations", help="Skip LLM explanation generation"
    ),
    free_text: str | None = typer.Option(None, "--free-text", help="Free-text role spec"),
    yes: bool = typer.Option(False, "--yes", help="Accept defaults for ambiguous free-text"),
) -> None:
    """Rank consultants for a given role ID."""
    if role_id is None and free_text is None:
        typer.echo("Provide a role ID or --free-text.", err=True)
        raise typer.Exit(code=1)

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))

    _telemetry.reset()
    configure_log_sink(config.observability.log_path)
    log_run_start(uuid.uuid4().hex[:16], "0.1.0")

    if not no_llm:
        configure_dspy_cache(config.cache_dir)
        configure_lm(config)

    workbook = config.data_dir / "demand-supply.xlsx"

    with stage_timer("ingest", _telemetry.current_telemetry):
        try:
            roles = ingest_roles(workbook)
            consultants = ingest_consultants_from_workbook(workbook)
            consultants = ingest_consultants(
                config.data_dir / "profiles", consultants, ocr_config=config.ocr
            )
            consultants = ingest_feedback(config.data_dir / "project_feedback", consultants)
        except IngestionError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)

    if free_text is not None:
        known_locations = {loc for r in roles for loc in r.locations}
        known_skills = {s.name for r in roles for s in r.required_skills}
        role, ambiguities = parse_free_text_role(free_text, known_locations, known_skills)
        if ambiguities:
            for amb in ambiguities:
                typer.echo(f"  warning: {amb}", err=True)
            if not yes:
                typer.confirm("Proceed with these defaults?", abort=True)
        resolved_role_id = "FREE-TEXT"
    else:
        _found = next((r for r in roles if r.id == role_id), None)
        if _found is None:
            typer.echo(f"Role {role_id!r} not found.", err=True)
            raise typer.Exit(code=1)
        role = _found
        resolved_role_id = role_id  # type: ignore[assignment]

    stale_warnings = stale_date.check(role, date.today())
    ingestion_rep = build_ingestion_report(
        roles, consultants, config.data_dir / "project_feedback", stale_warnings
    )

    with stage_timer("normalise", _telemetry.current_telemetry):
        consultants = canonicalise_locations(consultants)
        consultants = dedup_by_email(consultants)
        consultants = scrub_pii(consultants)

    if not no_llm:
        with stage_timer("extract", _telemetry.current_telemetry):
            consultants = extract_signals(consultants, config.scoring_config)

    with stage_timer("match", _telemetry.current_telemetry):
        ranked, gaps = match_role(
            role, consultants, adjacency_map, config.weights, config.scoring_config, top_n=top_n
        )

    with stage_timer("confidence_and_flags", _telemetry.current_telemetry):
        ranked = attach_confidence_levels(ranked, consultants, config.scoring_config)
        ranked = attach_info_flags(ranked, consultants, role, config.scoring_config)

    with stage_timer("gap", _telemetry.current_telemetry):
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

    if not no_llm and not no_explanations:
        with stage_timer("explain", _telemetry.current_telemetry):
            ranked = generate_explanations(ranked, role, consultants, config)

    stat = workbook.stat()
    snapshot_id = hashlib.sha256(f"{stat.st_mtime}{stat.st_size}".encode()).hexdigest()[:16]

    run_tel = _telemetry.snapshot()
    output = RunOutput(
        snapshot_id=snapshot_id,
        role_id=resolved_role_id,
        candidates=ranked,
        gap_report=gap_report,
        role_snapshot=role,
        data_quality=DataQualityReport(total_consultants_ingested=len(consultants)),
        ingestion_report=ingestion_rep,
        run_telemetry=run_tel,
    )

    log_data_quality(
        ingestion_rep.feedback_unmatched,
        ingestion_rep.profiles_low_confidence,
    )

    if output_json:
        typer.echo(render_json(output))
    else:
        print_results(
            ranked,
            gaps,
            config.scoring_config,
            gap_report=gap_report,
            ingestion_report=ingestion_rep,
            run_telemetry=run_tel,
        )


@app.command()
def ingest(
    data_dir: str = typer.Option("data/", "--data-dir", help="Directory containing source files"),
    force: bool = typer.Option(False, "--force", help="Force re-ingest even if index is current"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Ingest source files and report ingestion quality."""
    data_path = Path(data_dir)
    workbook = data_path / "demand-supply.xlsx"
    try:
        roles = ingest_roles(workbook)
        consultants = ingest_consultants_from_workbook(workbook)
        consultants = ingest_consultants(data_path / "profiles", consultants)
        consultants = ingest_feedback(data_path / "project_feedback", consultants)
    except IngestionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    report = build_ingestion_report(roles, consultants, data_path / "project_feedback", [])
    if output_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(f"profiles_parsed: {report.profiles_parsed}")
        typer.echo(f"low_confidence: {len(report.profiles_low_confidence)}")
        typer.echo(f"feedback_matched: {report.feedback_matched}")
        typer.echo(f"feedback_unmatched: {len(report.feedback_unmatched)}")
        typer.echo(f"supply_without_profile: {len(report.supply_without_profile)}")
        for w in report.warnings:
            typer.echo(f"  warning: {w}", err=True)


if __name__ == "__main__":
    app()
