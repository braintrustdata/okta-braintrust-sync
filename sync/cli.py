"""Legacy CLI entry point - redirects to new modular CLI."""

# Import the new modular CLI app
from sync.cli.app import app

# The app is now available for use by the CLI entry point
__all__ = ["app"]