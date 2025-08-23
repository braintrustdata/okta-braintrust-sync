# =====================================================================
# Example 4: Project Lifecycle Management
# =====================================================================
# This example demonstrates project lifecycle-based access control with:
# - 8 users representing different project stages and roles
# - Project lifecycle groups (Planning, Development, Testing, Production)
# - Stage-specific access patterns and permissions
# - Escalating permissions through project maturity stages
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

# ========== Project Lifecycle Users ==========
# Product Planning Phase
resource "okta_user" "emma_product_owner" {
  first_name = "Emma"
  last_name  = "Thompson"
  login      = "emma.thompson@lifecycle.com"
  email      = "emma.thompson@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "Product"
    title      = "Product Owner"
    location   = "Seattle"
    employeeType = "FullTime"
    level      = "Senior"
    projectPhase = "Planning"
    yearsExperience = "6"
    responsibilities = "Requirements,Roadmap,Stakeholders"
  })
}

resource "okta_user" "mike_business_analyst" {
  first_name = "Mike"
  last_name  = "Davis"
  login      = "mike.davis@lifecycle.com"
  email      = "mike.davis@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "Product"
    title      = "Business Analyst"
    location   = "Austin"
    employeeType = "FullTime"
    level      = "Mid"
    projectPhase = "Planning"
    yearsExperience = "3"
    responsibilities = "Analysis,Documentation,Requirements"
  })
}

# Development Phase
resource "okta_user" "sara_lead_developer" {
  first_name = "Sara"
  last_name  = "Wilson"
  login      = "sara.wilson@lifecycle.com"
  email      = "sara.wilson@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Lead Developer"
    location   = "San Francisco"
    employeeType = "FullTime"
    level      = "Senior"
    projectPhase = "Development"
    yearsExperience = "8"
    responsibilities = "Architecture,Development,CodeReview"
  })
}

resource "okta_user" "jason_backend_dev" {
  first_name = "Jason"
  last_name  = "Martinez"
  login      = "jason.martinez@lifecycle.com"
  email      = "jason.martinez@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Backend Developer"
    location   = "Denver"
    employeeType = "FullTime"
    level      = "Mid"
    projectPhase = "Development"
    yearsExperience = "4"
    responsibilities = "BackendDev,APIs,Database"
  })
}

# Testing Phase
resource "okta_user" "linda_qa_lead" {
  first_name = "Linda"
  last_name  = "Chen"
  login      = "linda.chen@lifecycle.com"
  email      = "linda.chen@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "QA"
    title      = "QA Lead"
    location   = "Portland"
    employeeType = "FullTime"
    level      = "Senior"
    projectPhase = "Testing"
    yearsExperience = "7"
    responsibilities = "TestStrategy,Automation,QualityGates"
  })
}

resource "okta_user" "tom_qa_engineer" {
  first_name = "Tom"
  last_name  = "Rodriguez"
  login      = "tom.rodriguez@lifecycle.com"
  email      = "tom.rodriguez@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "QA"
    title      = "QA Engineer"
    location   = "Chicago"
    employeeType = "FullTime"
    level      = "Mid"
    projectPhase = "Testing"
    yearsExperience = "3"
    responsibilities = "Testing,Automation,BugReporting"
  })
}

# Production/Operations Phase
resource "okta_user" "rachel_devops_lead" {
  first_name = "Rachel"
  last_name  = "Brown"
  login      = "rachel.brown@lifecycle.com"
  email      = "rachel.brown@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "Operations"
    title      = "DevOps Lead"
    location   = "Boston"
    employeeType = "FullTime"
    level      = "Senior"
    projectPhase = "Production"
    yearsExperience = "9"
    responsibilities = "Deployment,Infrastructure,Monitoring"
  })
}

resource "okta_user" "carlos_sre" {
  first_name = "Carlos"
  last_name  = "Garcia"
  login      = "carlos.garcia@lifecycle.com"
  email      = "carlos.garcia@lifecycle.com"
  
  custom_profile_attributes = jsonencode({
    department = "Operations"
    title      = "Site Reliability Engineer"
    location   = "Miami"
    employeeType = "FullTime"
    level      = "Senior"
    projectPhase = "Production"
    yearsExperience = "5"
    responsibilities = "Reliability,Performance,Incident"
  })
}

# ========== Project Lifecycle Groups ==========
resource "okta_group" "bt_planning_phase" {
  name        = "BT-Planning-Phase"
  description = "Users involved in project planning and requirements"
}

resource "okta_group" "bt_development_phase" {
  name        = "BT-Development-Phase"
  description = "Users involved in active development"
}

resource "okta_group" "bt_testing_phase" {
  name        = "BT-Testing-Phase"
  description = "Users involved in testing and quality assurance"
}

resource "okta_group" "bt_production_phase" {
  name        = "BT-Production-Phase"
  description = "Users involved in production operations"
}

# ========== Role-Based Groups ==========
resource "okta_group" "bt_project_leads" {
  name        = "BT-Project-Leads"
  description = "Technical and project leads across all phases"
}

resource "okta_group" "bt_senior_team" {
  name        = "BT-Senior-Team"
  description = "Senior-level team members"
}

resource "okta_group" "bt_cross_phase_access" {
  name        = "BT-Cross-Phase-Access"
  description = "Users needing access across multiple project phases"
}

# ========== Group Memberships ==========
# Project Phase Groups
resource "okta_group_memberships" "planning_phase" {
  group_id = okta_group.bt_planning_phase.id
  users = [
    okta_user.emma_product_owner.id,
    okta_user.mike_business_analyst.id,
  ]
}

resource "okta_group_memberships" "development_phase" {
  group_id = okta_group.bt_development_phase.id
  users = [
    okta_user.sara_lead_developer.id,
    okta_user.jason_backend_dev.id,
  ]
}

resource "okta_group_memberships" "testing_phase" {
  group_id = okta_group.bt_testing_phase.id
  users = [
    okta_user.linda_qa_lead.id,
    okta_user.tom_qa_engineer.id,
  ]
}

resource "okta_group_memberships" "production_phase" {
  group_id = okta_group.bt_production_phase.id
  users = [
    okta_user.rachel_devops_lead.id,
    okta_user.carlos_sre.id,
  ]
}

# Role-Based Groups
resource "okta_group_memberships" "project_leads" {
  group_id = okta_group.bt_project_leads.id
  users = [
    okta_user.emma_product_owner.id,
    okta_user.sara_lead_developer.id,
    okta_user.linda_qa_lead.id,
    okta_user.rachel_devops_lead.id,
  ]
}

resource "okta_group_memberships" "senior_team" {
  group_id = okta_group.bt_senior_team.id
  users = [
    okta_user.emma_product_owner.id,
    okta_user.sara_lead_developer.id,
    okta_user.linda_qa_lead.id,
    okta_user.rachel_devops_lead.id,
    okta_user.carlos_sre.id,
  ]
}

resource "okta_group_memberships" "cross_phase_access" {
  group_id = okta_group.bt_cross_phase_access.id
  users = [
    okta_user.emma_product_owner.id,
    okta_user.sara_lead_developer.id,
    okta_user.linda_qa_lead.id,
    okta_user.rachel_devops_lead.id,
  ]
}

# ========== Outputs ==========
output "project_phases" {
  description = "Users organized by project phase"
  value = {
    planning = [
      okta_user.emma_product_owner.email,
      okta_user.mike_business_analyst.email,
    ]
    development = [
      okta_user.sara_lead_developer.email,
      okta_user.jason_backend_dev.email,
    ]
    testing = [
      okta_user.linda_qa_lead.email,
      okta_user.tom_qa_engineer.email,
    ]
    production = [
      okta_user.rachel_devops_lead.id,
      okta_user.carlos_sre.email,
    ]
  }
}

output "leadership_structure" {
  description = "Leadership and senior roles"
  value = {
    project_leads = [
      okta_user.emma_product_owner.email,
      okta_user.sara_lead_developer.email,
      okta_user.linda_qa_lead.email,
      okta_user.rachel_devops_lead.email,
    ]
    senior_team = [
      okta_user.emma_product_owner.email,
      okta_user.sara_lead_developer.email,
      okta_user.linda_qa_lead.email,
      okta_user.rachel_devops_lead.email,
      okta_user.carlos_sre.email,
    ]
    cross_phase_access = [
      okta_user.emma_product_owner.email,
      okta_user.sara_lead_developer.email,
      okta_user.linda_qa_lead.email,
      okta_user.rachel_devops_lead.email,
    ]
  }
}

output "groups_created" {
  description = "All groups created for project lifecycle"
  value = {
    lifecycle_phases = [
      okta_group.bt_planning_phase.name,
      okta_group.bt_development_phase.name,
      okta_group.bt_testing_phase.name,
      okta_group.bt_production_phase.name,
    ]
    cross_functional = [
      okta_group.bt_project_leads.name,
      okta_group.bt_senior_team.name,
      okta_group.bt_cross_phase_access.name,
    ]
  }
}