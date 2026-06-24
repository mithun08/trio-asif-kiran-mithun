# Local CI Scripts

## `ci.sh` - Run all CI checks locally

Runs the full CI pipeline as defined in `.github/workflows/ci.yml`:
- Dependency installation (`uv sync --extra dev`)
- Ruff linting (`ruff check`)
- Ruff format check (`ruff format --check`)
- Type checking (`mypy`)
- Unit tests with coverage report

**Usage:**
```bash
./scripts/ci.sh
```

This is what you should run before pushing to ensure your code passes CI.

## `fix.sh` - Auto-fix code style issues

Automatically formats code using ruff. Useful before running the full CI.

**Usage:**
```bash
./scripts/fix.sh
```

Then commit the formatted changes.

## Quick Reference

| Script | Purpose |
|--------|---------|
| `./scripts/ci.sh` | Run full CI suite (like GitHub Actions) |
| `./scripts/fix.sh` | Auto-fix formatting issues |
| `make lint` | Run ruff linting only |
| `make fmt` | Auto-format code |
| `make typecheck` | Run mypy typecheck only |
| `make test-unit` | Run unit tests only |
| `make test` | Run all tests (unit + integration) |