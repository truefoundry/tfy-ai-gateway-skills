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

- **Owner team** (`ownedBy.team`, optional, not `everyone`) — cannot be added or changed later. Omit `ownedBy` when unset.
- **Expiration date** (optional, `YYYY-MM-DD`, in the future) — cannot be added or changed later.
- **Access** — for each grant: role, resource type, resource FQN (see "Common permissions").
- Optional: auto-rotation, secret store sync, notifications (see "Token features").

## Creating a virtual account

1. In one parallel batch: `list_virtual_accounts` with `nameSearchQuery=<name>` (similar VAs you can access), `check_virtual_account_exists` with `name` (whether the exact name is taken tenant-wide), and `get_manifest_json_schema` with type `virtual-account` (reuse it if still in the conversation).
2. If the name is taken or similar VAs exist, show them and ask whether to create a VA with a different name or update an existing one. Restate the user's choice (create a new name, or update `<name>`) in your reply before continuing. For an update, go to "Updating a virtual account".
3. Build the manifest without `permissions`. Set `ownedBy.team` only when the user names a team; otherwise omit `ownedBy`. Then `validate_manifest` → `apply_manifest` per `write-rules.md`.
4. Grant the requested access in one `create_grants` call with `subjectType: virtualaccount` and the new VA's `id` (from `list_virtual_accounts`) as `subjectId` (`access-management.md` → Access to one resource). If it fails, the VA exists with no access. Never re-apply; tell the user and retry only `create_grants` once the error is fixed. On 403 the caller cannot manage that resource: a manager of it must grant it, or offer to delete the VA.
5. Send the user to generate the token (see "Token").

## Updating a virtual account

**Never send `permissions`**; delete it from the fetched manifest (`write-rules.md` → Access). `get_virtual_account` returns the list last applied, not current access, so re-sending it can revoke grants.

- To add or remove a permission, use the grant tools with `subjectType: virtualaccount` and the VA's `id` as `subjectId` (`access-management.md` → Access to one resource). `list_grants` with `subjectType: virtualaccount` and `subjectId` shows what it holds now.
- Keep `ownedBy` and `expiration_date` exactly as returned.

## Common permissions

| Use case | `roleId` | `resourceType` |
|---|---|---|
| Access models in a provider account | `provider-account-access` | `provider-account` |
| Access all model provider accounts | `provider-account-access` | `provider-account` (FQN `model-provider-accounts:*`) |
| Use an MCP server | `mcp-server-user` | `mcp-server` |
| Invoke an agent | `agent-access` | `agent` |
| Access a secret group | `secret-group-access` | `secret-group` |
| View workspace deployments | `workspace-viewer` | `workspace` |
| Deploy to workspace | `workspace-editor` (shown as "Workspace Member" in the UI) | `workspace` |
| Tenant-wide role | the `id` from `list_roles` with `roleName` (`member`, `read-only-member` or a custom role); never the name | `tenant` (FQN = tenant name) |

- `resourceFqn` for a workspace is `<cluster-name>:<workspace-name>`.
- All resources of a kind is one grant with `<category>:*` (model provider accounts: `model-provider-accounts:*`), not `*` and not one grant per account (`access-management.md` → Grant).
- A VA can hold only one tenant-level role. Only tenant admins can grant `tenant-admin`.
- You can only grant roles on resources you can manage; otherwise `create_grants` returns 403.

## Manifest

```yaml
type: virtual-account
name: <va-name>                  # 3-36 chars: lowercase letters, digits, hyphens; starts with a letter
ownedBy:                         # optional; not "everyone"; cannot be added or changed later
  team: <team-name>
expiration_date: <YYYY-MM-DD>    # optional, future date; cannot be added or changed later
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
- [ ] Did I ask for the optional owner team and expiration date before creating, and omit `ownedBy` when no team was chosen?
- [ ] Did I leave `permissions` out of every manifest and grant access with `create_grants` after creating?
- [ ] Did I leave out `token_type`?
- [ ] After creation, did I send the user to the UI to get the token?

For more info: `search_docs` with "virtual account creation", "virtual account token", "VAT rotation", "virtual account permissions".
