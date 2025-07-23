# Okta-Braintrust Sync

> **🚀 Hybrid SCIM-like Identity Synchronization**  
> Sync users and groups from Okta to multiple Braintrust organizations with both declarative batch sync and real-time webhook support.

## Overview

This tool provides **hybrid synchronization** between Okta and Braintrust organizations, replicating SCIM functionality that's not natively available. It supports both **declarative batch operations** (Terraform-like) and **real-time event processing** via Okta webhooks.

### Key Features

- **🔄 Hybrid Sync Modes**: Choose between declarative batch sync, real-time webhooks, or both
- **🏢 Multi-Organization**: Sync to multiple Braintrust organizations simultaneously  
- **📋 Declarative Configuration**: Terraform-like YAML configuration with plan/apply workflow
- **⚡ Real-time Updates**: Immediate sync via Okta Event Hooks for security-critical changes
- **🔍 Comprehensive Auditing**: Detailed logs and reports for compliance and troubleshooting
- **🔧 Flexible Mapping**: Multiple identity mapping strategies (email, custom fields, manual)
- **🛡️ Production Ready**: Retry logic, error recovery, state management, and monitoring

### Architecture

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│    Okta     │────│  Sync Engine     │────│   Braintrust    │
│   (Source)  │    │                  │    │ (Destinations)  │
│             │    │ ┌──────────────┐ │    │                 │
│ • Users     │────│ │ Declarative  │ │────│ • Org 1        │
│ • Groups    │    │ │ (Batch)      │ │    │ • Org 2        │
│ • Events    │────│ │ Real-time    │ │────│ • Org N        │
│             │    │ │ (Webhooks)   │ │    │                 │
└─────────────┘    │ └──────────────┘ │    └─────────────────┘
                   │                  │
                   │ • State Mgmt     │
                   │ • Audit Logs     │
                   │ • Reconciliation │
                   └──────────────────┘
```

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/braintrustdata/okta-braintrust-sync
cd okta-braintrust-sync

# Install with uv (recommended)
uv sync --all-extras
source .venv/bin/activate

# Or install with pip
pip install -e ".[dev]"

# Verify installation
okta-braintrust-sync --help
```

### Configuration

Create your sync configuration file:

```bash
# Copy example configuration
cp config/examples/hybrid.yaml my-sync-config.yaml

# Set environment variables
export OKTA_API_TOKEN="your_okta_api_token"
export OKTA_DOMAIN="yourorg.okta.com"
export BT_PROD_API_KEY="your_braintrust_prod_key"
export BT_STAGING_API_KEY="your_braintrust_staging_key"
```

### Basic Usage

```bash
# Validate configuration and connectivity
okta-braintrust-sync validate --config my-sync-config.yaml

# Declarative mode: plan what will be synced
okta-braintrust-sync plan --config my-sync-config.yaml

# Apply the sync plan
okta-braintrust-sync apply --config my-sync-config.yaml

# Start real-time webhook server
okta-braintrust-sync webhook start --config my-sync-config.yaml

# Start hybrid mode (both declarative scheduler + webhooks)
okta-braintrust-sync start --config my-sync-config.yaml
```

## Configuration

### Example Configuration

```yaml
# Okta source configuration
okta:
  domain: "myorg.okta.com"
  api_token: "${OKTA_API_TOKEN}"
  
# Target Braintrust organizations  
braintrust_orgs:
  production:
    api_key: "${BT_PROD_API_KEY}"
    url: "https://api.braintrust.dev"
  staging:
    api_key: "${BT_STAGING_API_KEY}" 
    url: "https://api.braintrust.dev"

# Sync modes configuration
sync_modes:
  declarative:
    enabled: true
    schedule: "0 */4 * * *"        # Every 4 hours
    full_reconciliation: "0 2 * * 0"  # Weekly full sync
    
  realtime:
    enabled: true
    webhook_port: 8080
    critical_events_only: true    # Security-critical events only

# Sync rules - who gets synced where
sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'profile.department eq "Engineering"'
        braintrust_orgs: ["production", "staging"]
      - okta_filter: 'profile.department eq "QA"'
        braintrust_orgs: ["staging"]
    
    identity_mapping:
      strategy: "email"  # email, custom_field, mapping_file
      
  groups:
    enabled: true
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP" and profile.name sw "Engineering"'
        braintrust_orgs: ["production", "staging"]
        name_transform: "okta-{group.name}"
      - okta_group_filter: 'profile.name eq "QA Team"'
        braintrust_orgs: ["staging"]

# Sync behavior
sync_options:
  dry_run: false
  create_missing: true
  update_existing: true  
  remove_extra: false    # SCIM-like: don't delete users/groups not in Okta
  batch_size: 50

# Audit configuration
audit:
  enabled: true
  log_file: "./logs/sync-{timestamp}.log"
  retention_days: 90
```

See [Configuration Guide](docs/configuration.md) for complete reference.

## Sync Modes

### Declarative Mode (Terraform-like)

Plan and apply changes in controlled batches:

```bash
# See what will be synced
okta-braintrust-sync plan --config config.yaml

# Apply the changes
okta-braintrust-sync apply --config config.yaml

# Schedule regular syncs
okta-braintrust-sync start --declarative-only --config config.yaml
```

**Use Cases:**
- Initial bulk sync
- Scheduled reconciliation 
- Change review before application
- Large-scale updates

### Real-time Mode (Webhook-driven)

Immediate sync on Okta changes:

```bash
# Start webhook server
okta-braintrust-sync webhook start --config config.yaml

# Configure Okta Event Hook to point to: http://your-server:8080/webhook/events
```

**Use Cases:**
- Immediate user deprovisioning (security)
- Real-time access updates
- Live group membership changes
- SCIM-like behavior

### Hybrid Mode (Best of Both)

Combines both approaches:

```bash
# Start both modes
okta-braintrust-sync start --config config.yaml
```

**Benefits:**
- Real-time for security-critical events
- Scheduled reconciliation catches missed events
- Redundancy and reliability
- Flexible event routing

## Development

### Setup Development Environment

```bash
# Install development dependencies
uv sync --all-extras --dev

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run linting
ruff check --fix
mypy sync/
```

### Project Structure

```
okta-braintrust-sync/
├── sync/                    # Main Python package
│   ├── config/             # Configuration management
│   ├── clients/            # Okta & Braintrust API clients
│   ├── core/               # Sync engine & orchestration
│   ├── resources/          # User & group sync logic
│   ├── webhook/            # Real-time webhook handling
│   ├── audit/              # Logging & reporting
│   └── utils/              # Shared utilities
├── config/                 # Configuration schemas & examples
├── tests/                  # Test suite
├── docs/                   # Documentation
└── deployments/            # Deployment configurations
```

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests (requires test credentials)
pytest tests/integration/ --okta-token=$TEST_OKTA_TOKEN

# End-to-end tests
pytest tests/e2e/ --slow
```

## Deployment

### Docker

```bash
# Build image
docker build -t okta-braintrust-sync .

# Run declarative mode
docker run -v ./config.yaml:/app/config.yaml okta-braintrust-sync apply

# Run webhook server
docker run -p 8080:8080 -v ./config.yaml:/app/config.yaml okta-braintrust-sync webhook start
```

### Kubernetes

```bash
# Apply manifests
kubectl apply -f deployments/kubernetes/
```

### Systemd Service

```bash
# Install service
sudo cp deployments/systemd/okta-braintrust-sync.service /etc/systemd/system/
sudo systemctl enable okta-braintrust-sync
sudo systemctl start okta-braintrust-sync
```

## Monitoring & Troubleshooting

### Logs & Metrics

```bash
# View audit logs
tail -f logs/sync-$(date +%Y%m%d).log

# Check sync status
okta-braintrust-sync status --config config.yaml

# View last sync report
cat state/last-sync-report.json
```

### Common Issues

**Connection Issues:**
```bash
# Test Okta connectivity
okta-braintrust-sync validate --okta-only --config config.yaml

# Test Braintrust connectivity  
okta-braintrust-sync validate --braintrust-only --config config.yaml
```

**Webhook Issues:**
```bash
# Check webhook server status
curl http://localhost:8080/health

# Test webhook endpoint
curl -X POST http://localhost:8080/webhook/events \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

See [Troubleshooting Guide](docs/troubleshooting.md) for detailed solutions.

## Security

### Authentication

- **Okta**: API token with appropriate permissions
- **Braintrust**: Organization API keys with user/group management permissions
- **Webhooks**: Signature verification for event authenticity

### Best Practices

- Store credentials in environment variables or secure secret management
- Use least-privilege API permissions
- Enable audit logging for compliance
- Regularly rotate API tokens
- Monitor sync activities and failures

### Permissions Required

**Okta API Token Permissions:**
- `okta.users.read`
- `okta.groups.read`  
- `okta.events.read` (for webhooks)

**Braintrust API Key Permissions:**
- User management (create, update users)
- Group management (create, update, manage groups)
- Organization read access

## Support

### Getting Help

1. **Documentation**: Check [docs/](docs/) directory
2. **Issues**: [GitHub Issues](https://github.com/braintrustdata/okta-braintrust-sync/issues)
3. **Discussions**: [GitHub Discussions](https://github.com/braintrustdata/okta-braintrust-sync/discussions)

### Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## Quick Command Reference

```bash
# Configuration & Validation
okta-braintrust-sync validate --config config.yaml
okta-braintrust-sync show --config config.yaml

# Declarative Mode  
okta-braintrust-sync plan --config config.yaml
okta-braintrust-sync apply --config config.yaml

# Real-time Mode
okta-braintrust-sync webhook start --config config.yaml
okta-braintrust-sync webhook status

# Hybrid Mode
okta-braintrust-sync start --config config.yaml
okta-braintrust-sync status

# Utilities
okta-braintrust-sync reconcile --full --config config.yaml
okta-braintrust-sync replay --since "2024-01-15" --config config.yaml
```