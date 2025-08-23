"""Configuration models for flexible group assignment based on Okta groups or attributes."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class MappingStrategy(str, Enum):
    """Strategy for mapping users to groups.
    
    OKTA_GROUPS: Direct 1:1 or pattern-based mapping from Okta groups to Braintrust groups
    ATTRIBUTES: Map users to groups based on their Okta profile attributes (department, title, etc.)
    HYBRID: Use both Okta groups AND attributes to determine group assignments
    """
    OKTA_GROUPS = "okta_groups"  # Direct mapping from Okta groups
    ATTRIBUTES = "attributes"      # Mapping based on user attributes
    HYBRID = "hybrid"              # Combination of both strategies


class MatchOperator(str, Enum):
    """Operators for attribute matching.
    
    These operators allow flexible matching of user attributes to determine
    group assignments. For example, you can check if a user's department
    equals "Engineering" or if their title contains "Manager".
    """
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class AttributeCondition(BaseModel):
    """Single attribute condition for matching.
    
    This defines a single condition to check against a user's Okta profile.
    Multiple conditions can be combined using AttributeRule.
    
    Example:
        Check if user's department equals "Engineering":
        {
            "attribute": "department",
            "operator": "equals",
            "value": "Engineering"
        }
    """
    
    attribute: str = Field(
        ...,
        description="Okta user profile attribute name (e.g., 'department', 'title', 'location')"
    )
    operator: MatchOperator = Field(
        MatchOperator.EQUALS,
        description="Comparison operator"
    )
    value: Optional[Union[str, List[str]]] = Field(
        None,
        description="Value(s) to match against (not needed for EXISTS/NOT_EXISTS)"
    )
    case_sensitive: bool = Field(
        False,
        description="Whether the comparison should be case sensitive"
    )
    
    @model_validator(mode='after')
    def validate_value_requirement(self) -> 'AttributeCondition':
        """Validate that value is provided when needed."""
        if self.operator not in [MatchOperator.EXISTS, MatchOperator.NOT_EXISTS]:
            if self.value is None:
                raise ValueError(f"value is required for operator {self.operator}")
        
        if self.operator in [MatchOperator.IN, MatchOperator.NOT_IN]:
            if not isinstance(self.value, list):
                raise ValueError(f"value must be a list for operator {self.operator}")
        
        return self


class AttributeRule(BaseModel):
    """Rule for matching based on attributes with multiple conditions.
    
    Combines multiple AttributeConditions using AND/OR logic to create
    complex matching rules.
    
    Example:
        Match users who are in Engineering AND have Manager in their title:
        {
            "conditions": [
                {"attribute": "department", "operator": "equals", "value": "Engineering"},
                {"attribute": "title", "operator": "contains", "value": "Manager"}
            ],
            "logic": "AND"
        }
    """
    
    conditions: List[AttributeCondition] = Field(
        ...,
        description="List of conditions to match",
        min_length=1
    )
    logic: Literal["AND", "OR"] = Field(
        "AND",
        description="Logic operator for combining conditions"
    )
    
    def matches(self, user_profile: Dict[str, Any]) -> bool:
        """Check if user profile matches this rule."""
        results = []
        
        for condition in self.conditions:
            attr_value = user_profile.get(condition.attribute)
            result = self._evaluate_condition(condition, attr_value)
            results.append(result)
        
        if self.logic == "AND":
            return all(results)
        else:  # OR
            return any(results)
    
    def _evaluate_condition(self, condition: AttributeCondition, attr_value: Any) -> bool:
        """Evaluate a single condition against an attribute value."""
        # Handle EXISTS/NOT_EXISTS
        if condition.operator == MatchOperator.EXISTS:
            return attr_value is not None
        elif condition.operator == MatchOperator.NOT_EXISTS:
            return attr_value is None
        
        # For other operators, None values don't match
        if attr_value is None:
            return False
        
        # Convert to string for comparison
        attr_str = str(attr_value)
        if not condition.case_sensitive:
            attr_str = attr_str.lower()
        
        # Get comparison value(s)
        if isinstance(condition.value, list):
            compare_values = [str(v).lower() if not condition.case_sensitive else str(v) 
                            for v in condition.value]
        else:
            compare_value = str(condition.value)
            if not condition.case_sensitive:
                compare_value = compare_value.lower()
        
        # Evaluate based on operator
        if condition.operator == MatchOperator.EQUALS:
            return attr_str == compare_value
        elif condition.operator == MatchOperator.NOT_EQUALS:
            return attr_str != compare_value
        elif condition.operator == MatchOperator.CONTAINS:
            return compare_value in attr_str
        elif condition.operator == MatchOperator.NOT_CONTAINS:
            return compare_value not in attr_str
        elif condition.operator == MatchOperator.STARTS_WITH:
            return attr_str.startswith(compare_value)
        elif condition.operator == MatchOperator.ENDS_WITH:
            return attr_str.endswith(compare_value)
        elif condition.operator == MatchOperator.IN:
            return attr_str in compare_values
        elif condition.operator == MatchOperator.NOT_IN:
            return attr_str not in compare_values
        elif condition.operator == MatchOperator.REGEX:
            import re
            try:
                pattern = re.compile(condition.value, re.IGNORECASE if not condition.case_sensitive else 0)
                return bool(pattern.match(attr_str))
            except re.error:
                return False
        
        return False


class OktaGroupMapping(BaseModel):
    """Mapping from Okta group to Braintrust group.
    
    Defines how Okta groups should be mapped to Braintrust groups.
    Can use exact names or regex patterns for flexible matching.
    
    Example:
        Map all Okta groups starting with "eng-" to "Engineering Team":
        {
            "okta_group_pattern": "^eng-.*",
            "braintrust_group_name": "Engineering Team"
        }
    """
    
    okta_group_name: Optional[str] = Field(
        None,
        description="Exact Okta group name to match"
    )
    okta_group_pattern: Optional[str] = Field(
        None,
        description="Regex pattern to match Okta group names"
    )
    braintrust_group_name: str = Field(
        ...,
        description="Target Braintrust group name"
    )
    
    @model_validator(mode='after')
    def validate_group_identifier(self) -> 'OktaGroupMapping':
        """Ensure either name or pattern is provided."""
        if not self.okta_group_name and not self.okta_group_pattern:
            raise ValueError("Either okta_group_name or okta_group_pattern must be provided")
        if self.okta_group_name and self.okta_group_pattern:
            raise ValueError("Only one of okta_group_name or okta_group_pattern should be provided")
        return self


class AttributeGroupMapping(BaseModel):
    """Mapping from user attributes to Braintrust group.
    
    Maps users to Braintrust groups based on their Okta profile attributes.
    Priority determines which mappings are applied first when multiple match.
    
    Example:
        Add all Engineering managers to "Engineering Leaders" group:
        {
            "rule": {
                "conditions": [
                    {"attribute": "department", "operator": "equals", "value": "Engineering"},
                    {"attribute": "title", "operator": "contains", "value": "Manager"}
                ],
                "logic": "AND"
            },
            "braintrust_group_name": "Engineering Leaders",
            "priority": 10
        }
    """
    
    rule: AttributeRule = Field(
        ...,
        description="Attribute matching rule"
    )
    braintrust_group_name: str = Field(
        ...,
        description="Target Braintrust group name"
    )
    priority: int = Field(
        0,
        description="Priority for this mapping (higher = higher priority)"
    )


class GroupAssignmentConfig(BaseModel):
    """Configuration for group assignment after user acceptance.
    
    This is the main configuration that determines how users are assigned
    to groups when they accept their Braintrust invitation.
    
    Three strategies are supported:
    1. OKTA_GROUPS: Map based on user's Okta group memberships
    2. ATTRIBUTES: Map based on user's Okta profile attributes
    3. HYBRID: Combine both approaches
    """
    
    strategy: MappingStrategy = Field(
        MappingStrategy.OKTA_GROUPS,
        description="Strategy for determining group assignments"
    )
    
    # ========== OKTA_GROUPS Strategy Configuration ==========
    # Used when strategy = "okta_groups"
    okta_group_mappings: Optional[List[OktaGroupMapping]] = Field(
        None,
        description="Mappings from Okta groups to Braintrust groups"
    )
    auto_create_groups: bool = Field(
        False,
        description="Automatically create Braintrust groups if they don't exist"
    )
    sync_group_names: bool = Field(
        True,
        description="Use same group names in Braintrust as in Okta (when no explicit mapping)"
    )
    
    # ========== ATTRIBUTES Strategy Configuration ==========
    # Used when strategy = "attributes"
    attribute_mappings: Optional[List[AttributeGroupMapping]] = Field(
        None,
        description="Mappings from user attributes to Braintrust groups"
    )
    
    # ========== HYBRID Strategy Configuration ==========
    # Used when strategy = "hybrid"
    hybrid_mode: Literal["merge", "attributes_first", "groups_first"] = Field(
        "merge",
        description="How to combine results in hybrid mode"
    )
    # - "merge": Combine groups from both strategies
    # - "attributes_first": Use attribute mappings, fall back to group mappings
    # - "groups_first": Use group mappings, fall back to attribute mappings
    
    # ========== Common Options (Apply to All Strategies) ==========
    default_groups: Optional[List[str]] = Field(
        None,
        description="Default Braintrust groups to assign to all users"
    )
    exclude_groups: Optional[List[str]] = Field(
        None,
        description="Okta groups to exclude from sync (regex patterns supported)"
    )
    max_groups_per_user: Optional[int] = Field(
        None,
        description="Maximum number of groups a user can be assigned to",
        ge=1
    )
    
    @model_validator(mode='after')
    def validate_strategy_config(self) -> 'GroupAssignmentConfig':
        """Validate that required fields are present for the chosen strategy."""
        if self.strategy == MappingStrategy.OKTA_GROUPS:
            if not self.okta_group_mappings and not self.sync_group_names:
                raise ValueError(
                    "For OKTA_GROUPS strategy, either okta_group_mappings must be defined "
                    "or sync_group_names must be True"
                )
        
        elif self.strategy == MappingStrategy.ATTRIBUTES:
            if not self.attribute_mappings:
                raise ValueError("attribute_mappings is required for ATTRIBUTES strategy")
        
        elif self.strategy == MappingStrategy.HYBRID:
            if not self.okta_group_mappings and not self.attribute_mappings and not self.sync_group_names:
                raise ValueError(
                    "For HYBRID strategy, at least one of okta_group_mappings, "
                    "attribute_mappings, or sync_group_names must be configured"
                )
        
        return self


class BraintrustOrgGroupAssignment(BaseModel):
    """Group assignment configuration for a specific Braintrust organization.
    
    Allows per-organization customization of group assignment rules.
    Useful when different Braintrust orgs have different group structures
    or assignment requirements.
    """
    
    braintrust_org: str = Field(
        ...,
        description="Braintrust organization name"
    )
    group_assignment: GroupAssignmentConfig = Field(
        ...,
        description="Group assignment configuration for this org"
    )
    enabled: bool = Field(
        True,
        description="Whether group assignment is enabled for this org"
    )


class GroupAssignmentRules(BaseModel):
    """Complete group assignment rules for all organizations.
    
    Top-level configuration that can define:
    - A global configuration that applies to all orgs
    - Per-org configurations that override the global config
    
    The system will check for org-specific config first, then fall back
    to the global config if no org-specific config exists.
    """
    
    global_config: Optional[GroupAssignmentConfig] = Field(
        None,
        description="Global group assignment config (can be overridden per org)"
    )
    org_configs: Optional[List[BraintrustOrgGroupAssignment]] = Field(
        None,
        description="Per-organization group assignment configurations"
    )
    
    @model_validator(mode='after')
    def validate_at_least_one_config(self) -> 'GroupAssignmentRules':
        """Ensure at least one configuration is provided."""
        if not self.global_config and not self.org_configs:
            raise ValueError("Either global_config or org_configs must be provided")
        return self
    
    def get_config_for_org(self, org_name: str) -> Optional[GroupAssignmentConfig]:
        """Get the group assignment config for a specific org.
        
        Returns org-specific config if available, otherwise returns global config.
        """
        # Check for org-specific config first
        if self.org_configs:
            for org_config in self.org_configs:
                if org_config.braintrust_org == org_name and org_config.enabled:
                    return org_config.group_assignment
        
        # Fall back to global config
        return self.global_config