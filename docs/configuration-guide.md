# Complete YAML Configuration Guide

This guide provides comprehensive documentation for configuring the okta-braintrust-sync system, including all available options, strategies, and best practices.

## ⚠️ Implementation Status

**Currently Implemented (✅ Fully Functional):**
- ✅ **Declarative Sync Mode** - Scheduled synchronization
- ✅ **User/Group Sync** - From Okta to Braintrust
- ✅ **Group Assignment** - All 3 strategies (okta_groups, attributes, hybrid)
- ✅ **Groups → Roles → Projects Workflow** - Complete role-project assignment
- ✅ **8 Braintrust Permissions** - All permission types with object restrictions
- ✅ **YAML Configuration** - All configuration models
- ✅ **Audit Logging** - Basic logging and audit trails
- ✅ **Okta/Braintrust API Clients** - Full API integration
- ✅ **CLI Commands** - Sync, plan, validate commands

**Not Yet Implemented (⚠️ Removed from Configuration):**
- ⚠️ **Real-time/Webhook Mode** - Event-driven synchronization
- ⚠️ **Priority Rules** - Event routing between modes
- ⚠️ **Advanced CLI Features** - Status monitoring, reconciliation
- ⚠️ **User Updates** - Braintrust API limitation
- ⚠️ **ACL Removal** - Marked as destructive operation

**Recommendation:** Use only declarative mode with `realtime.enabled: false` for production deployments.

## Table of Contents

1. [Configuration Overview](#configuration-overview)
2. [Core Configuration Sections](#core-configuration-sections)
3. [Okta Configuration](#okta-configuration)
4. [Braintrust Organizations](#braintrust-organizations)
5. [Sync Rules](#sync-rules)
6. [Group Assignment Strategies](#group-assignment-strategies)
7. [Role-Project Assignment (Groups → Roles → Projects)](#role-project-assignment)
8. [Sync Modes](#sync-modes)
9. [Sync Options](#sync-options)
10. [Audit Configuration](#audit-configuration)
11. [Best Practices](#best-practices)
12. [Complete Examples](#complete-examples)

## Configuration Overview

The configuration file is structured in YAML format with the following top-level sections:

```yaml
# API Configuration
okta: {...}                          # Okta API settings
braintrust_orgs: {...}              # Braintrust organizations

# Sync Configuration  
sync_rules: {...}                    # What to sync (users/groups)
group_assignment: {...}              # How to assign users to groups
role_project_assignment: {...}       # Groups → Roles → Projects workflow

# Runtime Configuration
sync_modes: {...}                    # When to sync (schedule/realtime)
sync_options: {...}                 # How to sync (batching/retries)
audit: {...}                        # Logging and auditing

# External services removed - not implemented
```

## Core Configuration Sections

### Environment Variables

Use environment variables for sensitive values:

```yaml
okta:
  domain: "${OKTA_ORG_NAME}.okta.com"
  api_token: "${OKTA_API_TOKEN}"

braintrust_orgs:
  production:
    api_key: "${BRAINTRUST_PROD_API_KEY}"
```

**Required Environment Variables:**
- `OKTA_ORG_NAME` - Your Okta organization name
- `OKTA_API_TOKEN` - Okta API token with read permissions
- `BRAINTRUST_PROD_API_KEY` - Braintrust API key for production org
- `BRAINTRUST_DEV_API_KEY` - Braintrust API key for development org (if used)

## Okta Configuration

Configure Okta API access and rate limiting:

```yaml
okta:
  # Required: Okta domain
  domain: "yourorg.okta.com"
  # or with environment variable
  domain: "${OKTA_ORG_NAME}.okta.com"
  
  # Required: API token (use environment variable)
  api_token: "${OKTA_API_TOKEN}"
  
  # Optional: Webhook secret for real-time mode
  webhook_secret: "${OKTA_WEBHOOK_SECRET}"
  
  # Optional: Rate limiting (default: 600/minute)
  rate_limit_per_minute: 600
  
  # Optional: Request timeout (default: 30 seconds)
  timeout_seconds: 30
```

**API Token Requirements:**
- `okta.users.read` - Read user profiles and status
- `okta.groups.read` - Read group information and memberships
- `okta.logs.read` - Read event logs (for webhook mode)

## Braintrust Organizations

Configure one or more Braintrust organizations:

```yaml
braintrust_orgs:
  # Production environment
  production:
    api_key: "${BRAINTRUST_PROD_API_KEY}"
    url: "https://api.braintrust.dev"      # Default URL
    timeout_seconds: 30                     # Request timeout
    rate_limit_per_minute: 300             # API rate limit
  
  # Development environment (optional)
  development:
    api_key: "${BRAINTRUST_DEV_API_KEY}"
    url: "https://api.braintrust.dev"
    timeout_seconds: 30
    rate_limit_per_minute: 300
  
  # Custom/On-premise installation (optional)
  custom:
    api_key: "${BRAINTRUST_CUSTOM_API_KEY}"
    url: "https://braintrust.internal.com"
    timeout_seconds: 45
    rate_limit_per_minute: 200
```

## Sync Rules

Configure what users and groups to sync from Okta:

### User Sync Configuration

```yaml
sync_rules:
  users:
    enabled: true
    
    # User selection rules
    mappings:
      # Sync all active users to both orgs
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["production", "development"]
        enabled: true
      
      # Sync only employees to production
      - okta_filter: 'status eq "ACTIVE" and profile.employeeType eq "Employee"'
        braintrust_orgs: ["production"]
        enabled: true
    
    # Identity mapping strategy
    identity_mapping:
      strategy: "email"              # email, custom_field, mapping_file
      case_sensitive: false          # Email matching case sensitivity
      # custom_field: "braintrustId" # For custom_field strategy
      # mapping_file: "/path/file"   # For mapping_file strategy
    
    # Sync behavior
    create_missing: true             # Create new users in Braintrust
    update_existing: true            # Update existing user profiles
    sync_profile_fields:             # Okta fields to sync
      - "firstName"
      - "lastName"
      - "email"
      - "login"
```

### Group Sync Configuration

```yaml
sync_rules:
  groups:
    enabled: true
    
    # Group selection rules
    mappings:
      # Sync all groups with BT- prefix
      - okta_group_filter: 'type eq "OKTA_GROUP" and profile.name sw "BT-"'
        braintrust_orgs: ["production", "development"]
        name_transform: "{group.name}"  # Keep original names
        enabled: true
      
      # Sync department groups with transformation
      - okta_group_filter: 'profile.name sw "Department-"'
        braintrust_orgs: ["production"]
        name_transform: "Dept-{group.name}"  # Add prefix
        enabled: true
    
    # Sync behavior
    create_missing: true             # Create new groups in Braintrust
    update_existing: true            # Update existing group metadata
    sync_members: true               # Sync group memberships
    sync_description: true           # Sync group descriptions
```

### SCIM Filter Examples

**User Filters:**
```yaml
# All active users
okta_filter: 'status eq "ACTIVE"'

# Active employees only
okta_filter: 'status eq "ACTIVE" and profile.employeeType eq "Employee"'

# Engineering department
okta_filter: 'status eq "ACTIVE" and profile.department eq "Engineering"'

# Multiple departments
okta_filter: 'status eq "ACTIVE" and (profile.department eq "Engineering" or profile.department eq "Data")'

# Exclude contractors
okta_filter: 'status eq "ACTIVE" and profile.employeeType ne "Contractor"'
```

**Group Filters:**
```yaml
# Groups with specific prefix
okta_group_filter: 'type eq "OKTA_GROUP" and profile.name sw "BT-"'

# Groups containing specific text
okta_group_filter: 'profile.name co "Engineering"'

# Multiple patterns
okta_group_filter: 'profile.name sw "BT-" or profile.name sw "Team-"'
```

## Group Assignment Strategies

Configure how users are assigned to groups after they accept their Braintrust invitation. Three strategies are available:

### Strategy 1: Okta Groups (`okta_groups`)

Map users based on their Okta group memberships:

```yaml
group_assignment:
  global_config:
    strategy: "okta_groups"
    
    # Direct group mappings
    okta_group_mappings:
      # Exact name mapping
      - okta_group_name: "BT-Engineers"
        braintrust_group_name: "Engineering Team"
      
      # Pattern-based mapping
      - okta_group_pattern: "^BT-(.+)-Team$"
        braintrust_group_name: "\\1"  # Use captured group
    
    # Automatic name sync (when no explicit mapping)
    sync_group_names: true           # Use same names as Okta
    auto_create_groups: true         # Create missing groups
    
    # Common options
    default_groups: ["AllEmployees"] # Groups for all users
    exclude_groups: [".*-Temp$"]     # Groups to ignore
    max_groups_per_user: 10          # Limit assignments
```

### Strategy 2: Attributes (`attributes`)

Map users based on their Okta profile attributes:

```yaml
group_assignment:
  global_config:
    strategy: "attributes"
    
    attribute_mappings:
      # Engineering department
      - rule:
          conditions:
            - attribute: "department"
              operator: "equals"
              value: "Engineering"
        braintrust_group_name: "Engineers"
        priority: 50
      
      # Senior level staff
      - rule:
          conditions:
            - attribute: "level"
              operator: "in"
              value: ["Senior", "Principal", "Staff"]
        braintrust_group_name: "SeniorStaff"
        priority: 40
      
      # Complex rule: Engineering managers
      - rule:
          conditions:
            - attribute: "department"
              operator: "equals"
              value: "Engineering"
            - attribute: "title"
              operator: "contains"
              value: "Manager"
          logic: "AND"
        braintrust_group_name: "EngineeringLeaders"
        priority: 60
      
      # Regex pattern matching
      - rule:
          conditions:
            - attribute: "skills"
              operator: "regex"
              value: ".*(ML|Machine Learning|AI).*"
        braintrust_group_name: "MLSpecialists"
        priority: 30
    
    auto_create_groups: true
    max_groups_per_user: 15
```

### Strategy 3: Hybrid (`hybrid`)

Combine both Okta groups and attributes:

```yaml
group_assignment:
  global_config:
    strategy: "hybrid"
    hybrid_mode: "merge"             # merge, attributes_first, groups_first
    
    # Okta group mappings
    okta_group_mappings:
      - okta_group_name: "BT-Engineering"
        braintrust_group_name: "Engineers"
    
    # Attribute mappings
    attribute_mappings:
      - rule:
          conditions:
            - attribute: "specialization"
              operator: "equals"
              value: "Frontend"
        braintrust_group_name: "FrontendSpecialists"
        priority: 40
    
    sync_group_names: true
    auto_create_groups: true
    max_groups_per_user: 12
```

### Attribute Operators

Available operators for attribute matching:

```yaml
# Basic comparison
operator: "equals"          # Exact match
operator: "not_equals"      # Not equal
operator: "contains"        # String contains
operator: "not_contains"    # String does not contain
operator: "starts_with"     # String starts with
operator: "ends_with"       # String ends with

# List operations
operator: "in"              # Value in list
operator: "not_in"          # Value not in list

# Existence checks
operator: "exists"          # Attribute exists (non-null)
operator: "not_exists"      # Attribute does not exist (null)

# Pattern matching
operator: "regex"           # Regular expression match
```

### Priority and Logic

```yaml
# Priority determines order (higher = higher priority)
priority: 100               # Applied first
priority: 50                # Applied second
priority: 10                # Applied last

# Logic for combining conditions within a rule
logic: "AND"                # All conditions must match
logic: "OR"                 # Any condition must match
```

## Role-Project Assignment

Configure the Groups → Roles → Projects workflow:

### Standard Roles Definition

```yaml
role_project_assignment:
  global_config:
    # Define reusable roles
    standard_roles:
      # Admin role with full permissions
      - name: "AdminRole"
        description: "Full administrative access"
        member_permissions:
          - permission: "create"
            restrict_object_type: null      # All objects
          - permission: "read"
            restrict_object_type: null
          - permission: "update"
            restrict_object_type: null
          - permission: "delete"
            restrict_object_type: null
          - permission: "create_acls"
            restrict_object_type: null
          - permission: "read_acls"
            restrict_object_type: null
          - permission: "update_acls"
            restrict_object_type: null
          - permission: "delete_acls"
            restrict_object_type: null
      
      # Engineer role with CRUD but no ACL management
      - name: "EngineerRole"
        description: "Standard engineering permissions"
        member_permissions:
          - permission: "create"
            restrict_object_type: null
          - permission: "read"
            restrict_object_type: null
          - permission: "update"
            restrict_object_type: null
          - permission: "delete"
            restrict_object_type: "experiment"  # Only experiments
      
      # Data scientist role with ML focus
      - name: "DataScientistRole"
        description: "Data science and ML permissions"
        member_permissions:
          - permission: "read"
            restrict_object_type: null
          - permission: "create"
            restrict_object_type: "experiment"
          - permission: "create"
            restrict_object_type: "dataset"
          - permission: "update"
            restrict_object_type: "experiment"
          - permission: "update"
            restrict_object_type: "dataset"
          - permission: "delete"
            restrict_object_type: "experiment"
          - permission: "delete"
            restrict_object_type: "dataset"
      
      # Read-only analyst role
      - name: "AnalystRole"
        description: "Read-only access for analysis"
        member_permissions:
          - permission: "read"
            restrict_object_type: null
    
    auto_create_roles: true          # Create roles if they don't exist
    update_existing_roles: false     # Don't update existing roles
```

### Available Permissions

The 8 core Braintrust permissions:

```yaml
# CRUD Operations
permission: "create"        # Create new objects
permission: "read"          # View/read objects
permission: "update"        # Modify existing objects
permission: "delete"        # Delete objects

# ACL Management
permission: "create_acls"   # Grant permissions to others
permission: "read_acls"     # View existing permissions
permission: "update_acls"   # Modify existing permissions
permission: "delete_acls"   # Remove permissions
```

### Object Type Restrictions

Restrict permissions to specific object types:

```yaml
restrict_object_type: null            # All object types
restrict_object_type: "organization"  # Organization-level
restrict_object_type: "project"       # Projects only
restrict_object_type: "experiment"    # Experiments only
restrict_object_type: "dataset"       # Datasets only
restrict_object_type: "prompt"        # Prompts only
restrict_object_type: "group"         # Groups only
restrict_object_type: "role"          # Roles only
```

### Group-Role-Project Assignments

Map groups to roles on specific projects:

```yaml
role_project_assignment:
  global_config:
    group_assignments:
      # Engineering team gets Engineer role on development projects
      - group_name: "Engineers"
        role_name: "EngineerRole"
        project_match:
          name_contains: ["dev", "api", "service", "app"]
        enabled: true
        priority: 50
      
      # Data team gets DataScientist role on ML projects
      - group_name: "DataScientists"
        role_name: "DataScientistRole"
        project_match:
          name_pattern: "(?i).*(ml|model|analytics|data).*"
        enabled: true
        priority: 50
      
      # Admins get Admin role on all projects
      - group_name: "Administrators"
        role_name: "AdminRole"
        project_match:
          all_projects: true
        enabled: true
        priority: 100
      
      # Analysts get read-only on non-sensitive projects
      - group_name: "Analysts"
        role_name: "AnalystRole"
        project_match:
          all_projects: true
          exclude_patterns: [".*-sensitive$", ".*-confidential$"]
        enabled: true
        priority: 30
```

### Project Matching Rules

Multiple ways to specify which projects get role assignments:

```yaml
project_match:
  # Explicit lists
  project_names: ["project1", "project2"]
  project_ids: ["uuid1", "uuid2"]
  
  # Pattern matching
  name_pattern: "(?i).*(ml|ai|model).*"     # Regex pattern
  name_contains: ["api", "service"]         # Contains any of these
  name_starts_with: "dev-"                  # Starts with prefix
  name_ends_with: "-prod"                   # Ends with suffix
  
  # Tag matching (future feature)
  required_tags:
    environment: "production"
    team: "engineering"
  
  # Special selectors
  all_projects: true                        # All projects
  exclude_patterns: [".*-temp$", ".*-test$"] # Exclusion patterns
```

### Per-Organization Configuration

Override global config for specific organizations:

```yaml
role_project_assignment:
  # Global configuration (default)
  global_config: {...}
  
  # Per-org overrides
  org_configs:
    - braintrust_org: "production"
      enabled: true
      role_project_config:
        standard_roles: [...]         # Production-specific roles
        group_assignments: [...]      # Production-specific assignments
    
    - braintrust_org: "development"
      enabled: true
      role_project_config:
        standard_roles: [...]         # Dev-specific roles
        group_assignments: [...]      # Dev-specific assignments
```

## Sync Modes

Configure when and how synchronization occurs:

### Declarative Mode (Scheduled)

```yaml
sync_modes:
  declarative:
    enabled: true
    schedule: "0 */4 * * *"          # Every 4 hours (cron expression)
    full_reconciliation: "0 2 * * 0" # Weekly on Sunday at 2 AM
    max_concurrent_orgs: 3           # Process 3 orgs in parallel
```

### Real-time Mode (Webhooks) - ⚠️ **NOT YET IMPLEMENTED**

```yaml
sync_modes:
  realtime:
    enabled: false                   # ⚠️ NOT IMPLEMENTED - Keep disabled
    webhook_port: 8080               # Configuration placeholder only
    webhook_host: "0.0.0.0"          # Configuration placeholder only
    queue_backend: "memory"          # Only memory backend available
    max_queue_size: 10000            # Configuration placeholder only
    worker_count: 4                  # Configuration placeholder only
    critical_events_only: true       # Configuration placeholder only
```

> **⚠️ Important:** Real-time webhook mode is not yet implemented. Only declarative (scheduled) mode is currently functional.

### Priority Rules - ⚠️ **NOT YET IMPLEMENTED**

Configure which mode handles which events:

```yaml
sync_modes:
  priority_rules:
    # ⚠️ Priority rules not implemented - configuration placeholder only
    - event_types: ["user.lifecycle.create", "user.lifecycle.deactivate"]
      mode: "realtime"        # ⚠️ NOT IMPLEMENTED
    
    - event_types: ["group.user_membership.add", "group.user_membership.remove"]
      mode: "both"            # ⚠️ NOT IMPLEMENTED
    
    - event_types: ["*"]
      mode: "declarative"     # ✅ Only this mode works currently
```

> **⚠️ Important:** Priority rules and real-time event routing are not implemented. Only declarative mode is functional.

### Cron Expression Examples

```yaml
schedule: "0 */4 * * *"      # Every 4 hours
schedule: "0 2 * * *"        # Daily at 2 AM
schedule: "0 */2 * * *"      # Every 2 hours
schedule: "0 9,17 * * 1-5"   # 9 AM and 5 PM, weekdays only
schedule: "0 1 * * 0"        # Weekly on Sunday at 1 AM
```

## Sync Options

Configure how synchronization operations behave:

```yaml
sync_options:
  # Testing and safety
  dry_run: false                    # Set to true for testing
  
  # Performance tuning
  batch_size: 50                    # Resources per batch (1-1000)
  max_retries: 3                    # Retry attempts for failures
  retry_delay_seconds: 1.0          # Initial retry delay
  
  # Behavior options
  remove_extra: false               # Remove users/groups not in Okta
  continue_on_error: true           # Continue after individual errors
```

### Dry Run Mode

Test configuration without making changes:

```yaml
sync_options:
  dry_run: true                     # Enable dry run
```

When enabled:
- No actual changes made to Braintrust
- All operations logged as "would be performed"
- Perfect for testing new configurations
- Use for validating group assignments and role mappings

### Performance Tuning

```yaml
sync_options:
  batch_size: 25                    # Smaller for high-latency connections
  batch_size: 100                   # Larger for fast, reliable connections
  
  max_retries: 5                    # More retries for unreliable networks
  retry_delay_seconds: 2.0          # Longer delay for rate-limited APIs
```

### Error Handling

```yaml
sync_options:
  continue_on_error: true           # Continue processing after errors
  continue_on_error: false          # Stop on first error (fail-fast)
  
  remove_extra: true                # Remove users not in Okta (dangerous!)
  remove_extra: false               # Keep existing users (safer)
```

## Audit Configuration

Configure logging and auditing:

```yaml
audit:
  enabled: true                     # ✅ Enable audit logging
  log_level: "INFO"                 # ✅ DEBUG, INFO, WARNING, ERROR
  log_format: "json"                # ✅ json, text
  log_file: "/var/log/sync.log"     # ⚠️ File logging may not be fully implemented
  retention_days: 90                # ⚠️ Log retention may not be automated
  include_sensitive_data: false     # ✅ Include sensitive info (not recommended)
```

### Log Levels

```yaml
log_level: "DEBUG"      # Verbose debugging information
log_level: "INFO"       # General operational information
log_level: "WARNING"    # Warning conditions
log_level: "ERROR"      # Error conditions only
```

### Log Formats

```yaml
log_format: "json"      # Structured JSON logs (recommended)
log_format: "text"      # Human-readable text logs
```

## Best Practices

### Security

1. **Use Environment Variables for Secrets:**
   ```yaml
   okta:
     api_token: "${OKTA_API_TOKEN}"    # Never hardcode tokens
   ```

2. **Principle of Least Privilege:**
   ```yaml
   # Give minimal permissions needed
   member_permissions:
     - permission: "read"
       restrict_object_type: "experiment"  # Not all objects
   ```

3. **Regular Access Reviews:**
   ```yaml
   role_project_assignment:
     global_config:
       remove_unmanaged_acls: true        # Clean up old permissions
   ```

### Performance

1. **Batch Processing:**
   ```yaml
   sync_options:
     batch_size: 50                       # Balance speed vs. memory
   ```

2. **Appropriate Scheduling:**
   ```yaml
   sync_modes:
     declarative:
       schedule: "0 */4 * * *"            # Not too frequent
   ```

3. **Concurrent Processing:**
   ```yaml
   sync_modes:
     declarative:
       max_concurrent_orgs: 3             # Based on resources
   ```

### Reliability

1. **Error Handling:**
   ```yaml
   sync_options:
     max_retries: 3
     continue_on_error: true
   ```

2. **Health Monitoring:**
   ```yaml
   audit:
     enabled: true
     log_level: "INFO"
   ```

3. **Testing:**
   ```yaml
   sync_options:
     dry_run: true                        # Test before deploying
   ```

### Maintainability

1. **Clear Naming:**
   ```yaml
   standard_roles:
     - name: "EngineeringReadWrite"       # Descriptive names
       description: "Engineering team with read/write access to development projects"
   ```

2. **Organized Priorities:**
   ```yaml
   # Use consistent priority ranges
   priority: 100        # Admin/Leadership
   priority: 90         # Management
   priority: 50         # Department leads
   priority: 30         # Teams
   priority: 10         # Individual contributors
   ```

3. **Documentation:**
   ```yaml
   # Add comments explaining complex rules
   group_assignments:
     # Engineering team gets full access to development projects
     - group_name: "Engineers"
       role_name: "EngineerRole"
       project_match:
         name_contains: ["dev", "api", "service"]
   ```

## Complete Examples

### Minimal Startup Configuration

```yaml
# Minimal config for small teams
okta:
  domain: "${OKTA_ORG_NAME}.okta.com"
  api_token: "${OKTA_API_TOKEN}"

braintrust_orgs:
  production:
    api_key: "${BRAINTRUST_API_KEY}"

sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["production"]
        enabled: true
    identity_mapping:
      strategy: "email"
    create_missing: true
    update_existing: true

  groups:
    enabled: true
    mappings:
      - okta_group_filter: 'profile.name sw "BT-"'
        braintrust_orgs: ["production"]
        name_transform: "{group.name}"
        enabled: true
    create_missing: true
    sync_members: true

group_assignment:
  global_config:
    strategy: "okta_groups"
    sync_group_names: true
    auto_create_groups: true

role_project_assignment:
  global_config:
    standard_roles:
      - name: "TeamMember"
        description: "Basic team member access"
        member_permissions:
          - permission: "read"
          - permission: "create"
            restrict_object_type: "experiment"
          - permission: "update"
            restrict_object_type: "experiment"
    
    group_assignments:
      - group_name: "BT-Team"
        role_name: "TeamMember"
        project_match:
          all_projects: true
        enabled: true

sync_modes:
  declarative:
    enabled: true
    schedule: "0 */6 * * *"  # Every 6 hours

audit:
  enabled: true
  log_level: "INFO"
```

### Enterprise Configuration

```yaml
# Full enterprise config with multiple orgs and complex rules
okta:
  domain: "${OKTA_ORG_NAME}.okta.com"
  api_token: "${OKTA_API_TOKEN}"
  webhook_secret: "${OKTA_WEBHOOK_SECRET}"
  rate_limit_per_minute: 600
  timeout_seconds: 30

braintrust_orgs:
  production:
    api_key: "${BRAINTRUST_PROD_API_KEY}"
    rate_limit_per_minute: 300
  
  development:
    api_key: "${BRAINTRUST_DEV_API_KEY}"
    rate_limit_per_minute: 500
  
  sandbox:
    api_key: "${BRAINTRUST_SANDBOX_API_KEY}"
    rate_limit_per_minute: 100

sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE" and profile.employeeType ne "Contractor"'
        braintrust_orgs: ["production", "development"]
        enabled: true
      
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["sandbox"]
        enabled: true
    
    identity_mapping:
      strategy: "email"
      case_sensitive: false
    
    create_missing: true
    update_existing: true
    sync_profile_fields: ["firstName", "lastName", "email", "login", "department", "title"]

  groups:
    enabled: true
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP" and profile.name sw "BT-"'
        braintrust_orgs: ["production", "development", "sandbox"]
        name_transform: "{group.name}"
        enabled: true
    
    create_missing: true
    update_existing: true
    sync_members: true
    sync_description: true

group_assignment:
  global_config:
    strategy: "hybrid"
    hybrid_mode: "merge"
    
    okta_group_mappings:
      - okta_group_name: "BT-Engineering"
        braintrust_group_name: "Engineers"
      - okta_group_name: "BT-DataScience"
        braintrust_group_name: "DataScientists"
      - okta_group_name: "BT-Leadership"
        braintrust_group_name: "Leadership"
    
    attribute_mappings:
      - rule:
          conditions:
            - attribute: "department"
              operator: "equals"
              value: "Engineering"
            - attribute: "title"
              operator: "contains"
              value: "Senior"
          logic: "AND"
        braintrust_group_name: "SeniorEngineers"
        priority: 80
      
      - rule:
          conditions:
            - attribute: "title"
              operator: "regex"
              value: "(?i).*(manager|director|vp).*"
        braintrust_group_name: "Management"
        priority: 90
    
    auto_create_groups: true
    max_groups_per_user: 10

role_project_assignment:
  global_config:
    standard_roles:
      - name: "AdminRole"
        description: "Full administrative access"
        member_permissions:
          - permission: "create"
          - permission: "read"
          - permission: "update"
          - permission: "delete"
          - permission: "create_acls"
          - permission: "read_acls"
          - permission: "update_acls"
      
      - name: "EngineerRole"
        description: "Engineering team permissions"
        member_permissions:
          - permission: "create"
          - permission: "read"
          - permission: "update"
          - permission: "delete"
            restrict_object_type: "experiment"
      
      - name: "DataScientistRole"
        description: "Data science permissions"
        member_permissions:
          - permission: "read"
          - permission: "create"
            restrict_object_type: "experiment"
          - permission: "create"
            restrict_object_type: "dataset"
          - permission: "update"
            restrict_object_type: "experiment"
          - permission: "update"
            restrict_object_type: "dataset"
      
      - name: "ManagerRole"
        description: "Management oversight permissions"
        member_permissions:
          - permission: "read"
          - permission: "create_acls"
            restrict_object_type: "project"
          - permission: "read_acls"
          - permission: "update_acls"
            restrict_object_type: "project"
    
    auto_create_roles: true
    update_existing_roles: false
    
    group_assignments:
      # Leadership gets admin access to all projects
      - group_name: "Leadership"
        role_name: "AdminRole"
        project_match:
          all_projects: true
        enabled: true
        priority: 100
      
      # Engineering team gets engineer role on dev projects
      - group_name: "Engineers"
        role_name: "EngineerRole"
        project_match:
          name_contains: ["dev", "api", "service", "app"]
        enabled: true
        priority: 50
      
      # Data team gets data scientist role on ML projects
      - group_name: "DataScientists"
        role_name: "DataScientistRole"
        project_match:
          name_pattern: "(?i).*(ml|model|analytics|data).*"
        enabled: true
        priority: 50
      
      # Managers get oversight on their team's projects
      - group_name: "Management"
        role_name: "ManagerRole"
        project_match:
          all_projects: true
          exclude_patterns: [".*-restricted$"]
        enabled: true
        priority: 80
    
    remove_unmanaged_acls: false

sync_modes:
  declarative:
    enabled: true
    schedule: "0 */2 * * *"           # Every 2 hours
    full_reconciliation: "0 3 * * 0" # Weekly on Sunday at 3 AM
    max_concurrent_orgs: 2
  
  realtime:
    enabled: false                    # Not implemented - keep disabled
    webhook_port: 8080
    queue_backend: "memory"           # Only memory backend available
    max_queue_size: 10000
    worker_count: 4
    critical_events_only: true
  
  priority_rules:
    - event_types: ["user.lifecycle.deactivate", "user.lifecycle.suspend"]
      mode: "realtime"
    - event_types: ["group.user_membership.add", "group.user_membership.remove"]
      mode: "both"

sync_options:
  dry_run: false
  batch_size: 50
  max_retries: 3
  retry_delay_seconds: 1.0
  remove_extra: false
  continue_on_error: true

audit:
  enabled: true
  log_level: "INFO"
  log_format: "json"
  retention_days: 90
  include_sensitive_data: false

# External services (redis_url, database_url) removed - not implemented
```

This configuration guide provides complete coverage of all available options and should serve as a comprehensive reference for configuring the okta-braintrust-sync system for any organization size or complexity.