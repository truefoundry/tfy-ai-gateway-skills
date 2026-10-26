---
name: virtual-accounts
description: Read before listing, creating or changing virtual accounts — non-human identities for applications and services with scoped permissions — or when a user asks about VA tokens, rotation or secret store sync.
---

**Virtual accounts (VAs)** are non-human identities for applications, services and CI/CD pipelines. Each has its own token (VAT) and should hold only the permissions it needs. Recommend one VA per application.

## Reading virtual accounts

- `list_virtual_accounts` returns the VAs you can access. To find one by name, pass `nameSearchQuery=<name>` (substring match).
- `get_virtual_account` takes the VA's `id` (from `list_virtual_accounts`); it does not accept a name.

## Inputs to collect

Ask in one question, because the first two cannot be changed after creation:

- **Owner team** (`ownedBy.team`) — cannot be changed later; not `everyone`.
- **Expiration date** (optional, `YYYY-MM-DD`, in the future) — cannot be added or changed later.
- **Access** — for each grant: role, resource type, resource FQN (see "Common permissions").
- Optional: auto-rotation, secret store sync, notifications (see "Token features").

## Creating a virtual account

1. In one parallel batch: `list_virtual_accounts` with `nameSearchQuery=<name>` (similar VAs you can access), `check_virtual_account_exists` with `name` (whether the exact name is taken tenant-wide), and `get_manifest_json_schema` with type `virtual-account` (reuse it if still in the conversation).
2. If the name is taken or similar VAs exist, show them and ask whether to create a VA with a different name or update an existing one. Restate the user's choice (create a new name, or update `<name>`) in your reply before continuing. For an update, go to "Updating a virtual account".
3. Put the requested access in `permissions`. Never send `permissions: []`; it is rejected.
4. Build the manifest, then `validate_manifest` → `apply_manifest` per `write-rules.md`.
5. Send the user to generate the token (see "Token").

## Updating a virtual account

**Omit `permissions` on every update**; current access stays. A `permissions` list replaces all of the VA's grants, including those added on its Access Control page, and `get_virtual_account` returns the list last applied, not current access, so re-sending it can revoke grants.

- To add or remove a permission, send the user to the VA's **Access Control** in `{controlPlaneUrl}/access-management?tab=service-accounts`; tenant admins can also add one with a `role-binding` (`access-management.md`).
- Keep `ownedBy` and `expiration_date` exactly as returned.
- If the user wants to remove the VA's last permission, suggest deleting the VA instead (`delete_virtual_account`), because an empty list is rejected.

## Common permissions

| Use case | `role_id` | `resource_type` |
|---|---|---|
| Access models in a provider account | `provider-account-access` | `provider-account` |
| Access all model provider accounts | `provider-account-access` | `provider-account` (FQN `model-provider-accounts:*`) |
| Use an MCP server | `mcp-server-user` | `mcp-server` |
| Invoke an agent | `agent-access` | `agent` |
| Access a secret group | `secret-group-access` | `secret-group` |
| View workspace deployments | `workspace-viewer` | `workspace` |
| Deploy to workspace | `workspace-editor` (shown as "Workspace Member" in the UI) | `workspace` |
| Tenant-wide role | `member`, `read-only-member`, or a custom role name | `tenant` (FQN = tenant name) |

- `resource_fqn` for a workspace is `<cluster-name>:<workspace-name>`.
- For all resources of a kind, use `<category>:*` (e.g. `model-provider-accounts:*`), not `*`.
- A VA can hold only one tenant-level role. Only tenant admins can grant `tenant-admin`.
- You can only grant roles on resources you can manage; otherwise the apply returns 403.

## Manifest

```yaml
type: virtual-account
name: <va-name>                  # 3-36 chars: lowercase letters, digits, hyphens; starts with a letter
ownedBy:
  team: <team-name>              # cannot be changed after creation; not "everyone"
expiration_date: <YYYY-MM-DD>    # optional, future date; cannot be added or changed later
permissions:
  - role_id: <role-id>
    resource_fqn: <resource-fqn>
    resource_type: <resource-type>
auto_rotate:                     # optional; set at creation
  auto_rotate_interval: 360      # days, min 30
  grace_period: 30               # days, min 1
secret_store_config:             # optional; or { type: tfy-secrets, secret_group, key }
  type: secret-store
  integration_fqn: <secret-store-integration-fqn>
  secret_path: <path>
tags:                            # optional; no spaces, values <= 64 chars
  purpose: <purpose>
```

Do not set `token_type`. It overrides the tenant default and cannot be changed after creation.

## Token features

- **Auto-rotation:** `auto_rotate_interval` (days, default 360, min 30) and `grace_period` (days, default 30, min 1) — the old token stays valid during the grace period. Set it at creation.
- **Secret store sync:** an integrated secret store (`type: secret-store`: AWS Parameter Store, AWS Secrets Manager, Google Secret Manager, HashiCorp Vault, Azure Vault, etc.) or a TrueFoundry secret group (`type: tfy-secrets`). Tokens re-sync on every rotation.
- **Notifications:** email or Slack on rotation or upcoming expiry; the email or Slack integration must be set up first.

## Token

**Never generate or fetch a VA's token** — not via tools, API calls or docs API references. Send the user to `{controlPlaneUrl}/access-management?tab=service-accounts`, open **Tokens** on the VA's row, and select **Get Token** (needs the Manage Virtual Account permission). `controlPlaneUrl` is in the session context; call `get_session_context` only if it is missing.

## Checklist

- [ ] Do I have the `virtual-account` schema from `get_manifest_json_schema` in the conversation? If not, call it again.
- [ ] Did I ask for the owner team and expiration date before creating?
- [ ] Did I avoid sending an empty `permissions` list, and omit `permissions` on every update?
- [ ] Did I leave out `token_type`?
- [ ] After creation, did I send the user to the UI to get the token?

For more info: `search_docs` with "virtual account creation", "virtual account token", "VAT rotation", "virtual account permissions".
