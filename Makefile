.PHONY: install lint fmt typecheck test test-unit test-int run

install:
	uv sync --extra dev

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/

test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/unit/ -v

test-int:
	uv run pytest tests/integration/ -v

run:
	uv run dsm --help
