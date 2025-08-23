# Example 3: Department-Based Structure

This example demonstrates department-centric organization with hybrid strategy (both Okta groups AND attributes) using 9 users across 4 departments.

## User Structure

### Users (9 total) Across 4 Departments

#### Engineering Department (2 users)
- **Alex Thompson** - Backend Engineer, Mid, Austin, Backend specialization
- **Sarah Kim** - Engineering Manager, Manager, Seattle, Management specialization

#### Data Department (3 users)
- **Maya Patel** - Data Engineer, Senior, Denver, DataEngineering specialization
- **Raj Singh** - Senior Data Scientist, Senior, Boston, DataScience specialization
- **Lisa Chen** - Director of Data, Director, San Francisco, Leadership specialization

#### Product Department (2 users)
- **James Wilson** - Product Manager, Mid, New York, ProductManagement specialization
- **Anna Rodriguez** - Director of Product, Director, Los Angeles, ProductStrategy specialization

#### Operations Department (2 users)
- **David Martinez** - DevOps Engineer, Senior, Chicago, DevOps specialization
- **Kevin Brown** - Operations Manager, Manager, Portland, Operations specialization

## Hybrid Group Assignment Strategy

### Okta Groups (Explicit Department and Role Groups)
- **BT-Engineering-Dept**: Alex, Sarah
- **BT-Data-Dept**: Maya, Raj, Lisa
- **BT-Product-Dept**: James, Anna
- **BT-Operations-Dept**: David, Kevin
- **BT-Managers**: Sarah, Kevin
- **BT-Directors**: Lisa, Anna
- **BT-Senior-Staff**: Maya, Raj, David
- **BT-Tech-Leads**: Sarah, Maya, Raj, David

### Attribute-Based Groups (Specialized and Experience Groups)
- **BackendSpecialists**: Alex (specialization=Backend)
- **DataEngineers**: Maya (specialization=DataEngineering)
- **DataScientists**: Raj (specialization=DataScience)
- **DevOpsTeam**: David (specialization=DevOps)
- **ProductManagers**: James (specialization contains Product)
- **ExperiencedProfessionals**: Maya, Raj, David (5+ years experience)
- **ManagementTrack**: Sarah, Kevin (level=Manager/Director)
- **TechnicalLeadership**: Lisa (specialization=Leadership + technical dept)

## Department-Focused Role System

### Custom Department Roles
- **EngineeringRole**: Full development access, delete experiments only
- **DataRole**: Analytics/ML focus, experiment and dataset CRUD
- **ProductRole**: Project management focus, project CRUD + ACLs
- **OperationsRole**: Infrastructure focus, full access
- **DepartmentManager**: Team oversight, project ACLs
- **Director**: Cross-departmental oversight, full ACL permissions
- **SeniorSpecialist**: Advanced technical access
- **TechnicalLead**: Cross-team coordination, project ACL read/update

## Project Assignment Patterns

### Department-Specific Projects
- **Engineering**: `backend`, `api`, `service`, `web`, `mobile`, `app` projects
- **Data**: `data`, `analytics`, `ml`, `model`, `etl`, `pipeline`, `research` projects
- **Product**: `product`, `feature`, `user`, `customer`, `roadmap` projects
- **Operations**: `infra`, `deploy`, `ops`, `monitoring`, `platform` projects

### Cross-Departmental Projects
- **Tech Leads**: `cross-team`, `integration`, `platform`, `shared` projects
- **Senior Staff**: All projects except `*-restricted` and `*-sensitive`
- **Management Track**: `team`, `management`, `leadership`, `strategy` projects
- **Technical Leadership**: `architecture`, `platform`, `standards`, `review` projects

### Expected Group Memberships
- **Alex**: EngineeringDept, BackendSpecialists
- **Sarah**: EngineeringDept, Managers, TechLeads, ManagementTrack
- **Maya**: DataDept, SeniorStaff, TechLeads, DataEngineers, ExperiencedProfessionals
- **Raj**: DataDept, SeniorStaff, TechLeads, DataScientists, ExperiencedProfessionals
- **Lisa**: DataDept, Directors, TechnicalLeadership
- **James**: ProductDept, ProductManagers
- **Anna**: ProductDept, Directors
- **David**: OperationsDept, SeniorStaff, TechLeads, DevOpsTeam, ExperiencedProfessionals
- **Kevin**: OperationsDept, Managers, ManagementTrack

## Usage

### 1. Deploy Okta Resources
```bash
cd terraform/examples/03-department-based

export TF_VAR_okta_org_name="your-okta-org"
export TF_VAR_okta_api_token="your-okta-token"

terraform init
terraform plan
terraform apply
```

### 2. Test Projects to Create in Braintrust
Create these projects to test department-based access patterns:

**Engineering Projects:**
- `backend-user-service`
- `api-gateway-platform`
- `web-dashboard-frontend`
- `mobile-app-ios`

**Data Projects:**
- `data-analytics-warehouse`
- `ml-recommendation-model`
- `etl-customer-pipeline`
- `research-nlp-analysis`
- `experiment-ab-testing`

**Product Projects:**
- `product-user-onboarding`
- `feature-recommendation-ui`
- `customer-feedback-system`
- `roadmap-planning-tool`

**Operations Projects:**
- `infra-kubernetes-platform`
- `deploy-ci-cd-pipeline`
- `monitoring-observability`
- `platform-shared-services`

**Cross-Departmental Projects:**
- `cross-team-integration`
- `shared-component-library`
- `platform-developer-tools`
- `architecture-standards`
- `team-collaboration-tools`

### 3. Run Sync
```bash
export OKTA_API_TOKEN="your-okta-token"
export OKTA_ORG_NAME="your-okta-org"
export BRAINTRUST_PROD_API_KEY="your-prod-key"
export BRAINTRUST_DEV_API_KEY="your-dev-key"

python -m sync.cli sync --config terraform/examples/03-department-based/sync-config.yaml
```

## Expected Results

### Department-Specific Access
- **Engineering Dept**: EngineeringRole on backend/api/web/mobile projects
- **Data Dept**: DataRole on data/analytics/ml/research projects
- **Product Dept**: ProductRole on product/feature/customer projects
- **Operations Dept**: OperationsRole on infra/deploy/monitoring projects

### Leadership Access
- **Directors** (Lisa, Anna): Director role on ALL projects
- **Managers** (Sarah, Kevin): DepartmentManager role on non-restricted projects

### Specialization Access
- **Backend Specialists** (Alex): EngineeringRole on backend/api/microservice projects
- **Data Engineers** (Maya): DataRole on etl/pipeline/data-platform projects
- **Data Scientists** (Raj): DataRole on ml/model/algorithm projects
- **DevOps Team** (David): OperationsRole on infra/deploy/ci-cd projects
- **Product Managers** (James): ProductRole on product/feature/roadmap projects

### Cross-Functional Access
- **Tech Leads**: TechnicalLead role on cross-team/integration/platform projects
- **Senior Staff**: SeniorSpecialist role on all non-restricted projects
- **Experienced Professionals**: SeniorSpecialist role excluding intern/training projects

This demonstrates how department-centric organization can provide both clear departmental boundaries and flexible cross-functional collaboration through hybrid group assignment strategies.

## Cleanup
```bash
terraform destroy
```