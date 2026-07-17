from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import logging
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import streamlit as st

from matcher.config import AppConfig, ScoringConfig, load_adjacency
from matcher.models.errors import IngestionError
from matcher.models.output import RunOutput
from matcher.models.score import ScoredCandidate
from matcher.observability.run_log import configure_log_sink
from matcher.pipeline.orchestrate import (
    MatchContext,
    RoleNotFoundError,
    build_context,
    describe_parsed_role,
    resolve_role,
    run_ingest,
    run_match,
)
from matcher.pipeline.relevance import RelevanceVerdict
from matcher.scoring.ranker import band

# --- TEMPORARY DIAGNOSTIC: trace whatever is invoking `uv` as a subprocess ---
# Remove once the caller is identified. Patches subprocess.Popen (the primitive
# subprocess.run/call/check_output/os.popen all build on) and os.system, and
# prints a full stack trace to stderr the moment a command containing "uv" runs.
_orig_popen_init = subprocess.Popen.__init__


def _traced_popen_init(self, args, *a, **kw):  # type: ignore[no-untyped-def]
    try:
        cmd_str = args if isinstance(args, str) else " ".join(str(x) for x in args)
    except Exception:
        cmd_str = repr(args)
    if "uv" in cmd_str.lower():
        print(f"\n[SUBPROCESS TRACE] Popen: {cmd_str}", file=sys.stderr)
        traceback.print_stack(file=sys.stderr)
    return _orig_popen_init(self, args, *a, **kw)


subprocess.Popen.__init__ = _traced_popen_init  # type: ignore[method-assign]

_orig_system = os.system


def _traced_system(command: str) -> int:
    if "uv" in command.lower():
        print(f"\n[SUBPROCESS TRACE] os.system: {command}", file=sys.stderr)
        traceback.print_stack(file=sys.stderr)
    return _orig_system(command)


os.system = _traced_system  # type: ignore[assignment]
# --- END TEMPORARY DIAGNOSTIC ---

# Streamlit Community Cloud's dashboard secrets populate st.secrets only — they are
# never synced into os.environ. AppConfig (pydantic-settings) reads DSM_* purely from
# the environment/.env, so mirror any secrets across before the first AppConfig build.
_secrets_error: str | None = None
_synced_keys: list[str] = []
try:
    for _key, _value in st.secrets.items():
        if isinstance(_value, str | int | float | bool):
            os.environ.setdefault(_key, str(_value))
            _synced_keys.append(_key)
except Exception as _exc:
    _secrets_error = repr(_exc)

logging.getLogger("matcher.pipeline.ingest").setLevel(logging.ERROR)

st.set_page_config(page_title="Demand-Supply Matcher", page_icon="🧭", layout="wide")

with st.sidebar.expander("🔧 Debug: secrets/env (remove once resolved)"):
    st.write("secrets sync error:", _secrets_error or "none")
    st.write("keys synced from st.secrets:", _synced_keys or "none")
    try:
        st.write("st.secrets top-level keys:", list(st.secrets.keys()))
    except Exception as _exc:
        st.write("st.secrets access error:", repr(_exc))
    st.write("DSM_OPENROUTER_API_KEY in os.environ:", "DSM_OPENROUTER_API_KEY" in os.environ)
    st.write("DSM_DATA_DIR:", os.environ.get("DSM_DATA_DIR", "<not set>"))


@st.cache_resource(show_spinner=False)
def _load_config() -> tuple[AppConfig, dict[str, list[str]]]:
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))
    configure_log_sink(config.observability.log_path)
    return config, adjacency_map


@st.cache_resource(show_spinner="Running ingest — first load can take a while...")
def _ensure_ingested(no_llm: bool) -> None:
    config, _ = _load_config()
    run_ingest(config, config.data_dir, no_llm=no_llm)


@st.cache_resource(show_spinner="Loading consultant & role data...")
def _load_context(no_llm: bool) -> MatchContext:
    _ensure_ingested(no_llm)
    config, adjacency_map = _load_config()
    return build_context(config, adjacency_map, no_llm)


def _render_match(
    output: RunOutput,
    filtered_out: list[ScoredCandidate],
    scoring_config: ScoringConfig,
) -> None:
    if output.candidates:
        st.markdown("**Ranked shortlist**")
    for c in output.candidates:
        bands = [band(d.raw_score, scoring_config) for d in c.dimensions]
        strong = bands.count("Strong")
        gap_dims = [d.name for d, b in zip(c.dimensions, bands) if b == "Gap"]
        header = f"#{c.rank} — {c.consultant_name} ({strong}/{len(c.dimensions)} strong)"
        with st.expander(header):
            flags = ", ".join(c.info_flags) if c.info_flags else "none"
            st.caption(f"confidence: {c.confidence_level} · flags: {flags}")
            if gap_dims:
                st.caption(f"gaps: {', '.join(gap_dims)}")
            if c.explanation:
                st.write(c.explanation)
            if c.why_not_higher:
                st.caption(f"why not higher: {c.why_not_higher}")
            st.table(
                [
                    {"dimension": d.name, "band": b, "weight": d.weight}
                    for d, b in zip(c.dimensions, bands)
                ]
            )

    if filtered_out:
        with st.expander(f"Filtered out — hard filters ({len(filtered_out)})"):
            for c in filtered_out:
                flags = "; ".join(c.supply_gap_flags) if c.supply_gap_flags else "hard filter"
                st.write(f"- {c.consultant_name} ({flags})")

    gr = output.gap_report
    has_gap_content = gr.all_filtered or gr.no_required_skills or gr.partial_matches
    if has_gap_content:
        with st.expander("Gap analysis", expanded=gr.all_filtered):
            if gr.all_filtered:
                st.warning("All candidates were filtered out.")
                st.write(f"reasons: {', '.join(gr.filter_reasons)}")
                if gr.relaxed_candidates:
                    st.write(f"relaxed candidates: {', '.join(gr.relaxed_candidates)}")
            if gr.no_required_skills and gr.inferred_skills:
                st.write(f"inferred skills: {', '.join(gr.inferred_skills)}")
            if gr.partial_matches:
                st.write(f"partial matches: {', '.join(gr.partial_matches)}")

    if output.run_telemetry is not None:
        t = output.run_telemetry
        total_s = sum(t.stage_timings_ms.values()) / 1000.0
        st.caption(
            f"{total_s:.1f}s total · {t.llm_calls} LLM calls · "
            f"${t.total_cost_usd:.4f} · cache {int(t.cache_hit_rate * 100)}%"
        )


def _render_rejection(verdict: RelevanceVerdict) -> None:
    st.warning("No match run — this doesn't look like a staffing request.")
    st.caption(f"reason: {verdict.reason}")
    st.caption('try rephrasing with a real skill or role, e.g. "Python engineer, available ASAP"')


def _render_assistant_content(turn: dict[str, Any]) -> None:
    kind = turn["kind"]
    if kind == "error":
        st.error(turn["text"])
    elif kind == "rejected":
        _render_rejection(turn["verdict"])
    elif kind == "match":
        if turn.get("interpreted"):
            st.caption(f"interpreted as: {turn['interpreted']}")
        for amb in turn.get("ambiguities", []):
            st.caption(f"warning: {amb}")
        _render_match(turn["output"], turn["filtered_out"], turn["scoring_config"])


def _render_turn(turn: dict[str, Any]) -> None:
    with st.chat_message(turn["role"]):
        if turn["role"] == "user":
            st.markdown(turn["text"])
        else:
            _render_assistant_content(turn)


def _compute_turn(
    ctx: MatchContext, *, role_id: str | None, free_text: str | None, **run_kwargs: Any
) -> dict[str, Any]:
    try:
        role, resolved_role_id, ambiguities, verdict = resolve_role(ctx, role_id, free_text)
    except RoleNotFoundError as exc:
        return {"role": "assistant", "kind": "error", "text": str(exc)}

    if verdict is not None:
        return {"role": "assistant", "kind": "rejected", "verdict": verdict}

    try:
        result = run_match(ctx, role, resolved_role_id, free_text_query=free_text, **run_kwargs)
    except RuntimeError as exc:
        return {"role": "assistant", "kind": "error", "text": str(exc)}

    if isinstance(result, RelevanceVerdict):
        return {"role": "assistant", "kind": "rejected", "verdict": result}

    output, filtered_out = result
    return {
        "role": "assistant",
        "kind": "match",
        "output": output,
        "filtered_out": filtered_out,
        "ambiguities": ambiguities,
        "interpreted": describe_parsed_role(role) if free_text is not None else None,
        "scoring_config": ctx.config.scoring_config,
    }


def _submit_query(
    ctx: MatchContext, *, role_id: str | None, free_text: str | None, **run_kwargs: Any
) -> None:
    label = free_text if free_text is not None else f"Role: {role_id}"
    st.session_state.history.append({"role": "user", "text": label})
    _render_turn(st.session_state.history[-1])

    with st.chat_message("assistant"):
        with st.spinner("Matching consultants..."):
            turn = _compute_turn(ctx, role_id=role_id, free_text=free_text, **run_kwargs)
        st.session_state.history.append(turn)
        _render_assistant_content(turn)


st.title("Demand-Supply Matcher")
st.caption("Chat-based staffing shortlist assistant")

with st.sidebar:
    st.header("Filters")
    no_llm = st.toggle(
        "--no-llm",
        value=False,
        help="Skip LLM extraction/explanation; free-text parsing falls back to a "
        "deterministic regex parser with no negation support.",
    )
    top_n = st.slider("Top N", min_value=1, max_value=20, value=5)
    disable_availability = st.checkbox("Ignore availability filter", value=False)
    disable_location = st.checkbox("Ignore location filter", value=False)
    st.divider()

try:
    ctx = _load_context(no_llm)
except IngestionError as exc:
    st.error(f"Ingestion failed: {exc}")
    st.stop()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.subheader("Pick a role")
    placeholder = "— select —"
    role_labels = [placeholder] + [f"{r.id}: {r.title}" for r in ctx.roles]
    selected = st.selectbox("Role", role_labels, label_visibility="collapsed")
    run_role_clicked = st.button("Run for selected role", disabled=selected == placeholder)

if "history" not in st.session_state:
    st.session_state.history = []

for turn in st.session_state.history:
    _render_turn(turn)

run_kwargs = dict(
    top_n=top_n,
    disable_availability_filter=disable_availability,
    disable_location_filter=disable_location,
)

if run_role_clicked:
    role_id = selected.split(":", 1)[0]
    _submit_query(ctx, role_id=role_id, free_text=None, **run_kwargs)

query = st.chat_input("Describe the role you need staffed, e.g. 'Senior Python engineer, ASAP'")
if query:
    _submit_query(ctx, role_id=None, free_text=query, **run_kwargs)
