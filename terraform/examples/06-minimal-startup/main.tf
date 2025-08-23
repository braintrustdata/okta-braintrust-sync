# =====================================================================
# Example 6: Minimal Startup Team
# =====================================================================
# This example demonstrates a simple, scalable setup for small teams:
# - 6 users representing a typical early-stage startup team
# - Simple role-based groups with room for growth
# - Streamlined permissions focusing on velocity and collaboration
# - Minimal overhead while maintaining basic access control
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

# ========== Startup Team Members ==========
# Founder/CEO
resource "okta_user" "alex_founder" {
  first_name = "Alex"
  last_name  = "Chen"
  login      = "alex@startup.dev"
  email      = "alex@startup.dev"
  
  custom_profile_attributes = jsonencode({
    department = "Leadership"
    title      = "Founder & CEO"
    location   = "San Francisco"
    employeeType = "Founder"
    level      = "Founder"
    skills     = "Leadership,Strategy,Vision,Product"
    startDate  = "2023-01-01"
    isFounder  = "true"
  })
}

# Technical Co-founder/CTO
resource "okta_user" "sarah_cofounder" {
  first_name = "Sarah"
  last_name  = "Kim"
  login      = "sarah@startup.dev"
  email      = "sarah@startup.dev"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Co-founder & CTO"
    location   = "San Francisco"
    employeeType = "Founder"
    level      = "Founder"
    skills     = "Engineering,Architecture,Leadership,DevOps"
    startDate  = "2023-01-01"
    isFounder  = "true"
  })
}

# Lead Engineer
resource "okta_user" "mike_lead_engineer" {
  first_name = "Mike"
  last_name  = "Rodriguez"
  login      = "mike@startup.dev"
  email      = "mike@startup.dev"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Lead Engineer"
    location   = "Remote"
    employeeType = "Employee"
    level      = "Senior"
    skills     = "FullStack,React,Node.js,Python,AWS"
    startDate  = "2023-03-15"
    isFounder  = "false"
  })
}

# Product Manager
resource "okta_user" "emily_product" {
  first_name = "Emily"
  last_name  = "Johnson"
  login      = "emily@startup.dev"
  email      = "emily@startup.dev"
  
  custom_profile_attributes = jsonencode({
    department = "Product"
    title      = "Product Manager"
    location   = "Austin"
    employeeType = "Employee"
    level      = "Mid"
    skills     = "ProductManagement,UX,Analytics,CustomerResearch"
    startDate  = "2023-04-01"
    isFounder  = "false"
  })
}

# Data Scientist
resource "okta_user" "david_data_scientist" {
  first_name = "David"
  last_name  = "Park"
  login      = "david@startup.dev"
  email      = "david@startup.dev"
  
  custom_profile_attributes = jsonencode({
    department = "Data"
    title      = "Data Scientist"
    location   = "New York"
    employeeType = "Employee"
    level      = "Mid"
    skills     = "MachineLearning,Python,SQL,Statistics,Analytics"
    startDate  = "2023-05-01"
    isFounder  = "false"
  })
}

# Designer/Marketing
resource "okta_user" "lisa_designer" {
  first_name = "Lisa"
  last_name  = "Wong"
  login      = "lisa@startup.dev"
  email      = "lisa@startup.dev"
  
  custom_profile_attributes = jsonencode({
    department = "Design"
    title      = "Designer & Marketing"
    location   = "Seattle"
    employeeType = "Employee"
    level      = "Mid"
    skills     = "Design,UX,UI,Marketing,Branding,Content"
    startDate  = "2023-06-01"
    isFounder  = "false"
  })
}

# ========== Simple Role-Based Groups ==========
resource "okta_group" "bt_founders" {
  name        = "BT-Founders"
  description = "Company founders with full access"
}

resource "okta_group" "bt_leadership" {
  name        = "BT-Leadership"
  description = "Leadership team including founders and senior roles"
}

resource "okta_group" "bt_engineers" {
  name        = "BT-Engineers"
  description = "Engineering team members"
}

resource "okta_group" "bt_product_team" {
  name        = "BT-Product-Team"
  description = "Product management and design team"
}

resource "okta_group" "bt_data_team" {
  name        = "BT-Data-Team"
  description = "Data science and analytics team"
}

resource "okta_group" "bt_all_team" {
  name        = "BT-All-Team"
  description = "All team members for company-wide access"
}

# ========== Group Memberships ==========
# Founders group
resource "okta_group_memberships" "founders" {
  group_id = okta_group.bt_founders.id
  users = [
    okta_user.alex_founder.id,
    okta_user.sarah_cofounder.id,
  ]
}

# Leadership group (founders + senior roles)
resource "okta_group_memberships" "leadership" {
  group_id = okta_group.bt_leadership.id
  users = [
    okta_user.alex_founder.id,
    okta_user.sarah_cofounder.id,
    okta_user.mike_lead_engineer.id,
  ]
}

# Engineering team
resource "okta_group_memberships" "engineers" {
  group_id = okta_group.bt_engineers.id
  users = [
    okta_user.sarah_cofounder.id,
    okta_user.mike_lead_engineer.id,
  ]
}

# Product team
resource "okta_group_memberships" "product_team" {
  group_id = okta_group.bt_product_team.id
  users = [
    okta_user.alex_founder.id,
    okta_user.emily_product.id,
    okta_user.lisa_designer.id,
  ]
}

# Data team
resource "okta_group_memberships" "data_team" {
  group_id = okta_group.bt_data_team.id
  users = [
    okta_user.david_data_scientist.id,
  ]
}

# All team members
resource "okta_group_memberships" "all_team" {
  group_id = okta_group.bt_all_team.id
  users = [
    okta_user.alex_founder.id,
    okta_user.sarah_cofounder.id,
    okta_user.mike_lead_engineer.id,
    okta_user.emily_product.id,
    okta_user.david_data_scientist.id,
    okta_user.lisa_designer.id,
  ]
}

# ========== Outputs ==========
output "team_structure" {
  description = "Startup team organized by function"
  value = {
    founders = [
      okta_user.alex_founder.email,
      okta_user.sarah_cofounder.email,
    ]
    leadership = [
      okta_user.alex_founder.email,
      okta_user.sarah_cofounder.email,
      okta_user.mike_lead_engineer.email,
    ]
    engineering = [
      okta_user.sarah_cofounder.email,
      okta_user.mike_lead_engineer.email,
    ]
    product = [
      okta_user.alex_founder.email,
      okta_user.emily_product.email,
      okta_user.lisa_designer.email,
    ]
    data = [
      okta_user.david_data_scientist.email,
    ]
    all_team = [
      okta_user.alex_founder.email,
      okta_user.sarah_cofounder.email,
      okta_user.mike_lead_engineer.email,
      okta_user.emily_product.email,
      okta_user.david_data_scientist.email,
      okta_user.lisa_designer.email,
    ]
  }
}

output "team_growth_readiness" {
  description = "Team structure ready for scaling"
  value = {
    current_size = 6
    departments_established = ["Engineering", "Product", "Data", "Design", "Leadership"]
    groups_ready_for_scaling = [
      okta_group.bt_engineers.name,
      okta_group.bt_product_team.name,
      okta_group.bt_data_team.name,
    ]
    founder_control_maintained = true
  }
}

output "groups_created" {
  description = "All startup groups created"
  value = {
    role_based = [
      okta_group.bt_founders.name,
      okta_group.bt_leadership.name,
      okta_group.bt_engineers.name,
      okta_group.bt_product_team.name,
      okta_group.bt_data_team.name,
      okta_group.bt_all_team.name,
    ]
  }
}