# =====================================================================
# Example 3: Department-Based Structure
# =====================================================================
# This example demonstrates department-centric organization with:
# - 9 users across 4 departments (Engineering, Data, Product, Operations)
# - Hybrid strategy: both Okta groups AND attributes
# - Department-specific roles and project access patterns
# - Cross-departmental collaboration projects
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

# ========== Department-Based Users ==========
# Engineering Department
resource "okta_user" "alex_backend" {
  first_name = "Alex"
  last_name  = "Thompson"
  login      = "alex.thompson@datatech.com"
  email      = "alex.thompson@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Backend Engineer"
    location   = "Austin"
    employeeType = "FullTime"
    level      = "Mid"
    specialization = "Backend"
    yearsExperience = "3"
    manager    = "sarah.kim@datatech.com"
  })
}

resource "okta_user" "sarah_eng_manager" {
  first_name = "Sarah"
  last_name  = "Kim"
  login      = "sarah.kim@datatech.com"
  email      = "sarah.kim@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Engineering"
    title      = "Engineering Manager"
    location   = "Seattle"
    employeeType = "FullTime"
    level      = "Manager"
    specialization = "Management"
    yearsExperience = "8"
    manager    = ""
  })
}

# Data Department
resource "okta_user" "maya_data_engineer" {
  first_name = "Maya"
  last_name  = "Patel"
  login      = "maya.patel@datatech.com"
  email      = "maya.patel@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Data"
    title      = "Data Engineer"
    location   = "Denver"
    employeeType = "FullTime"
    level      = "Senior"
    specialization = "DataEngineering"
    yearsExperience = "5"
    manager    = "raj.singh@datatech.com"
  })
}

resource "okta_user" "raj_data_scientist" {
  first_name = "Raj"
  last_name  = "Singh"
  login      = "raj.singh@datatech.com"
  email      = "raj.singh@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Data"
    title      = "Senior Data Scientist"
    location   = "Boston"
    employeeType = "FullTime"
    level      = "Senior"
    specialization = "DataScience"
    yearsExperience = "6"
    manager    = "lisa.chen@datatech.com"
  })
}

resource "okta_user" "lisa_data_director" {
  first_name = "Lisa"
  last_name  = "Chen"
  login      = "lisa.chen@datatech.com"
  email      = "lisa.chen@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Data"
    title      = "Director of Data"
    location   = "San Francisco"
    employeeType = "FullTime"
    level      = "Director"
    specialization = "Leadership"
    yearsExperience = "12"
    manager    = ""
  })
}

# Product Department
resource "okta_user" "james_product_manager" {
  first_name = "James"
  last_name  = "Wilson"
  login      = "james.wilson@datatech.com"
  email      = "james.wilson@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Product"
    title      = "Product Manager"
    location   = "New York"
    employeeType = "FullTime"
    level      = "Mid"
    specialization = "ProductManagement"
    yearsExperience = "4"
    manager    = "anna.rodriguez@datatech.com"
  })
}

resource "okta_user" "anna_product_director" {
  first_name = "Anna"
  last_name  = "Rodriguez"
  login      = "anna.rodriguez@datatech.com"
  email      = "anna.rodriguez@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Product"
    title      = "Director of Product"
    location   = "Los Angeles"
    employeeType = "FullTime"
    level      = "Director"
    specialization = "ProductStrategy"
    yearsExperience = "10"
    manager    = ""
  })
}

# Operations Department
resource "okta_user" "david_devops" {
  first_name = "David"
  last_name  = "Martinez"
  login      = "david.martinez@datatech.com"
  email      = "david.martinez@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Operations"
    title      = "DevOps Engineer"
    location   = "Chicago"
    employeeType = "FullTime"
    level      = "Senior"
    specialization = "DevOps"
    yearsExperience = "7"
    manager    = "kevin.brown@datatech.com"
  })
}

resource "okta_user" "kevin_ops_manager" {
  first_name = "Kevin"
  last_name  = "Brown"
  login      = "kevin.brown@datatech.com"
  email      = "kevin.brown@datatech.com"
  
  custom_profile_attributes = jsonencode({
    department = "Operations"
    title      = "Operations Manager"
    location   = "Portland"
    employeeType = "FullTime"
    level      = "Manager"
    specialization = "Operations"
    yearsExperience = "9"
    manager    = ""
  })
}

# ========== Department Groups ==========
resource "okta_group" "bt_engineering_dept" {
  name        = "BT-Engineering-Dept"
  description = "Engineering Department for Braintrust access"
}

resource "okta_group" "bt_data_dept" {
  name        = "BT-Data-Dept"
  description = "Data Department for Braintrust access"
}

resource "okta_group" "bt_product_dept" {
  name        = "BT-Product-Dept"
  description = "Product Department for Braintrust access"
}

resource "okta_group" "bt_operations_dept" {
  name        = "BT-Operations-Dept"
  description = "Operations Department for Braintrust access"
}

# ========== Role-Based Groups ==========
resource "okta_group" "bt_managers" {
  name        = "BT-Managers"
  description = "All department managers"
}

resource "okta_group" "bt_directors" {
  name        = "BT-Directors"
  description = "All department directors"
}

resource "okta_group" "bt_senior_staff" {
  name        = "BT-Senior-Staff"
  description = "Senior level staff across departments"
}

# ========== Cross-Department Groups ==========
resource "okta_group" "bt_tech_leads" {
  name        = "BT-Tech-Leads"
  description = "Technical leaders across Engineering, Data, and Operations"
}

# ========== Group Memberships ==========
# Department Groups
resource "okta_group_memberships" "engineering_dept" {
  group_id = okta_group.bt_engineering_dept.id
  users = [
    okta_user.alex_backend.id,
    okta_user.sarah_eng_manager.id,
  ]
}

resource "okta_group_memberships" "data_dept" {
  group_id = okta_group.bt_data_dept.id
  users = [
    okta_user.maya_data_engineer.id,
    okta_user.raj_data_scientist.id,
    okta_user.lisa_data_director.id,
  ]
}

resource "okta_group_memberships" "product_dept" {
  group_id = okta_group.bt_product_dept.id
  users = [
    okta_user.james_product_manager.id,
    okta_user.anna_product_director.id,
  ]
}

resource "okta_group_memberships" "operations_dept" {
  group_id = okta_group.bt_operations_dept.id
  users = [
    okta_user.david_devops.id,
    okta_user.kevin_ops_manager.id,
  ]
}

# Role-Based Groups
resource "okta_group_memberships" "managers" {
  group_id = okta_group.bt_managers.id
  users = [
    okta_user.sarah_eng_manager.id,
    okta_user.kevin_ops_manager.id,
  ]
}

resource "okta_group_memberships" "directors" {
  group_id = okta_group.bt_directors.id
  users = [
    okta_user.lisa_data_director.id,
    okta_user.anna_product_director.id,
  ]
}

resource "okta_group_memberships" "senior_staff" {
  group_id = okta_group.bt_senior_staff.id
  users = [
    okta_user.maya_data_engineer.id,
    okta_user.raj_data_scientist.id,
    okta_user.david_devops.id,
  ]
}

# Cross-Department Groups
resource "okta_group_memberships" "tech_leads" {
  group_id = okta_group.bt_tech_leads.id
  users = [
    okta_user.sarah_eng_manager.id,
    okta_user.maya_data_engineer.id,
    okta_user.raj_data_scientist.id,
    okta_user.david_devops.id,
  ]
}

# ========== Outputs ==========
output "departments" {
  description = "Users organized by department"
  value = {
    engineering = [
      okta_user.alex_backend.email,
      okta_user.sarah_eng_manager.email,
    ]
    data = [
      okta_user.maya_data_engineer.email,
      okta_user.raj_data_scientist.email,
      okta_user.lisa_data_director.email,
    ]
    product = [
      okta_user.james_product_manager.email,
      okta_user.anna_product_director.email,
    ]
    operations = [
      okta_user.david_devops.email,
      okta_user.kevin_ops_manager.email,
    ]
  }
}

output "leadership" {
  description = "Leadership structure"
  value = {
    directors = [
      okta_user.lisa_data_director.email,
      okta_user.anna_product_director.email,
    ]
    managers = [
      okta_user.sarah_eng_manager.email,
      okta_user.kevin_ops_manager.email,
    ]
    senior_staff = [
      okta_user.maya_data_engineer.email,
      okta_user.raj_data_scientist.email,
      okta_user.david_devops.email,
    ]
  }
}

output "cross_functional" {
  description = "Cross-functional groups"
  value = {
    tech_leads = [
      okta_user.sarah_eng_manager.email,
      okta_user.maya_data_engineer.email,
      okta_user.raj_data_scientist.email,
      okta_user.david_devops.email,
    ]
  }
}

output "groups_created" {
  description = "All groups created"
  value = {
    departments = [
      okta_group.bt_engineering_dept.name,
      okta_group.bt_data_dept.name,
      okta_group.bt_product_dept.name,
      okta_group.bt_operations_dept.name,
    ]
    roles = [
      okta_group.bt_managers.name,
      okta_group.bt_directors.name,
      okta_group.bt_senior_staff.name,
    ]
    cross_functional = [
      okta_group.bt_tech_leads.name,
    ]
  }
}