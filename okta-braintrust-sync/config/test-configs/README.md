# Test Configurations for Okta-Braintrust Sync

These test configurations are designed to work with the Terraform test data setup. Use them in order to progressively test different features.

## Prerequisites

1. **Apply Terraform setup**: Run `terraform apply` in `terraform/test-setup/` first
2. **Set environment variables**:
   ```bash
   export OKTA_API_TOKEN="your-okta-token"
   export BRAINTRUST_TEST_API_KEY="your-braintrust-test-key"
   # For multi-org tests:
   export BRAINTRUST_DEV_API_KEY="your-braintrust-dev-key"
   export BRAINTRUST_PROD_API_KEY="your-braintrust-prod-key"
   ```
3. **Update Okta domain**: Edit the config files to replace `your-org.okta.com` with your actual domain

## Test Configurations

### 1. `basic-test.yaml` - Start Here

**Purpose**: Test basic connectivity and sync functionality

**What it does**:
- Syncs all active users (should find 5 users)
- Syncs all OKTA_GROUP types (should find 5 groups)
- Uses single Braintrust org for simplicity

**Expected Results**:
- 5 active users: carlos+ml1, carlos+ml2, carlos+ds1, carlos+ds2, carlos+admin
- 5 groups: ML-Engineering, Data-Science, GenAI-Platform-Admins, All-AI-ML, AD-Imported-Group
- 1 inactive user should be filtered out: carlos+inactive

**Test Commands**:
```bash
okta-braintrust-sync validate --config config/test-configs/basic-test.yaml
okta-braintrust-sync plan --config config/test-configs/basic-test.yaml
okta-braintrust-sync apply --config config/test-configs/basic-test.yaml --dry-run
```

### 2. `filtered-test.yaml` - Test Filtering

**Purpose**: Test user and group filtering capabilities

**What it does**:
- Filters users by department (only ML Engineering)
- Filters groups by name (only ML-Engineering group)

**Expected Results**:
- 2 users: carlos+ml1, carlos+ml2 (only ML Engineers)
- 1 group: ML-Engineering

**Test Commands**:
```bash
okta-braintrust-sync plan --config test-configs/filtered-test.yaml
# Should show much fewer items than basic-test
```

### 3. `exclude-groups-test.yaml` - Test Exclusion

**Purpose**: Test excluding unwanted groups (like AD imported groups)

**What it does**:
- Syncs all active users
- Excludes the AD-Imported-Group specifically

**Expected Results**:
- 5 active users (same as basic)
- 4 groups (excludes AD-Imported-Group)

**Test Commands**:
```bash
okta-braintrust-sync plan --config test-configs/exclude-groups-test.yaml
# Should show 4 groups instead of 5
```

### 4. `multi-team-test.yaml` - Test Multi-Organization

**Purpose**: Test syncing different teams to different Braintrust orgs

**What it does**:
- All users → dev environment
- Only ML Engineers and Platform Admin → prod environment
- All groups → dev environment  
- Only ML and Platform groups → prod environment

**Expected Results**:
- Dev org: 5 users, 4 groups
- Prod org: 3 users (2 ML + 1 admin), 2 groups

**Test Commands**:
```bash
okta-braintrust-sync plan --config test-configs/multi-team-test.yaml
# Should show different items for dev vs prod orgs
```

## Testing Workflow

### Step 1: Validate Setup
```bash
# Test that basic config can connect to both APIs
okta-braintrust-sync validate --config test-configs/basic-test.yaml
```

### Step 2: Basic Functionality
```bash
# See what would be synced
okta-braintrust-sync plan --config test-configs/basic-test.yaml

# Should show:
# - 5 users to be created
# - 5 groups to be created
# - No updates (since Braintrust org is empty)
```

### Step 3: Test Filtering
```bash
# Test user filtering
okta-braintrust-sync plan --config test-configs/filtered-test.yaml

# Should show much fewer items
```

### Step 4: Test Exclusions
```bash
# Test group exclusions
okta-braintrust-sync plan --config test-configs/exclude-groups-test.yaml

# Should show 4 groups instead of 5
```

### Step 5: Multi-Organization (Advanced)
```bash
# Test multi-org sync
okta-braintrust-sync plan --config test-configs/multi-team-test.yaml

# Should show different item counts per organization
```

### Step 6: Execute (When Ready)
```bash
# Start with dry run
okta-braintrust-sync apply --config test-configs/basic-test.yaml --dry-run

# When confident, remove --dry-run
okta-braintrust-sync apply --config test-configs/basic-test.yaml --auto-approve
```

## Troubleshooting

### No Users Found
- Check that Terraform was applied successfully
- Verify your Okta domain is correct in the config
- Make sure OKTA_API_TOKEN has user read permissions

### No Groups Found
- Check that your API token has group read permissions
- Verify groups were created by Terraform

### API Connection Errors
- Verify environment variables are set correctly
- Check that API tokens/keys are valid and not expired
- Ensure network connectivity to both Okta and Braintrust

### Unexpected Results
- Use `--user-filter` and `--group-filter` CLI options to test filters interactively
- Enable debug logging: `export STRUCTLOG_LEVEL=DEBUG`

## Cleanup

After testing, clean up the Okta test data:
```bash
cd terraform/test-setup/
terraform destroy
```

This will remove all test users and groups from Okta.