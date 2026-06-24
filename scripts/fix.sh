#!/bin/bash
set -e

echo "🔧 Fixing code style issues..."
echo ""

uv run ruff format src/ tests/
echo "✓ Formatted code with ruff"