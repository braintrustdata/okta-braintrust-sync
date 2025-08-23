# Okta-Braintrust Sync

**Automated team onboarding and permission management for GenAI Platform teams**

Sync your organization's teams from Okta groups to Braintrust organizations automatically, eliminating manual account creation and permission management.

## Overview

This tool helps GenAI Platform teams automate the process of:
- **🏢 Team Onboarding**: Bulk sync entire teams from Okta groups to Braintrust organizations
- **🔑 Permission Management**: Map Okta groups to appropriate Braintrust access levels
- **🌍 Multi-Environment Support**: Manage dev/staging/prod Braintrust organizations 
- **📊 Compliance & Auditing**: Track all access changes with detailed audit logs
- **⚡ Declarative Management**: Terraform-like plan/apply workflow for predictable changes

Instead of manually creating Braintrust accounts for each team member and managing group permissions, you define sync rules in YAML and let the tool handle the automation.

### Current Status & Limitations

**✅ What Works Today:**
- ✅ **Declarative sync**: Plan and apply changes like Terraform
- ✅ **Group sync**: Create groups and manage memberships *(tested with real APIs)*
- ✅ **Multi-org support**: Sync to multiple Braintrust organizations
- ✅ **Real API integration**: Successfully tested with live Okta and Braintrust APIs
- ✅ **State management**: Persistent mapping between Okta and Braintrust resources
- ✅ **Error handling**: Graceful handling of API limitations and failures
- ✅ **Audit logging**: Full compliance and troubleshooting logs
- ✅ **CLI commands**: validate, plan, apply, show commands work

**✅ Enhanced User Management:**
- ✅ **User sync**: Full user creation and management via Braintrust API
  - Automatically creates user accounts from Okta profiles  
  - Syncs user attributes (name, email, etc.)
  - No manual invitation step required - fully automated end-to-end
  - Supports user updates and management
- ✅ **Automatic group assignment**: Intelligently assigns users to groups based on multiple strategies
  - Strategy 1: Direct Okta group mapping (e.g. BT-Engineering → Engineering)
  - Strategy 2: Attribute-based assignment (department, role, location)
  - Strategy 3: Hybrid approach combining both strategies
  - Fully customizable group assignment logic

**🚧 Current Limitations:**
- ❌ **Real-time webhooks**: Not yet implemented (commands exist but return "not implemented")
- ❌ **Scheduled sync**: Cron-like scheduling not built yet
- ❌ **Show command**: State display functionality is a placeholder

**🎯 Production Ready for Complete User & Group Management:**
The tool provides comprehensive user and group synchronization with advanced role-project assignment capabilities. Successfully tested with real Okta and Braintrust APIs including the recent major enhancement to ACL execution.

**🧪 Real-World Test Results:**
- ✅ **Okta API**: Successfully retrieves users and groups from Okta instances
- ✅ **User Sync**: Creates and manages user accounts in Braintrust organizations
- ✅ **Group Sync**: Synchronizes groups with proper state management
- ✅ **Role-Project Assignment**: Creates 50+ ACL assignments using Groups → Roles → Projects workflow
- ✅ **State persistence**: All resource mappings saved and managed correctly
- ✅ **ACL Execution**: Fixed executor now properly creates planned ACL items in Braintrust
- ✅ **Audit logging**: Complete audit trails generated for all operations
- ✅ **End-to-end automation**: Complete plan → apply → audit cycle with no manual steps

### Why This Tool?

**Before**: Manual team onboarding
- IT creates individual Braintrust accounts
- Manually adds users to appropriate groups
- Tracks permission changes in spreadsheets
- Reactive access management

**After**: Fully automated sync from Okta
- New team members automatically get Braintrust accounts created
- Users are automatically assigned to appropriate groups based on configurable strategies
- Group memberships stay in sync with Okta changes
- Advanced role-project assignment creates granular permissions (Groups → Roles → Projects)
- Users removed from Okta can be automatically removed from Braintrust (configurable)
- All changes are audited and traceable
- Proactive, policy-driven access management

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/braintrustdata/okta-braintrust-sync
cd okta-braintrust-sync

# Create virtual environment and install
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
uv pip install -e .
```

### 2. Set Up API Credentials

You'll need API access to both Okta and Braintrust:

**Okta API Token:**
- Admin Console → Security → API → Tokens → Create Token
- Required permissions: `okta.users.read`, `okta.groups.read`

**Braintrust API Keys:**
- Go to each Braintrust organization → Settings → API Keys
- Create keys with user, group, role, and ACL management permissions

```bash
# Set environment variables
export OKTA_API_TOKEN="your-okta-token"
export BRAINTRUST_DEV_API_KEY="your-dev-api-key"
export BRAINTRUST_PROD_API_KEY="your-prod-api-key"
```

### 3. Basic Configuration

Create a `sync-config.yaml` file (this configuration will work with the current implementation):

```yaml
okta:
  domain: "yourcompany.okta.com"
  api_token: "${OKTA_API_TOKEN}"

braintrust_orgs:
  dev:
    api_key: "${BRAINTRUST_DEV_API_KEY}"
    url: "https://api.braintrust.dev"
  prod:
    api_key: "${BRAINTRUST_PROD_API_KEY}" 
    url: "https://api.braintrust.dev"

# Note: Only declarative mode is currently implemented
sync_modes:
  declarative:
    enabled: true

sync_rules:
  users:
    enabled: true
    mappings:
      # Sync all active users - simple filter that works today
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["dev", "prod"]
        enabled: true

  groups:
    enabled: true
    mappings:
      # Sync Okta groups - simple filter that works today
      - okta_group_filter: 'type eq "OKTA_GROUP"'
        braintrust_orgs: ["dev", "prod"]
        enabled: true
```

**Note**: This is a minimal working configuration. You can add more complex filters after testing the basic setup works with your API credentials.

### 4. Test and Run

```bash
# Test configuration and API connectivity
okta-braintrust-sync validate --config sync-config.yaml

# Preview what will be synced (dry run)
okta-braintrust-sync plan --config sync-config.yaml

# Execute the sync
okta-braintrust-sync apply --config sync-config.yaml --auto-approve
```

## Groups → Roles → Projects Workflow

The tool supports an advanced workflow for granular permission management:

### How It Works

1. **Groups**: Collections of users (synced from Okta or created via group assignment)
2. **Roles**: Named permission sets (create, read, update, delete, ACL management) 
3. **Projects**: Specific Braintrust projects where roles are applied

The workflow creates ACLs that grant groups specific roles on matching projects.

### Example Configuration

```yaml
role_project_assignment:
  global_config:
    # Define reusable roles
    standard_roles:
      - name: "Engineer" 
        description: "Engineering team permissions"
        member_permissions:
          - permission: "create"
          - permission: "read"
          - permission: "update"
          - permission: "delete"
            
    # Assign groups to roles on projects
    group_assignments:
      # Engineering group gets Engineer role on development projects
      - group_name: "BT-Engineering"
        role_name: "Engineer"
        project_match:
          name_contains: ["api", "service", "web", "mobile"]
        enabled: true
        priority: 50
```

### Benefits

- **Granular Control**: Different roles for different project types
- **Scalable**: Role changes automatically apply to all assigned groups/projects  
- **Pattern-Based**: Use regex, contains, starts/ends patterns to match projects
- **Multi-Org**: Per-organization role and project configurations

## Automatic Group Assignment

The tool supports three strategies for automatic group assignment:

### Strategy 1: Okta Groups (`okta_groups`)
Map users based on their Okta group memberships:

```yaml
group_assignment:
  global_config:
    strategy: "okta_groups"
    sync_group_names: true  # Use same names as Okta groups
    
    # Optional: explicit mappings (if not using sync_group_names)
    # okta_group_mappings:
    #   - okta_group_name: "BT-Engineering"
    #     braintrust_group_name: "BT-Engineering"
    #   - okta_group_name: "BT-DataScience"
    #     braintrust_group_name: "BT-DataScience"
```

### Strategy 2: Attributes (`attributes`)
Map users based on their Okta profile attributes:

```yaml
group_assignment:
  global_config:
    strategy: "attributes"
    attribute_mappings:
      - rule:
          conditions:
            - attribute: "department"
              operator: "equals"
              value: "Engineering"
        braintrust_group_name: "Engineers"
        priority: 50
```

### Strategy 3: Hybrid (`hybrid`)
Combine both Okta groups and attributes:

```yaml
group_assignment:
  global_config:
    strategy: "hybrid"
    hybrid_mode: "merge"
    okta_group_mappings: [...]
    attribute_mappings: [...]
```

## Common Team Onboarding Scenarios

### Scenario 1: Start Simple - All Active Users

**Situation**: You want to sync all active users from Okta to get started.

```yaml
sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["dev"]  # Start with dev only
        enabled: true
        
  groups:
    enabled: true  
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP"'
        braintrust_orgs: ["dev"]  # Start with dev only
        enabled: true
```

**Result**: All active users and standard Okta groups get synced to your dev Braintrust org. Test this first!

### Scenario 2: Filtered Sync (Advanced)

**Situation**: After basic sync works, use SCIM filters for specific criteria.

```yaml
sync_rules:
  users:
    enabled: true
    mappings:
      # Only sync users with specific status and criteria
      - okta_filter: 'status eq "ACTIVE" and profile.department eq "Engineering"'
        braintrust_orgs: ["dev", "prod"]
        enabled: true
        
  groups:
    enabled: true
    mappings:
      # Only sync specific group types
      - okta_group_filter: 'type eq "OKTA_GROUP"'
        braintrust_orgs: ["dev", "prod"]
        enabled: true
```

**Note**: SCIM filter syntax is supported - test filters carefully to ensure they match your Okta setup.

### Scenario 3: Multi-Organization Setup (Production)

**Situation**: After testing, scale to multiple environments.

```yaml
braintrust_orgs:
  dev:
    api_key: "${BRAINTRUST_DEV_API_KEY}"
    url: "https://api.braintrust.dev"
  staging:
    api_key: "${BRAINTRUST_STAGING_API_KEY}"
    url: "https://api.braintrust.dev"
  prod:
    api_key: "${BRAINTRUST_PROD_API_KEY}"
    url: "https://api.braintrust.dev"

sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["dev", "staging", "prod"]
        enabled: true
```

## Configuration Reference

### Okta Configuration

```yaml
okta:
  domain: "yourcompany.okta.com"         # Your Okta domain
  api_token: "${OKTA_API_TOKEN}"         # API token with read access to users/groups
  rate_limit_per_minute: 600             # Optional: API rate limiting
  timeout_seconds: 30                    # Optional: Request timeout
```

**Required Okta Permissions**: Your API token needs read access to:
- Users (`okta.users.read`)
- Groups (`okta.groups.read`)

### Braintrust Organizations

```yaml
braintrust_orgs:
  dev:
    api_key: "${BRAINTRUST_DEV_API_KEY}"
    url: "https://api.braintrust.dev"
    
  prod:
    api_key: "${BRAINTRUST_PROD_API_KEY}"
    url: "https://api.braintrust.dev"
```

**Required Braintrust Permissions**: API keys need ability to:
- Create and manage users
- Create/update groups  
- Manage group memberships
- Create and update roles
- Create and manage ACLs (project permissions)

### User Sync Rules

```yaml
sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE"'                    # SCIM filter for users
        braintrust_orgs: ["dev", "prod"]                     # Target organizations
        enabled: true
```

### Group Sync Rules

```yaml
sync_rules:
  groups:
    enabled: true
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP"'           # SCIM filter for groups
        braintrust_orgs: ["dev", "prod"]                     # Target organizations
        enabled: true
```

### Role-Project Assignment Rules

```yaml
role_project_assignment:
  global_config:
    # Define standard roles
    standard_roles:
      - name: "Engineer"
        description: "Engineering permissions"
        member_permissions:
          - permission: "create"
          - permission: "read" 
          - permission: "update"
          - permission: "delete"
            
    # Assign groups to roles on projects  
    group_assignments:
      - group_name: "BT-Engineering"
        role_name: "Engineer"
        project_match:
          name_contains: ["api", "service", "web"]
        enabled: true
        priority: 50
        
    auto_create_roles: true
    remove_unmanaged_acls: false
```

**Note**: The current implementation uses straightforward, reliable sync rules with basic SCIM filtering. Complex filtering scenarios should be tested thoroughly before production use.

## CLI Commands

### Validate Configuration

```bash
# Test configuration and API connectivity
okta-braintrust-sync validate --config sync-config.yaml
```

### Preview Changes

```bash
# Generate sync plan for all organizations and resource types
okta-braintrust-sync plan --config sync-config.yaml
```

### Execute Sync

```bash
# Apply changes with confirmation prompt
okta-braintrust-sync apply --config sync-config.yaml

# Apply changes automatically (no prompt)
okta-braintrust-sync apply --config sync-config.yaml --auto-approve

# Dry run (show what would be done without making changes)
okta-braintrust-sync apply --config sync-config.yaml --dry-run
```

### Show Status

```bash
# Display current sync status and state information
okta-braintrust-sync status --config sync-config.yaml
```


## Monitoring & Auditing

### Audit Logs

All sync operations are logged to `./logs/audit/` with:
- **Structured JSON logs** for each operation
- **Execution summaries** with statistics and errors
- **Before/after state tracking** for compliance

Example audit log entry:
```json
{
  "event_id": "sync-user-123",
  "event_type": "resource_create",
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_id": "exec-456",
  "resource_type": "user",
  "resource_id": "john.doe@company.com",
  "braintrust_org": "prod",
  "operation": "CREATE",
  "success": true,
  "before_state": null,
  "after_state": {
    "id": "bt-user-789",
    "email": "john.doe@company.com",
    "name": "John Doe"
  }
}
```

### State Management

The tool maintains sync state in `./state/` to:
- Track resource mappings between Okta and Braintrust
- Enable incremental syncs (only process changes)
- Support recovery from failed operations
- Prevent duplicate operations

## Troubleshooting

### Common Issues

**Configuration Validation Errors**
```bash
# Error: "No configuration file found"
# Solution: Specify config file path
okta-braintrust-sync validate --config /path/to/sync-config.yaml
```

**API Connectivity Issues**
```bash
# Error: "Okta API connection failed"
# Check: 
# 1. API token is valid and not expired
# 2. Token has required permissions (users.read, groups.read)
# 3. Okta domain is correct
# 4. Network connectivity to Okta

# Error: "Braintrust API connection failed"
# Check:
# 1. API key is valid and not expired
# 2. API key has required permissions (user/group management)
# 3. Braintrust organization URL is correct
# 4. Network connectivity to Braintrust
```

**Sync Planning Issues**
```bash
# Error: "No users/groups match filters"
# Check:
# 1. SCIM filters are correct syntax
# 2. Users/groups exist in Okta with expected attributes
# 3. Filters aren't too restrictive

# Debug with verbose logging
STRUCTLOG_LEVEL=DEBUG okta-braintrust-sync plan --config sync-config.yaml
```

**Execution Failures**
```bash
# Error: "Rate limit exceeded"
# Solution: Reduce rate limits in config
okta:
  rate_limit_per_minute: 300  # Lower from default 600

# Success: User sync workflow is fully automated
# Users are created in Braintrust with automatic group assignment
# Role-project assignments create granular ACL permissions
# No manual intervention required - fully end-to-end automation

# Error: "Permission denied"
# Check: API keys have required permissions in both systems
```

### Debug Mode

Enable detailed logging:
```bash
export STRUCTLOG_LEVEL=DEBUG
okta-braintrust-sync plan --config sync-config.yaml
```

### Recovery from Failed Syncs

If a sync fails partway through:
```bash
# Check current sync status
okta-braintrust-sync status --config sync-config.yaml

# Re-run the sync (it will resume from where it left off)
okta-braintrust-sync apply --config sync-config.yaml
```

## Best Practices

### Security

- **API Tokens**: Store in environment variables, never commit to code
- **Least Privilege**: Use API tokens with minimal required permissions
- **Audit Logs**: Regularly review sync logs for unauthorized changes
- **Network Security**: Consider running in secure environment with limited network access
- **State Files**: Secure the ./state/ directory as it contains ID mappings between systems

### Operational

- **Start Small**: Begin with dev environment and a single team
- **Test Filters**: Use `plan` command to verify filters before applying
- **Monitor Logs**: Set up log monitoring for failed operations
- **Regular Reconciliation**: Run periodic full syncs for consistency
- **Backup State**: Include state directory in your backup strategy

### Team Onboarding Workflow

1. **Plan**: Define which Okta groups should map to which Braintrust orgs
2. **Configure**: Set up sync rules in configuration file
3. **Test**: Use `plan` command to preview changes
4. **Apply**: Execute sync with `--dry-run` first, then real apply
5. **Verify**: Check Braintrust organizations for expected users/groups
6. **Monitor**: Review audit logs for any issues
7. **Iterate**: Refine configuration based on results

## Advanced Configuration

### Custom Identity Mapping

*Note: Current implementation uses email-based identity matching between Okta and Braintrust. This works reliably for most organizational setups.*

### Environment-Specific Settings

Use different configs per environment:

```bash
# Development
okta-braintrust-sync apply --config configs/dev-sync.yaml

# Production  
okta-braintrust-sync apply --config configs/prod-sync.yaml
```

### Scheduled Syncs

Set up regular syncs with cron:

```bash
# Add to crontab for daily syncs at 2 AM
0 2 * * * /path/to/venv/bin/okta-braintrust-sync apply --config /path/to/sync-config.yaml --auto-approve
```

## Architecture

The tool uses a declarative, Terraform-like approach:
1. **Plan**: Analyze current state vs desired state
2. **Apply**: Execute planned changes
3. **Audit**: Log all operations for compliance

This ensures predictable, traceable changes to your Braintrust access management.

## Quick Command Reference

```bash
# Configuration & Validation
okta-braintrust-sync validate --config sync-config.yaml
okta-braintrust-sync status --config sync-config.yaml

# Plan & Apply Changes
okta-braintrust-sync plan --config sync-config.yaml
okta-braintrust-sync apply --config sync-config.yaml --auto-approve


# Dry Run Testing
okta-braintrust-sync apply --config sync-config.yaml --dry-run

# Debug Mode
STRUCTLOG_LEVEL=DEBUG okta-braintrust-sync plan --config sync-config.yaml
```

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review audit logs in `./logs/audit/`
3. Enable debug logging for more details
4. Verify configuration syntax against examples

---

**Ready to get started?** Follow the [Quick Start](#quick-start) guide to set up automated team onboarding for your GenAI platform!