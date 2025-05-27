"""Command-line interface for Braintrust migration tool."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import structlog
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from braintrust_migrate.config import Config
from braintrust_migrate.orchestration import MigrationOrchestrator

# Constants
MAX_ERRORS_TO_DISPLAY = 10

# Create Typer app
app = typer.Typer(
    name="braintrust-migrate",
    help="Migrate Braintrust organizations with maximum fidelity",
    add_completion=False,
)

console = Console()


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Setup structured logging.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: Log format (json or text).
    """
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format.lower() == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


@app.command()
def migrate(
    resources: Annotated[
        str,
        typer.Option(
            "--resources",
            "-r",
            help="Comma-separated list of resources to migrate (all,datasets,prompts,tools,agents,experiments,logs,views)",
        ),
    ] = "all",
    projects: Annotated[
        str | None,
        typer.Option(
            "--projects",
            "-p",
            help="Comma-separated list of project names to migrate (if not specified, all projects will be migrated)",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            "-s",
            help="Directory for storing migration state and checkpoints",
        ),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        ),
    ] = "INFO",
    log_format: Annotated[
        str,
        typer.Option(
            "--log-format",
            "-f",
            help="Log format (json or text)",
        ),
    ] = "json",
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to configuration file (optional, uses environment variables by default)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Perform a dry run without making changes",
        ),
    ] = False,
) -> None:
    """Migrate resources from source to destination Braintrust organization.

    This command will migrate all specified resources from the source organization
    to the destination organization, maintaining dependencies and creating checkpoints
    for resumption.

    Examples:
        braintrust-migrate migrate --resources datasets,prompts
        braintrust-migrate migrate --projects "Project A,Project B" --resources datasets
        braintrust-migrate migrate --state-dir ./my-migration --log-level DEBUG
        braintrust-migrate migrate --dry-run
    """
    setup_logging(log_level, log_format)
    logger = structlog.get_logger(__name__)

    try:
        # Load configuration
        if config_file and config_file.exists():
            # TODO: Implement config file loading
            logger.info("Loading configuration from file", config_file=str(config_file))
            config = Config.from_env()  # For now, still use env vars
        else:
            config = Config.from_env()

        # Override config with CLI arguments
        if state_dir:
            config.state_dir = state_dir

        if resources != "all":
            config.resources = [r.strip() for r in resources.split(",")]

        # Parse and set project filter if provided
        if projects:
            config.project_names = [p.strip() for p in projects.split(",")]

        # Override logging config
        config.logging.level = log_level
        config.logging.format = log_format

        logger.info(
            "Starting migration",
            source_url=str(config.source.url),
            dest_url=str(config.destination.url),
            resources=config.resources,
            projects=getattr(config, "project_names", None),
            state_dir=str(config.state_dir),
            dry_run=dry_run,
        )

        if dry_run:
            console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
            logger.warning("Dry run mode enabled - no changes will be made")
            # TODO: Implement dry run logic
            return

        # Run migration
        asyncio.run(_run_migration(config))

    except KeyboardInterrupt:
        console.print("\n[red]Migration interrupted by user[/red]")
        logger.info("Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        logger.error("Migration failed", error=str(e), exc_info=True)
        sys.exit(1)


async def _run_migration(config: Config) -> None:
    """Run the migration process with progress reporting.

    Args:
        config: Migration configuration.
    """
    # Create orchestrator
    orchestrator = MigrationOrchestrator(config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        # Create main migration task
        migration_task = progress.add_task(
            "Migrating Braintrust organization...",
            total=None,
        )

        try:
            # Run migration
            results = await orchestrator.migrate_all()

            # Update progress to complete
            progress.update(migration_task, completed=1, total=1)

            # Display results
            _display_results(results)

            # Save results to file
            results_file = config.state_dir / "migration_results.json"
            config.ensure_checkpoint_dir()
            with open(results_file, "w") as f:
                json.dump(results, f, indent=2)

            # Check if migration was actually successful
            if results.get("success", False):
                console.print("\n[green]Migration completed successfully![/green]")
            else:
                console.print("\n[red]Migration failed![/red]")

            console.print(f"Results saved to: {results_file}")

            if results["summary"]["failed_resources"] > 0:
                console.print(
                    f"[yellow]Warning: {results['summary']['failed_resources']} resources failed to migrate[/yellow]"
                )

            if len(results["summary"]["errors"]) > 0:
                console.print(
                    f"[red]Errors encountered: {len(results['summary']['errors'])} error(s)[/red]"
                )

        except Exception:
            progress.update(migration_task, description="Migration failed")
            raise


def _display_results(results: dict) -> None:
    """Display migration results in a formatted table.

    Args:
        results: Migration results dictionary.
    """
    summary = results["summary"]

    # Summary table
    summary_table = Table(title="Migration Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Count", style="magenta", justify="right")

    summary_table.add_row("Total Projects", str(summary["total_projects"]))
    summary_table.add_row("Total Resources", str(summary["total_resources"]))
    summary_table.add_row("Migrated", str(summary["migrated_resources"]))
    summary_table.add_row("Skipped", str(summary["skipped_resources"]))
    summary_table.add_row("Failed", str(summary["failed_resources"]))

    console.print("\n")
    console.print(summary_table)

    # Project details table
    if results["projects"]:
        projects_table = Table(title="Project Details")
        projects_table.add_column("Project", style="cyan")
        projects_table.add_column("Total", justify="right")
        projects_table.add_column("Migrated", justify="right", style="green")
        projects_table.add_column("Skipped", justify="right", style="yellow")
        projects_table.add_column("Failed", justify="right", style="red")

        for project_name, project_data in results["projects"].items():
            projects_table.add_row(
                project_name,
                str(project_data["total_resources"]),
                str(project_data["migrated_resources"]),
                str(project_data["skipped_resources"]),
                str(project_data["failed_resources"]),
            )

        console.print("\n")
        console.print(projects_table)

    # Show errors if any
    if summary["errors"]:
        console.print("\n[red]Errors encountered:[/red]")
        for i, error in enumerate(
            summary["errors"][:MAX_ERRORS_TO_DISPLAY], 1
        ):  # Show first 10 errors
            console.print(f"  {i}. {error}")

        if len(summary["errors"]) > MAX_ERRORS_TO_DISPLAY:
            console.print(
                f"  ... and {len(summary['errors']) - MAX_ERRORS_TO_DISPLAY} more errors"
            )


@app.command()
def validate(
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        ),
    ] = "INFO",
) -> None:
    """Validate configuration and test connectivity to both organizations.

    This command will validate your configuration and test connectivity to both
    the source and destination Braintrust organizations without performing any
    migrations.
    """
    setup_logging(log_level, "text")  # Use text format for validation
    logger = structlog.get_logger(__name__)

    try:
        console.print("[blue]Validating configuration...[/blue]")

        # Load and validate configuration
        config = Config.from_env()
        console.print("[green]✓[/green] Configuration loaded successfully")

        # Test connectivity
        console.print("[blue]Testing connectivity...[/blue]")
        asyncio.run(_test_connectivity(config))

        console.print("[green]✓[/green] All validation checks passed!")

    except Exception as e:
        console.print(f"[red]✗ Validation failed: {e}[/red]")
        logger.error("Validation failed", error=str(e))
        sys.exit(1)


async def _test_connectivity(config: Config) -> None:
    """Test connectivity to both source and destination organizations.

    Args:
        config: Migration configuration.
    """
    from braintrust_migrate.client import create_client_pair

    async with create_client_pair(
        config.source,
        config.destination,
        config.migration,
    ) as (source_client, dest_client):
        # Test source connectivity
        source_health = await source_client.health_check()
        console.print(f"[green]✓[/green] Source organization: {source_health['url']}")

        # Test destination connectivity
        dest_health = await dest_client.health_check()
        console.print(
            f"[green]✓[/green] Destination organization: {dest_health['url']}"
        )

        # Check Brainstore status if needed
        source_brainstore = await source_client.check_brainstore_enabled()
        dest_brainstore = await dest_client.check_brainstore_enabled()

        if source_brainstore and dest_brainstore:
            console.print("[green]✓[/green] Brainstore enabled on both organizations")
        elif not source_brainstore and not dest_brainstore:
            console.print(
                "[yellow]![/yellow] Brainstore disabled on both organizations"
            )
        else:
            console.print(
                "[yellow]![/yellow] Brainstore status differs between organizations"
            )


@app.command()
def version() -> None:
    """Show version information."""
    from braintrust_migrate import __version__

    console.print(f"braintrust-migrate version {__version__}")


if __name__ == "__main__":
    app()
