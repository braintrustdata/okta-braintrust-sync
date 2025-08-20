"""Output formatters for CLI commands."""

from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from sync.core.planner import SyncPlan, SyncPlanItem
from sync.core.executor import ExecutionProgress
from sync.security.validation import sanitize_log_input


class SyncPlanFormatter:
    """Formats sync plans for display."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def format_terraform_style(self, plan: SyncPlan) -> None:
        """Display sync plan in Terraform-like style."""
        self.console.print()
        self.console.print("[bold blue]Sync Plan[/bold blue]")
        self.console.print()
        
        if plan.total_items == 0:
            self.console.print("[yellow]No changes to apply[/yellow]")
            return
        
        # Group items by organization and action
        by_org = {}
        for item in plan.get_all_items():
            org = sanitize_log_input(item.braintrust_org)
            if org not in by_org:
                by_org[org] = {"create": [], "update": [], "skip": []}
            by_org[org][item.action].append(item)
        
        for org_name, actions in by_org.items():
            self.console.print(f"[bold cyan]Organization: {org_name}[/bold cyan]")
            
            for action, items in actions.items():
                if not items:
                    continue
                
                action_color = {
                    "create": "green",
                    "update": "yellow", 
                    "skip": "blue"
                }[action]
                
                action_symbol = {
                    "create": "+",
                    "update": "~",
                    "skip": "="
                }[action]
                
                for item in items:
                    name = sanitize_log_input(item.okta_resource.get("displayName", item.okta_resource.get("email", "Unknown")))
                    self.console.print(f"  [{action_color}]{action_symbol} {item.resource_type}: {name}[/{action_color}]")
            
            self.console.print()
        
        # Summary
        create_count = sum(len(actions["create"]) for actions in by_org.values())
        update_count = sum(len(actions["update"]) for actions in by_org.values())
        skip_count = sum(len(actions["skip"]) for actions in by_org.values())
        
        summary_text = f"Plan: {create_count} to create, {update_count} to update, {skip_count} to skip"
        self.console.print(Panel(summary_text, title="Summary", border_style="blue"))
    
    def format_detailed_table(self, plan: SyncPlan) -> None:
        """Display sync plan as detailed table."""
        if plan.total_items == 0:
            self.console.print("[yellow]No items in sync plan[/yellow]")
            return
        
        table = Table(title="Sync Plan Details")
        table.add_column("Organization", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Action", style="bold")
        table.add_column("Resource", style="green")
        table.add_column("Details", style="dim")
        
        for item in plan.get_all_items():
            action_style = {
                "create": "[green]+[/green]",
                "update": "[yellow]~[/yellow]",
                "skip": "[blue]=[/blue]"
            }.get(item.action, item.action)
            
            name = sanitize_log_input(item.okta_resource.get("displayName", item.okta_resource.get("email", "Unknown")))
            details = self._get_item_details(item)
            
            table.add_row(
                sanitize_log_input(item.braintrust_org),
                item.resource_type,
                action_style,
                name,
                details
            )
        
        self.console.print(table)
    
    def _get_item_details(self, item: SyncPlanItem) -> str:
        """Get formatted details for a sync plan item."""
        details = []
        
        if hasattr(item, 'reason') and item.reason:
            details.append(f"Reason: {sanitize_log_input(item.reason)}")
        
        if item.action == "update" and hasattr(item, 'changes'):
            changes = getattr(item, 'changes', {})
            if changes:
                change_list = [f"{k}: {sanitize_log_input(str(v))}" for k, v in changes.items()]
                details.append(f"Changes: {', '.join(change_list)}")
        
        return "; ".join(details) if details else "No additional details"


class ProgressFormatter:
    """Formats execution progress for display."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def format_progress_summary(self, progress: ExecutionProgress) -> None:
        """Display execution progress summary."""
        # Status indicator
        status_color = {
            "initializing": "blue",
            "users": "cyan",
            "groups": "green",
            "drift_detection": "yellow",
            "finalizing": "orange",
            "completed": "green",
            "failed": "red"
        }.get(progress.current_phase, "white")
        
        status_text = f"[{status_color}]{progress.current_phase.replace('_', ' ').title()}[/{status_color}]"
        
        # Progress bar
        percentage = progress.get_completion_percentage()
        progress_text = f"{progress.completed_items}/{progress.total_items} items ({percentage:.1f}%)"
        
        # Timing info
        duration = (progress.completed_at - progress.started_at).total_seconds() if progress.completed_at else 0
        timing_text = f"Duration: {duration:.1f}s" if duration > 0 else "In progress..."
        
        self.console.print(f"Status: {status_text}")
        self.console.print(f"Progress: {progress_text}")
        self.console.print(f"{timing_text}")
        
        if progress.errors:
            self.console.print(f"[red]Errors: {len(progress.errors)}[/red]")
        
        if progress.warnings:
            self.console.print(f"[yellow]Warnings: {len(progress.warnings)}[/yellow]")
    
    def format_org_progress(self, progress: ExecutionProgress) -> None:
        """Display per-organization progress."""
        if not progress.org_progress:
            return
        
        table = Table(title="Progress by Organization")
        table.add_column("Organization", style="cyan")
        table.add_column("Completed", style="green")
        table.add_column("Failed", style="red")
        table.add_column("Skipped", style="blue")
        
        for org_name, stats in progress.org_progress.items():
            table.add_row(
                sanitize_log_input(org_name),
                str(stats.get("completed", 0)),
                str(stats.get("failed", 0)),
                str(stats.get("skipped", 0))
            )
        
        self.console.print(table)
    
    def format_errors_and_warnings(self, progress: ExecutionProgress) -> None:
        """Display errors and warnings."""
        if progress.errors:
            self.console.print("\n[red]Errors:[/red]")
            for i, error in enumerate(progress.errors, 1):
                sanitized_error = sanitize_log_input(error)
                self.console.print(f"  {i}. {sanitized_error}")
        
        if progress.warnings:
            self.console.print("\n[yellow]Warnings:[/yellow]")
            for i, warning in enumerate(progress.warnings, 1):
                sanitized_warning = sanitize_log_input(warning)
                self.console.print(f"  {i}. {sanitized_warning}")


class StateFormatter:
    """Formats state information for display."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def format_state_summary(self, state_summary: Dict[str, Any]) -> None:
        """Display state summary."""
        if "no_current_state" in state_summary:
            self.console.print("[yellow]No current state available[/yellow]")
            return
        
        table = Table(title="State Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        for key, value in state_summary.items():
            # Sanitize both key and value for display
            safe_key = sanitize_log_input(str(key).replace('_', ' ').title())
            safe_value = sanitize_log_input(str(value))
            table.add_row(safe_key, safe_value)
        
        self.console.print(table)
    
    def format_drift_warnings(self, warnings: List[Dict[str, Any]]) -> None:
        """Display drift warnings."""
        if not warnings:
            self.console.print("[green]No drift detected[/green]")
            return
        
        table = Table(title="Drift Warnings")
        table.add_column("Resource Type", style="cyan")
        table.add_column("Resource ID", style="magenta")
        table.add_column("Drift Type", style="yellow")
        table.add_column("Details", style="white")
        table.add_column("Severity", style="red")
        
        for warning in warnings:
            table.add_row(
                sanitize_log_input(warning.get("resource_type", "Unknown")),
                sanitize_log_input(warning.get("resource_id", "Unknown")),
                sanitize_log_input(warning.get("drift_type", "Unknown")),
                sanitize_log_input(warning.get("details", "")),
                sanitize_log_input(warning.get("severity", "warning"))
            )
        
        self.console.print(table)


class ConfigFormatter:
    """Formats configuration information for display."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def format_config_summary(self, config: SyncConfig) -> None:
        """Display configuration summary."""
        table = Table(title="Configuration Summary")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        # Okta configuration
        table.add_row("Okta Domain", sanitize_log_input(config.okta.domain))
        table.add_row("Okta Rate Limit", str(config.okta.rate_limit_per_minute))
        
        # Braintrust organizations
        org_names = list(config.braintrust_orgs.keys())
        table.add_row("Braintrust Orgs", sanitize_log_input(", ".join(org_names)))
        
        # Sync modes
        if config.sync_modes.users:
            table.add_row("User Sync", "Enabled")
        if config.sync_modes.groups:
            table.add_row("Group Sync", "Enabled")
        
        # Role-project assignments
        if config.role_project_assignment:
            table.add_row("Role-Project Assignment", "Configured")
        
        self.console.print(table)
    
    def format_validation_errors(self, errors: List[str]) -> None:
        """Display configuration validation errors."""
        if not errors:
            self.console.print("[green]Configuration is valid[/green]")
            return
        
        self.console.print("[red]Configuration Validation Errors:[/red]")
        for i, error in enumerate(errors, 1):
            sanitized_error = sanitize_log_input(error)
            self.console.print(f"  {i}. {sanitized_error}")