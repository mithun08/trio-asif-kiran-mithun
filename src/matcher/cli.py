from __future__ import annotations

import typer

app = typer.Typer(name="dsm", help="Demand-Supply Matcher CLI")


@app.command()
def match(
    role: str = typer.Argument(..., help="Role ID or free-text description"),
    top_n: int = typer.Option(5, "--top", "-n", help="Number of candidates to return"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Rank and explain consultants for a given role."""
    typer.echo(f"Matching candidates for role: {role!r} (top {top_n})")


@app.command()
def ingest(
    data_dir: str = typer.Option("data/", "--data-dir", help="Directory containing source files"),
    force: bool = typer.Option(False, "--force", help="Force re-ingest even if index is current"),
) -> None:
    """Ingest source files and rebuild the vector index."""
    typer.echo(f"Ingesting from {data_dir!r} (force={force})")


if __name__ == "__main__":
    app()
