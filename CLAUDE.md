# Project Preferences

## Code Style Guidelines

### Comments
- Add clear, explanatory comments to all code blocks
- Use block comments above classes and major functions to explain their purpose
- Add inline comments for complex logic or non-obvious code
- Group related configuration options with section headers using comment separators like:
  ```python
  # ========== Section Name ==========
  ```
- Include usage examples in docstrings where helpful

### Documentation Style
- Explain what each block of code does, not just what it is
- For configuration classes, explain when and how different options are used
- For enums and constants, explain the meaning and use case of each value
- Add examples in comments or docstrings to illustrate complex configurations

## Project-Specific Information

### Syncing Architecture
- The system supports both Okta groups and user attributes for syncing
- Group assignments can be based on:
  1. Direct Okta group memberships
  2. User profile attributes (department, title, location, etc.)
  3. Hybrid approach combining both

### Role-Project Workflow (Groups → Roles → Projects)
- Enables granular and reusable ACLs through a three-tier system:
  1. **Groups**: Collections of users (synced from Okta)
  2. **Roles**: Named permission sets (create, read, update, delete, ACL management)
  3. **Projects**: Specific Braintrust projects where roles are applied
- Workflow: Users → Groups → Roles → Projects via ACLs
- Benefits: Role changes automatically apply to all assigned groups/projects
- Supports pattern-based project matching (regex, contains, starts/ends with)
- Per-organization configuration with global defaults

### Dev Requirements
1. Make sure that changes made to the planning phase first as the planning phase determines what happens in the apply phase.

### Syncing Workflow - Stateless Architecture
**Target Architecture (In Progress):**
1. Cache resources from Okta and Braintrust to reduce network calls
2. Compare Okta resources directly against current Braintrust state (no state file dependency)
3. Generate plans based on actual reality, not tracked state
4. Use explicit deletion policies configured in YAML instead of state tracking
5. Plan overview that the user will say y/n before executing

**Key Design Principles:**
- **Stateless**: Always compare against current Braintrust reality, not persistent state
- **Explicit Deletion**: Users must explicitly configure what gets deleted in YAML
- **Self-Healing**: Automatically handles manual changes made outside the sync tool
- **Conservative**: Default to no deletion unless explicitly enabled

**Example Explicit Deletion Configuration:**
```yaml
deletion_policies:
  users:
    enabled: true
    okta_conditions:
      - status: "DEPROVISIONED"
      - status: "SUSPENDED"
    braintrust_conditions:
      - inactive_days: 30
  
  groups:
    enabled: false  # Conservative default - never auto-delete
  
  acls:
    enabled: true
    scope: "sync_managed_roles"  # Only ACLs using roles defined in config
```

**Benefits of Stateless Approach:**
- No state inconsistencies between tracked state and actual Braintrust state
- Simpler architecture without complex state management
- More reliable since it always reflects current reality
- Easier debugging and troubleshooting
- Self-healing when resources are modified externally

# Issue Resolution: ACL Planning and Role-Group Dependencies

## Problem Statement
User reported that ACL assignments were not being planned correctly - only 1 ACL was being created when many more were expected based on the configuration.

## Root Cause Analysis

### Issue #1: Group Name Mismatches in Configuration
**Problem**: ACL assignments in `terraform/examples/01-basic-teams/sync-config.yaml` referenced incorrect group names:
- Used `"DataScience"` instead of `"BT-DataScience"`
- Used `"ProductManagement"` instead of `"BT-ProductManagement"`  
- Used `"AllEmployees"` instead of `"BT-AllEmployees"`

**Root Cause**: The config had commented-out group mappings, so Okta groups were synced with their original names (e.g., "BT-DataScience"), but ACL assignments referenced different names.

### Issue #2: ACL Planner Only Checked Existing Resources
**Problem**: The ACL planner in `sync/core/planner.py:_generate_acl_plan()` only checked for existing groups and roles using cache lookups, ignoring resources planned to be created in the same sync.

**Root Cause**: 
```python
group = await client.find_group_by_name_cached(assignment.group_name)
role = await client.get_role_by_name_cached(assignment.role_name)

if not group or not role:
    # This skipped ACL planning even if group/role would be created in this sync
    self._logger.warning("Skipping ACL planning - group or role not found")
    continue
```

### Issue #3: Role Planning Showed 0 Items
**Problem**: No roles were being planned for creation despite having `auto_create_roles: true`.

**Root Cause**: Roles already existed in both Braintrust organizations (7 roles cached), and `update_existing_roles: false` was set, so no role operations were planned.

## Solution Implemented

### Fix #1: Corrected Group Names in Configuration ✅
Updated `terraform/examples/01-basic-teams/sync-config.yaml`:
```yaml
# Before:
- group_name: "DataScience"          # ❌ Wrong
- group_name: "ProductManagement"    # ❌ Wrong  
- group_name: "AllEmployees"         # ❌ Wrong

# After:
- group_name: "BT-DataScience"       # ✅ Correct
- group_name: "BT-ProductManagement" # ✅ Correct
- group_name: "BT-AllEmployees"      # ✅ Correct
```

### Fix #2: Enhanced ACL Planner to Check Planned Resources ✅
Modified `sync/core/planner.py`:

1. **Updated method signature** to pass current plan state:
   ```python
   async def _generate_acl_plan(self, target_organizations: List[str], current_plan: 'SyncPlan')
   ```

2. **Added helper methods** to find resources in current plan:
   ```python
   def _find_group_in_plan(self, plan: 'SyncPlan', group_name: str, org_name: str) -> Optional[Dict[str, Any]]
   def _find_role_in_plan(self, plan: 'SyncPlan', role_name: str, org_name: str) -> Optional[Dict[str, Any]]
   ```

3. **Enhanced group/role lookup logic**:
   ```python
   # Check for existing group first
   group = await client.find_group_by_name_cached(assignment.group_name)
   
   # If group doesn't exist, check if it will be created in this sync
   if not group:
       group = self._find_group_in_plan(current_plan, assignment.group_name, org_name)
   ```

4. **Improved dependency tracking** for planned resources:
   ```python
   dependencies = []
   if group_is_planned:
       dependencies.append(f"group-{assignment.group_name}-{org_name}")
   if role_is_planned:
       dependencies.append(f"role-{assignment.role_name}-{org_name}")
   ```

## Technical Details

### ACL Planning Flow (After Fix)
1. **Generate user plan** → Users that need to be created/updated
2. **Generate group plan** → Groups that need to be created/updated  
3. **Generate role plan** → Roles that need to be created/updated (currently 0 since roles exist)
4. **Generate ACL plan** → Now checks both:
   - Existing groups/roles in Braintrust cache
   - Groups/roles planned for creation in current sync
5. **Resolve dependencies** → ACLs depend on group/role creation

### Dependency Resolution
ACL items now correctly depend on planned resources:
- If group exists in Braintrust: No dependency
- If group will be created: Depends on `group-{name}-{org}`
- If role exists in Braintrust: No dependency  
- If role will be created: Depends on `role-{name}-{org}`

## Expected Outcome
After these fixes, the sync plan should show many more ACL assignments instead of just 1, covering all the configured group-role-project combinations across both organizations.

## Implementation Results
✅ **SUCCESSFUL FIX CONFIRMED**

**Before Fix:**
- ACL Count: 1 total
- Groups not found in plan during ACL planning

**After Fix:**
- ACL Count: 53 total (52 for carlos org, 1 for carlos-aws-hybrid org)
- All configured group-role-project assignments working correctly:
  - BT-Managers → Manager role: 35 projects (all projects)
  - BT-Engineering → Engineer role: 4 projects (infrastructure, mobile, api, web)
  - BT-DataScience → DataScientist role: 3 projects (research, metadata projects)
  - BT-ProductManagement → ProductManager role: 1 project (product-user-dashboard)
  - BT-AllEmployees → Employee role: 9 projects (shared, demo projects)

**Universal Solution:**
- The fix works for any organization names and group names configured in YAML
- Robust group name extraction handles multiple data structure formats:
  - Dict format: `name`, `displayName`, `profile.name`, `profile.displayName`
  - Object format: `.name`, `.displayName`, `.profile.name`, `.profile.displayName`
- Proper dependency tracking ensures ACLs are created after their dependent groups/roles 