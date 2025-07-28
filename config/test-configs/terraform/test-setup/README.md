# Okta Test Data Setup with Terraform

This Terraform configuration creates test users and groups in your Okta organization using alias emails for `carlos@braintrustdata.com` to test the okta-braintrust-sync tool.

## Prerequisites

1. **Okta Admin Access**: You need admin access to your Okta organization
2. **Okta API Token**: Create an API token with appropriate permissions
3. **Terraform**: Install Terraform on your machine

## Setup Instructions

### 1. Create Okta API Token

1. Log into your Okta Admin Console
2. Go to **Security** → **API** → **Tokens**
3. Click **Create Token**
4. Name it "terraform-test-setup"
5. Copy the token (you won't see it again!)

### 2. Set Environment Variables

```bash
# Set your Okta organization name (the subdomain)
export OKTA_ORG_NAME="your-org-name"  # e.g., "braintrust-dev"

# Set your API token
export OKTA_API_TOKEN="your-api-token-here"

# Optional: Set base URL if using custom domain
# export OKTA_BASE_URL="https://your-org.okta.com"
```

### 3. Initialize and Apply Terraform

```bash
# Navigate to this directory
cd terraform/test-setup/

# Initialize Terraform
terraform init

# Preview what will be created
terraform plan

# Apply the configuration (creates test data)
terraform apply
```

## What Gets Created

### Test Users (5 total)
All using `carlos+alias@braintrustdata.com` format:

- **carlos+ml1@braintrustdata.com** - ML Engineer 1 (Active)
- **carlos+ml2@braintrustdata.com** - ML Engineer 2 (Active)  
- **carlos+ds1@braintrustdata.com** - Data Scientist 1 (Active)
- **carlos+ds2@braintrustdata.com** - Data Scientist 2 (Active)
- **carlos+admin@braintrustdata.com** - Platform Admin (Active)
- **carlos+inactive@braintrustdata.com** - Inactive User (Suspended - for testing filters)

### Test Groups (5 total)

- **ML-Engineering** - Contains ml1, ml2
- **Data-Science** - Contains ds1, ds2  
- **GenAI-Platform-Admins** - Contains admin
- **All-AI-ML** - Contains all active users (parent group)
- **AD-Imported-Group** - Contains inactive user (for testing filters)

### Custom Profile Attributes

Each user has custom attributes:
- `department` - "ML Engineering", "Data Science", "Platform"
- `team` - Specific team name
- `role` - Job role

## Testing the Sync Tool

After applying this Terraform config, you can test various sync scenarios:

### Basic Test Configuration

```yaml
okta:
  domain: "your-org.okta.com"
  api_token: "${OKTA_API_TOKEN}"

braintrust_orgs:
  test:
    api_key: "${BRAINTRUST_TEST_API_KEY}"
    url: "https://api.braintrust.dev"

sync_modes:
  declarative:
    enabled: true

sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: 'status eq "ACTIVE"'
        braintrust_orgs: ["test"]
        enabled: true

  groups:
    enabled: true
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP"'
        braintrust_orgs: ["test"]
        enabled: true
```

### Test Commands

```bash
# Test that you can connect to both APIs
okta-braintrust-sync validate --config test-config.yaml

# See what would be synced (should show 5 active users, 4-5 groups)
okta-braintrust-sync plan --config test-config.yaml

# Test specific filters
okta-braintrust-sync plan --config test-config.yaml \
  --user-filter 'profile.department eq "ML Engineering"' \
  --group-filter 'profile.name eq "ML-Engineering"'
```

## Advanced Testing Scenarios

### Filter by Department
```yaml
sync_rules:
  users:
    mappings:
      - okta_filter: 'status eq "ACTIVE" and profile.department eq "ML Engineering"'
        braintrust_orgs: ["test"]
        enabled: true
```

### Filter by Specific Groups
```yaml
sync_rules:
  groups:
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP" and profile.name eq "ML-Engineering"'
        braintrust_orgs: ["test"]
        enabled: true
```

### Exclude AD Groups
```yaml
sync_rules:
  groups:
    mappings:
      - okta_group_filter: 'type eq "OKTA_GROUP" and profile.name ne "AD-Imported-Group"'
        braintrust_orgs: ["test"]
        enabled: true
```

## Expected Results

When you run the sync tool with this test data:

- **Active Users**: Should find 5 active users (all except inactive one)
- **Groups**: Should find 4-5 groups depending on filters
- **Filtering**: Inactive user should be excluded by `status eq "ACTIVE"` filter
- **Group Filtering**: AD-Imported-Group can be excluded with proper filters

## Cleanup

To remove all test data:

```bash
terraform destroy
```

This will delete all the test users and groups created by this configuration.

## Troubleshooting

### Permission Issues
If you get permission errors, make sure your Okta API token has:
- User management permissions
- Group management permissions
- Profile read permissions

### Custom Attributes
If custom profile attributes don't work, you may need to:
1. Define custom user profile attributes in Okta first
2. Or remove the `custom_profile_attributes` sections and just use standard fields

### Email Delivery
The alias emails (carlos+ml1@braintrustdata.com) will all deliver to carlos@braintrustdata.com, so you can test email notifications and password resets.