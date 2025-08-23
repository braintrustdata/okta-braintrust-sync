# Installation Guide

This guide provides detailed instructions for installing and setting up okta-braintrust-sync.

## Prerequisites

- Python 3.8 or higher
- Access to Okta Admin Console
- Braintrust API keys for target organizations
- Network access to both Okta and Braintrust APIs

## Installation Options

### Option 1: Development Installation (Recommended)

Clone and install in development mode for easy updates:

```bash
# Clone the repository
git clone https://github.com/BRAINTRUST_ORG/okta-braintrust-sync
cd okta-braintrust-sync

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with uv (recommended) or pip
uv pip install -e .

# Or with pip
# pip install -e .
```

### Option 2: Production Installation

Install directly from the repository:

```bash
# Create virtual environment
python -m venv okta-braintrust-sync-env
source okta-braintrust-sync-env/bin/activate

# Install from repository
pip install git+https://github.com/BRAINTRUST_ORG/okta-braintrust-sync.git
```

## Verify Installation

Test that the CLI is installed correctly:

```bash
okta-braintrust-sync --help
```

You should see the help output with available commands.

## API Credentials Setup

### Okta API Token

1. Log in to your Okta Admin Console
2. Navigate to **Security** → **API** → **Tokens**
3. Click **Create Token**
4. Provide a name (e.g., "Braintrust Sync")
5. Copy the token immediately (it won't be shown again)

**Required Permissions:**
- `okta.users.read` - Read user profiles and status
- `okta.groups.read` - Read group information and memberships

### Braintrust API Keys

For each Braintrust organization you want to sync to:

1. Log in to Braintrust
2. Navigate to **Settings** → **API Keys**
3. Click **Create API Key**
4. Provide a name (e.g., "Okta Sync")
5. Select permissions:
   - User management
   - Group management  
   - Role management
   - ACL management
6. Copy the API key

## Environment Variables

Set up environment variables for secure credential storage:

```bash
# Okta credentials
export OKTA_ORG_NAME="your-org-name"  # Without .okta.com
export OKTA_API_TOKEN="your-okta-api-token"

# Braintrust credentials
export BRAINTRUST_PROD_API_KEY="your-prod-api-key"
export BRAINTRUST_DEV_API_KEY="your-dev-api-key"  # Optional
```

For persistent environment variables, add to your shell profile:

```bash
# Add to ~/.bashrc, ~/.zshrc, etc.
echo 'export OKTA_ORG_NAME="your-org-name"' >> ~/.bashrc
echo 'export OKTA_API_TOKEN="your-okta-api-token"' >> ~/.bashrc
echo 'export BRAINTRUST_PROD_API_KEY="your-prod-api-key"' >> ~/.bashrc
```

## Directory Structure

After installation, create the following directory structure:

```
project-root/
├── sync-config.yaml          # Your configuration file
├── logs/                     # Created automatically
│   └── audit/               # Audit logs
└── state/                   # Created automatically
    └── sync-state.json      # Sync state tracking
```

The `logs/` and `state/` directories will be created automatically when you run the tool.

## Quick Configuration Test

Create a minimal test configuration:

```yaml
# test-config.yaml
okta:
  domain: "${OKTA_ORG_NAME}.okta.com"
  api_token: "${OKTA_API_TOKEN}"

braintrust_orgs:
  test:
    api_key: "${BRAINTRUST_PROD_API_KEY}"
    url: "https://api.braintrust.dev"

sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["test"]
        enabled: true
    identity_mapping:
      strategy: "email"
    create_missing: true
    update_existing: false

  groups:
    enabled: false  # Start simple

sync_modes:
  declarative:
    enabled: true
```

Test the configuration:

```bash
okta-braintrust-sync validate --config test-config.yaml
```

## Troubleshooting Installation

### Python Version Issues

Check your Python version:

```bash
python --version  # Should be 3.8+
```

If using an older version, install Python 3.8+ or use pyenv:

```bash
# Install with pyenv
pyenv install 3.11.0
pyenv local 3.11.0
```

### Dependencies Issues

If you encounter dependency conflicts:

```bash
# Clean install
pip uninstall okta-braintrust-sync
pip cache purge
pip install -e . --force-reinstall
```

### Permission Errors

On macOS/Linux, you may need to add the script directory to PATH:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
```

### API Connectivity Issues

Test API connectivity:

```bash
# Test Okta API
curl -H "Authorization: SSWS ${OKTA_API_TOKEN}" \
  "https://${OKTA_ORG_NAME}.okta.com/api/v1/users?limit=1"

# Test Braintrust API  
curl -H "Authorization: Bearer ${BRAINTRUST_PROD_API_KEY}" \
  "https://api.braintrust.dev/v1/organization"
```

## Next Steps

1. Review the [Configuration Guide](configuration-guide.md) for detailed setup
2. Check the [README.md](../README.md) for usage examples
3. Start with a simple configuration and gradually add features
4. Use `--dry-run` flag when testing new configurations

## Security Considerations

- Store API tokens as environment variables, never in configuration files
- Use restrictive file permissions on configuration files
- Regularly rotate API tokens
- Monitor audit logs for unauthorized access
- Use separate API keys per environment (dev/prod)

## Upgrading

To upgrade to a newer version:

```bash
# If installed in development mode
cd okta-braintrust-sync
git pull origin main
pip install -e . --upgrade

# If installed from repository  
pip install git+https://github.com/BRAINTRUST_ORG/okta-braintrust-sync.git --upgrade
```

Always test new versions with `--dry-run` before applying to production.