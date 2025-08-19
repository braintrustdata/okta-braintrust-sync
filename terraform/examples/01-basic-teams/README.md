# Example 1: Basic Team Structure

This example demonstrates a basic team structure with 8 users across 3 teams, showcasing the complete Groups → Roles → Projects workflow.

## Team Structure

### Users (8 total)
- **Engineering Team (3)**:
  - Alice Smith - Senior Software Engineer
  - Bob Johnson - Engineering Manager
  - Charlie Brown - Software Engineer

- **Data Science Team (3)**:
  - Diana Rodriguez - Senior Data Scientist  
  - Eve Wilson - Data Science Manager
  - Frank Lee - Data Scientist

- **Product Management Team (2)**:
  - Grace Chen - Senior Product Manager
  - Henry Davis - VP of Product

### Groups
- `BT-Engineering` - Engineering team members
- `BT-DataScience` - Data Science team members
- `BT-ProductManagement` - Product Management team members
- `BT-Managers` - All managers (Bob, Eve, Henry)
- `BT-AllEmployees` - All employees

## Workflow Demonstration

### 1. Okta → Braintrust Sync
- Users synced from Okta to Braintrust organizations
- Groups synced with BT- prefix mapping
- Profile attributes preserved

### 2. Group Assignment
- Users assigned to Braintrust groups based on Okta group memberships
- Direct mapping: `BT-Engineering` → `Engineering`

### 3. Role-Project Assignment
- **Roles Created**:
  - `Manager` - Full project management access
  - `Engineer` - Full development access
  - `DataScientist` - Experiment/dataset focused access
  - `ProductManager` - Product project management
  - `Employee` - Basic read access

- **Project Assignments**:
  - Managers → Manager role on ALL projects
  - Engineering → Engineer role on web/api/mobile/ML projects
  - DataScience → DataScientist role on research/data/ML projects
  - ProductManagement → ProductManager role on product/feature projects
  - AllEmployees → Employee role on shared/public projects

## Usage

### 1. Deploy Okta Resources
```bash
cd terraform/examples/01-basic-teams

# Set your Okta credentials
export TF_VAR_okta_org_name="your-okta-org"
export TF_VAR_okta_api_token="your-okta-token"

# Deploy
terraform init
terraform plan
terraform apply
```

### 2. Test Projects to Create in Braintrust
Create these test projects in your Braintrust organizations to see the role assignments:

**Engineering Projects:**
- `web-frontend-app`
- `api-backend-service` 
- `mobile-ios-app`
- `ml-recommendation-engine`
- `infrastructure-monitoring`

**Data Science Projects:**
- `research-nlp-models`
- `data-analytics-pipeline`
- `ml-fraud-detection`
- `experiment-ab-testing`

**Product Projects:**
- `product-user-dashboard`
- `feature-recommendation-ui`
- `customer-feedback-analysis`
- `roadmap-planning-tool`

**Shared Projects:**
- `shared-company-metrics`
- `public-demo-showcase`
- `all-hands-presentations`

### 3. Run Sync
```bash
# Set environment variables
export OKTA_API_TOKEN="your-okta-token"
export OKTA_ORG_NAME="your-okta-org"
export BRAINTRUST_PROD_API_KEY="your-prod-key"
export BRAINTRUST_DEV_API_KEY="your-dev-key"

# Run sync with the config
python -m sync.cli sync --config terraform/examples/01-basic-teams/sync-config.yaml
```

## Expected Results

### Group Memberships
- Alice, Bob, Charlie → Engineering group
- Diana, Eve, Frank → DataScience group  
- Grace, Henry → ProductManagement group
- Bob, Eve, Henry → Managers group
- All users → AllEmployees group

### Role Assignments by Project Pattern
- **web-frontend-app**: Engineering→Engineer, Managers→Manager, AllEmployees→Employee
- **research-nlp-models**: DataScience→DataScientist, Managers→Manager
- **product-user-dashboard**: ProductManagement→ProductManager, Managers→Manager
- **shared-company-metrics**: AllEmployees→Employee, Managers→Manager

### Permission Examples
- **Bob (Engineering Manager)**: Manager role = full access everywhere
- **Alice (Senior Engineer)**: Engineer role on engineering/ML projects, Employee role on shared projects
- **Diana (Senior Data Scientist)**: DataScientist role on research/data/ML projects, Employee role on shared projects
- **Grace (Product Manager)**: ProductManager role on product projects, Employee role on shared projects

## Cleanup
```bash
terraform destroy
```