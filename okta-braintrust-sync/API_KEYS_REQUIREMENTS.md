# API Keys and Setup Requirements

This document identifies where real API keys and external setup would be required for the okta-braintrust-sync tool.

## Summary

**You can test all Phase 2 components (Braintrust client, state management, base syncer) without any real API keys or external setup.** The comprehensive test suite uses mocks and can be run entirely offline.

## Testing Status ✅

### Completed Tests (No Real APIs Required)
- **Braintrust Client**: ✅ Unit tests with mocked braintrust-api SDK
- **State Management**: ✅ Full persistence, checkpointing, and ID mapping tests
- **Base Resource Syncer**: ✅ Sync plan generation and execution patterns
- **Integration Tests**: ✅ End-to-end workflow with mock data

### Test Commands (Run in venv)
```bash
# Activate virtual environment
source venv/bin/activate

# Test individual components
python -m pytest tests/test_state_manager.py -v
python -m pytest tests/test_base_syncer.py -v
python -m pytest tests/test_integration.py -v

# Run all tests
python -m pytest tests/ -v
```

## When Real API Keys Are Required

### 1. Okta API Access
**Required for**: Live sync operations with real Okta data

**Setup needed**:
- Okta organization admin access
- Create Okta API token with appropriate scopes:
  - `okta.users.read`
  - `okta.groups.read`
  - `okta.events.read` (for webhook mode)
- Configure in environment variables:
  ```bash
  OKTA_DOMAIN=your-domain.okta.com
  OKTA_API_TOKEN=your-api-token
  ```

**Configuration**:
```yaml
# config/sync.yaml
okta:
  domain: "your-domain.okta.com"
  api_token: "${OKTA_API_TOKEN}"
```

### 2. Braintrust API Access
**Required for**: Live sync operations with real Braintrust organizations

**Setup needed**:
- Braintrust organization admin access
- Generate API key from Braintrust dashboard
- Configure for each target organization:
  ```bash
  BRAINTRUST_ORG1_API_KEY=your-org1-key
  BRAINTRUST_ORG2_API_KEY=your-org2-key
  ```

**Configuration**:
```yaml
# config/sync.yaml
braintrust_orgs:
  production:
    api_key: "${BRAINTRUST_ORG1_API_KEY}"
    api_url: "https://api.braintrust.dev"
  staging:
    api_key: "${BRAINTRUST_ORG2_API_KEY}"
    api_url: "https://api.braintrust.dev"
```

### 3. Webhook Configuration (Optional)
**Required for**: Real-time sync via Okta Event Hooks

**Setup needed**:
- Public endpoint for webhook reception
- SSL certificate for HTTPS
- Configure Okta Event Hooks to point to your endpoint
- Webhook signature verification (recommended)

**Configuration**:
```yaml
# config/sync.yaml
sync_modes:
  webhook:
    enabled: true
    endpoint: "/webhook/okta"
    port: 8000
    verify_signature: true
    secret: "${WEBHOOK_SECRET}"
```

## Current Implementation Status

### ✅ Ready for Testing (No APIs needed)
- Configuration loading and validation
- State management with persistence
- Braintrust client wrapper (mocked)
- Okta client wrapper (mocked)  
- Base sync orchestration patterns
- CLI interface structure

### 🔄 Would Need Real APIs
- **Live user/group retrieval**: `okta_client.search_users()`, `braintrust_client.list_users()`
- **Live resource creation**: `braintrust_client.create_user()`, `braintrust_client.create_group()`
- **Live resource updates**: `braintrust_client.update_user()`, `braintrust_client.add_group_members()`
- **Webhook event processing**: Real Okta event payloads
- **Health checks**: `okta_client.health_check()`, `braintrust_client.health_check()`

## Development Workflow

### Phase 1: Development & Testing (Current)
```bash
# All testing can be done without real APIs
source venv/bin/activate
python -m pytest tests/ -v

# CLI validation (config validation only)
python -m sync.cli validate --config config/sync.yaml.example
```

### Phase 2: Integration Testing
```bash
# Requires real API keys
export OKTA_API_TOKEN="your-token"
export BRAINTRUST_ORG1_API_KEY="your-key"

# Test connectivity
python -m sync.cli validate --config config/sync.yaml

# Dry run sync
python -m sync.cli plan --config config/sync.yaml --dry-run
```

### Phase 3: Production Deployment
```bash
# Full sync with real data
python -m sync.cli apply --config config/sync.yaml
```

## Error Handling Without Real APIs

The current implementation includes comprehensive error handling that works with mocked APIs:

- **Network errors**: Simulated connection timeouts
- **Authentication errors**: Invalid API key scenarios  
- **Rate limiting**: Throttling behavior testing
- **Resource conflicts**: Duplicate creation attempts
- **State recovery**: Checkpoint restoration after failures

## Next Steps

1. **Continue with Phase 2 implementation** - User/Group syncers can be built and tested with mocks
2. **Add concrete resource syncers** - Implement `UserSyncer` and `GroupSyncer` classes
3. **Enhance CLI commands** - Complete `plan`, `apply`, `status` command implementations
4. **Add audit logging** - Comprehensive operation tracking
5. **Real API testing** - Only needed when ready for live integration

The hybrid architecture design allows for extensive development and testing without any external dependencies, making it easy to iterate on the sync logic before connecting to real systems.