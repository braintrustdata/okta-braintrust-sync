# Example 2: Attribute-Based Assignment

This example demonstrates pure attribute-based group assignment with 9 users with diverse attributes, showcasing complex attribute rules and multiple group memberships per user.

## User Structure

### Users (9 total) with Rich Attributes
- **Alice Johnson** - Senior Software Engineer, Engineering, San Francisco, FullTime
- **Bob Smith** - Principal Engineer, Engineering, Remote, FullTime  
- **Carol Davis** - ML Engineer, Engineering, New York, FullTime
- **David Wilson** - Senior Data Scientist, DataScience, Austin, FullTime
- **Eve Brown** - Director of Research, Research, San Francisco, FullTime
- **Frank Garcia** - Frontend Developer, Engineering, Remote, Contractor
- **Grace Lee** - Senior Product Manager, Product, Seattle, FullTime
- **Henry Chen** - VP of Product, Product, San Francisco, FullTime
- **Ivy Rodriguez** - Software Engineering Intern, Engineering, San Francisco, Intern

### Key Attributes Used
- **Department**: Engineering, DataScience, Research, Product
- **Level**: Intern, Mid, Senior, Principal, Director, VP
- **Location**: San Francisco, Remote, New York, Austin, Seattle
- **EmployeeType**: FullTime, Contractor, Intern
- **Skills**: Python, React, ML, Leadership, etc.
- **Title**: Various engineering and management titles

## Attribute-Based Group Assignment Strategy

### No Okta Groups
This example intentionally has **no Okta groups** to demonstrate pure attribute-based assignment.

### Complex Attribute Rules
Users are assigned to multiple groups based on various attribute combinations:

#### Leadership Groups (Highest Priority)
- **ExecutiveTeam**: VPs and C-Level (Henry)
- **Directors**: Director level (Eve)

#### Department Groups
- **Engineering**: Engineering department, not interns (Alice, Bob, Carol, Frank)
- **DataScience**: DataScience department (David)
- **Research**: Research department (Eve)
- **Product**: Product department (Grace, Henry)

#### Seniority Groups
- **SeniorStaff**: Senior+ level, full-time (Alice, David, Grace)
- **MidLevelStaff**: Mid level, full-time (Carol)

#### Specialized Groups
- **MLSpecialists**: ML skills or ML/AI titles (Carol, David)
- **FrontendTeam**: React skills or frontend titles (Frank)

#### Location Groups
- **RemoteWorkers**: Remote location (Bob, Frank)
- **SFOffice**: San Francisco location (Alice, Eve, Henry, Ivy)

#### Employment Type Groups
- **ExternalContractors**: Contractor type (Frank)
- **Interns**: Intern type (Ivy)
- **FullTimeEmployees**: FullTime type (Alice, Bob, Carol, David, Eve, Grace, Henry)

## Role-Project Assignment

### Roles Created
- **Executive**: Full organization access (Henry)
- **Director**: Cross-functional project access (Eve)
- **SeniorEngineer**: Broad technical access (Alice, Bob via SeniorStaff)
- **Engineer**: Standard development access (Carol via MidLevel, Frank via Frontend)
- **MLEngineer**: ML-focused access (Carol, David)
- **ProductManager**: Product project management (Grace, Henry)
- **Researcher**: Research project access (Eve)
- **Contractor**: Limited external access (Frank)
- **Intern**: Supervised learning access (Ivy)

### Expected Group Memberships
- **Alice**: Engineering, SeniorStaff, SFOffice, FullTimeEmployees
- **Bob**: Engineering, SeniorStaff, RemoteWorkers, FullTimeEmployees
- **Carol**: Engineering, MLSpecialists, MidLevelStaff, FullTimeEmployees
- **David**: DataScience, MLSpecialists, SeniorStaff, FullTimeEmployees
- **Eve**: Research, Directors, SFOffice, FullTimeEmployees
- **Frank**: Engineering, FrontendTeam, RemoteWorkers, ExternalContractors
- **Grace**: Product, SeniorStaff, FullTimeEmployees
- **Henry**: Product, ExecutiveTeam, SFOffice, FullTimeEmployees
- **Ivy**: Interns, SFOffice

## Usage

### 1. Deploy Okta Resources
```bash
cd terraform/examples/02-attribute-based

export TF_VAR_okta_org_name="your-okta-org"
export TF_VAR_okta_api_token="your-okta-token"

terraform init
terraform plan
terraform apply
```

### 2. Test Projects to Create in Braintrust
Create these projects to see the complex role assignments:

**Engineering Projects:**
- `api-gateway-service`
- `web-dashboard-ui`
- `mobile-app-react-native`
- `infra-kubernetes-platform`
- `service-user-authentication`

**ML/Data Projects:**
- `ml-recommendation-model`
- `data-analytics-pipeline`
- `ai-chatbot-nlp`
- `model-fraud-detection`
- `prediction-sales-forecast`

**Research Projects:**
- `research-new-algorithms`
- `experiment-ab-testing`
- `paper-ml-optimization`
- `research-distributed-systems`

**Product Projects:**
- `product-user-onboarding`
- `feature-recommendation-engine`
- `customer-feedback-analysis`
- `roadmap-q4-planning`

**Specialized Projects:**
- `remote-team-collaboration`
- `public-demo-showcase`
- `external-contractor-portal`
- `intern-training-program`
- `internal-company-tools`

### 3. Run Sync
```bash
export OKTA_API_TOKEN="your-okta-token"
export OKTA_ORG_NAME="your-okta-org"
export BRAINTRUST_PROD_API_KEY="your-prod-key"
export BRAINTRUST_DEV_API_KEY="your-dev-key"

python -m sync.cli sync --config terraform/examples/02-attribute-based/sync-config.yaml
```

## Expected Results

### Complex Multi-Group Assignments
Users will be assigned to multiple groups based on various attributes:

- **Henry (VP Product)**: ExecutiveTeam→Executive role on ALL projects
- **Eve (Research Director)**: Directors→Director role on ALL projects, Research→Researcher on research projects
- **Alice (Senior Engineer)**: Engineering→SeniorEngineer on engineering projects, SeniorStaff→SeniorEngineer on most projects
- **Carol (ML Engineer)**: Engineering→SeniorEngineer on engineering projects, MLSpecialists→MLEngineer on ML projects
- **Frank (Contractor)**: ExternalContractors→Contractor on public/external projects, FrontendTeam→Engineer on UI projects

### Attribute-Driven Access Patterns
- **ML Projects**: Accessed by MLSpecialists (Carol, David) with MLEngineer role
- **Frontend Projects**: Accessed by FrontendTeam (Frank) with Engineer role  
- **Remote Projects**: Accessed by RemoteWorkers (Bob, Frank) with their respective roles
- **Research Projects**: Accessed by Research team (Eve) with Researcher role
- **Contractor Projects**: Accessed by ExternalContractors (Frank) with Contractor role
- **Intern Projects**: Accessed by Interns (Ivy) with Intern role

This demonstrates how rich attribute data can create sophisticated, multi-dimensional access control patterns.

## Cleanup
```bash
terraform destroy
```