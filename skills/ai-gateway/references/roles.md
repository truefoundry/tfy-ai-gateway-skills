---
name: roles
description: Create and manage custom roles and role bindings for fine-grained access control.
---

**Roles** define named sets of permissions that can be assigned to users, teams, or virtual accounts. TrueFoundry supports built-in roles and custom roles.

## Contents
- Access Control Strategy
- Fetching Existing Roles
- Creating Custom Roles (Write Flow)
- Verified Permission Strings
- Role Bindings (fetching, creating, deleting)
- Checklists

## Access Control Strategy

There are two ways to grant access in TrueFoundry:

1. **Custom role + tenant-scoped role binding** — for granting broad permissions across the entire tenant (e.g., "this user can create provider accounts and MCP servers"). Create a custom role with the permissions needed, then bind it at the tenant level.
2. **Collaborators on the entity** — for granting access to a *specific* resource (e.g., "this user can manage this particular provider account"). Add the user or team as a collaborator in the entity's manifest, or add them to a team that already has access.

> **Note**: When to use which:
> - Need to grant someone broad platform-level capabilities? → Custom role + tenant binding
> - Need to give someone access to a specific provider account, MCP server, workspace, etc.? → Add them as a collaborator on that entity, or add them to an appropriate team

## Fetching Existing Roles

Use the `list_roles` tool to get all roles (built-in and custom).

Each role in the response has two permission representations:
- `manifest.permissions`: `["account:ReadAccount", "cluster:ReadCluster"]` — **this is the correct format** to use when creating roles
- `permissionSetsV2[].permissions`: `["READ_ACCOUNT", "READ_CLUSTER"]` — internal expanded format, do NOT copy this

> **CRITICAL**: When creating custom roles, always use the `{resource-type}:{ActionInCamelCase}` format (as seen in `manifest.permissions`). Never use the `SCREAMING_SNAKE_CASE` format from `permissionSetsV2`.

## Creating Custom Roles (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `role`.

### Phase 2: Determine Permissions

1. Ask the user what actions the role should allow.
2. Use the verified permission reference table below to map user intent → permission strings.
3. If the needed permission is not in the table, use `search_docs` with terms like "role permissions", "access control permissions list".

### Phase 3: Validate and Apply

Build the manifest → write to file → `python scripts/validate_schema.py --file-path <manifest.yaml>` → `apply_manifest` with `dryRun: true` → fix if needed → `apply_manifest` without dry-run.

### Manifest Structure

```yaml
type: role
name: <unique-role-name>           # lowercase, 3-35 chars, letters/digits/hyphens
displayName: <Human Readable Name>
description: <What this role is for>
resourceType: tenant               # MUST be "tenant" for custom roles
permissions:
  - <resource-type>:<ActionInCamelCase>
  - <resource-type>:<ActionInCamelCase>
```

### Critical Rules

- `resourceType` MUST be `tenant` for custom roles. Do NOT use `provider-account`, `workspace`, `cluster`, or any other resource type — those are for built-in roles only. Using anything other than `tenant` causes `"Resource type is not supported"`.
- Permission strings MUST follow the format `{resource-type}:{ActionInCamelCase}` (e.g., `provider-account:CreateProviderAccount`). SCREAMING_SNAKE_CASE (e.g., `CREATE_PROVIDER_ACCOUNT`) or no-prefix formats are **invalid** and will be rejected by dry-run.
- `name` pattern: `^[a-z][a-z0-9\-]{1,33}[a-z0-9]$` (starts with letter, ends with letter/digit, 3–35 chars).
- **Global Settings** resource prefix is `settings` — NOT `global-settings`.

## Verified Permission Strings (All Validated via Dry-Run)

Format: `{resource-type}:{ActionInCamelCase}`

### Tenant

| UI Display Name | Permission String |
|---|---|
| Assign Role | `tenant:AssignRole` |

### Provider Accounts / Models / Guardrails

| UI Display Name | Permission String |
|---|---|
| Create Provider Account | `provider-account:CreateProviderAccount` |
| Read Provider Account | `provider-account:ReadProviderAccount` |
| Use Integrations | `provider-account:UseIntegrations` |
| Manage Provider Account | `provider-account:ManageProviderAccount` |
| Delete Provider Account | `provider-account:DeleteProviderAccount` |

### MCP Server

| UI Display Name | Permission String |
|---|---|
| Manage MCP Server | `mcp-server:ManageMcpServer` |
| Read MCP Server | `mcp-server:ReadMcpServer` |
| Delete MCP Server | `mcp-server:DeleteMcpServer` |
| Use MCP Server | `mcp-server:UseMcpServer` |
| Create MCP Server | `mcp-server:CreateMcpServer` |

### Agent

| UI Display Name | Permission String |
|---|---|
| Create Agent | `agent:CreateAgent` |
| Delete Agent | `agent:DeleteAgent` |
| Read Agent | `agent:ReadAgent` |
| Manage Agent | `agent:ManageAgent` |

### Gateway Controls

| UI Display Name | Permission String |
|---|---|
| Manage Gateway Controls | `gateway-controls:ManageGatewayControls` |
| List Gateway Controls | `gateway-controls:ListGatewayControls` |

### Cluster

| UI Display Name | Permission String |
|---|---|
| Manage Clusters | `cluster:ManageClusters` |
| Read Cluster | `cluster:ReadCluster` |
| Delete Cluster | `cluster:DeleteCluster` |
| Create Cluster | `cluster:CreateCluster` |

### Workspace

| UI Display Name | Permission String |
|---|---|
| Read Workspace | `workspace:ReadWorkspace` |
| Manage Workspace | `workspace:ManageWorkspace` |
| Delete Workspace | `workspace:DeleteWorkspace` |
| Create Workspace | `workspace:CreateWorkspace` |
| List Workspaces | `workspace:ListWorkspaces` |

### Application

| UI Display Name | Permission String |
|---|---|
| List Applications | `application:ListApplications` |
| Manage Applications | `application:ManageApplications` |

### Repository

| UI Display Name | Permission String |
|---|---|
| Create Repository | `repository:CreateRepository` |
| Delete Data | `repository:DeleteData` |
| Write Data | `repository:WriteData` |
| Manage Repository | `repository:ManageRepository` |
| Read Data | `repository:ReadData` |
| Read Repository | `repository:ReadRepository` |
| Delete Repository | `repository:DeleteRepository` |

### Secret Group

| UI Display Name | Permission String |
|---|---|
| Create Secret Group | `secret-group:CreateSecretGroup` |
| Delete Secret Group | `secret-group:DeleteSecretGroup` |
| Read Data | `secret-group:ReadData` |
| Write Data | `secret-group:WriteData` |
| Manage Secret Group | `secret-group:ManageSecretGroup` |
| Read Secret Group | `secret-group:ReadSecretGroup` |

### Tracing Project

| UI Display Name | Permission String |
|---|---|
| Read Tracing Project | `tracing-project:ReadTracingProject` |
| Read Data | `tracing-project:ReadData` |
| Manage Tracing Project | `tracing-project:ManageTracingProject` |
| Write Data | `tracing-project:WriteData` |
| Delete Tracing Project | `tracing-project:DeleteTracingProject` |
| Create Tracing Project | `tracing-project:CreateTracingProject` |

### User

| UI Display Name | Permission String |
|---|---|
| Manage Users | `user:ManageUsers` |
| List Users | `user:ListUsers` |

### Team

| UI Display Name | Permission String |
|---|---|
| Create Team | `team:CreateTeam` |
| Read Team | `team:ReadTeam` |
| Delete Team | `team:DeleteTeam` |
| Manage Team | `team:ManageTeam` |

### Virtual Account

| UI Display Name | Permission String |
|---|---|
| Manage Virtual Account | `virtual-account:ManageVirtualAccount` |
| Read Virtual Account | `virtual-account:ReadVirtualAccount` |
| Delete Virtual Account | `virtual-account:DeleteVirtualAccount` |
| Create Virtual Account | `virtual-account:CreateVirtualAccount` |

### External Identity

| UI Display Name | Permission String |
|---|---|
| List External Identities | `external-identity:ListExternalIdentities` |
| Manage External Identities | `external-identity:ManageExternalIdentities` |

### Role

| UI Display Name | Permission String |
|---|---|
| Manage Roles | `role:ManageRoles` |
| List Roles | `role:ListRoles` |

### Global Settings

> ⚠️ Resource prefix is `settings`, NOT `global-settings`

| UI Display Name | Permission String |
|---|---|
| List Settings | `settings:ListSettings` |
| Manage Settings | `settings:ManageSettings` |

### Environment

| UI Display Name | Permission String |
|---|---|
| Manage Environments | `environment:ManageEnvironments` |
| List Environments | `environment:ListEnvironments` |

### Policy

| UI Display Name | Permission String |
|---|---|
| Manage Policies | `policy:ManagePolicies` |
| List Policies | `policy:ListPolicies` |

## Example: Gateway Config Creator Role

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

## Role Bindings

**Role Bindings** assign roles to subjects (users, teams, virtual accounts, or external identities). After creating a custom role, you need a role binding to actually grant it to someone.

> **Note**: For custom roles, role bindings are always **tenant-scoped** — the binding grants the role's permissions across the entire tenant. For granting access to a *specific* resource, use **collaborators** on the entity's manifest instead.

## Fetching Existing Role Bindings

Use the `list_role_bindings` tool to get all role bindings. To check if a specific role binding already exists, use `check_role_binding_exists` with the binding name.


## Creating / Updating Role Bindings (Write Flow)

> **CRITICAL**: Role bindings do NOT use `get_manifest_json_schema`, `validate_schema.py`, or `apply_manifest`. Use the `create_or_update_role_binding` tool directly.

### Phase 1: Gather Requirements

1. Ask the user:
   - **Who** should get access? (user email, team name, virtual account name, or external identity name)
   - **What role** should they get? (the custom role name you created, or a built-in role name from `list_roles`)
2. Get the **tenant name** — this is the `resourceFqn` for tenant-scoped bindings. Use `get_me` or the tenant context to determine it.

### Phase 2: Create or Update

1. Build the role binding payload following the manifest structure below.
2. Call `create_or_update_role_binding` directly as a tool (not from sandbox) with `dryRun: true`.
3. If dry-run fails, fix and retry.
4. Once dry-run passes, call `create_or_update_role_binding` directly as a tool (not from sandbox) without dry-run.

### Manifest Structure

```yaml
type: role-binding
name: <unique-binding-name>        # lowercase, 3-64 chars, letter start/end, hyphens allowed
subjects:
  - type: <subject-type>           # user | team | virtualaccount | external-identity
    name: <subject-name>           # email for user; name for team/virtualaccount/external-identity
permissions:
  - resourceType: tenant           # always "tenant" for custom role bindings
    resourceFqn: <tenant-name>     # the tenant name
    role: <role-name>              # name of the custom role to assign
```

### Critical Rules

- `type` MUST be `role-binding`.
- `name` pattern: starts with a lowercase letter, ends with a letter or digit, 3–64 chars, only lowercase letters, digits, and hyphens.
- `subjects` MUST have at least 1 item.
- `permissions` MUST have at least 1 item.
- Subject `type` MUST be one of: `user`, `team`, `virtualaccount`, `external-identity`. Any other value is rejected.
- For subject type `user`, `name` is the user's **email address**. For `team`, `virtualaccount`, and `external-identity`, `name` is the entity's name.
- The `role` in each permission MUST match an existing role name (built-in or custom). Use `list_roles` to verify.
- For custom roles, `resourceType` is `tenant` and `resourceFqn` is the tenant name.
- Matching is by `name` — if a role binding with the same name exists, it is updated. Otherwise a new one is created.

## Example: Assign Custom Role to a User

```yaml
type: role-binding
name: alice-gateway-config-creatorm
subjects:
  - type: user
    name: alice@example.com
permissions:
  - resourceType: tenant
    resourceFqn: my-tenant
    role: gateway-config-creator
```

## Example: Assign Custom Role to a Team

```yaml
type: role-binding
name: backend-team-gateway-creator
subjects:
  - type: team
    name: backend-team
permissions:
  - resourceType: tenant
    resourceFqn: my-tenant
    role: gateway-config-creator
```

## Deleting a Role Binding

Use the `delete_role_binding` tool with the role binding ID. First use `list_role_bindings` or `check_role_binding_exists` to find the binding, then delete by its `id`.

## Checklists

### Custom Role Creation
- [ ] Did I confirm no built-in role covers the user's needs?
- [ ] Did I call `get_manifest_json_schema` with type `role`?
- [ ] Is `resourceType` set to `tenant` (NOT `provider-account`, `workspace`, etc.)?
- [ ] Are all permission strings in `{resource-type}:{ActionInCamelCase}` format (NOT SCREAMING_SNAKE_CASE)?
- [ ] For Global Settings, did I use prefix `settings` (not `global-settings`)?

### Role Binding (assigning the role)
- [ ] Did I determine the correct role name (custom or built-in) from `list_roles`?
- [ ] Does each subject have a valid `type` (`user`, `team`, `virtualaccount`, or `external-identity`)?
- [ ] For `user` subjects, is `name` an email address?
- [ ] Is `resourceType` set to `tenant` and `resourceFqn` set to the tenant name?

### Resource-Specific Access (no role binding needed)
- [ ] Did I add the user/team as a **collaborator** on the entity's manifest instead of creating a role binding?

For more info: `search_docs` with "custom role permissions", "role binding", "assign role to user", "access control".
