from __future__ import annotations

from pathlib import Path

import typer

from matcher.config import AppConfig, load_adjacency
from matcher.pipeline.ingest import ingest_consultants_from_workbook, ingest_roles
from matcher.pipeline.match import match_role
from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email
from matcher.render.text import print_results

app = typer.Typer(name="dsm", help="Demand-Supply Matcher CLI")


@app.command()
def match(
    role_id: str = typer.Argument(..., help="Role ID (e.g. ROLE-01)"),
    top_n: int = typer.Option(5, "--top", "-n", help="Number of candidates to return"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Rank consultants for a given role ID."""
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))

    workbook = config.data_dir / "demand-supply.xlsx"
    roles = ingest_roles(workbook)
    role = next((r for r in roles if r.id == role_id), None)
    if role is None:
        typer.echo(f"Role {role_id!r} not found.", err=True)
        raise typer.Exit(code=1)

    consultants = ingest_consultants_from_workbook(workbook)
    consultants = dedup_by_email(canonicalise_locations(consultants))
    ranked, gaps = match_role(role, consultants, adjacency_map, config.scoring_config, top_n=top_n)
    print_results(ranked, gaps, config.scoring_config)


@app.command()
def ingest(
    data_dir: str = typer.Option("data/", "--data-dir", help="Directory containing source files"),
    force: bool = typer.Option(False, "--force", help="Force re-ingest even if index is current"),
) -> None:
    """Ingest source files and rebuild the vector index."""
    typer.echo(f"Ingesting from {data_dir!r} (force={force})")


if __name__ == "__main__":
    app()
