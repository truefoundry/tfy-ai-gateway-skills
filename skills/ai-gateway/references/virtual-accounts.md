---
name: virtual-accounts
description: Create and manage virtual accounts — non-human identities for applications and services with scoped permissions.
---

**Virtual Accounts** are non-human identities for applications, services, and CI/CD pipelines. Each virtual account has its own token (VAT) and can be scoped to minimum required permissions. One virtual account per application is recommended.

## Creating Virtual Accounts (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `virtual-account`.

### Phase 2: Determine Permissions

1. A virtual account must have at least one permission assigned. Use `ask_user_question` to ask the user what permissions this VA should have (role, resource, resource type).

### Phase 3: Validate and Apply

1. Build the manifest following the JSON schema strictly.
2. Call `apply_manifest` with `dryRun: true` to validate.
3. If validation fails, fix and retry.
4. Once dry-run passes, call `apply_manifest` without dry-run to create the virtual account.

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

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I ask the user what permissions this VA should have?
- [ ] Does the VA have at least one permission assigned?
- [ ] Did I validate with `apply_manifest` (dryRun: true) before creating?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about virtual accounts.
Search terms: "virtual account creation", "virtual account token", "VAT rotation", "virtual account permissions", "secret store sync"
