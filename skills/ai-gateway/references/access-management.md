---
name: access-management
description: Read for questions about who can access what — identity types, PATs vs virtual account tokens, Identity Providers, tenant roles, custom roles, giving or removing access to a resource, and role bindings (access as code). For adding, inviting, deactivating or deleting users, read `users.md`.
---

**Access Management** covers identities, authentication, roles and access grants. For a specific entity, read its own file.

## Identity types

- **Users** — people who log in. Each user can create Personal Access Tokens (PATs). See `users.md`.
- **Teams** — groups of users; access granted to a team applies to every member. See `teams.md`.
- **Virtual accounts** — non-human identities for applications, with their own token (VAT). See `virtual-accounts.md`.
- **Identity Providers** — validates JWTs from your IdP (Okta, Azure AD, any OIDC) and resolves them to an existing user, team or virtual account; they never create one. Docs: https://www.truefoundry.com/docs/platform/identity-providers

## Authentication

The Gateway takes TrueFoundry API keys, not provider keys, as a Bearer token: `Authorization: Bearer <truefoundry-api-key>`, or `OPENAI_BASE_URL="https://<gateway-host>"` and `OPENAI_API_KEY="<truefoundry-api-key>"` for the OpenAI SDK.

| Token type | Tied to | Best for |
|---|---|---|
| **Personal Access Token (PAT)** | A user | Development and testing |
| **Virtual Account Token (VAT)** | A virtual account | Production applications, CI/CD, shared apps |

Recommend virtual accounts for production, CI/CD and shared apps: a PAT stops working when its owner is deactivated or deleted.

## How access works

Every piece of access is a **grant**: a subject (user, team, virtual account or agent) holds a role on a resource. A tenant role is a grant on the tenant itself. `list_grants` rows show `source`: `AUTH_API` (UI, grant tools or a manifest) or `ROLE_BINDING` (binding in `roleBindingName`).

| Need | Use |
|---|---|
| Broad platform capability for a person or group | Tenant or custom role on the tenant (see "Tenant roles") |
| Access to one resource (provider account, MCP server, workspace) | Grant tools (see "Access to one resource") |
| Access as code (Git, applied with other manifests) | A `role-binding` (see "Role bindings") |
| Several people need the same access | Grant to a team; future members inherit it |
| An application needs access | A virtual account + grant tools (`virtual-accounts.md`) |

Tenant admins can use every model without a grant.

## Access to one resource

Use the grant tools. Each adds or removes one grant and leaves every other grant alone. `create_grants` needs manage on the resource or Assign Role on the tenant; on 403, tell the user a manager of the resource or a tenant admin must grant it.

Never write access through `collaborators`, `authorized_subjects` or a virtual account's `permissions` in a manifest: that list replaces every grant made by a manifest or on the Access Control page, and a stale fetch silently revokes access granted since (`write-rules.md` → Access).

**Ids.** `subjectId` is an internal id, never an email or name:
- user: `list_users` with `query=<email>` → `id`
- team: `list_teams_for_user` with `includeMembership=false` → `id` of the row whose `teamName` matches
- virtual account: `list_virtual_accounts` with `nameSearchQuery=<name>` → `id`

Identify the resource by its `fqn` (as `resourceFqn`) or `id` (as `resourceId`) from its list tool (`list_provider_accounts`, `list_mcp_servers`, `list_workspaces`, …); send exactly one of the two.

**Who has access:** `list_grants` with `resourceType` and `resourceId`. Each row has `subjectType`, `subjectSlug` (email or name), `roleId`, `roleName` and `source`. What one subject holds: `list_grants` with `subjectType` and `subjectId` (a user's rows include grants inherited from their teams). It returns 100 rows by default; pass `limit` and `offset` for more.

A 403 from `list_grants` means you lack manage on that resource (or, by subject, on that subject), or the id is wrong. When the id came from a list tool, it is the permission — not that `create_grants` will fail (Assign Role on the tenant allows granting without manage). Say which refusal it was, offer `create_grants` (approval applies), and only if that also 403s tell the user a manager of the resource or a tenant admin must grant it.

**Grant:** `create_grants` with `{"grants": [{"resourceType", "resourceFqn" or "resourceId", "subjectType", "subjectId", "roleId"}]}` — up to 100 grants, all or nothing; an existing grant is left as is. `subjectType` is `user`, `team`, `virtualaccount` or `agent`.

All model provider accounts is one wildcard grant: `resourceType` `provider-account`, `resourceFqn` `model-provider-accounts:*` (do not list accounts), `roleId` `provider-account-access` (`provider-account-manager` to manage them). It needs tenant-admin or Assign Role and accepts only `virtualaccount` or `agent`; for a user or team, say so and offer grants on named accounts. Bare `*` is rejected.

**Revoke:** `revoke_grant` with one grant's `resourceType`, `resourceId` or `resourceFqn`, `subjectType`, `subjectId` and `roleId`, from its `list_grants` row. Only `AUTH_API` grants can be revoked: a `ROLE_BINDING` grant returns 404 — change or delete its binding instead. A grant inherited from a team is revoked on the team. To change a role, create the new grant first, then revoke the old one.

Role IDs per resource are platform constants:

| `resourceType` | Roles |
|---|---|
| `provider-account` | `provider-account-manager` (change settings, models, access), `provider-account-access` (use every model) |
| `mcp-server` | `mcp-server-manager`, `mcp-server-user`, `mcp-server-approver` |
| `agent` | `agent-manager`, `agent-access` |
| `workspace` | `workspace-admin`, `workspace-editor` (shown as Member), `workspace-viewer` |
| `cluster` | `cluster-admin`, `cluster-member`, `cluster-viewer` |
| `secret-group` | `secret-group-admin`, `secret-group-editor`, `secret-group-viewer`, `secret-group-access` |
| `tracing-project` | `tracing-project-admin`, `tracing-project-editor`, `tracing-project-viewer` |
| `mlf-project` (ML repo) | `mlf-project-admin`, `mlf-project-editor`, `mlf-project-viewer` |

## Tenant roles

- **Tenant Admin** (`tenant-admin`): full control; not editable. Keep to a few users.
- **Member** (`member`): the baseline every user holds; it cannot be revoked. Editable — changes apply to every member.
- **Read-Only Member** (`read-only-member`): read-only across supported resources; not editable.
- **Custom roles**: tenant-wide permission sets created by admins (see "Custom roles").
- **Team Member** / **Team Manager**: team-scoped, given by team membership (`teams.md`), not by a tenant grant.

A subject can hold several tenant roles; their permissions add up.

**Role ids.** `list_roles` with `resourceType: tenant` (or `roleName=<name>`) → the role's `id`. Only `tenant-admin` has its name as its id; `member`, `read-only-member` and custom roles have generated ids.

**Give a tenant role** to a user, team, virtual account or agent: `create_grants` with `resourceType: tenant`, `resourceFqn: <tenantName>`, the subject, and the role's `id` as `roleId`. Granting `tenant-admin` needs the caller to be tenant-admin.

**Change or remove:** grant the new role first, then `revoke_grant` the old one with its `list_grants` row. The last `tenant-admin` grant and a user's `member` role cannot be revoked (422).

**Who holds which tenant role:** `list_grants` with `resourceType: tenant`, `resourceId: <tenantName>` and a `roleId` filter, paging until a page is short. Name every holder by `subjectType` — users, teams, virtual accounts and agents; leave none out.

In the UI: `{controlPlaneUrl}/access-management?tab=users` (or `tab=teams`, `tab=service-accounts`) → the row's menu → **Manage Permissions** → **Organisation Roles** → **Add Roles**.

## Role bindings

A `role-binding` manifest grants roles as code. Use one only when the user asks for access as code (to keep in Git, or to apply with their other manifests).

- **Read:** `list_role_bindings` (filter by `name` or `id`). To export current access as bindings, `get_role_binding_manifests` with `resourceType`+`resourceId` or `subjectType`+`subjectId`. Covers `AUTH_API` only; one manifest per role (per subject when called for a subject).
- **Write:** `apply_manifest` creates or updates (by `name`); `delete_manifest` with type `role-binding` and the name deletes it. Tenant admins only (else 403). Follow `write-rules.md`; schema from `get_manifest_json_schema` (type `role-binding`).
- Applying a binding takes over matching `AUTH_API` grants. Deleting it later removes that access.

```yaml
type: role-binding
name: <binding-name>            # 3-66 chars: lowercase letters, digits, hyphens; starts with a letter
subjects:
  - type: user                  # user | team | virtualaccount | agent
    name: <email, or team / virtual account / agent name>
permissions:
  - resourceType: workspace     # a resourceType from the table above, or tenant
    resourceFqn: <resource-fqn> # the tenant name for tenant
    role: workspace-editor      # a role name valid for that resource type
```

A binding is either one subject with many permissions or many subjects with one permission, not many of both — write one binding per role when several people need several roles. User and team subjects cannot use a wildcard `resourceFqn`. ML repos are `mlf-project`, not `ml-repo`.

## Custom roles

Custom roles are tenant-wide and need Pro or Enterprise.

**Reading.** `list_roles` (pass `roleName=<name>` for one). Custom roles list permissions in `manifest.permissions` (e.g. `["cluster:ReadCluster", "settings:ListSettings"]`) — use that format. Never copy `permissionSetsV2[].permissions` (e.g. `READ_CLUSTER`); it is internal and fails validation.

### Creating or updating

1. In one batch: `get_manifest_json_schema` with type `role` (reuse if still in the conversation), `list_roles` with `roleName=<name>`, and `get_actions_for_resource_type` with `resourceType: tenant`. Each permission key is `<scope>:<name>` from its result (e.g. scope `provider-account`, name `CreateProviderAccount`).
   - **Applying under an existing name replaces the whole permission list for everyone who holds it.** If `list_roles` returns a role, show it and ask whether to update or pick another name. Never apply `member`, `team-member` or `team-manager` unless the user wants to change that default for everyone.
2. Ask what the role should allow; map each action to a key from step 1.
3. Build the manifest, then `validate_manifest` → `apply_manifest` per `write-rules.md`. Then give the role to subjects as in "Tenant roles".

Rules:
- `resourceType: tenant`. Other values are rejected.
- You can only put permissions you hold yourself into a role; else apply fails.
- At least one permission, no duplicates.
- `name`: 3-35 chars, lowercase letters, digits and hyphens; starts with a letter, ends with a letter or digit. Built-in names (`tenant-admin`, `admin`, `read-only-member`) are reserved.

```yaml
type: role
name: gateway-config-creator
displayName: Gateway Config Creator
description: Create provider accounts, virtual accounts and MCP servers, and manage gateway configs.
resourceType: tenant
permissions:
  - provider-account:CreateProviderAccount
  - virtual-account:CreateVirtualAccount
  - mcp-server:CreateMcpServer
  - gateway-controls:ManageGatewayControls
```

**Deleting:** `delete_manifest` with type `role` and the name. It fails (409) while any grant still uses the role, and for built-in roles: revoke its grants first.

Docs: [roles and permissions](https://www.truefoundry.com/docs/platform/manage-user-roles-and-permissions) · [role bindings](https://www.truefoundry.com/docs/platform/manage-user-roles-and-permissions#manage-access-as-code).
