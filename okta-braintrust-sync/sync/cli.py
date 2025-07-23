"""Command-line interface for okta-braintrust-sync."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from sync.config.loader import ConfigLoader, find_config_file
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
    
    # TODO: Add API connectivity tests
    console.print("[yellow]API connectivity validation not yet implemented[/yellow]")
    
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
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="Show what would be synced without making changes",
    ),
) -> None:
    """Generate and display sync plan (Terraform-like)."""
    console.print("[yellow]Sync planning not yet implemented[/yellow]")
    console.print("This will show:")
    console.print("  • Users to be created/updated in each Braintrust org")
    console.print("  • Groups to be created/updated in each Braintrust org")
    console.print("  • Group memberships to be synchronized")
    console.print("  • Resources that would be skipped and why")


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
) -> None:
    """Apply sync plan to synchronize resources."""
    console.print("[yellow]Sync execution not yet implemented[/yellow]")
    console.print("This will execute the sync plan and:")
    console.print("  • Create/update users in Braintrust organizations") 
    console.print("  • Create/update groups in Braintrust organizations")
    console.print("  • Synchronize group memberships")
    console.print("  • Generate detailed audit logs")


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


if __name__ == "__main__":
    app()