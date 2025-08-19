# =====================================================================
# Example 1: Basic Team Structure
# =====================================================================
# This example creates a simple team structure with:
# - 8 users across 3 teams (Engineering, DataScience, ProductManagement)
# - Basic Okta groups with BT- prefix
# - Simple group-based role assignments
# =====================================================================

terraform {
  required_providers {
    okta = {
      source  = "okta/okta"
      version = "~> 4.0"
    }
  }
}

# Configure the Okta Provider
provider "okta" {
  org_name = var.okta_org_name
  api_token = var.okta_api_token
  base_url = var.okta_base_url
}

# Variables
variable "okta_org_name" {
  description = "Okta organization name"
  type        = string
}

variable "okta_api_token" {
  description = "Okta API token"
  type        = string
  sensitive   = true
}

variable "okta_base_url" {
  description = "Okta base URL"
  type        = string
  default     = "okta.com"
}

# ========== Users ==========
# Engineering Team
resource "okta_user" "alice_engineer" {
  first_name = "Alice"
  last_name  = "Smith"
  login      = "alice.smith@company.com"
  email      = "alice.smith@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Senior Software Engineer"
    location   = "San Francisco"
    employeeType = "Employee"
    manager    = "bob.johnson@company.com"
  })
}

resource "okta_user" "bob_engineer" {
  first_name = "Bob"
  last_name  = "Johnson"
  login      = "bob.johnson@company.com"
  email      = "bob.johnson@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Engineering Manager"
    location   = "San Francisco"
    employeeType = "Employee"
    manager    = ""
  })
}

resource "okta_user" "charlie_engineer" {
  first_name = "Charlie"
  last_name  = "Brown"
  login      = "charlie.brown@company.com"
  email      = "charlie.brown@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Software Engineer"
    location   = "Remote"
    employeeType = "Employee"
    manager    = "bob.johnson@company.com"
  })
}

# Data Science Team
resource "okta_user" "diana_data" {
  first_name = "Diana"
  last_name  = "Rodriguez"
  login      = "diana.rodriguez@company.com"
  email      = "diana.rodriguez@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "DataScience"
    title      = "Senior Data Scientist"
    location   = "New York"
    employeeType = "Employee"
    manager    = "eve.wilson@company.com"
  })
}

resource "okta_user" "eve_data" {
  first_name = "Eve"
  last_name  = "Wilson"
  login      = "eve.wilson@company.com"
  email      = "eve.wilson@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "DataScience"
    title      = "Data Science Manager"
    location   = "New York"
    employeeType = "Employee"
    manager    = ""
  })
}

resource "okta_user" "frank_data" {
  first_name = "Frank"
  last_name  = "Lee"
  login      = "frank.lee@company.com"
  email      = "frank.lee@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "DataScience"
    title      = "Data Scientist"
    location   = "Remote"
    employeeType = "Employee"
    manager    = "eve.wilson@company.com"
  })
}

# Product Management Team
resource "okta_user" "grace_product" {
  first_name = "Grace"
  last_name  = "Chen"
  login      = "grace.chen@company.com"
  email      = "grace.chen@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "ProductManagement"
    title      = "Senior Product Manager"
    location   = "San Francisco"
    employeeType = "Employee"
    manager    = "henry.davis@company.com"
  })
}

resource "okta_user" "henry_product" {
  first_name = "Henry"
  last_name  = "Davis"
  login      = "henry.davis@company.com"
  email      = "henry.davis@company.com"
  
  custom_profile_attributes = jsonencode({
    department = "ProductManagement"
    title      = "VP of Product"
    location   = "San Francisco"
    employeeType = "Employee"
    manager    = ""
  })
}

# ========== Groups ==========
# Braintrust groups (with BT- prefix for sync)
resource "okta_group" "bt_engineering" {
  name        = "BT-Engineering"
  description = "Engineering team members for Braintrust access"
}

resource "okta_group" "bt_datascience" {
  name        = "BT-DataScience"
  description = "Data Science team members for Braintrust access"
}

resource "okta_group" "bt_productmanagement" {
  name        = "BT-ProductManagement"
  description = "Product Management team members for Braintrust access"
}

resource "okta_group" "bt_managers" {
  name        = "BT-Managers"
  description = "All managers for Braintrust admin access"
}

resource "okta_group" "bt_allemployees" {
  name        = "BT-AllEmployees"
  description = "All employees for basic Braintrust access"
}

# ========== Group Memberships ==========
# Engineering Team
resource "okta_group_memberships" "engineering_members" {
  group_id = okta_group.bt_engineering.id
  users = [
    okta_user.alice_engineer.id,
    okta_user.bob_engineer.id,
    okta_user.charlie_engineer.id,
  ]
}

# Data Science Team
resource "okta_group_memberships" "datascience_members" {
  group_id = okta_group.bt_datascience.id
  users = [
    okta_user.diana_data.id,
    okta_user.eve_data.id,
    okta_user.frank_data.id,
  ]
}

# Product Management Team
resource "okta_group_memberships" "productmanagement_members" {
  group_id = okta_group.bt_productmanagement.id
  users = [
    okta_user.grace_product.id,
    okta_user.henry_product.id,
  ]
}

# Managers Group
resource "okta_group_memberships" "managers_members" {
  group_id = okta_group.bt_managers.id
  users = [
    okta_user.bob_engineer.id,
    okta_user.eve_data.id,
    okta_user.henry_product.id,
  ]
}

# All Employees Group
resource "okta_group_memberships" "allemployees_members" {
  group_id = okta_group.bt_allemployees.id
  users = [
    okta_user.alice_engineer.id,
    okta_user.bob_engineer.id,
    okta_user.charlie_engineer.id,
    okta_user.diana_data.id,
    okta_user.eve_data.id,
    okta_user.frank_data.id,
    okta_user.grace_product.id,
    okta_user.henry_product.id,
  ]
}

# ========== Outputs ==========
output "users" {
  description = "Created users"
  value = {
    engineering = [
      okta_user.alice_engineer.email,
      okta_user.bob_engineer.email,
      okta_user.charlie_engineer.email,
    ]
    datascience = [
      okta_user.diana_data.email,
      okta_user.eve_data.email,
      okta_user.frank_data.email,
    ]
    productmanagement = [
      okta_user.grace_product.email,
      okta_user.henry_product.email,
    ]
  }
}

output "groups" {
  description = "Created groups"
  value = {
    engineering       = okta_group.bt_engineering.name
    datascience      = okta_group.bt_datascience.name
    productmanagement = okta_group.bt_productmanagement.name
    managers         = okta_group.bt_managers.name
    allemployees     = okta_group.bt_allemployees.name
  }
}