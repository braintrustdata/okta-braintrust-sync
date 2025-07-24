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
- ✅ **User sync**: Create and update users from Okta to Braintrust
- ✅ **Group sync**: Create groups and manage memberships
- ✅ **Multi-org support**: Sync to multiple Braintrust organizations
- ✅ **Comprehensive testing**: All functionality tested with mocks
- ✅ **Audit logging**: Full compliance and troubleshooting logs
- ✅ **CLI commands**: validate, plan, apply, show commands work

**🚧 Current Limitations:**
- ❌ **Real-time webhooks**: Not yet implemented (commands exist but return "not implemented")
- ❌ **Scheduled sync**: Cron-like scheduling not built yet
- ❌ **Braintrust API testing**: Needs real API testing with live credentials
- ❌ **Advanced filtering**: Some complex SCIM filters may need refinement

**🎯 Ready for Real-World Testing:**
The core functionality is complete and ready for testing with real Okta and Braintrust API credentials. The declarative sync workflow is fully functional.

### Why This Tool?

**Before**: Manual team onboarding
- IT creates individual Braintrust accounts
- Manually adds users to appropriate groups
- Tracks permission changes in spreadsheets
- Reactive access management

**After**: Automated sync from Okta
- New team members get Braintrust access automatically
- Group memberships stay in sync with Okta
- All changes are audited and traceable
- Proactive, policy-driven access management

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd okta-braintrust-sync

# Create virtual environment and install
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

### 2. Set Up API Credentials

You'll need API access to both Okta and Braintrust:

**Okta API Token:**
- Admin Console → Security → API → Tokens → Create Token
- Required permissions: `okta.users.read`, `okta.groups.read`

**Braintrust API Keys:**
- Go to each Braintrust organization → Settings → API Keys
- Create keys with user and group management permissions

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

### Scenario 2: Department-Based Filtering (Advanced)

**Situation**: After basic sync works, filter by department.

```yaml
sync_rules:
  users:
    enabled: true
    mappings:
      # Only sync ML Engineering and Data Science teams
      - okta_filter: 'status eq "ACTIVE" and profile.department eq "Engineering"'
        braintrust_orgs: ["dev", "prod"]
        enabled: true
        
  groups:
    enabled: true
    mappings:
      # Only sync specific groups by name
      - okta_group_filter: 'type eq "OKTA_GROUP" and profile.name eq "ML-Team"'
        braintrust_orgs: ["dev", "prod"]
        enabled: true
```

**Note**: Complex filters like department matching should be tested after you verify basic sync works with your Okta setup.

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
- Create/update users
- Create/update groups  
- Manage group memberships

### User Sync Rules

```yaml
sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE"'                    # SCIM filter for users
        braintrust_orgs: ["dev", "prod"]                     # Target organizations
        identity_mapping: "email"                            # How to match users (email/custom)
        domain_filters: ["company.com"]                      # Optional: Only sync specific domains
        custom_field_mappings:                               # Optional: Map custom fields
          department: "profile.department"
          team: "profile.customField.team"
```

### Group Sync Rules

```yaml
sync_rules:
  groups:
    enabled: true
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP"'           # SCIM filter for groups
        braintrust_orgs: ["dev", "prod"]                     # Target organizations
        group_name_template: "${okta_group_name_lower}"      # How to name groups in Braintrust
        group_name_prefix: "okta-"                           # Optional: Add prefix
        group_name_suffix: "-team"                           # Optional: Add suffix
        member_filters:                                      # Optional: Filter group members
          - 'status eq "ACTIVE"'
```

### Template Variables

Use these variables in `group_name_template`:

- `${okta_group_name}` - Original Okta group name
- `${okta_group_name_lower}` - Lowercase version
- `${okta_group_name_slug}` - URL-safe slug version
- `${braintrust_org}` - Target Braintrust organization name

## CLI Commands

### Validate Configuration

```bash
# Test configuration and API connectivity
okta-braintrust-sync validate --config sync-config.yaml

# Test only Okta connectivity
okta-braintrust-sync validate --config sync-config.yaml --okta-only

# Test only Braintrust connectivity
okta-braintrust-sync validate --config sync-config.yaml --braintrust-only
```

### Preview Changes

```bash
# Generate sync plan for all organizations
okta-braintrust-sync plan --config sync-config.yaml

# Plan for specific organizations
okta-braintrust-sync plan --config sync-config.yaml --org dev --org staging

# Plan for specific resource types
okta-braintrust-sync plan --config sync-config.yaml --resource user --resource group

# Plan with custom filters
okta-braintrust-sync plan --config sync-config.yaml \
  --user-filter 'profile.department eq "ML Engineering"' \
  --group-filter 'profile.name sw "Team-"'
```

### Execute Sync

```bash
# Apply changes with confirmation prompt
okta-braintrust-sync apply --config sync-config.yaml

# Apply changes automatically (no prompt)
okta-braintrust-sync apply --config sync-config.yaml --auto-approve

# Dry run (show what would be done without making changes)
okta-braintrust-sync apply --config sync-config.yaml --dry-run

# Control concurrency and error handling
okta-braintrust-sync apply --config sync-config.yaml \
  --max-concurrent 10 \
  --continue-on-error
```

### Show Configuration

```bash
# Display current configuration summary
okta-braintrust-sync show --config sync-config.yaml
```

### Webhook Commands (Not Yet Implemented)

```bash
# These commands exist but return "not yet implemented"
okta-braintrust-sync webhook start --config sync-config.yaml    # ❌ Not working yet
okta-braintrust-sync webhook status                            # ❌ Not working yet  
okta-braintrust-sync start --config sync-config.yaml           # ❌ Not working yet
okta-braintrust-sync status                                    # ❌ Not working yet
```

**Current Status**: The webhook server and scheduled sync functionality are not implemented yet. Use the declarative `plan` and `apply` commands which are fully functional.

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
# Check current state
okta-braintrust-sync show --config sync-config.yaml

# Re-run the sync (it will resume from where it left off)
okta-braintrust-sync apply --config sync-config.yaml --continue-on-error
```

## Best Practices

### Security

- **API Tokens**: Store in environment variables, never commit to code
- **Least Privilege**: Use API tokens with minimal required permissions
- **Audit Logs**: Regularly review sync logs for unauthorized changes
- **Network Security**: Consider running in secure environment with limited network access
- **State Files**: Protect state directory as it contains resource mappings

### Operational

- **Start Small**: Begin with dev environment and a single team
- **Test Filters**: Use `plan` command to verify filters before applying
- **Monitor Logs**: Set up log monitoring for failed operations
- **Regular Reconciliation**: Run periodic full syncs to catch drift
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

For complex identity scenarios:

```yaml
sync_rules:
  users:
    mappings:
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["prod"]
        identity_mapping: "custom"
        identity_mapping_file: "./identity-mappings.json"  # Custom mapping file
```

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
okta-braintrust-sync show --config sync-config.yaml

# Plan & Apply Changes
okta-braintrust-sync plan --config sync-config.yaml
okta-braintrust-sync apply --config sync-config.yaml --auto-approve

# Dry Run Testing
okta-braintrust-sync apply --config sync-config.yaml --dry-run

# Filtered Operations
okta-braintrust-sync plan --config sync-config.yaml --org dev --resource user
```

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review audit logs in `./logs/audit/`
3. Enable debug logging for more details
4. Verify configuration syntax against examples

---

**Ready to get started?** Follow the [Quick Start](#quick-start) guide to set up automated team onboarding for your GenAI platform!