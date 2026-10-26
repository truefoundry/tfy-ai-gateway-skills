---
name: access-management
description: Read for questions about who can access what — identity types, PATs vs virtual account tokens, Identity Providers, tenant roles, custom roles, role bindings, and giving a user or team access to a resource.
---

**Access Management** covers identities, authentication, roles and access grants for the Gateway. For a specific entity, read its own file: `teams.md`, `virtual-accounts.md`, `personal-access-tokens.md`.

## Identity types

- **Users** — people who log in. Each user can create Personal Access Tokens (PATs).
- **Teams** — groups of users; access granted to a team applies to every member. See `teams.md`.
- **Virtual accounts** — non-human identities for applications, with their own token (VAT). See `virtual-accounts.md`.
- **Identity Providers** — TrueFoundry validates JWTs from your IdP (Okta, Azure AD, any OIDC provider) and resolves them to a user or virtual account through `identity_provider_mapping` on the virtual account, team, or user. Configure under Settings > Security & Access > Identity Providers. Docs: https://www.truefoundry.com/docs/platform/identity-providers

## Authentication

The Gateway takes TrueFoundry API keys, not provider keys (OpenAI, Anthropic, etc.). Pass the key as a Bearer token:

```
Authorization: Bearer <truefoundry-api-key>
```

Or via OpenAI SDK environment variables:

```bash
export OPENAI_BASE_URL="https://<gateway-host>"
export OPENAI_API_KEY="<truefoundry-api-key>"
```

| Token type | Tied to | Best for |
|---|---|---|
| **Personal Access Token (PAT)** | A user | Development and testing |
| **Virtual Account Token (VAT)** | A virtual account | Production applications, CI/CD, shared apps |

Recommend virtual accounts for production, CI/CD and shared apps: a PAT becomes invalid when its owner is deleted or deactivated.

## Choosing how to grant access

| Need | Use |
|---|---|
| Broad platform capability for a person or group (e.g. "can create provider accounts") | A tenant role or custom role, assigned in the UI (see "Assign a tenant role") |
| Access to one specific resource (a provider account, MCP server, workspace) | The grant tools (see "Access to one resource"); a `role-binding` only if the user asks for access as code |
| Several people need the same access | Grant it to a team; future members inherit it |
| An application needs access | A virtual account: `permissions` at creation, the grant tools afterwards (see `virtual-accounts.md`) |

Roles can be assigned to users, teams (every member inherits them), virtual accounts, and agents. Tenant admins can use every model without being a collaborator.

## Access to one resource

Use the grant tools. Each adds or removes one grant and leaves every other grant alone. They apply the same checks as the **Access Control** page: the caller needs manage on the resource (or `ASSIGN_ROLE` on the tenant); otherwise they return 403, so tell the user a manager of the resource must do it. If these tools are not listed, send the user to the resource's three-dot menu → **Access Control** → **Grant Access**.

Never change access by editing `collaborators` or a VA's `permissions` in a manifest: that list replaces every grant made by a manifest or on the Access Control page, and the fetched copy can be stale, so access granted since is silently revoked (`write-rules.md` → Collaborators).

**Ids.** `subjectId` is an internal id, never an email or name:
- user: `list_users` with `query=<email>` → `id`
- team: `list_teams_for_user` → the team's `id`
- virtual account: `list_virtual_accounts` with `nameSearchQuery=<name>` → `id`

Identify the resource by its `fqn` (as `resourceFqn`) or `id` (as `resourceId`) from its list tool (`list_provider_accounts`, `list_mcp_servers`, `list_workspaces`, …); send exactly one of the two.

**Who has access:** `list_grants` with `resourceType` and `resourceId`. Each row has `subjectType`, `subjectSlug` (email or name), `roleId`, `roleName` and `source`: `AUTH_API` (granted in the UI, a tool or a manifest) or `ROLE_BINDING` (from the binding in `roleBindingName`). It returns 100 rows by default; pass `limit` and `offset` for more.

**Grant:** `create_grants` with `{"grants": [{"resourceType", "resourceFqn" or "resourceId", "subjectType", "subjectId", "roleId"}]}` — up to 100 grants, all or nothing. `subjectType` is `user`, `team`, `virtualaccount` or `agent`. Wildcards such as `model-provider-accounts:*` need tenant-admin or `ASSIGN_ROLE` and only accept `virtualaccount` or `agent`.

**Revoke:** `revoke_grant` with one grant's `resourceType`, `resourceId` or `resourceFqn`, `subjectType`, `subjectId` and `roleId`, copied from its `list_grants` row. Only `AUTH_API` grants can be revoked (a `ROLE_BINDING` grant returns 404; change its binding instead). To change a role, create the new grant first, then revoke the old one.

Model access is granted at the **provider account** level:

- **Manager** (`provider-account-manager`) — can change settings, add or remove models, and manage access.
- **User** (`provider-account-access`) — can use every model in the account; cannot change settings or access.

Role IDs for other resources are in `write-rules.md` → Collaborators and `virtual-accounts.md` → Common permissions.

### Role bindings (access as code)

Use a `role-binding` only when the user asks for access as code (to keep in Git, or to apply with their other manifests). Only tenant admins can apply one; others get 403.

1. Call `get_manifest_json_schema` with type `role-binding` (reuse it if it is still in the conversation).
2. Build the manifest below. If the user wants to apply it here, `validate_manifest` → `apply_manifest` per `write-rules.md`; otherwise give them the YAML. Re-applying the same `name` updates that binding.

```yaml
type: role-binding
name: <binding-name>            # 3-66 chars: lowercase letters, digits, hyphens; starts with a letter
subjects:
  - type: user                  # user | team | virtualaccount | agent
    name: <email, or team / virtual account / agent name>
permissions:
  - resourceType: workspace     # e.g. workspace, cluster, provider-account
    resourceFqn: <resource-fqn>
    role: workspace-editor      # a role valid for that resource type
```

A binding is either one subject with many permissions or many subjects with one permission, not many of both — write one binding per role when several people need several roles.

## Roles

- **Tenant Admin** (`tenant-admin`): full control; not editable. Keep to a few users.
- **Member** (`member`): default role with a small baseline (read clusters, list environments/settings/users, create repositories, secret groups, agents); no access to individual models, MCP servers or workspaces. Editable — changes apply to every member.
- **Read-Only Member** (`read-only-member`): read-only across supported resources; not editable.
- **Team Member** / **Team Manager**: team-scoped defaults for the team's virtual accounts and membership.
- **Custom roles**: tenant-wide permission sets created by admins.

### Assign a tenant role

Do this in the UI:

- **To a user:** open `{controlPlaneUrl}/access-management?tab=users`, edit the user, select the role, and save.
- **To a team:** open `{controlPlaneUrl}/access-management?tab=teams`, edit the team, select the role, and save — every member inherits it.

Full walkthrough: https://www.truefoundry.com/docs/platform/manage-user-roles-and-permissions

### Reading existing roles

Call `list_roles` (pass `roleName=<name>` to fetch one). Custom roles list their permissions in `manifest.permissions` (e.g. `["cluster:ReadCluster", "settings:ListSettings"]`) — that is the format to use. Built-in roles may have no `manifest`. Never copy `permissionSetsV2[].permissions` (e.g. `READ_CLUSTER`); it is an internal format and fails validation.

## Creating or updating a custom role

Custom roles are not available on the Free plan.

### Steps

1. In one parallel batch: `get_manifest_json_schema` with type `role` (reuse it if still in the conversation), `list_roles` with `roleName=<name>`, and `get_section_content` with url `https://www.truefoundry.com/docs/platform/manage-user-roles-and-permissions#available-platform-permissions` for the permission keys.
   - **Applying a role under an existing name overwrites it for everyone who holds it.** If `list_roles` returns a role, show it and ask whether to update it or pick another name. Never apply a role named `member`, `team-member` or `team-manager` unless the user explicitly wants to change that default for everyone.
   - If `get_section_content` returns a page layout instead of content, fetch `#ai-gateway`, `#ai-engineering` and `#common` from the same URL.
2. Ask the user what the role should allow, and map each action to a permission key from the docs. Copy the keys verbatim.
3. Build the manifest, then `validate_manifest` → `apply_manifest` per `write-rules.md`.

### Rules

- Set `resourceType: tenant`. Other values (`provider-account`, `workspace`, `cluster`) are reserved for built-in roles and return "Resource type is not supported".
- Permission keys use `{resource-type}:{ActionInCamelCase}` (e.g. `provider-account:CreateProviderAccount`).
- The Global Settings prefix is `settings`, not `global-settings` — a common validation failure.
- You can only put permissions you hold yourself into a role; the apply fails otherwise.
- At least one permission, with no duplicates.

### Manifest

```yaml
type: role
name: <role-name>                  # 3-35 chars: lowercase letters, digits, hyphens; starts with a letter, ends with a letter or digit
displayName: <Human Readable Name>
description: <What this role is for>
resourceType: tenant
permissions:
  - <resource-type>:<ActionInCamelCase>
```

Example — a role that can create gateway resources:

```yaml
type: role
name: gateway-config-creator
displayName: Gateway Config Creator
description: Allows creating provider accounts, virtual accounts, MCP servers, and managing gateway configurations.
resourceType: tenant
permissions:
  - provider-account:CreateProviderAccount
  - virtual-account:CreateVirtualAccount
  - mcp-server:CreateMcpServer
  - gateway-controls:ManageGatewayControls
```

### Checklist

- [ ] Do I have the `role` schema from `get_manifest_json_schema` in the conversation? If not, call it again.
- [ ] Did I check `list_roles` with `roleName` and confirm with the user before overwriting an existing role?
- [ ] Is `resourceType` set to `tenant`?
- [ ] Are all permission keys copied verbatim from the docs, in `{resource-type}:{ActionInCamelCase}` format?
- [ ] Do I hold every permission I'm putting in the role, and is there at least one, with no duplicates?

For more info: `search_docs` with "authentication PAT VAT", "identity providers", "access control provider account", "custom role permissions", "assign role to user", "role binding".
