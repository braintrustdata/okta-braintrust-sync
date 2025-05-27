#!/bin/bash
# Development setup script for Braintrust Migration Tool

set -e

echo "🚀 Setting up Braintrust Migration Tool development environment..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first:"
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "✅ Found uv"

# Create virtual environment and install dependencies
echo "📦 Installing dependencies with uv..."
uv sync --all-extras

echo "✅ Dependencies installed"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Please create one based on docs/environment-setup.md"
    echo "You can copy the example from docs/environment-setup.md"
else
    echo "✅ Found .env file"
fi

# Run linting
echo "🔍 Running code quality checks..."
uv run ruff check --fix
echo "✅ Linting passed"

# Run type checking
echo "🔍 Running type checks..."
uv run mypy braintrust_migrate/
echo "✅ Type checking passed"

# Run tests
echo "🧪 Running tests..."
uv run pytest tests/ -v
echo "✅ Tests passed"

echo ""
echo "🎉 Development environment is ready!"
echo ""
echo "Next steps:"
echo "1. Create a .env file based on docs/environment-setup.md"
echo "2. Run 'uv run braintrust-migrate --help' to see available commands"
echo "3. Run 'uv run braintrust-migrate validate' to test your API connections"
echo ""
echo "Development commands:"
echo "- 'uv run ruff check --fix' - Run linting"
echo "- 'uv run mypy braintrust_migrate/' - Run type checking" 
echo "- 'uv run pytest' - Run tests"
echo "- 'uv run pytest --cov-report=html' - Run tests with coverage report" 