# =====================================================================
# Example 5: Contractor/External Access Management
# =====================================================================
# This example demonstrates security-focused access patterns for external users:
# - 9 users with mix of employees, contractors, vendors, and consultants
# - Security-focused groups based on employment type and access level
# - Restricted access patterns with time-limited and project-specific permissions
# - Demonstrates external user management and compliance requirements
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

# ========== Internal Employees ==========
resource "okta_user" "alice_security_lead" {
  first_name = "Alice"
  last_name  = "Johnson"
  login      = "alice.johnson@securetech.com"
  email      = "alice.johnson@securetech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Security"
    title      = "Security Lead"
    location   = "San Francisco"
    employeeType = "Employee"
    level      = "Senior"
    clearanceLevel = "Internal"
    contractEndDate = ""
    vendorCompany = ""
    accessRestrictions = "None"
    projectAssignments = "All"
  })
}

resource "okta_user" "bob_project_manager" {
  first_name = "Bob"
  last_name  = "Smith"
  login      = "bob.smith@securetech.com"
  email      = "bob.smith@securetech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Project Manager"
    location   = "Austin"
    employeeType = "Employee"
    level      = "Senior"
    clearanceLevel = "Internal"
    contractEndDate = ""
    vendorCompany = ""
    accessRestrictions = "None"
    projectAssignments = "All"
  })
}

resource "okta_user" "carol_data_engineer" {
  first_name = "Carol"
  last_name  = "Davis"
  login      = "carol.davis@securetech.com"
  email      = "carol.davis@securetech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Data Engineer"
    location   = "Remote"
    employeeType = "Employee"
    level      = "Mid"
    clearanceLevel = "Internal"
    contractEndDate = ""
    vendorCompany = ""
    accessRestrictions = "None"
    projectAssignments = "DataProjects"
  })
}

# ========== Short-term Contractors ==========
resource "okta_user" "david_frontend_contractor" {
  first_name = "David"
  last_name  = "Wilson"
  login      = "david.wilson@freelance.com"
  email      = "david.wilson@freelance.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Frontend Developer"
    location   = "Remote"
    employeeType = "Contractor"
    level      = "Mid"
    clearanceLevel = "Limited"
    contractEndDate = "2024-06-30"
    vendorCompany = "Freelance"
    accessRestrictions = "PublicProjectsOnly"
    projectAssignments = "UIProjects"
  })
}

resource "okta_user" "eve_qa_contractor" {
  first_name = "Eve"
  last_name  = "Brown"
  login      = "eve.brown@testpro.com"
  email      = "eve.brown@testpro.com"
  
  custom_profile_attributes = jsonencode({
    department = "QA"
    title      = "QA Contractor"
    location   = "Denver"
    employeeType = "Contractor"
    level      = "Mid"
    clearanceLevel = "Limited"
    contractEndDate = "2024-09-15"
    vendorCompany = "TestPro Solutions"
    accessRestrictions = "TestingOnly"
    projectAssignments = "QAProjects"
  })
}

# ========== Vendor Representatives ==========
resource "okta_user" "frank_vendor_liaison" {
  first_name = "Frank"
  last_name  = "Garcia"
  login      = "frank.garcia@cloudvendor.com"
  email      = "frank.garcia@cloudvendor.com"
  
  custom_profile_attributes = jsonencode({
    department = "External"
    title      = "Technical Liaison"
    location   = "Chicago"
    employeeType = "Vendor"
    level = "Senior"
    clearanceLevel = "Restricted"
    contractEndDate = "2024-12-31"
    vendorCompany = "CloudVendor Inc"
    accessRestrictions = "VendorProjectsOnly"
    projectAssignments = "IntegrationProjects"
  })
}

resource "okta_user" "grace_vendor_support" {
  first_name = "Grace"
  last_name  = "Lee"
  login      = "grace.lee@datatools.com"
  email      = "grace.lee@datatools.com"
  
  custom_profile_attributes = jsonencode({
    department = "External"
    title      = "Support Engineer"
    location   = "Seattle"
    employeeType = "Vendor"
    level      = "Mid"
    clearanceLevel = "Restricted"
    contractEndDate = "2025-03-31"
    vendorCompany = "DataTools Corp"
    accessRestrictions = "SupportOnly"
    projectAssignments = "SupportProjects"
  })
}

# ========== External Consultants ==========
resource "okta_user" "henry_security_consultant" {
  first_name = "Henry"
  last_name  = "Chen"
  login      = "henry.chen@securityfirm.com"
  email      = "henry.chen@securityfirm.com"
  
  custom_profile_attributes = jsonencode({
    department = "Security"
    title      = "Security Consultant"
    location   = "Boston"
    employeeType = "Consultant"
    level      = "Expert"
    clearanceLevel = "Privileged"
    contractEndDate = "2024-08-31"
    vendorCompany = "Security Firm LLC"
    accessRestrictions = "SecurityProjectsOnly"
    projectAssignments = "SecurityProjects"
  })
}

resource "okta_user" "ivy_compliance_auditor" {
  first_name = "Ivy"
  last_name  = "Rodriguez"
  login      = "ivy.rodriguez@auditfirm.com"
  email      = "ivy.rodriguez@auditfirm.com"
  
  custom_profile_attributes = jsonencode({
    department = "Compliance"
    title      = "Compliance Auditor"
    location   = "New York"
    employeeType = "Consultant"
    level      = "Expert"
    clearanceLevel = "Audit"
    contractEndDate = "2024-07-15"
    vendorCompany = "Audit Firm Partners"
    accessRestrictions = "AuditOnly"
    projectAssignments = "ComplianceProjects"
  })
}

# ========== Employment Type Groups ==========
resource "okta_group" "bt_employees" {
  name        = "BT-Employees"
  description = "Full-time internal employees"
}

resource "okta_group" "bt_contractors" {
  name        = "BT-Contractors"
  description = "Short-term contractors and freelancers"
}

resource "okta_group" "bt_vendors" {
  name        = "BT-Vendors"
  description = "Vendor representatives and liaisons"
}

resource "okta_group" "bt_consultants" {
  name        = "BT-Consultants"
  description = "External consultants and specialists"
}

# ========== Security Clearance Groups ==========
resource "okta_group" "bt_internal_access" {
  name        = "BT-Internal-Access"
  description = "Internal clearance level access"
}

resource "okta_group" "bt_limited_access" {
  name        = "BT-Limited-Access"
  description = "Limited clearance level access"
}

resource "okta_group" "bt_restricted_access" {
  name        = "BT-Restricted-Access"
  description = "Restricted clearance level access"
}

resource "okta_group" "bt_privileged_access" {
  name        = "BT-Privileged-Access"
  description = "Privileged clearance level access"
}

resource "okta_group" "bt_audit_access" {
  name        = "BT-Audit-Access"
  description = "Audit-specific access for compliance"
}

# ========== Project Access Groups ==========
resource "okta_group" "bt_public_projects" {
  name        = "BT-Public-Projects"
  description = "Access to public and open-source projects"
}

resource "okta_group" "bt_external_safe" {
  name        = "BT-External-Safe"
  description = "External-safe projects without sensitive data"
}

# ========== Group Memberships ==========
# Employment Type Groups
resource "okta_group_memberships" "employees" {
  group_id = okta_group.bt_employees.id
  users = [
    okta_user.alice_security_lead.id,
    okta_user.bob_project_manager.id,
    okta_user.carol_data_engineer.id,
  ]
}

resource "okta_group_memberships" "contractors" {
  group_id = okta_group.bt_contractors.id
  users = [
    okta_user.david_frontend_contractor.id,
    okta_user.eve_qa_contractor.id,
  ]
}

resource "okta_group_memberships" "vendors" {
  group_id = okta_group.bt_vendors.id
  users = [
    okta_user.frank_vendor_liaison.id,
    okta_user.grace_vendor_support.id,
  ]
}

resource "okta_group_memberships" "consultants" {
  group_id = okta_group.bt_consultants.id
  users = [
    okta_user.henry_security_consultant.id,
    okta_user.ivy_compliance_auditor.id,
  ]
}

# Security Clearance Groups
resource "okta_group_memberships" "internal_access" {
  group_id = okta_group.bt_internal_access.id
  users = [
    okta_user.alice_security_lead.id,
    okta_user.bob_project_manager.id,
    okta_user.carol_data_engineer.id,
  ]
}

resource "okta_group_memberships" "limited_access" {
  group_id = okta_group.bt_limited_access.id
  users = [
    okta_user.david_frontend_contractor.id,
    okta_user.eve_qa_contractor.id,
  ]
}

resource "okta_group_memberships" "restricted_access" {
  group_id = okta_group.bt_restricted_access.id
  users = [
    okta_user.frank_vendor_liaison.id,
    okta_user.grace_vendor_support.id,
  ]
}

resource "okta_group_memberships" "privileged_access" {
  group_id = okta_group.bt_privileged_access.id
  users = [
    okta_user.henry_security_consultant.id,
  ]
}

resource "okta_group_memberships" "audit_access" {
  group_id = okta_group.bt_audit_access.id
  users = [
    okta_user.ivy_compliance_auditor.id,
  ]
}

# Project Access Groups
resource "okta_group_memberships" "public_projects" {
  group_id = okta_group.bt_public_projects.id
  users = [
    okta_user.david_frontend_contractor.id,
    okta_user.eve_qa_contractor.id,
  ]
}

resource "okta_group_memberships" "external_safe" {
  group_id = okta_group.bt_external_safe.id
  users = [
    okta_user.david_frontend_contractor.id,
    okta_user.eve_qa_contractor.id,
    okta_user.frank_vendor_liaison.id,
    okta_user.grace_vendor_support.id,
  ]
}

# ========== Outputs ==========
output "employment_types" {
  description = "Users organized by employment type"
  value = {
    employees = [
      okta_user.alice_security_lead.email,
      okta_user.bob_project_manager.email,
      okta_user.carol_data_engineer.email,
    ]
    contractors = [
      okta_user.david_frontend_contractor.email,
      okta_user.eve_qa_contractor.email,
    ]
    vendors = [
      okta_user.frank_vendor_liaison.email,
      okta_user.grace_vendor_support.email,
    ]
    consultants = [
      okta_user.henry_security_consultant.email,
      okta_user.ivy_compliance_auditor.email,
    ]
  }
}

output "clearance_levels" {
  description = "Users organized by security clearance level"
  value = {
    internal = [
      okta_user.alice_security_lead.email,
      okta_user.bob_project_manager.email,
      okta_user.carol_data_engineer.email,
    ]
    limited = [
      okta_user.david_frontend_contractor.email,
      okta_user.eve_qa_contractor.email,
    ]
    restricted = [
      okta_user.frank_vendor_liaison.email,
      okta_user.grace_vendor_support.email,
    ]
    privileged = [
      okta_user.henry_security_consultant.email,
    ]
    audit = [
      okta_user.ivy_compliance_auditor.email,
    ]
  }
}

output "contract_details" {
  description = "Contract end dates and vendor companies"
  value = {
    expiring_soon = {
      "henry.chen@securityfirm.com" = "2024-08-31"
      "ivy.rodriguez@auditfirm.com" = "2024-07-15"
      "david.wilson@freelance.com" = "2024-06-30"
    }
    vendor_companies = {
      "frank.garcia@cloudvendor.com" = "CloudVendor Inc"
      "grace.lee@datatools.com" = "DataTools Corp"
      "henry.chen@securityfirm.com" = "Security Firm LLC"
      "ivy.rodriguez@auditfirm.com" = "Audit Firm Partners"
    }
  }
}

output "groups_created" {
  description = "All security and access groups created"
  value = {
    employment_types = [
      okta_group.bt_employees.name,
      okta_group.bt_contractors.name,
      okta_group.bt_vendors.name,
      okta_group.bt_consultants.name,
    ]
    clearance_levels = [
      okta_group.bt_internal_access.name,
      okta_group.bt_limited_access.name,
      okta_group.bt_restricted_access.name,
      okta_group.bt_privileged_access.name,
      okta_group.bt_audit_access.name,
    ]
    project_access = [
      okta_group.bt_public_projects.name,
      okta_group.bt_external_safe.name,
    ]
  }
}