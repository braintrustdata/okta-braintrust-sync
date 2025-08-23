"""API client configuration models."""

from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator


class OktaConfig(BaseModel):
    """Okta API configuration."""
    
    domain: str = Field(
        ..., 
        description="Okta domain (e.g., 'yourorg.okta.com')",
        min_length=1
    )
    api_token: SecretStr = Field(
        ...,
        description="Okta API token with appropriate permissions"
    )
    webhook_secret: SecretStr | None = Field(
        None,
        description="Secret for webhook signature verification"
    )
    rate_limit_per_minute: int = Field(
        600,
        description="Rate limit for Okta API calls per minute",
        ge=1
    )
    timeout_seconds: int = Field(
        30,
        description="Timeout for Okta API calls in seconds",
        ge=1
    )
    max_retries: int = Field(
        3,
        description="Maximum number of retry attempts",
        ge=0
    )
    retry_delay_seconds: float = Field(
        1.0,
        description="Initial delay between retries in seconds",
        ge=0.1
    )
    
    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate Okta domain format."""
        # Remove protocol if present
        v = v.replace("https://", "").replace("http://", "")
        # Remove trailing slash
        v = v.rstrip("/")
        
        if not v.endswith(".okta.com") and not v.endswith(".oktapreview.com"):
            raise ValueError("Domain must be a valid Okta domain (.okta.com or .oktapreview.com)")
        
        return v


class BraintrustOrgConfig(BaseModel):
    """Individual Braintrust organization configuration."""
    
    api_key: SecretStr = Field(
        ...,
        description="Braintrust API key for this organization"
    )
    api_url: HttpUrl = Field(
        HttpUrl("https://api.braintrust.dev"),
        description="Braintrust API URL"
    )
    # Backward compatibility alias
    url: HttpUrl = Field(
        HttpUrl("https://api.braintrust.dev"),
        description="Braintrust API URL (alias for api_url)"
    )
    timeout_seconds: int = Field(
        30,
        description="Timeout for Braintrust API calls in seconds",
        ge=1
    )
    rate_limit_per_minute: int = Field(
        300,
        description="Rate limit for Braintrust API calls per minute",
        ge=1
    )
    max_retries: int = Field(
        3,
        description="Maximum number of retry attempts",
        ge=0
    )
    retry_delay_seconds: float = Field(
        1.0,
        description="Initial delay between retries in seconds",
        ge=0.1
    )