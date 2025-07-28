# Output useful information for testing
output "test_users" {
  description = "Test users created for sync testing"
  value = {
    ml_engineers = {
      ml1 = {
        id    = okta_user.test_ml_engineer_1.id
        email = okta_user.test_ml_engineer_1.email
        login = okta_user.test_ml_engineer_1.login
      }
      ml2 = {
        id    = okta_user.test_ml_engineer_2.id
        email = okta_user.test_ml_engineer_2.email
        login = okta_user.test_ml_engineer_2.login
      }
    }
    data_scientists = {
      ds1 = {
        id    = okta_user.test_data_scientist_1.id
        email = okta_user.test_data_scientist_1.email
        login = okta_user.test_data_scientist_1.login
      }
      ds2 = {
        id    = okta_user.test_data_scientist_2.id
        email = okta_user.test_data_scientist_2.email
        login = okta_user.test_data_scientist_2.login
      }
    }
    platform_admin = {
      id    = okta_user.test_platform_admin.id
      email = okta_user.test_platform_admin.email
      login = okta_user.test_platform_admin.login
    }
    inactive_user = {
      id     = okta_user.test_inactive_user.id
      email  = okta_user.test_inactive_user.email
      status = okta_user.test_inactive_user.status
    }
  }
}

output "test_groups" {
  description = "Test groups created for sync testing"
  value = {
    ml_engineering = {
      id   = okta_group.ml_engineering.id
      name = okta_group.ml_engineering.name
    }
    data_science = {
      id   = okta_group.data_science.id
      name = okta_group.data_science.name
    }
    genai_platform_admins = {
      id   = okta_group.genai_platform_admins.id
      name = okta_group.genai_platform_admins.name
    }
    all_ai_ml = {
      id   = okta_group.all_ai_ml.id
      name = okta_group.all_ai_ml.name
    }
    test_ad_group = {
      id   = okta_group.test_ad_group.id
      name = okta_group.test_ad_group.name
    }
  }
}

output "sync_config_suggestions" {
  description = "Suggested configuration for testing"
  value = {
    basic_user_filter    = "status eq \"ACTIVE\""
    department_filter    = "status eq \"ACTIVE\" and profile.department eq \"ML Engineering\""
    basic_group_filter   = "type eq \"OKTA_GROUP\""
    ml_group_filter      = "type eq \"OKTA_GROUP\" and profile.name eq \"ML-Engineering\""
    all_groups_filter    = "type eq \"OKTA_GROUP\" and profile.name ne \"AD-Imported-Group\""
    expected_active_users = 5
    expected_groups      = 4  # Excluding AD-Imported-Group
  }
}