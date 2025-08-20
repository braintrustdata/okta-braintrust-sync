"""Client factory for creating API clients from configuration."""

from typing import Dict
from pydantic import SecretStr

from sync.config.models import SyncConfig, OktaConfig, BraintrustOrgConfig
from sync.clients.okta import OktaClient
from sync.clients.braintrust import BraintrustClient
from sync.security.validation import sanitize_log_input

import structlog

logger = structlog.get_logger(__name__)


class ClientFactory:
    """Factory for creating API clients from configuration."""
    
    @staticmethod
    def create_okta_client(config: OktaConfig) -> OktaClient:
        """Create Okta client from configuration.
        
        Args:
            config: Okta configuration
            
        Returns:
            Configured Okta client
            
        Raises:
            ValueError: If configuration is invalid
        """
        try:
            return OktaClient(
                domain=config.domain,
                api_token=config.api_token,
                timeout_seconds=config.timeout_seconds,
                rate_limit_per_minute=config.rate_limit_per_minute,
                max_retries=config.max_retries,
                retry_delay_seconds=config.retry_delay_seconds,
            )
        except Exception as e:
            logger.error(
                "Failed to create Okta client",
                domain=sanitize_log_input(config.domain),
                error=sanitize_log_input(str(e))
            )
            raise ValueError(f"Failed to create Okta client: {e}") from e
    
    @staticmethod
    def create_braintrust_client(
        org_name: str, 
        config: BraintrustOrgConfig
    ) -> BraintrustClient:
        """Create Braintrust client from configuration.
        
        Args:
            org_name: Organization name
            config: Braintrust organization configuration
            
        Returns:
            Configured Braintrust client
            
        Raises:
            ValueError: If configuration is invalid
        """
        try:
            return BraintrustClient(
                api_key=config.api_key,
                api_url=config.api_url,
                timeout_seconds=config.timeout_seconds,
                rate_limit_per_minute=config.rate_limit_per_minute,
                max_retries=config.max_retries,
                retry_delay_seconds=config.retry_delay_seconds,
            )
        except Exception as e:
            logger.error(
                "Failed to create Braintrust client",
                org_name=sanitize_log_input(org_name),
                api_url=sanitize_log_input(config.api_url),
                error=sanitize_log_input(str(e))
            )
            raise ValueError(f"Failed to create Braintrust client for {org_name}: {e}") from e
    
    @staticmethod
    def create_braintrust_clients(
        config: SyncConfig
    ) -> Dict[str, BraintrustClient]:
        """Create all Braintrust clients from configuration.
        
        Args:
            config: Full sync configuration
            
        Returns:
            Dictionary of organization name to Braintrust client
            
        Raises:
            ValueError: If any client creation fails
        """
        clients = {}
        failed_orgs = []
        
        for org_name, org_config in config.braintrust_orgs.items():
            try:
                client = ClientFactory.create_braintrust_client(org_name, org_config)
                # Set the organization name on the client for convenience
                client.org_name = org_name
                clients[org_name] = client
                
                logger.info(
                    "Created Braintrust client",
                    org_name=sanitize_log_input(org_name),
                    api_url=sanitize_log_input(org_config.api_url)
                )
                
            except Exception as e:
                failed_orgs.append((org_name, str(e)))
                logger.error(
                    "Failed to create Braintrust client",
                    org_name=sanitize_log_input(org_name),
                    error=sanitize_log_input(str(e))
                )
        
        if failed_orgs:
            error_details = "; ".join([f"{org}: {error}" for org, error in failed_orgs])
            raise ValueError(f"Failed to create clients for organizations: {error_details}")
        
        return clients
    
    @staticmethod
    def validate_clients(
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient]
    ) -> Dict[str, bool]:
        """Validate that all clients can connect to their APIs.
        
        Args:
            okta_client: Okta client to validate
            braintrust_clients: Braintrust clients to validate
            
        Returns:
            Dictionary of client name to health status
        """
        import asyncio
        
        async def check_health():
            results = {}
            
            # Check Okta client
            try:
                okta_healthy = await okta_client.health_check()
                results["okta"] = okta_healthy
                logger.info(
                    "Okta health check",
                    healthy=okta_healthy,
                    domain=sanitize_log_input(okta_client.domain)
                )
            except Exception as e:
                results["okta"] = False
                logger.error(
                    "Okta health check failed",
                    error=sanitize_log_input(str(e)),
                    domain=sanitize_log_input(okta_client.domain)
                )
            
            # Check Braintrust clients
            for org_name, client in braintrust_clients.items():
                try:
                    bt_healthy = await client.health_check()
                    results[f"braintrust_{org_name}"] = bt_healthy
                    logger.info(
                        "Braintrust health check",
                        org_name=sanitize_log_input(org_name),
                        healthy=bt_healthy,
                        api_url=sanitize_log_input(client.api_url)
                    )
                except Exception as e:
                    results[f"braintrust_{org_name}"] = False
                    logger.error(
                        "Braintrust health check failed",
                        org_name=sanitize_log_input(org_name),
                        error=sanitize_log_input(str(e)),
                        api_url=sanitize_log_input(client.api_url)
                    )
            
            return results
        
        return asyncio.run(check_health())


class ComponentFactory:
    """Factory for creating various sync components."""
    
    @staticmethod
    def create_state_manager(config: SyncConfig) -> "StateManager":
        """Create state manager from configuration.
        
        Args:
            config: Sync configuration
            
        Returns:
            Configured state manager
        """
        from sync.core.enhanced_state import StateManager
        
        state_dir = config.state_management.state_directory
        return StateManager(state_dir=state_dir)
    
    @staticmethod
    def create_audit_logger(config: SyncConfig) -> "AuditLogger":
        """Create audit logger from configuration.
        
        Args:
            config: Sync configuration
            
        Returns:
            Configured audit logger
        """
        from sync.audit.logger import AuditLogger
        
        return AuditLogger(
            enabled=config.audit.enabled,
            log_level=config.audit.log_level,
            log_format=config.audit.log_format,
            log_file=config.audit.log_file,
            retention_days=config.audit.retention_days,
            include_sensitive_data=config.audit.include_sensitive_data,
        )
    
    @staticmethod
    def create_sync_planner(
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: "StateManager",
        config: SyncConfig
    ) -> "SyncPlanner":
        """Create sync planner from configuration.
        
        Args:
            okta_client: Okta client
            braintrust_clients: Braintrust clients
            state_manager: State manager
            config: Sync configuration
            
        Returns:
            Configured sync planner
        """
        from sync.core.planner import SyncPlanner
        
        return SyncPlanner(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=state_manager,
            sync_config=config,
        )
    
    @staticmethod
    def create_sync_executor(
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: "StateManager",
        audit_logger: "AuditLogger",
        config: SyncConfig
    ) -> "SyncExecutor":
        """Create sync executor from configuration.
        
        Args:
            okta_client: Okta client
            braintrust_clients: Braintrust clients
            state_manager: State manager
            audit_logger: Audit logger
            config: Sync configuration
            
        Returns:
            Configured sync executor
        """
        from sync.core.executor import SyncExecutor
        
        return SyncExecutor(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=state_manager,
            audit_logger=audit_logger,
        )