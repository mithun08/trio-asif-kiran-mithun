#!/bin/bash
set -e

echo "🚀 Running local CI checks..."
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

# Function to run a check and track failures
run_check() {
    local name=$1
    local command=$2

    echo -e "${YELLOW}▶ $name${NC}"
    if eval "$command"; then
        echo -e "${GREEN}✓ $name passed${NC}"
    else
        echo -e "${RED}✗ $name failed${NC}"
        FAILED=$((FAILED + 1))
    fi
    echo ""
}

# Install dependencies
echo -e "${YELLOW}▶ Installing dependencies${NC}"
uv sync --extra dev
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Linting
run_check "Ruff lint" "uv run ruff check src/ tests/"
run_check "Ruff format check" "uv run ruff format --check src/ tests/"

# Type checking
run_check "MyPy typecheck" "uv run mypy src/"

# Unit tests with coverage
run_check "Unit tests with coverage" "uv run pytest tests/unit/ -v --cov=matcher --cov-report=xml"

# Summary
echo ""
echo "════════════════════════════════"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ $FAILED check(s) failed${NC}"
    exit 1
fi
