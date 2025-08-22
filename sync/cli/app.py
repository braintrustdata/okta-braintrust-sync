"""Main CLI application using modular components."""

import asyncio
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from sync.config.loader import ConfigLoader, find_config_file
from sync.config.models import SyncConfig
from sync.cli.formatters import SyncPlanFormatter, ProgressFormatter, StateFormatter, ConfigFormatter
from sync.cli.factory import ClientFactory, ComponentFactory
from sync.security.validation import (
    sanitize_log_input, validate_file_path, validate_cli_string_input
)

import structlog

# Initialize rich console for output
console = Console()
logger = structlog.get_logger(__name__)

# Create Typer app
app = typer.Typer(
    name="okta-braintrust-sync",
    help="Synchronize users and groups between Okta and Braintrust organizations.",
    rich_markup_mode="rich",
)


def load_configuration(config_file: Optional[Path] = None) -> SyncConfig:
    """Load and validate configuration.
    
    Args:
        config_file: Optional path to config file
        
    Returns:
        Validated configuration
        
    Raises:
        typer.Exit: If configuration loading fails
    """
    try:
        # Find config file if not specified
        if config_file is None:
            config_file = find_config_file()
            if config_file is None:
                console.print("[red]Error: No configuration file found[/red]")
                console.print("Please create a config.yaml file or specify --config")
                raise typer.Exit(1)
        
        # Validate config file path for security
        config_path_str = str(config_file)
        if not validate_file_path(config_path_str):
            console.print(f"[red]Error: Invalid or unsafe configuration file path: {sanitize_log_input(config_path_str)}[/red]")
            raise typer.Exit(1)
        
        # Load configuration
        loader = ConfigLoader()
        config = loader.load_config(config_file)
        
        console.print(f"[green]✓[/green] Loaded configuration from {config_file}")
        return config
        
    except Exception as e:
        console.print(f"[red]Error loading configuration: {sanitize_log_input(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def validate(
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
) -> None:
    """Validate configuration file."""
    console.print("[blue]Validating configuration...[/blue]")
    
    try:
        config = load_configuration(config_file)
        formatter = ConfigFormatter(console)
        formatter.format_config_summary(config)
        console.print("[green]✓ Configuration is valid[/green]")
        
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Validation failed: {sanitize_log_input(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def plan(
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
) -> None:
    """Show what would be synchronized without making changes."""
    
    async def run_plan():
        
        config = load_configuration(config_file)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Create clients
            progress.add_task("Creating API clients...", total=None)
            try:
                okta_client = ClientFactory.create_okta_client(config.okta)
                braintrust_clients = ClientFactory.create_braintrust_clients(config)
            except Exception as e:
                console.print(f"[red]Failed to create clients: {sanitize_log_input(str(e))}[/red]")
                raise typer.Exit(1)
            
            # Validate connectivity
            progress.add_task("Checking API connectivity...", total=None)
            health_results = ClientFactory.validate_clients(okta_client, braintrust_clients)
            unhealthy = [name for name, healthy in health_results.items() if not healthy]
            
            if unhealthy:
                console.print(f"[red]API connectivity issues: {', '.join(unhealthy)}[/red]")
                raise typer.Exit(1)
            
            # Create components
            progress.add_task("Initializing sync components...", total=None)
            state_manager = ComponentFactory.create_state_manager(config)
            planner = ComponentFactory.create_sync_planner(
                okta_client, braintrust_clients, state_manager, config
            )
            
            # Generate plan
            progress.add_task("Generating sync plan...", total=None)
            sync_plan = await planner.generate_sync_plan()
        
        # Display plan in multiple formats for best review experience
        formatter = SyncPlanFormatter(console)
        
        # Show high-level resource summary first
        formatter.format_resource_summary(sync_plan)
        
        # Show operations summary by organization and type
        formatter.format_summary_matrix(sync_plan)
        
        # Show users in table format
        formatter.format_users_table(sync_plan)
        
        # Show groups in table format
        formatter.format_groups_table(sync_plan)
        
        # Show detailed ACL assignments in matrix format
        formatter.format_acl_matrix(sync_plan)
    
    try:
        asyncio.run(run_plan())
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Plan generation failed: {sanitize_log_input(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def apply(
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without making changes"
    ),
    auto_approve: bool = typer.Option(
        False, "--auto-approve", help="Skip interactive approval"
    ),
) -> None:
    """Apply synchronization changes."""
    
    async def run_apply():
        config = load_configuration(config_file)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Create clients and components
            progress.add_task("Setting up sync environment...", total=None)
            try:
                okta_client = ClientFactory.create_okta_client(config.okta)
                braintrust_clients = ClientFactory.create_braintrust_clients(config)
                state_manager = ComponentFactory.create_state_manager(config)
                audit_logger = ComponentFactory.create_audit_logger(config)
                
                planner = ComponentFactory.create_sync_planner(
                    okta_client, braintrust_clients, state_manager, config
                )
                executor = ComponentFactory.create_sync_executor(
                    okta_client, braintrust_clients, state_manager, audit_logger, config
                )
            except Exception as e:
                console.print(f"[red]Setup failed: {sanitize_log_input(str(e))}[/red]")
                raise typer.Exit(1)
            
            # Generate plan
            progress.add_task("Generating sync plan...", total=None)
            sync_plan = await planner.generate_sync_plan()
        
        # Show plan using the same improved format as the plan command
        formatter = SyncPlanFormatter(console)
        
        # Show high-level resource summary first
        formatter.format_resource_summary(sync_plan)
        
        # Show operations summary by organization and type
        formatter.format_summary_matrix(sync_plan)
        
        # Show users in table format
        formatter.format_users_table(sync_plan)
        
        # Show groups in table format
        formatter.format_groups_table(sync_plan)
        
        # Show detailed ACL assignments in matrix format with priority explanation
        console.print()
        console.print("[dim]Note: Priority determines which rule takes precedence (higher = higher priority)[/dim]")
        formatter.format_acl_matrix(sync_plan)
        
        if sync_plan.total_items == 0:
            console.print("[green]No changes needed[/green]")
            return
        
        # Get approval unless auto-approved or dry run
        if not auto_approve and not dry_run:
            if not typer.confirm("Do you want to apply these changes?"):
                console.print("Operation cancelled")
                return
        
        # Execute plan
        console.print("\n[blue]Executing sync plan...[/blue]")
        
        def progress_callback(exec_progress):
            # Update progress display (simplified for now)
            pass
        
        try:
            execution_result = await executor.execute_sync_plan(
                sync_plan,
                dry_run=dry_run,
                continue_on_error=True,
                max_concurrent_operations=5,
            )
            
            # Display results
            progress_formatter = ProgressFormatter(console)
            progress_formatter.format_progress_summary(execution_result)
            progress_formatter.format_org_progress(execution_result)
            progress_formatter.format_errors_and_warnings(execution_result)
            
            if execution_result.failed_items > 0:
                console.print(f"[yellow]Completed with {execution_result.failed_items} failures[/yellow]")
            else:
                console.print("[green]✓ Sync completed successfully[/green]")
                
        except Exception as e:
            console.print(f"[red]Execution failed: {sanitize_log_input(str(e))}[/red]")
            raise typer.Exit(1)
    
    try:
        asyncio.run(run_apply())
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Apply failed: {sanitize_log_input(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
) -> None:
    """Show current sync status and state information."""
    config = load_configuration(config_file)
    
    try:
        state_manager = ComponentFactory.create_state_manager(config)
        current_state = state_manager.get_current_state()
        
        if current_state is None:
            console.print("[yellow]No current sync state found[/yellow]")
            return
        
        # Display state summary
        formatter = StateFormatter(console)
        state_summary = state_manager.get_managed_resource_summary()
        formatter.format_state_summary(state_summary)
        
        # Display drift warnings if any
        if hasattr(current_state, 'drift_warnings') and current_state.drift_warnings:
            warnings_data = [w.model_dump() for w in current_state.drift_warnings]
            formatter.format_drift_warnings(warnings_data)
        
    except Exception as e:
        console.print(f"[red]Failed to get status: {sanitize_log_input(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def drift_detect(
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
) -> None:
    """Detect configuration drift in managed resources."""
    
    async def run_drift_detection():
        config = load_configuration(config_file)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Setup
            progress.add_task("Setting up drift detection...", total=None)
            try:
                braintrust_clients = ClientFactory.create_braintrust_clients(config)
                state_manager = ComponentFactory.create_state_manager(config)
            except Exception as e:
                console.print(f"[red]Setup failed: {sanitize_log_input(str(e))}[/red]")
                raise typer.Exit(1)
            
            # Run drift detection for each org
            all_warnings = []
            for org_name, client in braintrust_clients.items():
                progress.add_task(f"Checking drift for {org_name}...", total=None)
                try:
                    current_roles = await client.list_roles()
                    current_acls = await client.list_org_acls(org_name=org_name, object_type="project")
                    
                    warnings = state_manager.detect_drift(current_roles, current_acls, org_name)
                    all_warnings.extend(warnings)
                    
                except Exception as e:
                    console.print(f"[yellow]Warning: Drift detection failed for {org_name}: {sanitize_log_input(str(e))}[/yellow]")
        
        # Display results
        formatter = StateFormatter(console)
        warnings_data = [w.model_dump() for w in all_warnings]
        formatter.format_drift_warnings(warnings_data)
        
        if all_warnings:
            console.print(f"[yellow]Found {len(all_warnings)} drift warnings[/yellow]")
        else:
            console.print("[green]✓ No drift detected[/green]")
    
    try:
        asyncio.run(run_drift_detection())
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Drift detection failed: {sanitize_log_input(str(e))}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()