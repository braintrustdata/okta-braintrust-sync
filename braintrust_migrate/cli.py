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
    # Call the async implementation
    asyncio.run(
        _migrate_main(
            resources, projects, state_dir, log_level, log_format, config_file, dry_run
        )
    )


async def _migrate_main(
    resources: str,
    projects: str | None,
    state_dir: Path | None,
    log_level: str,
    log_format: str,
    config_file: Path | None,
    dry_run: bool,
) -> None:
    """Async implementation of the migrate command."""
    setup_logging(log_level, log_format)
    logger = structlog.get_logger(__name__)

    try:
        # Load configuration
        if config_file and config_file.exists():
            # Load configuration from YAML/JSON file
            logger.info("Loading configuration from file", config_file=str(config_file))
            try:
                config = Config.from_file(config_file)
                logger.info("Successfully loaded configuration from file")
            except Exception as e:
                logger.error(
                    "Failed to load config file, falling back to environment variables",
                    error=str(e),
                )
                config = Config.from_env()
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
            # Perform dry run: validate configuration and test connectivity only
            await _run_dry_run(config)
            return

        # Run migration
        await _run_migration(config)

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
        # Create main migration task with unknown total initially
        migration_task = progress.add_task(
            "Initializing migration...",
            total=None,  # Will update once we know the scope
        )

        try:
            # Import here to avoid circular dependencies
            from braintrust_migrate.client import create_client_pair

            progress.update(
                migration_task,
                description="🔗 Connecting to organizations...",
            )

            async with create_client_pair(
                config.source,
                config.destination,
                config.migration,
            ) as (source_client, dest_client):
                progress.update(
                    migration_task,
                    description="🔍 Discovering projects...",
                )

                # Discover projects first to set up progress tracking
                projects = await orchestrator._discover_projects(
                    source_client, dest_client
                )
                num_projects = len(projects)

                # Set up project-based progress tracking
                # We'll show organization migration as "prep", then project 1/N, 2/N, etc.
                total_projects = max(
                    num_projects, 1
                )  # At least 1 to avoid division by zero

                progress.update(
                    migration_task,
                    total=total_projects,
                    completed=0,
                    description=f"📋 Found {num_projects} projects to migrate",
                )

                # Show project list for user awareness
                if num_projects > 0:
                    project_names = [p["name"] for p in projects[:3]]  # Show first 3
                    if num_projects > 3:
                        project_names.append(f"... and {num_projects - 3} more")
                    console.print(f"[blue]Projects:[/blue] {', '.join(project_names)}")

                progress.update(migration_task, description="🚀 Starting migration...")

                # Run migration with project-based progress tracking
                results = await _run_migration_with_progress(
                    orchestrator, progress, migration_task, num_projects
                )

                # Final update
                progress.update(
                    migration_task,
                    completed=total_projects,
                    description="✅ Migration completed",
                )

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
            progress.update(migration_task, description="❌ Migration failed")
            raise


async def _run_migration_with_progress(
    orchestrator, progress, migration_task, total_projects
):
    """Run migration with detailed progress updates.

    Args:
        orchestrator: MigrationOrchestrator instance
        progress: Rich progress instance
        migration_task: Progress task ID
        total_projects: Total number of projects to migrate

    Returns:
        Migration results
    """
    from datetime import datetime

    import structlog

    from braintrust_migrate.client import create_client_pair

    # Track progress during migration
    start_time = datetime.now()
    logger = structlog.get_logger(__name__)
    projects_completed = 0

    # Create timestamped checkpoint directory
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    checkpoint_dir = orchestrator.config.ensure_checkpoint_dir() / timestamp

    total_results = {
        "start_time": start_time.isoformat(),
        "checkpoint_dir": str(checkpoint_dir),
        "organization_resources": {},
        "projects": {},
        "summary": {
            "total_projects": 0,
            "total_resources": 0,
            "migrated_resources": 0,
            "skipped_resources": 0,
            "failed_resources": 0,
            "errors": [],
        },
    }

    async with create_client_pair(
        orchestrator.config.source,
        orchestrator.config.destination,
        orchestrator.config.migration,
    ) as (source_client, dest_client):
        # Discover projects
        projects = await orchestrator._discover_projects(source_client, dest_client)
        total_results["summary"]["total_projects"] = len(projects)

        # Create global ID mapping registry
        global_id_mappings = {}
        for project in projects:
            global_id_mappings[project["source_id"]] = project["dest_id"]

        # STEP 1: Migrate organization-scoped resources first (doesn't count toward project progress)
        progress.update(
            migration_task,
            description="🏢 Migrating organization resources...",
            completed=projects_completed,
        )

        try:
            org_results = await orchestrator._migrate_organization_resources(
                source_client,
                dest_client,
                checkpoint_dir,
                global_id_mappings,
            )
            total_results["organization_resources"] = org_results

            # Don't increment project counter for org resources, just update description
            progress.update(
                migration_task,
                description="✅ Organization resources migrated",
                completed=projects_completed,
            )

            # Aggregate organization results
            summary = total_results["summary"]
            summary["total_resources"] += org_results.get("total_resources", 0)
            summary["migrated_resources"] += org_results.get("migrated_resources", 0)
            summary["skipped_resources"] += org_results.get("skipped_resources", 0)
            summary["failed_resources"] += org_results.get("failed_resources", 0)
            summary["errors"].extend(org_results.get("errors", []))

        except Exception as e:
            progress.update(
                migration_task,
                description="❌ Organization migration failed",
                completed=projects_completed,
            )
            logger.error("Organization resource migration failed", error=str(e))
            total_results["summary"]["errors"].append(
                {"type": "org_error", "error": str(e)}
            )

        # STEP 2: Migrate project-scoped resources (1 per project)
        for i, project in enumerate(projects):
            project_name = project["name"]

            progress.update(
                migration_task,
                description=f"📁 Migrating project {i + 1} of {total_projects}: {project_name}",
                completed=projects_completed,
            )

            try:
                project_results = await orchestrator._migrate_project(
                    project,
                    source_client,
                    dest_client,
                    checkpoint_dir,
                    global_id_mappings,
                )

                total_results["projects"][project_name] = project_results

                # Aggregate project results
                summary = total_results["summary"]
                summary["total_resources"] += project_results.get("total_resources", 0)
                summary["migrated_resources"] += project_results.get(
                    "migrated_resources", 0
                )
                summary["skipped_resources"] += project_results.get(
                    "skipped_resources", 0
                )
                summary["failed_resources"] += project_results.get(
                    "failed_resources", 0
                )
                summary["errors"].extend(project_results.get("errors", []))

                # Complete this project
                projects_completed += 1

                # Show mini summary for this project
                migrated = project_results.get("migrated_resources", 0)
                total = project_results.get("total_resources", 0)
                skipped = project_results.get("skipped_resources", 0)
                failed = project_results.get("failed_resources", 0)

                if total > 0:
                    console.print(
                        f"[blue]  {project_name}:[/blue] "
                        f"[green]{migrated} migrated[/green], "
                        f"[yellow]{skipped} skipped[/yellow]"
                        + (f", [red]{failed} failed[/red]" if failed > 0 else "")
                    )

                progress.update(
                    migration_task,
                    description=f"✅ Completed project {projects_completed} of {total_projects}: {project_name}",
                    completed=projects_completed,
                )

            except Exception as e:
                # Still increment project counter even on failure
                projects_completed += 1
                logger.error(
                    "Project migration failed", project=project_name, error=str(e)
                )
                total_results["summary"]["errors"].append(
                    {
                        "type": "project_error",
                        "project": project_name,
                        "error": str(e),
                    }
                )
                progress.update(
                    migration_task,
                    description=f"❌ Failed project {projects_completed} of {total_projects}: {project_name}",
                    completed=projects_completed,
                )

    # Finalize results
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    total_results.update(
        {
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "success": total_results["summary"]["failed_resources"] == 0
            and len(total_results["summary"]["errors"]) == 0,
        }
    )

    # Generate detailed migration report
    report_path = orchestrator._generate_migration_report(total_results, checkpoint_dir)
    total_results["report_path"] = str(report_path)

    return total_results


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


@app.command()
def run_dry_run(
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        ),
    ] = "INFO",
) -> None:
    """Run a dry run to validate configuration and test connectivity.

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


async def _run_dry_run(config: Config) -> None:
    """Run a dry run to validate configuration and test connectivity.

    Args:
        config: Migration configuration.
    """
    from braintrust_migrate.orchestration import MigrationOrchestrator

    console.print("\n[cyan]🔍 Performing dry run validation...[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=False,
    ) as progress:
        # Create validation tasks
        validation_task = progress.add_task(
            "Validating configuration and connectivity...",
            total=None,
        )

        try:
            # Test connectivity to both organizations
            await _test_connectivity(config)
            progress.update(validation_task, description="✅ Connectivity validated")

            # Create orchestrator to validate migration setup
            orchestrator = MigrationOrchestrator(config)
            progress.update(
                validation_task, description="✅ Migration orchestrator initialized"
            )

            # Test discovery of resources (read-only operations)
            progress.update(
                validation_task, description="🔍 Discovering source resources..."
            )

            # Import here to avoid circular dependencies
            from braintrust_migrate.client import create_client_pair

            async with create_client_pair(
                config.source,
                config.destination,
                config.migration,
            ) as (source_client, dest_client):
                # Discover projects
                projects = await orchestrator._discover_projects(
                    source_client, dest_client
                )
                progress.update(
                    validation_task,
                    description=f"✅ Discovered {len(projects)} projects",
                )

                # Test resource discovery for each migrator type
                test_results = await _test_resource_discovery(
                    source_client,
                    dest_client,
                    projects[:1] if projects else [],  # Test with first project only
                    config,
                    progress,
                    validation_task,
                )

            progress.update(validation_task, completed=1, total=1)

            # Display dry run results
            _display_dry_run_results(projects, test_results)

            console.print("\n[green]✅ Dry run completed successfully![/green]")
            console.print(
                "[yellow]📝 No changes were made to either organization[/yellow]"
            )

        except Exception as e:
            progress.update(validation_task, description="❌ Dry run failed")
            console.print(f"\n[red]❌ Dry run failed: {e}[/red]")
            raise


async def _test_resource_discovery(
    source_client,
    dest_client,
    projects: list[dict],
    config: Config,
    progress,
    validation_task,
) -> dict[str, dict]:
    """Test resource discovery for validation purposes.

    Args:
        source_client: Source client
        dest_client: Destination client
        projects: List of projects to test with
        config: Migration configuration
        progress: Progress object
        validation_task: Validation task ID

    Returns:
        Dictionary of resource discovery results
    """
    from braintrust_migrate.resources import (
        DatasetMigrator,
        ExperimentMigrator,
        FunctionMigrator,
        PromptMigrator,
    )

    test_results = {}

    # Test with a subset of migrators to avoid overwhelming output
    test_migrators = [
        ("datasets", DatasetMigrator),
        ("prompts", PromptMigrator),
        ("functions", FunctionMigrator),
        ("experiments", ExperimentMigrator),
    ]

    for resource_name, migrator_class in test_migrators:
        if resource_name in config.resources or "all" in config.resources:
            try:
                progress.update(
                    validation_task,
                    description=f"🔍 Testing {resource_name} discovery...",
                )

                # Create temporary migrator for testing
                temp_dir = config.state_dir / "dry_run_temp"
                temp_dir.mkdir(exist_ok=True)

                migrator = migrator_class(source_client, dest_client, temp_dir)

                # Test with first project if available
                project_id = projects[0]["source_id"] if projects else None
                if hasattr(migrator, "set_destination_project_id") and projects:
                    migrator.set_destination_project_id(projects[0]["dest_id"])

                # Test resource discovery (read-only)
                resources = await migrator.list_source_resources(project_id)

                test_results[resource_name] = {
                    "discovered_count": len(resources),
                    "status": "success",
                    "sample_resources": [
                        getattr(r, "name", getattr(r, "id", "unnamed"))
                        for r in resources[:3]  # Show first 3 as examples
                    ],
                }

                # Clean up temp directory
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)

            except Exception as e:
                test_results[resource_name] = {
                    "discovered_count": 0,
                    "status": "error",
                    "error": str(e),
                }

    return test_results


def _display_dry_run_results(
    projects: list[dict], test_results: dict[str, dict]
) -> None:
    """Display dry run results in a formatted table.

    Args:
        projects: List of discovered projects
        test_results: Results from resource discovery tests
    """
    # Projects table
    if projects:
        projects_table = Table(title="📁 Discovered Projects")
        projects_table.add_column("Project Name", style="cyan")
        projects_table.add_column("Source ID", style="blue")
        projects_table.add_column("Dest ID", style="green")

        for project in projects:
            projects_table.add_row(
                project["name"], project["source_id"], project["dest_id"]
            )

        console.print("\n")
        console.print(projects_table)

    # Resource discovery results
    if test_results:
        resources_table = Table(title="🔍 Resource Discovery Test Results")
        resources_table.add_column("Resource Type", style="cyan")
        resources_table.add_column("Status", style="magenta")
        resources_table.add_column("Count", justify="right", style="blue")
        resources_table.add_column("Sample Names", style="yellow")

        for resource_name, results in test_results.items():
            status = (
                "✅ Success"
                if results["status"] == "success"
                else f"❌ {results.get('error', 'Failed')}"
            )
            count = str(results["discovered_count"])
            samples = ", ".join(results.get("sample_resources", []))

            resources_table.add_row(
                resource_name.title(),
                status,
                count,
                samples[:50] + "..." if len(samples) > 50 else samples,
            )

        console.print("\n")
        console.print(resources_table)


if __name__ == "__main__":
    app()
