# UI + Deployment Plan

| Field | Value |
|---|---|
| Status | Learning activity / trial — no active development pressure |
| Companion | `PLAN.md` |

## Decisions made

- **UI:** Streamlit. Chat-based (like NotebookLM) via `st.chat_message`/`st.chat_input`, with a sidebar for filters (role, location, availability, top-N, `--no-llm` toggle). Chosen over Gradio (too demo/single-IO oriented for this layout) and Chainlit (more chat-native polish, but a second framework — unnecessary complexity for a trial).
- **UI architecture:** thin layer directly on `src/matcher` — the Streamlit app calls pipeline functions in-process, no separate HTTP/API layer.
- **Deployment:** Streamlit Community Cloud (share.streamlit.io). Free, connects directly to GitHub, auto-redeploys on push to the target branch, has built-in secrets management for `DSM_OPENROUTER_API_KEY`. Chosen over Hugging Face Spaces (equally viable, no reason to prefer it here) and a containerized cloud deploy (Cloud Run/Fargate/Container Apps — overkill until this moves past trial).
- **CI relationship:** Streamlit Cloud does not go through `.github/workflows/ci.yml` — it watches the repo independently via its own GitHub integration. The two run alongside each other, not coupled. No changes needed to the existing CI workflow.
- **Scope:** trial only for now. Production-grade concerns (persistent storage instead of Streamlit Cloud's ephemeral disk, real per-user auth instead of a shared password, cost alerting, standalone Milvus instead of Milvus Lite, secrets manager) are deferred — noted below for later, not being built now.

## Two independent tracks

Either can be picked up first; the only real dependency is that deployment needs *some* working app to point at.

### Track A — UI

1. Scaffold a Streamlit app wired directly to `src/matcher` (no HTTP layer).
2. Chat interface: free-text role queries routed through `pipeline/free_text_role.py`'s `parse()` and the existing `match` path (same as CLI's `--free-text`).
3. Sidebar filters: role dropdown (from ingested roles) as an alternative to free text, location/availability toggles, top-N slider, `--no-llm` switch for the deterministic fallback.
4. Results rendering: ranked shortlist as bands + signals (never a %), expandable per-candidate explanation, gap-analysis view for unfillable roles — reuse `render/text.py` / `render/json.py` formatting rather than re-deriving it.

### Track B — Deployment

5. Prep repo for Streamlit Community Cloud: confirm entrypoint path and dependency manifest are readable from the `uv`-managed project (no Dockerfile needed); decide where `app.py` lives; keep `data/` and `.cache/` out of the deployed surface.
6. Create the Streamlit Cloud app: connect GitHub repo, point at branch/entrypoint, set `DSM_OPENROUTER_API_KEY` (and any other env vars) in its secrets dashboard — never committed to the repo.
7. Decide cold-start data strategy: Streamlit Cloud storage is ephemeral, so `.cache/milvus/`, `.cache/dspy/`, and the profile-text cache won't persist across restarts. Either bake a pre-built cache into the repo, or accept re-running ingest on startup for the trial dataset (acceptable given low deploy frequency).
8. Verify the deployed app end-to-end: run a real role query through the hosted chat UI and confirm it matches local CLI output for the same query before sharing the trial link.

## Deferred to a future "production" pass (not now)

- Swap Milvus Lite (embedded, single-process, doesn't survive restarts) for a standalone Milvus instance.
- Move `.cache/` to a persistent volume or object storage.
- Real per-user auth / SSO instead of a shared password gate.
- Secrets manager instead of platform-native secrets.
- Cost alerting wired to the existing structlog token/cost telemetry (NFR-09), not just logged.
- Confirm provider zero-retention config (TDD §5.2) is actually enforced, not just configured.
- A real re-ingest schedule/trigger instead of a frozen trial snapshot.
