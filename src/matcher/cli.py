from __future__ import annotations

import os

# Milvus Lite and torch (via sentence-transformers) each link their own libomp;
# the duplicate OpenMP init segfaults on macOS. Allow the duplicate, and force
# faiss's HNSW add single-threaded — allowing the duplicate alone is not enough,
# only pinning threads avoids the crash in faiss `add`. Set before any native
# lib is imported so libomp reads it at init and Milvus Lite inherits it.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import json
import logging
import resource
from pathlib import Path

import typer

from matcher.config import AppConfig, load_adjacency
from matcher.models.errors import IngestionError
from matcher.observability.run_log import configure_log_sink
from matcher.pipeline.orchestrate import (
    RoleNotFoundError,
    build_context,
    describe_parsed_role,
    resolve_role,
    run_ingest,
    run_match,
)
from matcher.pipeline.relevance import RelevanceVerdict
from matcher.render.json import render_json
from matcher.render.text import print_results

_FD_LIMIT_TARGET = 8192


def _raise_fd_limit() -> None:
    # Concurrent LLM extraction opens more file descriptors (sockets + model
    # files + litellm's per-call lazy imports) than macOS's default ulimit -n
    # of 256 allows, causing Errno 24. Raise the soft limit once at startup
    # instead of requiring a manual `ulimit -n` before every run.
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = _FD_LIMIT_TARGET if hard == resource.RLIM_INFINITY else min(_FD_LIMIT_TARGET, hard)
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError):
        pass


_raise_fd_limit()

# ingest.py logs routine per-file data-quality notices ("no workbook match",
# "orphan feedback file") at WARNING via the stdlib logger; those already
# surface in the ingestion report, so keep them out of the console by
# default — real errors still propagate at ERROR and above.
logging.getLogger("matcher.pipeline.ingest").setLevel(logging.ERROR)

app = typer.Typer(name="dsm", help="Demand-Supply Matcher CLI")


def _print_rejection(verdict: RelevanceVerdict, query: str, output_json: bool) -> None:
    if output_json:
        typer.echo(json.dumps({"status": "rejected", "reason": verdict.reason, "query": query}))
    else:
        typer.echo("No match run — this doesn't look like a staffing request.")
        typer.echo(f"  reason: {verdict.reason}")
        typer.echo(
            '  try rephrasing with a real skill or role, e.g. "Python engineer, available ASAP"'
        )


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
    configure_log_sink(config.observability.log_path)

    try:
        ctx = build_context(config, adjacency_map, no_llm)
    except IngestionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    try:
        role, resolved_role_id, ambiguities, verdict = resolve_role(ctx, role_id, free_text)
    except RoleNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    if free_text is not None:
        typer.echo(f"  interpreted as: {describe_parsed_role(role)}", err=True)
        for amb in ambiguities:
            typer.echo(f"  warning: {amb}", err=True)

        if verdict is not None:
            _print_rejection(verdict, free_text, output_json)
            return

        if ambiguities and not yes:
            typer.confirm("Proceed with these defaults?", abort=True)

    result = run_match(
        ctx,
        role,
        resolved_role_id,
        top_n=top_n,
        no_explanations=no_explanations,
        free_text_query=free_text,
    )
    if isinstance(result, RelevanceVerdict):
        _print_rejection(result, free_text or "", output_json)
        return
    output, gaps = result

    if output_json:
        typer.echo(render_json(output))
    else:
        print_results(
            output.candidates,
            gaps,
            config.scoring_config,
            gap_report=output.gap_report,
            ingestion_report=output.ingestion_report,
            run_telemetry=output.run_telemetry,
        )


@app.command()
def ingest(
    data_dir: str = typer.Option("data/", "--data-dir", help="Directory containing source files"),
    force: bool = typer.Option(False, "--force", help="Force re-ingest even if index is current"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM extraction"),
) -> None:
    """Ingest source files and report ingestion quality."""
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    configure_log_sink(config.observability.log_path)
    try:
        report = run_ingest(config, Path(data_dir), force=force, no_llm=no_llm)
    except IngestionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    if output_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(f"profiles_parsed: {report.profiles_parsed}")
        typer.echo(f"low_confidence: {len(report.profiles_low_confidence)}")
        typer.echo(f"feedback_matched: {report.feedback_matched}")
        typer.echo(f"feedback_unmatched: {len(report.feedback_unmatched)}")
        typer.echo(f"admitted_external: {len(report.admitted_external)}")
        typer.echo(f"quarantined_records: {len(report.quarantined_records)}")
        typer.echo(f"supply_without_profile: {len(report.supply_without_profile)}")
        for w in report.warnings:
            typer.echo(f"  warning: {w}", err=True)


if __name__ == "__main__":
    app()
