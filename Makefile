.PHONY: install lint fmt typecheck test test-unit test-int eval eval-promptfoo bench run

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

eval:
	uv run pytest tests/evals/test_deepeval_golden.py -v

eval-promptfoo:
	promptfoo eval --config tests/evals/promptfoo.yaml

bench:
	uv run pytest tests/integration/test_latency_ac8.py -v

run:
	uv run dsm --help
