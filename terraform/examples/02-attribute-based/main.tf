# =====================================================================
# Example 2: Attribute-Based Assignment
# =====================================================================
# This example demonstrates attribute-based group assignment with:
# - 9 users with diverse attributes (title, department, location, level)
# - No Okta groups - relies purely on profile attributes
# - Complex attribute-based role assignments
# - Demonstrates hybrid strategy and attribute rules
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

# ========== Users with Rich Attributes ==========
resource "okta_user" "alice_senior_eng" {
  first_name = "Alice"
  last_name  = "Johnson"
  login      = "alice.johnson@techcorp.com"
  email      = "alice.johnson@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Senior Software Engineer"
    location   = "San Francisco"
    employeeType = "FullTime"
    level      = "Senior"
    skills     = "Python,JavaScript,React,AWS"
    costCenter = "ENG-001"
    manager    = "bob.smith@techcorp.com"
    startDate  = "2021-03-15"
  })
}

resource "okta_user" "bob_principal_eng" {
  first_name = "Bob"
  last_name  = "Smith"
  login      = "bob.smith@techcorp.com"
  email      = "bob.smith@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Principal Engineer"
    location   = "Remote"
    employeeType = "FullTime"
    level      = "Principal"
    skills     = "Go,Kubernetes,DevOps,Architecture"
    costCenter = "ENG-001"
    manager    = ""
    startDate  = "2019-01-10"
  })
}

resource "okta_user" "carol_ml_engineer" {
  first_name = "Carol"
  last_name  = "Davis"
  login      = "carol.davis@techcorp.com"
  email      = "carol.davis@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "ML Engineer"
    location   = "New York"
    employeeType = "FullTime"
    level      = "Mid"
    skills     = "Python,TensorFlow,MLOps,Data"
    costCenter = "ENG-ML-002"
    manager    = "bob.smith@techcorp.com"
    startDate  = "2022-06-01"
  })
}

resource "okta_user" "david_data_scientist" {
  first_name = "David"
  last_name  = "Wilson"
  login      = "david.wilson@techcorp.com"
  email      = "david.wilson@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "DataScience"
    title      = "Senior Data Scientist"
    location   = "Austin"
    employeeType = "FullTime"
    level      = "Senior"
    skills     = "Python,R,Statistics,ML"
    costCenter = "DS-001"
    manager    = "eve.brown@techcorp.com"
    startDate  = "2020-09-12"
  })
}

resource "okta_user" "eve_research_director" {
  first_name = "Eve"
  last_name  = "Brown"
  login      = "eve.brown@techcorp.com"
  email      = "eve.brown@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "Research"
    title      = "Director of Research"
    location   = "San Francisco"
    employeeType = "FullTime"
    level      = "Director"
    skills     = "Leadership,AI,Strategy,PhD"
    costCenter = "RES-001"
    manager    = ""
    startDate  = "2018-02-20"
  })
}

resource "okta_user" "frank_contractor" {
  first_name = "Frank"
  last_name  = "Garcia"
  login      = "frank.garcia@external.com"
  email      = "frank.garcia@external.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Frontend Developer"
    location   = "Remote"
    employeeType = "Contractor"
    level      = "Mid"
    skills     = "React,TypeScript,CSS,Design"
    costCenter = "EXT-001"
    manager    = "alice.johnson@techcorp.com"
    startDate  = "2023-01-15"
  })
}

resource "okta_user" "grace_product_manager" {
  first_name = "Grace"
  last_name  = "Lee"
  login      = "grace.lee@techcorp.com"
  email      = "grace.lee@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "Product"
    title      = "Senior Product Manager"
    location   = "Seattle"
    employeeType = "FullTime"
    level      = "Senior"
    skills     = "Strategy,Analytics,UX,Roadmaps"
    costCenter = "PROD-001"
    manager    = "henry.chen@techcorp.com"
    startDate  = "2021-11-08"
  })
}

resource "okta_user" "henry_vp_product" {
  first_name = "Henry"
  last_name  = "Chen"
  login      = "henry.chen@techcorp.com"
  email      = "henry.chen@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "Product"
    title      = "VP of Product"
    location   = "San Francisco"
    employeeType = "FullTime"
    level      = "VP"
    skills     = "Leadership,Strategy,Vision,Growth"
    costCenter = "PROD-001"
    manager    = ""
    startDate  = "2017-05-30"
  })
}

resource "okta_user" "ivy_intern" {
  first_name = "Ivy"
  last_name  = "Rodriguez"
  login      = "ivy.rodriguez@techcorp.com"
  email      = "ivy.rodriguez@techcorp.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Software Engineering Intern"
    location   = "San Francisco"
    employeeType = "Intern"
    level      = "Intern"
    skills     = "JavaScript,Python,Learning"
    costCenter = "ENG-001"
    manager    = "alice.johnson@techcorp.com"
    startDate  = "2023-06-01"
  })
}

# ========== No Groups - Pure Attribute-Based ==========
# This example intentionally has no Okta groups to demonstrate
# pure attribute-based group assignment

# ========== Outputs ==========
output "users_by_department" {
  description = "Users organized by department"
  value = {
    engineering = [
      okta_user.alice_senior_eng.email,
      okta_user.bob_principal_eng.email,
      okta_user.carol_ml_engineer.email,
      okta_user.frank_contractor.email,
      okta_user.ivy_intern.email,
    ]
    datascience = [
      okta_user.david_data_scientist.email,
    ]
    research = [
      okta_user.eve_research_director.email,
    ]
    product = [
      okta_user.grace_product_manager.email,
      okta_user.henry_vp_product.email,
    ]
  }
}

output "users_by_level" {
  description = "Users organized by level"
  value = {
    intern = [okta_user.ivy_intern.email]
    mid = [okta_user.carol_ml_engineer.email, okta_user.frank_contractor.email]
    senior = [okta_user.alice_senior_eng.email, okta_user.david_data_scientist.email, okta_user.grace_product_manager.email]
    principal = [okta_user.bob_principal_eng.email]
    director = [okta_user.eve_research_director.email]
    vp = [okta_user.henry_vp_product.email]
  }
}

output "users_by_location" {
  description = "Users organized by location"
  value = {
    san_francisco = [okta_user.alice_senior_eng.email, okta_user.eve_research_director.email, okta_user.henry_vp_product.email, okta_user.ivy_intern.email]
    remote = [okta_user.bob_principal_eng.email, okta_user.frank_contractor.email]
    new_york = [okta_user.carol_ml_engineer.email]
    austin = [okta_user.david_data_scientist.email]
    seattle = [okta_user.grace_product_manager.email]
  }
}

output "users_by_type" {
  description = "Users organized by employee type"
  value = {
    fulltime = [
      okta_user.alice_senior_eng.email,
      okta_user.bob_principal_eng.email,
      okta_user.carol_ml_engineer.email,
      okta_user.david_data_scientist.email,
      okta_user.eve_research_director.email,
      okta_user.grace_product_manager.email,
      okta_user.henry_vp_product.email,
    ]
    contractor = [okta_user.frank_contractor.email]
    intern = [okta_user.ivy_intern.email]
  }
}