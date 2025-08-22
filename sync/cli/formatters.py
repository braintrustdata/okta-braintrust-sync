"""Output formatters for CLI commands."""

from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from sync.core.planner import SyncPlan, SyncPlanItem
from sync.core.executor import ExecutionProgress
from sync.security.validation import sanitize_log_input
from sync.config.models import SyncConfig


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
                    # Extract name based on resource type and Okta data structure
                    if item.okta_resource_type == "user":
                        # For users, try profile.email, then profile.displayName, then profile.login
                        profile = item.okta_resource.get("profile", {})
                        name = profile.get("email") or profile.get("displayName") or profile.get("login") or "Unknown User"
                    elif item.okta_resource_type == "group":
                        # For groups, use profile.name
                        profile = item.okta_resource.get("profile", {})
                        name = profile.get("name") or item.okta_resource.get("name", "Unknown Group")
                    elif item.okta_resource_type == "role":
                        # For roles, use the role name
                        name = item.okta_resource.get("name", "Unknown Role")
                    elif item.okta_resource_type == "acl":
                        # For ACLs, show group -> role -> project
                        group_name = item.okta_resource.get("group_name", "Unknown")
                        role_name = item.okta_resource.get("role_name", "Unknown")
                        project_name = item.okta_resource.get("project_name", "Unknown")
                        name = f"{group_name} → {role_name} → {project_name}"
                    else:
                        # Fallback for other resource types
                        name = item.okta_resource.get("name") or item.okta_resource.get("displayName", "Unknown")
                    
                    name = sanitize_log_input(name)
                    
                    # Build the main line
                    main_line = f"  [{action_color}]{action_symbol} {item.okta_resource_type}: {name}[/{action_color}]"
                    self.console.print(main_line)
                    
                    # Add additional details if available
                    if item.metadata:
                        # For users, show which groups they'll be added to
                        if item.okta_resource_type == "user" and "group_memberships" in item.metadata:
                            groups = item.metadata["group_memberships"]
                            if groups:
                                group_list = [sanitize_log_input(g) for g in groups[:3]]  # Show first 3
                                group_text = ", ".join(group_list)
                                if len(groups) > 3:
                                    group_text += f" + {len(groups) - 3} more"
                                self.console.print(f"    [dim]→ Groups: {group_text}[/dim]")
                        
                        # For groups, show which roles they'll get
                        elif item.okta_resource_type == "group" and "role_assignments" in item.metadata:
                            roles = item.metadata["role_assignments"]
                            if roles:
                                role_list = [sanitize_log_input(r) for r in roles[:2]]  # Show first 2
                                role_text = ", ".join(role_list)
                                if len(roles) > 2:
                                    role_text += f" + {len(roles) - 2} more"
                                self.console.print(f"    [dim]→ Roles: {role_text}[/dim]")
                        
                        # For roles, show permission count and type
                        elif item.okta_resource_type == "role":
                            permission_count = item.metadata.get("permission_count", 0)
                            role_type = item.metadata.get("role_type", "custom")
                            self.console.print(f"    [dim]→ {permission_count} permissions ({role_type})[/dim]")
                        
                        # For ACLs, show additional context
                        elif item.okta_resource_type == "acl":
                            priority = item.metadata.get("priority", "N/A")
                            self.console.print(f"    [dim]→ Priority: {priority}[/dim]")
            
            self.console.print()
        
        # Summary
        create_count = sum(len(actions["create"]) for actions in by_org.values())
        update_count = sum(len(actions["update"]) for actions in by_org.values())
        skip_count = sum(len(actions["skip"]) for actions in by_org.values())
        
        summary_text = f"Plan: {create_count} to create, {update_count} to update, {skip_count} to skip"
        self.console.print(Panel(summary_text, title="Summary", border_style="blue"))
    
    def format_summary_matrix(self, plan: SyncPlan) -> None:
        """Display sync plan as summary tables organized by resource type."""
        self.console.print()
        self.console.print("[bold blue]Sync Plan Summary[/bold blue]")
        self.console.print()
        
        if plan.total_items == 0:
            self.console.print("[yellow]No changes to apply[/yellow]")
            return
        
        # Group items by organization and resource type
        by_org_and_type = {}
        for item in plan.get_all_items():
            org = sanitize_log_input(item.braintrust_org)
            resource_type = item.okta_resource_type
            
            if org not in by_org_and_type:
                by_org_and_type[org] = {}
            if resource_type not in by_org_and_type[org]:
                by_org_and_type[org][resource_type] = {"create": 0, "update": 0, "skip": 0, "delete": 0}
            
            # Handle the action - get the enum value if it's an enum, otherwise use string
            if hasattr(item.action, 'value'):
                action_key = item.action.value
            else:
                action_key = str(item.action).lower()
            
            if action_key not in by_org_and_type[org][resource_type]:
                by_org_and_type[org][resource_type][action_key] = 0
            by_org_and_type[org][resource_type][action_key] += 1
        
        # Display summary table for each organization
        for org_name, types in by_org_and_type.items():
            table = Table(title=f"Operations for {org_name}")
            table.add_column("Resource Type", style="cyan")
            table.add_column("Create", style="green")
            table.add_column("Update", style="yellow")
            table.add_column("Delete", style="red")
            table.add_column("Skip", style="blue")
            table.add_column("Total", style="bold")
            
            for resource_type, counts in types.items():
                total = counts["create"] + counts["update"] + counts.get("delete", 0) + counts["skip"]
                table.add_row(
                    resource_type.title(),
                    str(counts["create"]) if counts["create"] > 0 else "-",
                    str(counts["update"]) if counts["update"] > 0 else "-",
                    str(counts.get("delete", 0)) if counts.get("delete", 0) > 0 else "-",
                    str(counts["skip"]) if counts["skip"] > 0 else "-",
                    str(total)
                )
            
            self.console.print(table)
            self.console.print()
    
    def format_acl_matrix(self, plan: SyncPlan) -> None:
        """Display ACL assignments in a structured matrix format."""
        acl_items = [item for item in plan.get_all_items() if item.okta_resource_type == "acl"]
        
        if not acl_items:
            self.console.print("[yellow]No ACL assignments in plan[/yellow]")
            return
        
        self.console.print()
        self.console.print("[bold blue]Access Control Assignments (Groups → Roles → Projects)[/bold blue]")
        self.console.print()
        
        # Group ACLs by organization
        by_org = {}
        for item in acl_items:
            org = sanitize_log_input(item.braintrust_org)
            if org not in by_org:
                by_org[org] = []
            by_org[org].append(item)
        
        for org_name, items in by_org.items():
            # Group by role for cleaner display
            by_role = {}
            for item in items:
                role_name = sanitize_log_input(item.okta_resource.get("role_name", "Unknown"))
                if role_name not in by_role:
                    by_role[role_name] = []
                by_role[role_name].append(item)
            
            table = Table(title=f"ACL Assignments - {org_name}")
            table.add_column("Role", style="magenta")
            table.add_column("Group", style="cyan")
            table.add_column("Project", style="green")
            table.add_column("Action", style="bold")
            table.add_column("Priority", style="dim")
            
            for role_name, role_items in by_role.items():
                for i, item in enumerate(role_items):
                    group_name = sanitize_log_input(item.okta_resource.get("group_name", "Unknown"))
                    project_name = sanitize_log_input(item.okta_resource.get("project_name", "Unknown"))
                    priority = item.metadata.get("priority", "N/A") if item.metadata else "N/A"
                    
                    action_style = {
                        "create": "[green]+[/green]",
                        "update": "[yellow]~[/yellow]",
                        "skip": "[blue]=[/blue]"
                    }.get(item.action, item.action)
                    
                    # Only show role name on first row of each role group
                    role_display = role_name if i == 0 else ""
                    
                    table.add_row(
                        role_display,
                        group_name,
                        project_name,
                        action_style,
                        str(priority)
                    )
                
                # Add separator line between roles if there are multiple
                if len(by_role) > 1 and role_name != list(by_role.keys())[-1]:
                    table.add_row("", "", "", "", "")
            
            self.console.print(table)
            self.console.print()
    
    def format_users_table(self, plan: SyncPlan) -> None:
        """Display users in a table format grouped by organization."""
        user_items = [item for item in plan.get_all_items() if item.okta_resource_type == "user"]
        
        if not user_items:
            return
        
        self.console.print()
        self.console.print("[bold blue]User Sync Operations[/bold blue]")
        self.console.print()
        
        # Group by organization
        by_org = {}
        for item in user_items:
            org = sanitize_log_input(item.braintrust_org)
            if org not in by_org:
                by_org[org] = []
            by_org[org].append(item)
        
        for org_name, items in by_org.items():
            table = Table(title=f"Users - {org_name}")
            table.add_column("Email", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Action", style="bold")
            
            for item in sorted(items, key=lambda x: x.okta_resource.get("profile", {}).get("email", "")):
                profile = item.okta_resource.get("profile", {})
                email = sanitize_log_input(profile.get("email") or profile.get("login", "Unknown"))
                name = sanitize_log_input(f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip() or "N/A")
                status = sanitize_log_input(item.okta_resource.get("status", "Unknown"))
                
                action_style = {
                    "create": "[green]+[/green]",
                    "update": "[yellow]~[/yellow]",
                    "skip": "[blue]=[/blue]"
                }.get(item.action, item.action)
                
                table.add_row(email, name, status, action_style)
            
            self.console.print(table)
            self.console.print()
    
    def format_groups_table(self, plan: SyncPlan) -> None:
        """Display groups in a table format grouped by organization."""
        group_items = [item for item in plan.get_all_items() if item.okta_resource_type == "group"]
        
        if not group_items:
            return
        
        self.console.print()
        self.console.print("[bold blue]Group Sync Operations[/bold blue]")
        self.console.print()
        
        # Group by organization
        by_org = {}
        for item in group_items:
            org = sanitize_log_input(item.braintrust_org)
            if org not in by_org:
                by_org[org] = []
            by_org[org].append(item)
        
        for org_name, items in by_org.items():
            table = Table(title=f"Groups - {org_name}")
            table.add_column("Group Name", style="cyan")
            table.add_column("Description", style="dim")
            table.add_column("Type", style="yellow")
            table.add_column("Action", style="bold")
            
            for item in sorted(items, key=lambda x: x.okta_resource.get("profile", {}).get("name", "")):
                profile = item.okta_resource.get("profile", {})
                name = sanitize_log_input(profile.get("name") or item.okta_resource.get("name", "Unknown"))
                description = sanitize_log_input(profile.get("description", "")[:50] or "N/A")
                if len(profile.get("description", "")) > 50:
                    description += "..."
                group_type = sanitize_log_input(item.okta_resource.get("type", "OKTA_GROUP"))
                
                action_style = {
                    "create": "[green]+[/green]",
                    "update": "[yellow]~[/yellow]",
                    "skip": "[blue]=[/blue]"
                }.get(item.action, item.action)
                
                table.add_row(name, description, group_type, action_style)
            
            self.console.print(table)
            self.console.print()
    
    def format_resource_summary(self, plan: SyncPlan) -> None:
        """Display a high-level summary of what resources will be affected."""
        self.console.print()
        self.console.print("[bold blue]Resource Summary[/bold blue]")
        self.console.print()
        
        if plan.total_items == 0:
            self.console.print("[yellow]No changes to apply[/yellow]")
            return
        
        # Collect unique resource names by type
        resources_by_type = {}
        
        for item in plan.get_all_items():
            resource_type = item.okta_resource_type
            
            # Extract resource name
            if resource_type == "user":
                profile = item.okta_resource.get("profile", {})
                name = profile.get("email") or profile.get("displayName") or profile.get("login") or "Unknown User"
            elif resource_type == "group":
                profile = item.okta_resource.get("profile", {})
                name = profile.get("name") or item.okta_resource.get("name", "Unknown Group")
            elif resource_type == "role":
                name = item.okta_resource.get("name", "Unknown Role")
            elif resource_type == "acl":
                # For ACLs, track the project being accessed
                name = item.okta_resource.get("project_name", "Unknown Project")
            else:
                name = item.okta_resource.get("name", "Unknown")
            
            name = sanitize_log_input(name)
            
            if resource_type not in resources_by_type:
                resources_by_type[resource_type] = set()
            resources_by_type[resource_type].add(name)
        
        # Display summary table
        table = Table(title="Affected Resources")
        table.add_column("Type", style="cyan")
        table.add_column("Count", style="green")
        table.add_column("Examples", style="dim")
        
        for resource_type, names in resources_by_type.items():
            name_list = sorted(list(names))
            count = len(name_list)
            
            # Show first 3 examples
            examples = name_list[:3]
            if count > 3:
                examples.append(f"... +{count - 3} more")
            
            examples_text = ", ".join(examples)
            
            table.add_row(
                resource_type.title(),
                str(count),
                examples_text
            )
        
        self.console.print(table)
        
        # Show organization distribution
        org_counts = {}
        for item in plan.get_all_items():
            org = sanitize_log_input(item.braintrust_org)
            org_counts[org] = org_counts.get(org, 0) + 1
        
        self.console.print()
        org_table = Table(title="Operations by Organization")
        org_table.add_column("Organization", style="cyan")
        org_table.add_column("Operations", style="green")
        
        for org, count in org_counts.items():
            org_table.add_row(org, str(count))
        
        self.console.print(org_table)
    
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
            
            # Extract name based on resource type and Okta data structure
            if item.okta_resource_type == "user":
                # For users, try profile.email, then profile.displayName, then profile.login
                profile = item.okta_resource.get("profile", {})
                name = profile.get("email") or profile.get("displayName") or profile.get("login") or "Unknown User"
            elif item.okta_resource_type == "group":
                # For groups, use profile.name
                profile = item.okta_resource.get("profile", {})
                name = profile.get("name") or item.okta_resource.get("name", "Unknown Group")
            elif item.okta_resource_type == "role":
                # For roles, use the role name
                name = item.okta_resource.get("name", "Unknown Role")
            elif item.okta_resource_type == "acl":
                # For ACLs, show group -> role -> project
                group_name = item.okta_resource.get("group_name", "Unknown")
                role_name = item.okta_resource.get("role_name", "Unknown")
                project_name = item.okta_resource.get("project_name", "Unknown")
                name = f"{group_name} → {role_name} → {project_name}"
            else:
                # Fallback for other resource types
                name = item.okta_resource.get("name") or item.okta_resource.get("displayName", "Unknown")
            
            name = sanitize_log_input(name)
            details = self._get_item_details(item)
            
            table.add_row(
                sanitize_log_input(item.braintrust_org),
                item.okta_resource_type,
                action_style,
                name,
                details
            )
        
        self.console.print(table)
    
    def _get_item_details(self, item: SyncPlanItem) -> str:
        """Get formatted details for a sync plan item."""
        details = []
        
        # Show reason if available
        if hasattr(item, 'reason') and item.reason:
            details.append(f"Reason: {sanitize_log_input(item.reason)}")
        
        # Show changes for updates
        if item.action == "update" and hasattr(item, 'changes'):
            changes = getattr(item, 'changes', {})
            if changes:
                change_list = [f"{k}: {sanitize_log_input(str(v))}" for k, v in changes.items()]
                details.append(f"Changes: {', '.join(change_list)}")
        
        # Show metadata if available (group memberships, role assignments, etc.)
        if item.metadata:
            metadata_details = []
            
            # For users, show group memberships
            if item.okta_resource_type == "user" and "group_memberships" in item.metadata:
                groups = item.metadata["group_memberships"]
                if groups:
                    group_list = [sanitize_log_input(g) for g in groups]
                    metadata_details.append(f"Groups: {', '.join(group_list)}")
            
            # For groups, show role assignments
            if item.okta_resource_type == "group" and "role_assignments" in item.metadata:
                roles = item.metadata["role_assignments"]
                if roles:
                    role_list = [sanitize_log_input(r) for r in roles]
                    metadata_details.append(f"Roles: {', '.join(role_list)}")
            
            # Add any other metadata
            for key, value in item.metadata.items():
                if key not in ["group_memberships", "role_assignments"]:
                    safe_key = sanitize_log_input(str(key))
                    safe_value = sanitize_log_input(str(value))
                    metadata_details.append(f"{safe_key}: {safe_value}")
            
            if metadata_details:
                details.extend(metadata_details)
        
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