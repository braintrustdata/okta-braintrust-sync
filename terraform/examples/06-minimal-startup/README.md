# Example 6: Minimal Startup Team

This example demonstrates a simple, scalable setup for small teams with streamlined permissions focusing on velocity and collaboration while maintaining room for growth.

## User Structure

### Users (6 total) - Typical Early-Stage Startup Team

#### Founders (2 users)
- **Alex Chen** - Founder & CEO, Leadership department, San Francisco
- **Sarah Kim** - Co-founder & CTO, Engineering department, San Francisco

#### Core Team (4 users)
- **Mike Rodriguez** - Lead Engineer, Senior level, Remote
- **Emily Johnson** - Product Manager, Mid level, Austin
- **David Park** - Data Scientist, Mid level, New York
- **Lisa Wong** - Designer & Marketing, Mid level, Seattle

## Simple Role-Based Access Strategy

### Okta Groups (Role-Based)
- **BT-Founders**: Alex, Sarah (company founders)
- **BT-Leadership**: Alex, Sarah, Mike (leadership team)
- **BT-Engineers**: Sarah, Mike (engineering team)
- **BT-Product-Team**: Alex, Emily, Lisa (product and design)
- **BT-Data-Team**: David (data science team)
- **BT-All-Team**: Everyone (company-wide access)

### Attribute-Based Groups (Growth-Ready)
- **CompanyFounders**: Alex, Sarah (isFounder=true)
- **EngineeringDept**: Sarah, Mike (department=Engineering)
- **ProductDept**: Emily (department=Product)
- **DataDept**: David (department=Data)
- **DesignDept**: Lisa (department=Design)
- **LeadershipDept**: Alex (department=Leadership)
- **FullStackDevelopers**: Mike (skills contain FullStack)
- **MLSpecialists**: David (skills contain MachineLearning)
- **ProductManagers**: Emily (skills contain ProductManagement)
- **Designers**: Lisa (skills contain Design/UX/UI)
- **DevOpsTeam**: Sarah (skills contain DevOps)
- **StrategicLeadership**: Alex, Sarah (skills contain Leadership)
- **SeniorTeamMembers**: Mike (level=Senior)
- **MidLevelTeamMembers**: Emily, David, Lisa (level=Mid)
- **EarlyEmployees**: Mike, Emily, David, Lisa (startDate=2023)

## Startup-Focused Role System

### Roles (Minimal but Scalable)
- **FounderRole**: Full organizational access including all ACL permissions
- **LeadershipRole**: Broad strategic access with project ACL management
- **TeamMemberRole**: Collaborative development access with experiment/dataset deletion
- **EngineeringRole**: Technical development focus with full CRUD access
- **ProductRole**: Product management with project creation and ACL management
- **DataRole**: Analytics and ML focus with experiment/dataset CRUD

## Project Access Patterns

### Founder/Leadership Projects
- **Pattern**: `company-*`, `startup-*`, `founder-*`, `team-*`, `strategic-*`
- **Access**: FounderRole for founders, LeadershipRole for leadership team
- **Examples**: `company-strategic-planning`, `startup-roadmap-2024`, `founder-investor-updates`

### Engineering Projects
- **Pattern**: `dev-*`, `backend-*`, `frontend-*`, `api-*`, `app-*`, `infra-*`
- **Access**: EngineeringRole for engineers, TeamMemberRole for others
- **Examples**: `dev-mvp-platform`, `backend-user-service`, `api-core-services`

### Product Projects
- **Pattern**: `product-*`, `feature-*`, `user-*`, `market-*`, `strategy-*`
- **Access**: ProductRole for product team, TeamMemberRole for others
- **Examples**: `product-user-research`, `feature-onboarding-flow`, `strategy-go-to-market`

### Data Projects
- **Pattern**: `data-*`, `analytics-*`, `ml-*`, `model-*`, `insight-*`
- **Access**: DataRole for data team, TeamMemberRole for others
- **Examples**: `data-user-analytics`, `ml-recommendation-engine`, `analytics-dashboard`

### Team/Shared Projects
- **Pattern**: `team-*`, `company-*`, `shared-*`, `startup-*`, `internal-*`
- **Access**: TeamMemberRole for all team members
- **Examples**: `team-collaboration-docs`, `shared-design-system`, `startup-process-documentation`

### Design/Creative Projects
- **Pattern**: `design-*`, `ui-*`, `ux-*`, `creative-*`, `brand-*`
- **Access**: TeamMemberRole for designers, ProductRole for product team
- **Examples**: `design-brand-identity`, `ui-design-system`, `creative-marketing-assets`

## Expected Group Memberships
- **Alex**: Founders, Leadership, ProductTeam, AllTeam, CompanyFounders, LeadershipDept, StrategicLeadership
- **Sarah**: Founders, Leadership, Engineers, AllTeam, CompanyFounders, EngineeringDept, DevOpsTeam, StrategicLeadership
- **Mike**: Leadership, Engineers, AllTeam, EngineeringDept, FullStackDevelopers, SeniorTeamMembers, EarlyEmployees
- **Emily**: ProductTeam, AllTeam, ProductDept, ProductManagers, MidLevelTeamMembers, EarlyEmployees
- **David**: DataTeam, AllTeam, DataDept, MLSpecialists, MidLevelTeamMembers, EarlyEmployees
- **Lisa**: ProductTeam, AllTeam, DesignDept, Designers, MidLevelTeamMembers, EarlyEmployees

## Usage

### 1. Deploy Okta Resources
```bash
cd terraform/examples/06-minimal-startup

export TF_VAR_okta_org_name="your-okta-org"
export TF_VAR_okta_api_token="your-okta-token"

terraform init
terraform plan
terraform apply
```

### 2. Test Projects to Create in Braintrust
Create these projects to test startup team access patterns:

**Founder/Leadership Projects:**
- `company-strategic-planning`
- `startup-roadmap-2024`
- `founder-investor-updates`
- `team-hiring-pipeline`

**Engineering Projects:**
- `dev-mvp-platform`
- `backend-user-service`
- `frontend-web-app`
- `api-core-services`
- `infra-aws-deployment`
- `app-mobile-prototype`

**Product Projects:**
- `product-user-research`
- `feature-onboarding-flow`
- `market-competitive-analysis`
- `product-roadmap-q3`
- `user-feedback-system`
- `strategy-go-to-market`

**Data Projects:**
- `data-user-analytics`
- `ml-recommendation-engine`
- `analytics-dashboard`
- `data-pipeline-events`
- `insight-user-behavior`
- `model-churn-prediction`

**Team/Shared Projects:**
- `team-collaboration-docs`
- `company-knowledge-base`
- `startup-process-documentation`
- `shared-design-system`
- `team-weekly-metrics`
- `internal-tools-development`

**Design/Creative Projects:**
- `design-brand-identity`
- `ui-design-system`
- `ux-user-journey-mapping`
- `creative-marketing-assets`
- `brand-website-design`

### 3. Run Sync
```bash
export OKTA_API_TOKEN="your-okta-token"
export OKTA_ORG_NAME="your-okta-org"
export BRAINTRUST_PROD_API_KEY="your-prod-key"
export BRAINTRUST_DEV_API_KEY="your-dev-key"

python -m sync.cli sync --config terraform/examples/06-minimal-startup/sync-config.yaml
```

## Expected Results

### Founder Control
- **Founders** (Alex, Sarah): FounderRole on ALL projects (complete organizational control)
- **Company Founders**: FounderRole ensuring founder-level access through both groups and attributes

### Leadership Access
- **Leadership Team** (Alex, Sarah, Mike): LeadershipRole on ALL projects (broad strategic access)
- **Strategic Leadership**: LeadershipRole for users with leadership skills

### Department-Based Access
- **Engineers**: EngineeringRole on dev/tech projects (full development access)
- **Product Team**: ProductRole on product/strategy projects (product management focus)
- **Data Team**: DataRole on data/analytics/ML projects (specialized data access)

### Collaborative Access
- **All Team**: TeamMemberRole on team/company/shared projects (collaborative access)
- **Team Employees**: TeamMemberRole on team/shared/collaboration projects

### Skill-Based Specialization
- **Full-Stack Developers** (Mike): EngineeringRole on fullstack/web projects
- **ML Specialists** (David): DataRole on ML/AI/prediction projects
- **Product Managers** (Emily): ProductRole on product/PM/strategy projects
- **Designers** (Lisa): TeamMemberRole on design/UI/UX projects
- **DevOps Team** (Sarah): EngineeringRole on devops/infrastructure projects

### Experience-Based Access
- **Senior Team Members** (Mike): TeamMemberRole on all non-founder/confidential projects
- **Mid-Level Team Members** (Emily, David, Lisa): TeamMemberRole on all non-strategic projects
- **Early Employees**: TeamMemberRole on early/founding/startup projects

## Startup-Optimized Features

### Growth-Ready Structure
- Simple role hierarchy that scales with team growth
- Department-based groups ready for new hires
- Skill-based groups for specialization as team grows
- Founder control maintained while enabling delegation

### Velocity-Focused Configuration
- Reduced sync frequency (every 6 hours) for small team overhead
- Collaborative permissions emphasizing team access over restrictions
- Minimal bureaucracy while maintaining basic access control
- Simple audit requirements appropriate for startup stage

### Scalability Preparation
- Groups established for common startup departments
- Attribute-based assignment ready for complex scenarios
- Role system that accommodates both generalists and specialists
- Foundation for adding security and compliance features as company grows

This demonstrates how early-stage startups can implement structured access control without sacrificing velocity, while building a foundation that scales with company growth.

## Cleanup
```bash
terraform destroy
```