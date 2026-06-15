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

1. A virtual account must have at least one permission assigned. Use `ask_user_question` to ask the user what permissions this VA should have (role, resource, resource type).

### Phase 3: Build and Validate

1. Build the manifest following the JSON schema strictly. Write it to a file.
2. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
3. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run to create the virtual account.

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

- [ ] Called `get_manifest_json_schema` with type `virtual-account`?
- [ ] Asked user what permissions this VA should have?
- [ ] At least one permission assigned?
- [ ] Validated with `scripts/validate_schema.py`?
- [ ] Dry-run with `apply_manifest` (dryRun: true) passed?
- [ ] Applied with `apply_manifest` (direct tool call, not sandbox)?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about virtual accounts.
Search terms: "virtual account creation", "virtual account token", "VAT rotation", "virtual account permissions", "secret store sync"
