# Deployment — Streamlit Community Cloud

Companion to `UI_DEPLOYMENT_PLAN.md`. This is the concrete how-to for Track B once the app is
ready to deploy.

## Repo readiness (done)

- **Entrypoint:** `app.py` at the repo root.
- **Dependency manifest:** `pyproject.toml` + `uv.lock` — Streamlit Community Cloud detects
  `uv`-managed projects natively; no `requirements.txt` or Dockerfile needed.
- **Python version:** pinned via `.python-version` (3.12), already read by Streamlit Cloud.
- **Data for the deployed app:** `deploy_data/` — a committed copy of the synthetic
  `demand-supply.xlsx` / `profiles/*.pdf` / `project_feedback/*.md` fixtures (confirmed
  synthetic, safe to commit). The live `data/` directory stays gitignored for local dev; the
  deployed app is pointed at `deploy_data/` via the `DSM_DATA_DIR` env var below, so nothing
  changed in `.gitignore`.
- **`.cache/`** stays gitignored — the deployed app rebuilds it on cold start (see below).

## Cold-start data strategy (decided)

Commit synthetic `deploy_data/`; the deployed app runs a real ingest on first load rather than
shipping a pre-built `.cache/`. `app.py` wraps this in `_ensure_ingested()` (calls
`matcher.pipeline.orchestrate.run_ingest`, the same function `dsm ingest` uses — extraction,
embedding, and the Milvus index build all run for real) and caches the result for the life of
the process via `st.cache_resource`. First load pays the full ingest cost (LLM calls, docling
parsing, embedding); every rerun after that is fast until the container restarts, at which point
Streamlit Cloud's ephemeral disk wipes `.cache/` and the next visitor pays it again. Acceptable
for a low-traffic trial; revisit if this becomes a live tool.

## Steps to create the app (do this in the Streamlit Cloud dashboard)

1. Push this branch (with `deploy_data/` and `app.py`) to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Connect the GitHub repo, pick the branch, set the main file path to `app.py`.
4. Under **Advanced settings → Secrets**, add:
   ```toml
   DSM_OPENROUTER_API_KEY = "sk-or-..."
   DSM_DATA_DIR = "deploy_data/"
   ```
   Streamlit Cloud exposes each top-level secret both via `st.secrets` and as a regular
   environment variable, which is what `AppConfig` (a `pydantic-settings` `BaseSettings` with
   `env_prefix="DSM_"`) reads automatically — no code changes needed for either variable.
5. Deploy. Watch the build log for the `uv sync` step and the first-load ingest spinner.

## Verifying before sharing the trial link (plan item 8)

Run the same query against the local CLI and the hosted app, and confirm they match:

```bash
DSM_DATA_DIR=deploy_data/ uv run dsm match --free-text "Senior Python engineer, available ASAP"
```

(`dsm match` has no `--data-dir` flag — it reads `AppConfig.data_dir`, which `DSM_DATA_DIR` overrides, the same env var the deployed app's secrets set.)

Then submit the identical text through the hosted chat UI and compare the shortlist, bands, and
gap analysis. Do this once after every redeploy that touches scoring, matching, or ingest logic.

## Restricting access

Streamlit Community Cloud's own **"Who can view this app"** setting (in the app's dashboard
settings, under Sharing) is the trial-appropriate access gate — restrict to specific viewer
emails rather than building a custom password prompt into `app.py`. This is the "shared
password" referred to in the plan's deferred-work list; swapping it for real per-user auth is
explicitly out of scope for the trial.
