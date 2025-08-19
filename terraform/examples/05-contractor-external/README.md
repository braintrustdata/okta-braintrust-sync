# Example 5: Contractor/External Access Management

This example demonstrates security-focused access patterns for external users with time-limited and project-specific permissions based on employment type and security clearance levels.

## User Structure

### Users (9 total) Across Employment Types

#### Internal Employees (3 users)
- **Alice Johnson** - Security Lead, Internal clearance, San Francisco
- **Bob Smith** - Project Manager, Internal clearance, Austin  
- **Carol Davis** - Data Engineer, Internal clearance, Remote

#### Short-term Contractors (2 users)
- **David Wilson** - Frontend Developer, Limited clearance, Contract ends 2024-06-30
- **Eve Brown** - QA Contractor, Limited clearance, Contract ends 2024-09-15

#### Vendor Representatives (2 users)
- **Frank Garcia** - Technical Liaison, CloudVendor Inc, Restricted clearance
- **Grace Lee** - Support Engineer, DataTools Corp, Restricted clearance

#### External Consultants (2 users)
- **Henry Chen** - Security Consultant, Security Firm LLC, Privileged clearance
- **Ivy Rodriguez** - Compliance Auditor, Audit Firm Partners, Audit clearance

## Security-Focused Access Strategy

### Employment Type Groups (Okta Groups)
- **BT-Employees**: Alice, Bob, Carol
- **BT-Contractors**: David, Eve
- **BT-Vendors**: Frank, Grace
- **BT-Consultants**: Henry, Ivy

### Security Clearance Groups (Okta Groups)
- **BT-Internal-Access**: Alice, Bob, Carol (full internal access)
- **BT-Limited-Access**: David, Eve (limited contractor access)
- **BT-Restricted-Access**: Frank, Grace (restricted vendor access)
- **BT-Privileged-Access**: Henry (privileged security consultant)
- **BT-Audit-Access**: Ivy (audit-specific access)

### Project Access Groups (Okta Groups)
- **BT-Public-Projects**: David, Eve (public projects only)
- **BT-External-Safe**: David, Eve, Frank, Grace (external-safe projects)

### Attribute-Based Security Groups
- **ShortTermContracts**: David, Eve (contracts ending June-September 2024)
- **LongTermContracts**: Frank, Grace (contracts ending 2025+)
- **PublicOnlyAccess**: David (accessRestrictions=PublicProjectsOnly)
- **TestingOnlyAccess**: Eve (accessRestrictions=TestingOnly)
- **VendorProjectsOnly**: Frank (accessRestrictions=VendorProjectsOnly)
- **SupportOnlyAccess**: Grace (accessRestrictions=SupportOnly)
- **SecurityProjectsOnly**: Henry (accessRestrictions=SecurityProjectsOnly)
- **AuditOnlyAccess**: Ivy (accessRestrictions=AuditOnly)
- **CloudVendorUsers**: Frank (vendorCompany=CloudVendor Inc)
- **DataToolsUsers**: Grace (vendorCompany=DataTools Corp)
- **SecurityConsultants**: Henry (vendorCompany contains Security Firm)
- **AuditConsultants**: Ivy (vendorCompany contains Audit Firm)
- **ExpertConsultants**: Henry, Ivy (level=Expert + employeeType=Consultant)

## Security-Tiered Role System

### Access Levels (Least to Most Privileged)
1. **SupportRole**: Read-only support access
   - Read all objects only
2. **PublicProjectsRole**: External-safe access
   - Read all, create experiments
3. **ContractorRole**: Limited development access
   - Read all, create/update/delete experiments
4. **VendorRole**: Restricted integration access
   - Read all, create/update experiments
5. **TestingSpecialistRole**: QA and testing focus
   - Read all, create/update/delete experiments
6. **ConsultantRole**: Specialized expert access
   - Read all, create/update all, delete experiments
7. **SecuritySpecialistRole**: Security project access
   - Read all, create/update all, delete experiments, read ACLs
8. **AuditRole**: Read-only compliance access
   - Read all, read ACLs (compliance monitoring)
9. **InternalEmployeeRole**: Full internal access
   - Full CRUD + project ACL management

## Project Access Patterns

### Security-Based Project Categories

#### Public/External-Safe Projects
- **Pattern**: `public-*`, `open-*`, `demo-*`, `training-*`, `external-*`
- **Access**: PublicProjectsRole for contractors, vendors, external users
- **Examples**: `public-demo-application`, `open-source-library`, `training-materials-portal`

#### Contractor Projects
- **Pattern**: `ui-*`, `frontend-*`, `qa-*`, `test-*`, `temporary-*`
- **Access**: ContractorRole for contractors, TestingSpecialistRole for QA
- **Examples**: `ui-redesign-project`, `qa-automation-suite`, `temporary-feature-development`

#### Vendor/Integration Projects
- **Pattern**: `integration-*`, `vendor-*`, `api-*`, `connector-*`, `sync-*`
- **Access**: VendorRole for vendor representatives
- **Examples**: `integration-cloudvendor-platform`, `api-datatools-connector`, `vendor-sync-service`

#### Security/Compliance Projects
- **Pattern**: `security-*`, `compliance-*`, `auth-*`, `crypto-*`, `risk-*`
- **Access**: SecuritySpecialistRole for security consultants, AuditRole for auditors
- **Examples**: `security-audit-framework`, `compliance-reporting-system`, `auth-security-enhancement`

#### Support Projects
- **Pattern**: `support-*`, `help-*`, `documentation-*`, `training-*`
- **Access**: SupportRole for vendor support, PublicProjectsRole for others
- **Examples**: `support-documentation-portal`, `help-desk-integration`, `user-guide-generator`

#### Internal/Sensitive Projects (Employee Only)
- **Pattern**: `*-internal`, `*-sensitive`, `*-confidential`
- **Access**: InternalEmployeeRole only
- **Examples**: `internal-hr-system`, `financial-reporting-sensitive`, `strategic-planning-internal`

### Contract Duration Access
- **Short-term contracts**: Restricted to public/demo/training projects
- **Long-term contracts**: Broader access excluding sensitive/confidential projects

## Expected Group Memberships
- **Alice**: Employees, InternalAccess, FullTimeEmployees
- **Bob**: Employees, InternalAccess, FullTimeEmployees
- **Carol**: Employees, InternalAccess, FullTimeEmployees
- **David**: Contractors, LimitedAccess, PublicProjects, ExternalSafe, ShortTermContracts, PublicOnlyAccess, UIProjectSpecialists
- **Eve**: Contractors, LimitedAccess, PublicProjects, ExternalSafe, ShortTermContracts, TestingOnlyAccess, QAProjectSpecialists
- **Frank**: Vendors, RestrictedAccess, ExternalSafe, LongTermContracts, VendorProjectsOnly, IntegrationSpecialists, CloudVendorUsers
- **Grace**: Vendors, RestrictedAccess, ExternalSafe, LongTermContracts, SupportOnlyAccess, DataToolsUsers
- **Henry**: Consultants, PrivilegedAccess, SecurityProjectsOnly, SecurityConsultants, ExpertConsultants
- **Ivy**: Consultants, AuditAccess, AuditOnlyAccess, AuditConsultants, ExpertConsultants

## Usage

### 1. Deploy Okta Resources
```bash
cd terraform/examples/05-contractor-external

export TF_VAR_okta_org_name="your-okta-org"
export TF_VAR_okta_api_token="your-okta-token"

terraform init
terraform plan
terraform apply
```

### 2. Test Projects to Create in Braintrust
Create these projects to test security-focused access patterns:

**Public/External-Safe Projects:**
- `public-demo-application`
- `open-source-library`
- `demo-showcase-frontend`
- `training-materials-portal`
- `external-api-documentation`

**Contractor Projects:**
- `ui-redesign-project`
- `frontend-modernization`
- `qa-automation-suite`
- `test-data-generation`
- `temporary-feature-development`

**Vendor/Integration Projects:**
- `integration-cloudvendor-platform`
- `api-datatools-connector`
- `vendor-sync-service`
- `external-payment-gateway`
- `third-party-auth-integration`

**Security/Compliance Projects:**
- `security-audit-framework`
- `compliance-reporting-system`
- `auth-security-enhancement`
- `crypto-key-management`
- `risk-assessment-tools`

**Support Projects:**
- `support-documentation-portal`
- `help-desk-integration`
- `training-video-library`
- `support-ticket-system`
- `user-guide-generator`

**Internal/Sensitive Projects (Employee Only):**
- `internal-hr-system`
- `financial-reporting-sensitive`
- `employee-data-confidential`
- `strategic-planning-internal`
- `competitive-analysis-sensitive`

### 3. Run Sync
```bash
export OKTA_API_TOKEN="your-okta-token"
export OKTA_ORG_NAME="your-okta-org"
export BRAINTRUST_PROD_API_KEY="your-prod-key"
export BRAINTRUST_DEV_API_KEY="your-dev-key"

python -m sync.cli sync --config terraform/examples/05-contractor-external/sync-config.yaml
```

## Expected Results

### Employment Type Access
- **Employees**: InternalEmployeeRole on ALL projects (full access)
- **Contractors**: ContractorRole on non-internal/sensitive projects
- **Vendors**: VendorRole on integration/vendor/external projects
- **Consultants**: ConsultantRole on consulting/advisory projects

### Security Clearance Access
- **Internal Access**: Full access to all projects
- **Limited Access**: Access excluding internal/sensitive/confidential/prod projects
- **Restricted Access**: Access to integration/vendor/public/external projects only
- **Privileged Access**: SecuritySpecialistRole on security/compliance projects
- **Audit Access**: AuditRole read-only on ALL projects

### Specialized Access Patterns
- **Public-only users**: PublicProjectsRole on public/demo projects only
- **Testing-only users**: TestingSpecialistRole on QA/test/validation projects
- **Vendor-specific users**: VendorRole on integration/vendor projects
- **Support users**: SupportRole on support/documentation/training projects
- **Security specialists**: SecuritySpecialistRole on security/auth/crypto projects
- **Audit users**: AuditRole read-only on all projects for compliance

### Contract Duration Security
- **Short-term contracts**: Restricted to public/demo/training projects
- **Long-term contracts**: Broader access excluding sensitive/confidential
- **Automatic removal**: Access removed when contracts end (remove_unmanaged_acls: true)

### Enhanced Security Features
- **Hourly sync**: More frequent monitoring for security compliance
- **Sequential processing**: max_concurrent_orgs: 1 for security
- **Fail-fast**: continue_on_error: false for security issues
- **Extended audit**: 90-day retention for compliance requirements
- **Automatic cleanup**: remove_extra: true to remove expired access

This demonstrates comprehensive external user security management with layered access controls, time-based restrictions, and compliance-focused auditing.

## Cleanup
```bash
terraform destroy
```