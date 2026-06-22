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

Build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

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
- Permission strings MUST follow the format `{resource-type}:{ActionInCamelCase}` (e.g., `provider-account:CreateProviderAccount`). SCREAMING_SNAKE_CASE (e.g., `CREATE_PROVIDER_ACCOUNT`) or no-prefix formats are **invalid** and will be rejected.
- `name` pattern: `^[a-z][a-z0-9\-]{1,33}[a-z0-9]$` (starts with letter, ends with letter/digit, 3–35 chars).
- **Global Settings** resource prefix is `settings` — NOT `global-settings`.

## Verified Permission Strings

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

## Checklists

### Custom Role Creation
- [ ] Did I confirm no built-in role covers the user's needs?
- [ ] Did I call `get_manifest_json_schema` with type `role`?
- [ ] Is `resourceType` set to `tenant` (NOT `provider-account`, `workspace`, etc.)?
- [ ] Are all permission strings in `{resource-type}:{ActionInCamelCase}` format (NOT SCREAMING_SNAKE_CASE)?
- [ ] For Global Settings, did I use prefix `settings` (not `global-settings`)?

For more info: `search_docs` with "custom role permissions", "access control".
