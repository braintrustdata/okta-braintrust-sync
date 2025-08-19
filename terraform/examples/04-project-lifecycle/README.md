# Example 4: Project Lifecycle Management

This example demonstrates project lifecycle-based access control with stage-specific roles and escalating permissions through project maturity phases.

## User Structure

### Users (8 total) Across Project Lifecycle Phases

#### Planning Phase (2 users)
- **Emma Thompson** - Product Owner, Senior, Seattle, 6 years experience
- **Mike Davis** - Business Analyst, Mid, Austin, 3 years experience

#### Development Phase (2 users)
- **Sara Wilson** - Lead Developer, Senior, San Francisco, 8 years experience
- **Jason Martinez** - Backend Developer, Mid, Denver, 4 years experience

#### Testing Phase (2 users)
- **Linda Chen** - QA Lead, Senior, Portland, 7 years experience
- **Tom Rodriguez** - QA Engineer, Mid, Chicago, 3 years experience

#### Production Phase (2 users)
- **Rachel Brown** - DevOps Lead, Senior, Boston, 9 years experience
- **Carlos Garcia** - Site Reliability Engineer, Senior, Miami, 5 years experience

## Lifecycle Access Strategy

### Okta Groups (Lifecycle Phases)
- **BT-Planning-Phase**: Emma, Mike
- **BT-Development-Phase**: Sara, Jason
- **BT-Testing-Phase**: Linda, Tom
- **BT-Production-Phase**: Rachel, Carlos
- **BT-Project-Leads**: Emma, Sara, Linda, Rachel
- **BT-Senior-Team**: Emma, Sara, Linda, Rachel, Carlos
- **BT-Cross-Phase-Access**: Emma, Sara, Linda, Rachel

### Attribute-Based Groups (Specializations)
- **RequirementsSpecialists**: Emma, Mike (responsibilities contain "Requirements")
- **ArchitectureTeam**: Sara (responsibilities contain "Architecture")
- **CodeReviewTeam**: Sara (responsibilities contain "CodeReview")
- **AutomationSpecialists**: Linda, Tom (responsibilities contain "Automation")
- **InfrastructureTeam**: Rachel (responsibilities contain "Infrastructure")
- **IncidentResponseTeam**: Carlos (responsibilities contain "Incident")
- **VeteranTeam**: Sara, Linda, Rachel (7+ years experience)
- **MidLevelContributors**: Mike, Jason, Tom (3-6 years experience)
- **DepartmentLeads**: Emma, Sara, Linda, Rachel (Lead/Manager/Owner titles)

## Lifecycle-Based Role System

### Stage-Specific Roles
- **PlanningRole**: Requirements and project setup focus
  - Read all, create/update projects, create/read project ACLs
- **DevelopmentRole**: Full development access
  - Create/read/update all, delete experiments/datasets
- **TestingRole**: Testing and validation focus
  - Read all, create/update/delete experiments
- **ProductionRole**: Operations and monitoring
  - Read all, create/update datasets, delete all, read ACLs
- **ProjectLeadRole**: Cross-phase oversight
  - Full access including project ACL management
- **SeniorContributorRole**: Broad technical access
  - Create/read/update all, delete experiments/datasets, read project ACLs
- **ArchitectRole**: Design authority
  - Full access including ACL read/update
- **OperationsRole**: Infrastructure focus
  - Read all, create/update datasets, delete all

## Project Access Patterns

### Lifecycle Stage Projects
- **Planning Phase**: `concept-*`, `planning-*`, `requirements-*`, `design-*`, `prototype-*`
- **Development Phase**: `dev-*`, `feature-*`, `api-*`, `service-*`, `app-*`, `build-*`
- **Testing Phase**: `test-*`, `qa-*`, `validation-*`, `verify-*`, `integration-*`
- **Production Phase**: `prod-*`, `live-*`, `ops-*`, `monitor-*`, `deploy-*`, `release-*`

### Specialized Access
- **Requirements Specialists**: `requirements`, `specs`, `analysis`, `business` projects
- **Architecture Team**: `architecture`, `design`, `platform`, `framework` projects
- **Code Review Team**: Development projects (dev/code/feature/api/service)
- **Automation Specialists**: `automation`, `ci-cd`, `pipeline`, `test-automation` projects
- **Infrastructure Team**: `infrastructure`, `deployment`, `kubernetes`, `cloud` projects
- **Incident Response**: `incident`, `emergency`, `hotfix`, `critical` projects

### Experience-Based Access
- **Veteran Team**: All projects except junior/training
- **Mid-Level Contributors**: All projects except senior/critical/prod
- **Department Leads**: Team and coordination projects

## Expected Group Memberships
- **Emma**: PlanningPhase, ProjectLeads, SeniorTeam, CrossPhaseAccess, RequirementsSpecialists, DepartmentLeads
- **Mike**: PlanningPhase, RequirementsSpecialists, MidLevelContributors
- **Sara**: DevelopmentPhase, ProjectLeads, SeniorTeam, CrossPhaseAccess, ArchitectureTeam, CodeReviewTeam, VeteranTeam, DepartmentLeads
- **Jason**: DevelopmentPhase, MidLevelContributors
- **Linda**: TestingPhase, ProjectLeads, SeniorTeam, CrossPhaseAccess, AutomationSpecialists, VeteranTeam, DepartmentLeads
- **Tom**: TestingPhase, AutomationSpecialists, MidLevelContributors
- **Rachel**: ProductionPhase, ProjectLeads, SeniorTeam, CrossPhaseAccess, InfrastructureTeam, VeteranTeam, DepartmentLeads
- **Carlos**: ProductionPhase, SeniorTeam, IncidentResponseTeam

## Usage

### 1. Deploy Okta Resources
```bash
cd terraform/examples/04-project-lifecycle

export TF_VAR_okta_org_name="your-okta-org"
export TF_VAR_okta_api_token="your-okta-token"

terraform init
terraform plan
terraform apply
```

### 2. Test Projects to Create in Braintrust
Create these projects to test lifecycle-based access patterns:

**Planning Phase Projects:**
- `concept-new-feature`
- `requirements-user-portal`
- `design-system-architecture`
- `planning-q4-roadmap`
- `prototype-recommendation-engine`

**Development Phase Projects:**
- `dev-user-authentication`
- `feature-payment-processing`
- `api-notification-service`
- `build-mobile-app`
- `implement-search-functionality`

**Testing Phase Projects:**
- `test-payment-integration`
- `qa-user-registration`
- `validation-performance-benchmarks`
- `integration-third-party-services`
- `automation-regression-suite`

**Production Phase Projects:**
- `prod-payment-gateway`
- `live-user-dashboard`
- `ops-monitoring-alerts`
- `deploy-recommendation-system`
- `monitor-api-performance`

**Cross-Phase Projects:**
- `architecture-microservices-platform`
- `team-collaboration-tools`
- `incident-response-system`
- `critical-security-updates`
- `cross-team-integration`

### 3. Run Sync
```bash
export OKTA_API_TOKEN="your-okta-token"
export OKTA_ORG_NAME="your-okta-org"
export BRAINTRUST_PROD_API_KEY="your-prod-key"
export BRAINTRUST_DEV_API_KEY="your-dev-key"

python -m sync.cli sync --config terraform/examples/04-project-lifecycle/sync-config.yaml
```

## Expected Results

### Lifecycle-Based Access
- **Planning Phase**: PlanningRole on concept/requirements/design projects
- **Development Phase**: DevelopmentRole on dev/feature/api/build projects  
- **Testing Phase**: TestingRole on test/qa/validation projects
- **Production Phase**: ProductionRole on prod/live/ops/deploy projects

### Leadership Access
- **Project Leads**: ProjectLeadRole on all non-restricted projects
- **Cross-Phase Access**: SeniorContributorRole on all non-restricted projects
- **Senior Team**: SeniorContributorRole on all non-intern projects

### Specialized Access
- **Architecture Team** (Sara): ArchitectRole on architecture/design/platform projects
- **Requirements Specialists** (Emma, Mike): PlanningRole on requirements/specs projects
- **Automation Specialists** (Linda, Tom): TestingRole on automation/ci-cd projects
- **Infrastructure Team** (Rachel): OperationsRole on infrastructure/deployment projects
- **Incident Response** (Carlos): ProductionRole on incident/emergency projects

### Experience-Based Access
- **Veteran Team**: SeniorContributorRole on all non-junior/training projects
- **Mid-Level Contributors**: DevelopmentRole on all non-senior/critical/prod projects
- **Department Leads**: ProjectLeadRole on team/coordination projects

This demonstrates how project lifecycle management can provide stage-appropriate access control while maintaining cross-functional collaboration and expertise-based specialization.

## Cleanup
```bash
terraform destroy
```