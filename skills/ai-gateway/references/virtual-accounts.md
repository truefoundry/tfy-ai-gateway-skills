---
name: virtual-accounts
description: Create and manage virtual accounts — non-human identities for applications and services with scoped permissions.
---

**Virtual Accounts** are non-human identities for applications, services, and CI/CD pipelines. Each virtual account has its own token (VAT) and can be scoped to minimum required permissions. One virtual account per application is recommended.

## Fetching existing virtual accounts

Use the `list_virtual_accounts` tool to get the list of all virtual accounts. Use `get_virtual_account` to inspect a single VA by name or ID.

## Creating Virtual Accounts (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `virtual-account`.

### Phase 2: Determine Permissions

1. A virtual account MUST have at least one permission — it cannot exist with zero permissions. Use `ask_user_question` to ask the user what permissions this VA should have (role, resource, resource type).
2. **When updating/revoking permissions**: if removing a permission would leave the VA with zero permissions, do NOT proceed. Inform the user that a VA cannot have empty permissions — they must either keep at least one permission or delete the VA entirely.

### Phase 3: Validate and Apply

Build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Manifest Structure

```yaml
type: virtual-account
name: <unique-va-name>
permissions:
  - role_id: <role-id>
    resource_fqn: <resource-fqn>
    resource_type: <resource-type>
tags:
  purpose: <purpose-tag>
  created-by: <creator-email>
token_type: <jwt>
```

### Common Permission Patterns

| Use Case | role_id | resource_type |
|---|---|---|
| Access models in a provider account | `provider-account-access` | `provider-account` |
| View workspace deployments | `workspace-viewer` | `workspace` |
| Deploy to workspace | `workspace-member` | `workspace` |

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `virtual-account`?
- [ ] Did I ask the user what permissions this VA should have?
- [ ] Does the VA have at least one permission assigned?
- [ ] If revoking permissions, did I verify the VA won't end up with zero permissions?

For more info: `search_docs` with "virtual account creation", "virtual account token", "VAT rotation", "virtual account permissions".
