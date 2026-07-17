from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from matcher.config import AppConfig
from matcher.llm.cache import configure_dspy_cache
from matcher.llm.client import configure_lm, make_lm
from matcher.models.consultant import Consultant
from matcher.models.ingestion_report import IngestionReport
from matcher.models.output import DataQualityReport, RunOutput
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate
from matcher.observability import telemetry as _telemetry
from matcher.observability.run_log import log_data_quality, log_run_start
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
from matcher.pipeline.reconcile import ReconcileResult, reconcile_external_people
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
from matcher.scoring.confidence import attach_confidence_levels
from matcher.scoring.info_flags import attach_info_flags

CONFIG_VERSION = "0.1.0"


class RoleNotFoundError(Exception):
    def __init__(self, role_id: str) -> None:
        super().__init__(f"Role {role_id!r} not found.")
        self.role_id = role_id


@dataclass
class MatchContext:
    config: AppConfig
    adjacency_map: dict[str, list[str]]
    no_llm: bool
    roles: list[Role]
    consultants: list[Consultant]
    reconcile_result: ReconcileResult
    index_client: Any
    embedding_model: Any
    query_lm: Any


def run_ingest(
    config: AppConfig,
    data_dir: Path,
    *,
    force: bool = False,
    no_llm: bool = False,
) -> IngestionReport:
    workbook = data_dir / "demand-supply.xlsx"
    text_cache_path = config.cache_dir / "profile_text_cache.json"
    text_cache = {} if force else load_text_cache(text_cache_path)

    roles = ingest_roles(workbook)
    consultants = ingest_consultants_from_workbook(workbook)
    consultants = ingest_consultants(data_dir / "profiles", consultants, cache=text_cache)
    consultants = ingest_feedback(data_dir / "project_feedback", consultants)
    consultants, reconcile_result = reconcile_external_people(
        consultants,
        data_dir / "profiles",
        data_dir / "project_feedback",
        config.ocr,
        cache=text_cache,
    )
    save_text_cache(text_cache, text_cache_path)

    store_path = config.cache_dir / "extracted_consultants.json"
    existing_store = load_store(store_path) if not force else []
    existing_by_email = {c.email.casefold(): c for c in existing_store}

    consultants_to_extract: list[Consultant] = []
    consultants_unchanged: list[Consultant] = []
    for consultant in consultants:
        pdf_path = data_dir / "profiles" / f"{consultant.email}.pdf"
        feedback_dir = data_dir / "project_feedback"
        feedback_paths = (
            [feedback_dir / f for f in feedback_dir.glob(f"{consultant.email}_*.md")]
            if feedback_dir.exists()
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

    if not no_llm and consultants_to_extract:
        configure_dspy_cache(config.cache_dir)
        primary_lm = configure_lm(config)
        fallback_lm = make_lm(config.model_fallback, config)
        extracted = asyncio.run(
            extract_signals_async(
                consultants_to_extract,
                config.scoring_config,
                max_workers=config.max_concurrent_extractions,
                primary_lm=primary_lm,
                fallback_lm=fallback_lm,
                app_config=config,
            )
        )
    else:
        extracted = consultants_to_extract

    all_consultants = consultants_unchanged + extracted
    save_store(all_consultants, store_path)

    report = build_ingestion_report(
        roles, all_consultants, data_dir / "project_feedback", [], reconcile_result
    )
    build_index(
        all_consultants, roles, config.cache_dir / "milvus", model_name=config.embedding_model
    )
    return report


def build_context(
    config: AppConfig, adjacency_map: dict[str, list[str]], no_llm: bool
) -> MatchContext:
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

    roles = ingest_roles(workbook)
    consultants = ingest_consultants_from_workbook(workbook)
    consultants = ingest_consultants(
        config.data_dir / "profiles", consultants, ocr_config=config.ocr, cache=text_cache
    )
    consultants = ingest_feedback(config.data_dir / "project_feedback", consultants)
    consultants, reconcile_result = reconcile_external_people(
        consultants,
        config.data_dir / "profiles",
        config.data_dir / "project_feedback",
        config.ocr,
        cache=text_cache,
    )
    save_text_cache(text_cache, text_cache_path)

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

    return MatchContext(
        config=config,
        adjacency_map=adjacency_map,
        no_llm=no_llm,
        roles=roles,
        consultants=consultants,
        reconcile_result=reconcile_result,
        index_client=index_client,
        embedding_model=embedding_model,
        query_lm=query_lm,
    )


def describe_parsed_role(role: Role) -> str:
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


def resolve_role(
    ctx: MatchContext,
    role_id: str | None,
    free_text: str | None,
    today: date | None = None,
) -> tuple[Role, str, list[str], RelevanceVerdict | None]:
    if free_text is not None:
        today = today or date.today()
        known_locations = {loc for r in ctx.roles for loc in r.locations}
        known_skills = {s.name for r in ctx.roles for s in r.required_skills}
        role, ambiguities = parse_free_text_role(
            free_text, known_locations, known_skills, lm=ctx.query_lm, today=today
        )
        plausibility = check_domain_plausibility(free_text, role, lm=ctx.query_lm)
        if plausibility is not None and not plausibility.in_domain:
            return role, "FREE-TEXT", ambiguities, plausibility
        return role, "FREE-TEXT", ambiguities, None

    found = next((r for r in ctx.roles if r.id == role_id), None)
    if found is None:
        raise RoleNotFoundError(role_id or "")
    return found, role_id or "", [], None


def _compute_snapshot_id(
    workbook: Path,
    profiles_dir: Path,
    feedback_dir: Path,
    embedding_model: str = "",
) -> str:
    h = hashlib.sha256()

    for path in sorted(
        [workbook, Path("config/default.yaml"), Path("config/skill_adjacency.yaml")]
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


def run_match(
    ctx: MatchContext,
    role: Role,
    resolved_role_id: str,
    *,
    top_n: int = 5,
    no_explanations: bool = False,
    free_text_query: str | None = None,
    disable_availability_filter: bool = False,
    disable_location_filter: bool = False,
    persist_snapshot: bool = True,
) -> tuple[RunOutput, list[ScoredCandidate]] | RelevanceVerdict:
    config = ctx.config
    _telemetry.reset()
    run_id = uuid.uuid4().hex[:16]
    log_run_start(run_id, CONFIG_VERSION)

    if free_text_query is not None:
        verdict = check_skill_evidence(
            role,
            ctx.consultants,
            ctx.roles,
            ctx.adjacency_map,
            config.scoring_config,
            index_client=ctx.index_client,
            embedding_model=ctx.embedding_model,
            lm=ctx.query_lm,
            query_text=free_text_query,
        )
        if verdict is not None and not verdict.in_domain:
            return verdict

    stale_warnings = stale_date.check(role, date.today())
    ingestion_rep = build_ingestion_report(
        ctx.roles,
        ctx.consultants,
        config.data_dir / "project_feedback",
        stale_warnings,
        ctx.reconcile_result,
    )

    with stage_timer("match", _telemetry.current_telemetry):
        ranked, gaps = match_role(
            role,
            ctx.consultants,
            ctx.adjacency_map,
            config.weights,
            config.scoring_config,
            top_n=top_n,
            disable_availability_filter=disable_availability_filter,
            disable_location_filter=disable_location_filter,
            index_client=ctx.index_client,
            embedding_model=ctx.embedding_model,
        )

    with stage_timer("confidence_and_flags", _telemetry.current_telemetry):
        ranked = attach_confidence_levels(ranked, ctx.consultants, config.scoring_config)
        ranked = attach_info_flags(ranked, ctx.consultants, role, config.scoring_config)

    with stage_timer("gap", _telemetry.current_telemetry):
        gap_report = build_gap_report(
            role,
            ctx.consultants,
            ranked,
            gaps,
            ctx.adjacency_map,
            config.weights,
            config.scoring_config,
            config,
        )

    if not ctx.no_llm and not no_explanations:
        with stage_timer("explain", _telemetry.current_telemetry):
            ranked = generate_explanations(ranked, role, ctx.consultants, config)

    run_tel = _telemetry.snapshot()
    output = RunOutput(
        snapshot_id=_compute_snapshot_id(
            config.data_dir / "demand-supply.xlsx",
            config.data_dir / "profiles",
            config.data_dir / "project_feedback",
            embedding_model=config.embedding_model,
        ),
        run_id=run_id,
        role_id=resolved_role_id,
        candidates=ranked,
        gap_report=gap_report,
        role_snapshot=role,
        data_quality=DataQualityReport(total_consultants_ingested=len(ctx.consultants)),
        ingestion_report=ingestion_rep,
        run_telemetry=run_tel,
        config_version=CONFIG_VERSION,
    )

    if persist_snapshot:
        try:
            save_snapshot(output, config.observability.snapshot_dir)
            prune_snapshots(
                config.observability.snapshot_dir, config.observability.snapshot_retention
            )
        except OSError:
            pass

    log_data_quality(ingestion_rep.feedback_unmatched, ingestion_rep.profiles_low_confidence)
    return output, gaps
