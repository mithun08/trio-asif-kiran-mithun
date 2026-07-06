from __future__ import annotations

import os

# Milvus Lite and torch (via sentence-transformers) each link their own libomp;
# the duplicate OpenMP init segfaults on macOS. Allow the duplicate, and force
# faiss's HNSW add single-threaded — allowing the duplicate alone is not enough,
# only pinning threads avoids the crash in faiss `add`. Set before any native
# lib is imported so libomp reads it at init and Milvus Lite inherits it.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio
import hashlib
import json
import logging
import resource
import uuid
from datetime import date
from pathlib import Path

import typer

from matcher.config import AppConfig, load_adjacency
from matcher.llm.cache import configure_dspy_cache
from matcher.llm.client import configure_lm, make_lm
from matcher.models.consultant import Consultant
from matcher.models.errors import IngestionError
from matcher.models.output import DataQualityReport, RunOutput
from matcher.models.role import Role
from matcher.observability import telemetry as _telemetry
from matcher.observability.run_log import configure_log_sink, log_data_quality, log_run_start
from matcher.observability.snapshot_archive import prune_snapshots, save_snapshot
from matcher.observability.timing import stage_timer
from matcher.pipeline import stale_date
from matcher.pipeline.explain import generate_explanations
from matcher.pipeline.extract import extract_signals, extract_signals_async
from matcher.pipeline.free_text_role import parse as parse_free_text_role
from matcher.pipeline.gap import build_gap_report
from matcher.pipeline.index import build_index, load_index
from matcher.pipeline.ingest import (
    ingest_consultants,
    ingest_consultants_from_workbook,
    ingest_feedback,
    ingest_roles,
)
from matcher.pipeline.ingestion_report import build as build_ingestion_report
from matcher.pipeline.match import match_role
from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email, scrub_pii
from matcher.pipeline.reconcile import reconcile_external_people
from matcher.pipeline.relevance import (
    RelevanceVerdict,
    check_domain_plausibility,
    check_skill_evidence,
)
from matcher.pipeline.store import (
    hash_consultant_sources,
    load_store,
    load_text_cache,
    save_store,
    save_text_cache,
)
from matcher.render.json import render_json
from matcher.render.text import print_results
from matcher.scoring.confidence import attach_confidence_levels
from matcher.scoring.info_flags import attach_info_flags

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


def _compute_snapshot_id(
    workbook: Path,
    profiles_dir: Path,
    feedback_dir: Path,
    embedding_model: str = "",
) -> str:
    h = hashlib.sha256()

    for path in sorted(
        [
            workbook,
            Path("config/default.yaml"),
            Path("config/skill_adjacency.yaml"),
        ]
    ):
        if path.exists():
            s = path.stat()
            h.update(f"{path.name}:{s.st_mtime}:{s.st_size}".encode())

    for directory in (profiles_dir, feedback_dir):
        if directory.exists():
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    s = path.stat()
                    h.update(f"{path.name}:{s.st_mtime}:{s.st_size}".encode())

    if embedding_model:
        h.update(embedding_model.encode())

    return h.hexdigest()[:16]


def _describe_parsed_role(role: Role) -> str:
    parts = [f"title={role.title!r}"]
    required = [rs.name for rs in role.required_skills if rs.mandatory]
    preferred = [rs.name for rs in role.required_skills if not rs.mandatory]
    if required:
        parts.append(f"require={required}")
    if preferred:
        parts.append(f"prefer={preferred}")
    if role.exclude_skills:
        parts.append(f"exclude_skills={role.exclude_skills}")
    if role.locations:
        parts.append(f"locations={role.locations}")
    if role.exclude_locations:
        parts.append(f"exclude_locations={role.exclude_locations}")
    if role.exclude_supply_states:
        parts.append(f"exclude_supply_states={role.exclude_supply_states}")
    parts.append(f"start_date={role.start_date}")
    return " | ".join(parts)


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

    _telemetry.reset()
    configure_log_sink(config.observability.log_path)
    run_id = uuid.uuid4().hex[:16]
    log_run_start(run_id, "0.1.0")

    primary_lm = None
    fallback_lm = None
    query_lm = None
    if not no_llm:
        configure_dspy_cache(config.cache_dir)
        primary_lm = configure_lm(config)
        fallback_lm = make_lm(config.model_fallback, config)
        query_lm = make_lm(config.model_skill_inference, config)

    workbook = config.data_dir / "demand-supply.xlsx"
    text_cache_path = config.cache_dir / "profile_text_cache.json"
    text_cache = load_text_cache(text_cache_path)

    with stage_timer("ingest", _telemetry.current_telemetry):
        try:
            roles = ingest_roles(workbook)
            consultants = ingest_consultants_from_workbook(workbook)
            consultants = ingest_consultants(
                config.data_dir / "profiles",
                consultants,
                ocr_config=config.ocr,
                cache=text_cache,
            )
            consultants = ingest_feedback(config.data_dir / "project_feedback", consultants)
            consultants, reconcile_result = reconcile_external_people(
                consultants,
                config.data_dir / "profiles",
                config.data_dir / "project_feedback",
                config.ocr,
                cache=text_cache,
            )
        except IngestionError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)
        save_text_cache(text_cache, text_cache_path)

    if free_text is not None:
        known_locations = {loc for r in roles for loc in r.locations}
        known_skills = {s.name for r in roles for s in r.required_skills}
        role, ambiguities = parse_free_text_role(
            free_text, known_locations, known_skills, lm=query_lm, today=date.today()
        )
        typer.echo(f"  interpreted as: {_describe_parsed_role(role)}", err=True)
        if ambiguities:
            for amb in ambiguities:
                typer.echo(f"  warning: {amb}", err=True)

        plausibility = check_domain_plausibility(free_text, role, lm=query_lm)
        if plausibility is not None and not plausibility.in_domain:
            _print_rejection(plausibility, free_text, output_json)
            return

        if ambiguities and not yes:
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
        roles, consultants, config.data_dir / "project_feedback", stale_warnings, reconcile_result
    )

    with stage_timer("normalise", _telemetry.current_telemetry):
        consultants = canonicalise_locations(consultants)
        consultants = dedup_by_email(consultants)
        consultants = scrub_pii(consultants)

    if not no_llm:
        store_path = config.cache_dir / "extracted_consultants.json"
        if store_path.exists():
            stored = load_store(store_path)
            stored_by_email = {c.email.casefold(): c for c in stored}
            consultants = [stored_by_email.get(c.email.casefold(), c) for c in consultants]
            consultants_needing_extract = [
                c for c in consultants if c.email.casefold() not in stored_by_email
            ]
            if consultants_needing_extract:
                with stage_timer("extract", _telemetry.current_telemetry):
                    extracted_new = extract_signals(
                        consultants_needing_extract,
                        config.scoring_config,
                        app_config=config,
                        primary_lm=primary_lm,
                        fallback_lm=fallback_lm,
                    )
                extracted_map = {c.email.casefold(): c for c in extracted_new}
                consultants = [extracted_map.get(c.email.casefold(), c) for c in consultants]
        else:
            with stage_timer("extract", _telemetry.current_telemetry):
                consultants = extract_signals(
                    consultants,
                    config.scoring_config,
                    app_config=config,
                    primary_lm=primary_lm,
                    fallback_lm=fallback_lm,
                )

    index_client = load_index(config.cache_dir / "milvus")
    embedding_model = None
    if index_client is not None:
        from sentence_transformers import SentenceTransformer

        embedding_model = SentenceTransformer(config.embedding_model)

    if free_text is not None:
        verdict = check_skill_evidence(
            role,
            consultants,
            roles,
            adjacency_map,
            config.scoring_config,
            index_client=index_client,
            embedding_model=embedding_model,
            lm=query_lm,
            query_text=free_text,
        )
        if verdict is not None and not verdict.in_domain:
            _print_rejection(verdict, free_text, output_json)
            return

    with stage_timer("match", _telemetry.current_telemetry):
        ranked, gaps = match_role(
            role,
            consultants,
            adjacency_map,
            config.weights,
            config.scoring_config,
            top_n=top_n,
            index_client=index_client,
            embedding_model=embedding_model,
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

    snapshot_id = _compute_snapshot_id(
        workbook,
        config.data_dir / "profiles",
        config.data_dir / "project_feedback",
        embedding_model=config.embedding_model,
    )

    run_tel = _telemetry.snapshot()
    output = RunOutput(
        snapshot_id=snapshot_id,
        run_id=run_id,
        role_id=resolved_role_id,
        candidates=ranked,
        gap_report=gap_report,
        role_snapshot=role,
        data_quality=DataQualityReport(total_consultants_ingested=len(consultants)),
        ingestion_report=ingestion_rep,
        run_telemetry=run_tel,
    )

    try:
        save_snapshot(output, config.observability.snapshot_dir)
        prune_snapshots(config.observability.snapshot_dir, config.observability.snapshot_retention)
    except OSError:
        pass

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
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM extraction"),
) -> None:
    """Ingest source files and report ingestion quality."""
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    configure_log_sink(config.observability.log_path)
    data_path = Path(data_dir)
    workbook = data_path / "demand-supply.xlsx"
    text_cache_path = config.cache_dir / "profile_text_cache.json"
    text_cache = {} if force else load_text_cache(text_cache_path)
    try:
        roles = ingest_roles(workbook)
        consultants = ingest_consultants_from_workbook(workbook)
        consultants = ingest_consultants(data_path / "profiles", consultants, cache=text_cache)
        consultants = ingest_feedback(data_path / "project_feedback", consultants)
        consultants, reconcile_result = reconcile_external_people(
            consultants,
            data_path / "profiles",
            data_path / "project_feedback",
            config.ocr,
            cache=text_cache,
        )
    except IngestionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    save_text_cache(text_cache, text_cache_path)

    store_path = config.cache_dir / "extracted_consultants.json"
    existing_store = load_store(store_path) if not force else []
    existing_by_email = {c.email.casefold(): c for c in existing_store}

    consultants_to_extract: list[Consultant] = []
    consultants_unchanged: list[Consultant] = []
    for consultant in consultants:
        pdf_path = data_path / "profiles" / f"{consultant.email}.pdf"
        feedback_paths = (
            [
                data_path / "project_feedback" / f
                for f in (data_path / "project_feedback").glob(f"{consultant.email}_*.md")
            ]
            if (data_path / "project_feedback").exists()
            else []
        )
        current_hash = hash_consultant_sources(
            pdf_path if pdf_path.exists() else None,
            feedback_paths,
        )
        existing = existing_by_email.get(consultant.email.casefold())
        if existing is not None and existing.source_hash == current_hash and not force:
            consultants_unchanged.append(
                existing.model_copy(
                    update={
                        "available_from": consultant.available_from,
                        "supply_state": consultant.supply_state,
                        "rolloff_confidence": consultant.rolloff_confidence,
                        "days_on_beach": consultant.days_on_beach,
                    }
                )
            )
        else:
            consultants_to_extract.append(
                consultant.model_copy(update={"source_hash": current_hash})
            )

    ingest_primary_lm = None
    ingest_fallback_lm = None
    if not no_llm and consultants_to_extract:
        configure_dspy_cache(config.cache_dir)
        ingest_primary_lm = configure_lm(config)
        ingest_fallback_lm = make_lm(config.model_fallback, config)
        extracted = asyncio.run(
            extract_signals_async(
                consultants_to_extract,
                config.scoring_config,
                max_workers=config.max_concurrent_extractions,
                primary_lm=ingest_primary_lm,
                fallback_lm=ingest_fallback_lm,
                app_config=config,
            )
        )
    else:
        extracted = consultants_to_extract

    all_consultants = consultants_unchanged + extracted
    save_store(all_consultants, store_path)

    report = build_ingestion_report(
        roles, all_consultants, data_path / "project_feedback", [], reconcile_result
    )
    build_index(
        all_consultants, roles, config.cache_dir / "milvus", model_name=config.embedding_model
    )
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
