terraform {
  required_providers {
    okta = {
      source  = "okta/okta"
      version = "~> 4.0"
    }
  }
}

# Configure the Okta Provider
# You'll need to set these environment variables:
# export OKTA_ORG_NAME="your-org-name"
# export OKTA_API_TOKEN="your-api-token"
provider "okta" {
  # Configuration will be read from environment variables
}

# Test Users - using alias emails for carlos@braintrustdata.com
resource "okta_user" "test_ml_engineer_1" {
  first_name = "Carlos"
  last_name  = "ML1"
  login      = "carlos+ml1@braintrustdata.com"
  email      = "carlos+ml1@braintrustdata.com"
  status     = "ACTIVE"
  
  # Custom profile attributes
  custom_profile_attributes = jsonencode({
    department = "ML Engineering"
    team       = "Core ML"
    role       = "Senior Engineer"
  })
}

resource "okta_user" "test_ml_engineer_2" {
  first_name = "Carlos"
  last_name  = "ML2"
  login      = "carlos+ml2@braintrustdata.com"
  email      = "carlos+ml2@braintrustdata.com"
  status     = "ACTIVE"
  
  custom_profile_attributes = jsonencode({
    department = "ML Engineering"
    team       = "Core ML"
    role       = "Engineer"
  })
}

resource "okta_user" "test_data_scientist_1" {
  first_name = "Carlos"
  last_name  = "DS1"
  login      = "carlos+ds1@braintrustdata.com"
  email      = "carlos+ds1@braintrustdata.com"
  status     = "ACTIVE"
  
  custom_profile_attributes = jsonencode({
    department = "Data Science"
    team       = "Research"
    role       = "Data Scientist"
  })
}

resource "okta_user" "test_data_scientist_2" {
  first_name = "Carlos"
  last_name  = "DS2"
  login      = "carlos+ds2@braintrustdata.com"
  email      = "carlos+ds2@braintrustdata.com"
  status     = "ACTIVE"
  
  custom_profile_attributes = jsonencode({
    department = "Data Science"
    team       = "Analytics"
    role       = "Senior Data Scientist"
  })
}

resource "okta_user" "test_platform_admin" {
  first_name = "Carlos"
  last_name  = "Admin"
  login      = "carlos+admin@braintrustdata.com"
  email      = "carlos+admin@braintrustdata.com"
  status     = "ACTIVE"
  
  custom_profile_attributes = jsonencode({
    department = "Platform"
    team       = "GenAI Platform"
    role       = "Platform Engineer"
  })
}

resource "okta_user" "test_inactive_user" {
  first_name = "Carlos"
  last_name  = "Inactive"
  login      = "carlos+inactive@braintrustdata.com"
  email      = "carlos+inactive@braintrustdata.com"
  status     = "SUSPENDED"  # This user should be filtered out
  
  custom_profile_attributes = jsonencode({
    department = "Former Employee"
    team       = "N/A"
    role       = "N/A"
  })
}

# Test Groups
resource "okta_group" "ml_engineering" {
  name        = "ML-Engineering"
  description = "Machine Learning Engineering Team"
}

resource "okta_group" "data_science" {
  name        = "Data-Science"
  description = "Data Science Team"
}

resource "okta_group" "genai_platform_admins" {
  name        = "GenAI-Platform-Admins"
  description = "GenAI Platform Administration Team"
}

resource "okta_group" "all_ai_ml" {
  name        = "All-AI-ML"
  description = "All AI/ML Teams (Parent Group)"
}

# Test group for filtering (should be excluded)
resource "okta_group" "test_ad_group" {
  name        = "AD-Imported-Group"
  description = "Simulated AD imported group that should be filtered out"
}

# Group Memberships
resource "okta_group_memberships" "ml_engineering_members" {
  group_id = okta_group.ml_engineering.id
  users = [
    okta_user.test_ml_engineer_1.id,
    okta_user.test_ml_engineer_2.id,
  ]
}

resource "okta_group_memberships" "data_science_members" {
  group_id = okta_group.data_science.id
  users = [
    okta_user.test_data_scientist_1.id,
    okta_user.test_data_scientist_2.id,
  ]
}

resource "okta_group_memberships" "genai_platform_admin_members" {
  group_id = okta_group.genai_platform_admins.id
  users = [
    okta_user.test_platform_admin.id,
  ]
}

resource "okta_group_memberships" "all_ai_ml_members" {
  group_id = okta_group.all_ai_ml.id
  users = [
    okta_user.test_ml_engineer_1.id,
    okta_user.test_ml_engineer_2.id,
    okta_user.test_data_scientist_1.id,
    okta_user.test_data_scientist_2.id,
    okta_user.test_platform_admin.id,
  ]
}

# Add inactive user to a group to test filtering
resource "okta_group_memberships" "ad_group_members" {
  group_id = okta_group.test_ad_group.id
  users = [
    okta_user.test_inactive_user.id,
  ]
}