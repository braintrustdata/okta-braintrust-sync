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

### Syncing Workflow
1. Cache resources from Okta and Braintrust to reduce network calls
2. Check if resources (users, groups, roles, ACLs) already exist in the state and match what is retrieved from Okta based on the yaml config
3. Create resources that don't exist in state but defined in the yaml, delete resources that are defined to be deleted by the yaml config.
4. Plan overview that the user will say y/n before executing. 