"""Command-line interface for okta-braintrust-sync."""

import asyncio
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text
from pydantic import SecretStr

from sync.audit.logger import AuditLogger
from sync.config.loader import ConfigLoader, find_config_file
from sync.config.models import SyncConfig
from sync.clients.okta import OktaClient
from sync.clients.braintrust import BraintrustClient
from sync.core.enhanced_state import StateManager
from sync.core.planner import SyncPlanner
from sync.core.executor import SyncExecutor, ExecutionProgress
from sync.version import __version__

# Create the main Typer app
app = typer.Typer(
    name="okta-braintrust-sync",
    help="Hybrid SCIM-like identity synchronization between Okta and Braintrust organizations",
    add_completion=False,
)

# Create console for rich output
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"okta-braintrust-sync {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Okta-Braintrust Sync - Hybrid identity synchronization tool."""
    pass


@app.command()
def validate(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    okta_only: bool = typer.Option(
        False,
        "--okta-only",
        help="Only validate Okta connectivity",
    ),
    braintrust_only: bool = typer.Option(
        False,
        "--braintrust-only", 
        help="Only validate Braintrust connectivity",
    ),
) -> None:
    """Validate configuration and connectivity to APIs."""
    # Find config file if not provided
    if config is None:
        config = find_config_file()
        if config is None:
            console.print("[red]Error: No configuration file found[/red]")
            console.print("Please create a configuration file or specify one with --config")
            raise typer.Exit(1)
    
    console.print(f"Validating configuration: {config}")
    
    # Load and validate configuration
    loader = ConfigLoader()
    try:
        sync_config = loader.load_config(config)
        console.print("[green]✓[/green] Configuration is valid")
    except Exception as e:
        console.print(f"[red]✗[/red] Configuration validation failed: {e}")
        raise typer.Exit(1)
    
    # Test API connectivity
    try:
        async def test_connectivity():
            # Initialize clients
            okta_client, braintrust_clients = await _initialize_clients(sync_config)
            
            # Test Okta connectivity
            console.print("Testing Okta API connectivity...")
            okta_healthy = await okta_client.health_check()
            if okta_healthy:
                console.print("[green]✓[/green] Okta API connection successful")
            else:
                console.print("[red]✗[/red] Okta API connection failed")
                return False
            
            # Test Braintrust connectivity for each org
            for org_name, client in braintrust_clients.items():
                console.print(f"Testing Braintrust API connectivity for {org_name}...")
                bt_healthy = await client.health_check()
                if bt_healthy:
                    console.print(f"[green]✓[/green] Braintrust API connection successful for {org_name}")
                else:
                    console.print(f"[red]✗[/red] Braintrust API connection failed for {org_name}")
                    return False
            
            return True
        
        connectivity_ok = asyncio.run(test_connectivity())
        if not connectivity_ok:
            console.print("[red]API connectivity tests failed[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]✗[/red] API connectivity test failed: {e}")
        raise typer.Exit(1)
    
    console.print("[green]Validation completed successfully![/green]")


@app.command()
def plan(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c", 
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    organizations: Optional[List[str]] = typer.Option(
        None,
        "--org",
        help="Target Braintrust organizations (default: all configured)",
    ),
    resource_types: Optional[List[str]] = typer.Option(
        None,
        "--resource",
        help="Resource types to sync (user, group)",
    ),
    user_filter: Optional[str] = typer.Option(
        None,
        "--user-filter",
        help="Okta SCIM filter for users",
    ),
    group_filter: Optional[str] = typer.Option(
        None,
        "--group-filter", 
        help="Okta SCIM filter for groups",
    ),
) -> None:
    """Generate and display sync plan (Terraform-like)."""
    # Auto-discover config if not provided
    if config is None:
        config = find_config_file()
        if config:
            console.print(f"Using config file: [cyan]{config}[/cyan]")
    
    # Load configuration
    loader = ConfigLoader()
    try:
        sync_config = loader.load_config(config)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load configuration: {e}")
        raise typer.Exit(1)
    
    async def generate_plan():
        try:
            # Initialize clients and planner
            okta_client, braintrust_clients = await _initialize_clients(sync_config)
            state_manager = StateManager()
            
            # Create sync state if none exists
            current_state = state_manager.get_current_state()
            if not current_state:
                current_state = state_manager.create_sync_state("plan_session")
            
            planner = SyncPlanner(
                config=sync_config,
                okta_client=okta_client,
                braintrust_clients=braintrust_clients,
                state_manager=state_manager,
            )
            
            # Set defaults
            target_orgs = organizations or list(braintrust_clients.keys())
            target_resources = resource_types or ["user", "group"]
            okta_filters = {}
            if user_filter:
                okta_filters["user"] = user_filter
            if group_filter:
                okta_filters["group"] = group_filter
            
            console.print("Generating sync plan...")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Planning synchronization...", total=None)
                
                plan = await planner.generate_sync_plan(
                    target_organizations=target_orgs,
                    resource_types=target_resources,
                    okta_filters=okta_filters,
                    dry_run=True,
                )
            
            # Display plan
            _display_sync_plan(plan)
            
            return plan
            
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to generate sync plan: {e}")
            raise typer.Exit(1)
    
    asyncio.run(generate_plan())


@app.command()
def apply(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file", 
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be synced without making changes",
    ),
    organizations: Optional[List[str]] = typer.Option(
        None,
        "--org",
        help="Target Braintrust organizations (default: all configured)",
    ),
    resource_types: Optional[List[str]] = typer.Option(
        None,
        "--resource",
        help="Resource types to sync (user, group)",
    ),
    auto_approve: bool = typer.Option(
        False,
        "--auto-approve",
        help="Skip interactive confirmation",
    ),
    max_concurrent: int = typer.Option(
        5,
        "--max-concurrent",
        help="Maximum concurrent operations",
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--stop-on-error",
        help="Continue execution after individual item failures",
    ),
) -> None:
    """Apply sync plan to synchronize resources."""
    # Auto-discover config if not provided
    if config is None:
        config = find_config_file()
        if config:
            console.print(f"Using config file: [cyan]{config}[/cyan]")
    
    # Load configuration
    loader = ConfigLoader()
    try:
        sync_config = loader.load_config(config)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load configuration: {e}")
        raise typer.Exit(1)
    
    async def execute_sync():
        try:
            # Initialize clients and components
            okta_client, braintrust_clients = await _initialize_clients(sync_config)
            state_manager = StateManager()
            
            # Create sync state
            current_state = state_manager.get_current_state()
            if not current_state:
                current_state = state_manager.create_sync_state("apply_session")
            
            planner = SyncPlanner(
                config=sync_config,
                okta_client=okta_client,
                braintrust_clients=braintrust_clients,
                state_manager=state_manager,
            )
            
            # Generate plan first
            target_orgs = organizations or list(braintrust_clients.keys())
            target_resources = resource_types or ["user", "group"]
            
            console.print("Generating sync plan...")
            plan = await planner.generate_sync_plan(
                target_organizations=target_orgs,
                resource_types=target_resources,
                dry_run=dry_run,
            )
            
            # Display plan
            _display_sync_plan(plan)
            
            # Confirm execution unless auto-approved or dry run
            if not dry_run and not auto_approve:
                if not typer.confirm("\nDo you want to apply these changes?"):
                    console.print("Operation cancelled.")
                    return
            
            # Execute plan
            progress_data = {"current_progress": None}
            
            def progress_callback(progress: ExecutionProgress):
                progress_data["current_progress"] = progress
            
            # Initialize audit logger
            audit_logger = AuditLogger(
                audit_dir=Path("./logs/audit"),
                structured_logging=True,
            )
            
            executor = SyncExecutor(
                okta_client=okta_client,
                braintrust_clients=braintrust_clients,
                state_manager=state_manager,
                audit_logger=audit_logger,
                progress_callback=progress_callback,
            )
            
            console.print(f"\n{'[yellow]DRY RUN:[/yellow] ' if dry_run else ''}Executing sync plan...")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Synchronizing resources...", total=plan.total_items)
                
                # Execute plan with progress updates
                final_progress = await executor.execute_sync_plan(
                    plan=plan,
                    dry_run=dry_run,
                    continue_on_error=continue_on_error,
                    max_concurrent_operations=max_concurrent,
                )
                
                progress.update(task, completed=final_progress.completed_items + final_progress.failed_items)
            
            # Display results
            _display_execution_results(final_progress, dry_run)
            
            return final_progress
            
        except Exception as e:
            console.print(f"[red]✗[/red] Sync execution failed: {e}")
            raise typer.Exit(1)
    
    asyncio.run(execute_sync())


@app.command()
def show(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """Show current sync state and configuration."""
    console.print("[yellow]State display not yet implemented[/yellow]")
    
    # For now, show basic config info
    if config is None:
        config = find_config_file()
    
    if config:
        console.print(f"Configuration file: {config}")
        
        # Show basic config structure
        loader = ConfigLoader()
        try:
            sync_config = loader.load_config(config)
            
            table = Table(title="Sync Configuration Summary")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Okta Domain", sync_config.okta.domain)
            table.add_row("Braintrust Orgs", ", ".join(sync_config.braintrust_orgs.keys()))
            table.add_row("Declarative Mode", "✓" if sync_config.sync_modes.declarative.enabled else "✗")
            table.add_row("Real-time Mode", "✓" if sync_config.sync_modes.realtime.enabled else "✗")
            table.add_row("User Sync", "✓" if sync_config.sync_rules.users and sync_config.sync_rules.users.enabled else "✗")
            table.add_row("Group Sync", "✓" if sync_config.sync_rules.groups and sync_config.sync_rules.groups.enabled else "✗")
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Failed to load configuration: {e}[/red]")
    else:
        console.print("[red]No configuration file found[/red]")


# Webhook commands
webhook_app = typer.Typer(help="Real-time webhook server commands")
app.add_typer(webhook_app, name="webhook")


@webhook_app.command("start")
def webhook_start(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        "-p",
        help="Override webhook server port",
    ),
) -> None:
    """Start the webhook server for real-time sync."""
    console.print("[yellow]Webhook server not yet implemented[/yellow]")
    console.print("This will start a FastAPI server to receive Okta Event Hooks")


@webhook_app.command("status")
def webhook_status() -> None:
    """Show webhook server status."""
    console.print("[yellow]Webhook status not yet implemented[/yellow]")


@webhook_app.command("test")
def webhook_test(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """Test webhook endpoint with sample events."""
    console.print("[yellow]Webhook testing not yet implemented[/yellow]")


@app.command()
def start(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    declarative_only: bool = typer.Option(
        False,
        "--declarative-only",
        help="Only run declarative mode (no webhook server)",
    ),
    webhook_only: bool = typer.Option(
        False,
        "--webhook-only", 
        help="Only run webhook server (no scheduled sync)",
    ),
) -> None:
    """Start the hybrid sync system (both declarative scheduler and webhook server)."""
    console.print("[yellow]Hybrid sync system not yet implemented[/yellow]")
    console.print("This will start:")
    console.print("  • Scheduled declarative sync (if enabled)")
    console.print("  • Webhook server for real-time events (if enabled)")
    console.print("  • Health check endpoint")
    console.print("  • Metrics collection")


@app.command()
def status() -> None:
    """Show overall sync system status."""
    console.print("[yellow]Status monitoring not yet implemented[/yellow]")
    console.print("This will show:")
    console.print("  • Last sync time and results")
    console.print("  • Webhook server status")
    console.print("  • Recent errors and warnings")  
    console.print("  • API connectivity status")


@app.command()
def reconcile(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Perform full reconciliation (ignore last sync state)",
    ),
) -> None:
    """Force a reconciliation sync to fix any drift."""
    console.print("[yellow]Reconciliation not yet implemented[/yellow]")
    console.print("This will compare Okta state with Braintrust state and fix discrepancies")


# Helper functions

async def _initialize_clients(config: SyncConfig):
    """Initialize Okta and Braintrust clients from configuration.
    
    Args:
        config: Sync configuration
        
    Returns:
        Tuple of (okta_client, braintrust_clients_dict)
    """
    # Initialize Okta client
    okta_client = OktaClient(
        domain=config.okta.domain,
        api_token=config.okta.api_token,
        timeout_seconds=config.okta.timeout_seconds,
        rate_limit_per_minute=config.okta.rate_limit_per_minute,
    )
    
    # Initialize Braintrust clients
    braintrust_clients = {}
    for org_name, org_config in config.braintrust_orgs.items():
        braintrust_clients[org_name] = BraintrustClient(
            api_key=org_config.api_key,
            api_url=org_config.url,
            timeout_seconds=org_config.timeout_seconds,
            rate_limit_per_minute=org_config.rate_limit_per_minute,
        )
    
    return okta_client, braintrust_clients


def _display_sync_plan(plan):
    """Display sync plan in a formatted table.
    
    Args:
        plan: SyncPlan object to display
    """
    summary = plan.get_summary()
    
    # Display plan header
    console.print(f"\n[bold]Sync Plan: {plan.plan_id}[/bold]")
    console.print(f"Target Organizations: [cyan]{', '.join(plan.target_organizations)}[/cyan]")
    
    if summary["estimated_duration_minutes"]:
        console.print(f"Estimated Duration: [yellow]{summary['estimated_duration_minutes']:.1f} minutes[/yellow]")
    
    # Display summary statistics
    summary_table = Table(title="Plan Summary")
    summary_table.add_column("Resource Type", style="cyan")
    summary_table.add_column("Total Items", justify="right", style="green")
    
    summary_table.add_row("Users", str(summary["user_items"]))
    summary_table.add_row("Groups", str(summary["group_items"]))
    summary_table.add_row("[bold]Total[/bold]", f"[bold]{summary['total_items']}[/bold]")
    
    console.print(summary_table)
    
    # Display actions breakdown
    if summary["actions"]:
        actions_table = Table(title="Actions Breakdown")
        actions_table.add_column("Action", style="cyan")
        actions_table.add_column("Count", justify="right", style="green")
        actions_table.add_column("Description", style="dim")
        
        action_descriptions = {
            "create": "New resources to be created",
            "update": "Existing resources to be updated", 
            "skip": "Resources that are already up to date",
        }
        
        for action, count in summary["actions"].items():
            description = action_descriptions.get(action.lower(), "")
            actions_table.add_row(action.upper(), str(count), description)
        
        console.print(actions_table)
    
    # Display organization breakdown
    if summary["organizations"]:
        org_table = Table(title="Organizations Breakdown")
        org_table.add_column("Organization", style="cyan")
        org_table.add_column("Items", justify="right", style="green")
        
        for org, count in summary["organizations"].items():
            org_table.add_row(org, str(count))
        
        console.print(org_table)
    
    # Display warnings if any
    if summary["warnings"]:
        console.print("\n[yellow]⚠ Warnings:[/yellow]")
        for warning in summary["warnings"]:
            console.print(f"  • {warning}")
    
    # Display detailed plan items if not too many
    if plan.total_items <= 50:
        _display_detailed_plan_items(plan)
    else:
        console.print(f"\n[dim]Plan contains {plan.total_items} items. Only showing summary.[/dim]")


def _display_grouped_items(items, title: str):
    """Display sync plan items in a detailed table.
    
    Args:
        items: List of sync plan items
        title: Table title
    """
    if not items:
        return
    
    table = Table(title=title)
    table.add_column("Action", style="cyan", width=8)
    table.add_column("Resource ID", style="green")
    table.add_column("Organization", style="blue")
    table.add_column("Changes", style="dim", width=50)
    
    # Sort items by action for better display
    action_order = {"CREATE": 1, "UPDATE": 2, "DELETE": 3, "SKIP": 4}
    sorted_items = sorted(items, key=lambda x: action_order.get(x.action.value if hasattr(x.action, 'value') else str(x.action), 5))
    
    # Action colors
    action_colors = {
        "CREATE": "[green]CREATE[/green]",
        "UPDATE": "[yellow]UPDATE[/yellow]", 
        "DELETE": "[red]DELETE[/red]",
        "SKIP": "[dim]SKIP[/dim]",
    }
    
    previous_resource_id = None
    for i, item in enumerate(sorted_items):
        action_str = item.action.value if hasattr(item.action, 'value') else str(item.action)
        colored_action = action_colors.get(action_str, action_str)
        
        # Show detailed changes like Terraform
        changes_display = _format_terraform_style_changes(item)
        
        # Add separator line between different resources (groups/users)
        if previous_resource_id is not None and previous_resource_id != item.okta_resource_id:
            table.add_row("[dim]───[/dim]", "[dim]───[/dim]", "[dim]───[/dim]", "[dim]───[/dim]")
        
        table.add_row(
            colored_action,
            item.okta_resource_id,
            item.braintrust_org,
            changes_display,
        )
        
        previous_resource_id = item.okta_resource_id
    
    console.print(table)


def _format_terraform_style_changes(item) -> str:
    """Format changes in Terraform-style diff format.
    
    Args:
        item: SyncPlanItem with action and proposed changes
        
    Returns:
        Formatted changes string showing before/after like Terraform
    """
    if item.action.value == "SKIP" or (hasattr(item.action, 'name') and item.action.name == "SKIP"):
        return "No changes needed"
    
    if item.action.value == "DELETE" or (hasattr(item.action, 'name') and item.action.name == "DELETE"):
        return "[red]Will be deleted[/red]"
    
    if item.action.value == "CREATE" or (hasattr(item.action, 'name') and item.action.name == "CREATE"):
        return "[green]Will be created[/green]"
    
    # For UPDATE actions, show the actual changes
    if not item.proposed_changes:
        return "No specific changes listed"
    
    changes = []
    for field, new_value in item.proposed_changes.items():
        if field == "member_users":
            if isinstance(new_value, list):
                if len(new_value) == 0:
                    changes.append("[dim]member_users = [][/dim] (empty)")
                else:
                    # Show all members, no truncation
                    members_str = ", ".join(new_value)
                    changes.append(f"[dim]member_users = [[/dim][green]{members_str}[/green][dim]][/dim]")
            else:
                changes.append(f"[dim]member_users = [/dim][green]{new_value}[/green]")
        elif field == "member_groups":
            if isinstance(new_value, list):
                if len(new_value) == 0:
                    changes.append("[dim]member_groups = [][/dim] (empty)")
                else:
                    groups_str = ", ".join(new_value)
                    changes.append(f"[dim]member_groups = [[/dim][green]{groups_str}[/green][dim]][/dim]")
            else:
                changes.append(f"[dim]member_groups = [/dim][green]{new_value}[/green]")
        else:
            changes.append(f"[dim]{field} = [/dim][green]{new_value}[/green]")
    
    return "\n".join(changes)


def _improve_reason_description(reason: str) -> str:
    """Improve reason descriptions to be more user-friendly.
    
    Args:
        reason: Original reason string
        
    Returns:
        Improved reason description
    """
    # Replace technical terms with user-friendly descriptions
    improvements = {
        "member_users": "group membership",
        "Updates needed: member_users": "Group membership needs updating",
        "Resource exists in Braintrust but not in Okta (managed by sync tool)": "Resource deleted from Okta - will be removed",
    }
    
    for old, new in improvements.items():
        if old in reason:
            reason = reason.replace(old, new)
    
    return reason


def _display_detailed_plan_items(plan):
    """Display detailed plan items in tables.
    
    Args:
        plan: SyncPlan object with items to display
    """
    # Display user items grouped by action
    if plan.user_items:
        _display_grouped_items(plan.user_items, "User Sync Items")
    
    # Display group items grouped by action
    if plan.group_items:
        _display_grouped_items(plan.group_items, "Group Sync Items")


def _display_execution_results(progress: ExecutionProgress, dry_run: bool):
    """Display execution results and statistics.
    
    Args:
        progress: ExecutionProgress object with results
        dry_run: Whether this was a dry run
    """
    # Display execution summary
    console.print(f"\n[bold]{'Dry Run ' if dry_run else ''}Execution Results: {progress.execution_id}[/bold]")
    
    duration = (
        progress.completed_at - progress.started_at
    ).total_seconds() if progress.completed_at else 0
    
    console.print(f"Duration: [cyan]{duration:.1f} seconds[/cyan]")
    console.print(f"Completion: [green]{progress.get_completion_percentage():.1f}%[/green]")
    
    # Results summary table
    results_table = Table(title="Results Summary")
    results_table.add_column("Status", style="cyan")
    results_table.add_column("Count", justify="right", style="green")
    results_table.add_column("Percentage", justify="right", style="dim")
    
    total = progress.total_items or 1
    results_table.add_row(
        "[green]Completed[/green]",
        str(progress.completed_items),
        f"{(progress.completed_items / total) * 100:.1f}%",
    )
    results_table.add_row(
        "[red]Failed[/red]",
        str(progress.failed_items),
        f"{(progress.failed_items / total) * 100:.1f}%",
    )
    results_table.add_row(
        "[dim]Skipped[/dim]", 
        str(progress.skipped_items),
        f"{(progress.skipped_items / total) * 100:.1f}%",
    )
    results_table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{progress.total_items}[/bold]",
        "[bold]100.0%[/bold]",
    )
    
    console.print(results_table)
    
    # Organization breakdown
    if progress.org_progress:
        org_table = Table(title="Results by Organization")
        org_table.add_column("Organization", style="cyan")
        org_table.add_column("Completed", justify="right", style="green")
        org_table.add_column("Failed", justify="right", style="red")
        org_table.add_column("Skipped", justify="right", style="dim")
        
        for org_name, org_stats in progress.org_progress.items():
            org_table.add_row(
                org_name,
                str(org_stats.get("completed", 0)),
                str(org_stats.get("failed", 0)),
                str(org_stats.get("skipped", 0)),
            )
        
        console.print(org_table)
    
    # Display errors if any
    if progress.errors:
        console.print(f"\n[red]✗ Errors ({len(progress.errors)}):[/red]")
        for i, error in enumerate(progress.errors[:5], 1):  # Show first 5 errors
            console.print(f"  {i}. {error}")
        
        if len(progress.errors) > 5:
            console.print(f"  ... and {len(progress.errors) - 5} more errors")
    
    # Display warnings if any
    if progress.warnings:
        console.print(f"\n[yellow]⚠ Warnings ({len(progress.warnings)}):[/yellow]")
        for i, warning in enumerate(progress.warnings[:3], 1):  # Show first 3 warnings
            console.print(f"  {i}. {warning}")
        
        if len(progress.warnings) > 3:
            console.print(f"  ... and {len(progress.warnings) - 3} more warnings")
    
    # Final status message
    if progress.current_phase == "completed":
        if progress.failed_items == 0:
            status_msg = f"[green]✓ {'Dry run c' if dry_run else 'C'}ompleted successfully![/green]"
        else:
            status_msg = f"[yellow]⚠ {'Dry run c' if dry_run else 'C'}ompleted with {progress.failed_items} failures[/yellow]"
    else:
        status_msg = f"[red]✗ {'Dry run' if dry_run else 'Execution'} failed or was interrupted[/red]"
    
    console.print(f"\n{status_msg}")


@app.command()
def check_groups(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    organization: Optional[str] = typer.Option(
        None,
        "--org",
        "-o",
        help="Target Braintrust organization (if not specified, checks all)",
    ),
    hours: int = typer.Option(
        24,
        "--hours",
        "-h",
        help="Check invitations sent within this many hours",
    ),
    auto_apply: bool = typer.Option(
        False,
        "--auto-apply",
        help="Automatically apply group assignments without confirmation",
    ),
) -> None:
    """Check for accepted invitations and assign users to their appropriate groups.
    
    This command will:
    1. Check for users who have accepted their Braintrust invitations
    2. Determine which groups they should be in based on their Okta attributes
    3. Add them to those groups in Braintrust
    """
    # Find config file if not provided
    if config is None:
        config = find_config_file()
        if config is None:
            console.print("[red]Error: No configuration file found[/red]")
            console.print("Please create a configuration file or specify one with --config")
            raise typer.Exit(1)
    
    # Load configuration
    loader = ConfigLoader()
    try:
        sync_config = loader.load_config(config)
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)
    
    # Determine which organizations to check
    target_orgs = []
    if organization:
        if organization not in sync_config.braintrust_orgs:
            console.print(f"[red]Error: Organization '{organization}' not found in configuration[/red]")
            console.print(f"Available organizations: {', '.join(sync_config.braintrust_orgs.keys())}")
            raise typer.Exit(1)
        target_orgs = [organization]
    else:
        target_orgs = list(sync_config.braintrust_orgs.keys())
    
    console.print(f"[bold]Checking for accepted invitations and assigning groups[/bold]")
    console.print(f"Organizations: [cyan]{', '.join(target_orgs)}[/cyan]")
    console.print(f"Time window: [yellow]{hours} hours[/yellow]")
    
    # Run the check asynchronously
    asyncio.run(_check_groups_async(sync_config, target_orgs, hours, auto_apply))


async def _check_groups_async(
    config: SyncConfig,
    target_orgs: List[str],
    hours: int,
    auto_apply: bool,
) -> None:
    """Run group assignment check asynchronously."""
    # Initialize clients
    okta_client, braintrust_clients = await _initialize_clients(config)
    
    # Initialize state manager
    state_manager = StateManager(state_dir=Path("./state"))
    
    # Initialize user syncer with group assignment enabled
    from sync.resources.users import UserSyncer
    user_syncer = UserSyncer(
        okta_client=okta_client,
        braintrust_clients=braintrust_clients,
        state_manager=state_manager,
        enable_auto_group_assignment=True,
    )
    
    overall_results = {
        "total_checked": 0,
        "total_accepted": 0,
        "total_assigned": 0,
        "errors": [],
    }
    
    # Check each organization
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for org in target_orgs:
            task = progress.add_task(f"Checking {org}...", total=1)
            
            try:
                results = await user_syncer.check_and_assign_groups_for_accepted_invitations(
                    braintrust_org=org,
                    check_window_hours=hours,
                )
                
                overall_results["total_checked"] += results.get("checked_users", 0)
                overall_results["total_accepted"] += results.get("accepted_users", 0)
                overall_results["total_assigned"] += results.get("assigned_users", 0)
                overall_results["errors"].extend(results.get("errors", []))
                
                # Display org results
                console.print(f"\n[bold]{org}:[/bold]")
                console.print(f"  Checked: [cyan]{results.get('checked_users', 0)}[/cyan]")
                console.print(f"  Accepted: [green]{results.get('accepted_users', 0)}[/green]")
                console.print(f"  Assigned to groups: [yellow]{results.get('assigned_users', 0)}[/yellow]")
                
                if results.get("errors"):
                    console.print(f"  [red]Errors: {len(results['errors'])}[/red]")
                
            except Exception as e:
                console.print(f"[red]Error checking {org}: {e}[/red]")
                overall_results["errors"].append(f"{org}: {e}")
            
            progress.update(task, completed=1)
    
    # Display overall summary
    console.print("\n[bold]Overall Summary:[/bold]")
    results_table = Table()
    results_table.add_column("Metric", style="cyan")
    results_table.add_column("Count", justify="right", style="green")
    
    results_table.add_row("Invitations Checked", str(overall_results["total_checked"]))
    results_table.add_row("Users Accepted", str(overall_results["total_accepted"]))
    results_table.add_row("Users Assigned to Groups", str(overall_results["total_assigned"]))
    
    console.print(results_table)
    
    if overall_results["errors"]:
        console.print(f"\n[red]Errors encountered ({len(overall_results['errors'])}):[/red]")
        for error in overall_results["errors"][:5]:
            console.print(f"  • {error}")
        if len(overall_results["errors"]) > 5:
            console.print(f"  ... and {len(overall_results['errors']) - 5} more")
    
    # Clean up
    await okta_client.close()
    for client in braintrust_clients.values():
        await client.close()


if __name__ == "__main__":
    app()