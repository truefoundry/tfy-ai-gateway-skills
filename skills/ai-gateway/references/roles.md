---
name: roles
description: Create and manage custom roles and role bindings for fine-grained access control.
---

**Roles** define named sets of permissions that can be assigned to users, teams, or virtual accounts. TrueFoundry supports built-in roles and custom roles. Custom roles let you grant exactly the permissions needed — no more, no less.

## Fetching Existing Roles

Use the `list_roles` tool to get all roles (built-in and custom). If you need to inspect a specific role's permissions, look for it in the response by name.

## Creating / Updating Roles (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `role`.

### Phase 2: Determine Permissions

1. Ask the user what actions the role should allow.
2. Use the verified permission reference table below to map user intent → permission strings.
3. If the needed permission is not in the table, use `search_docs` with terms like "role permissions", "access control permissions list".

### Phase 3: Build and Validate

1. Build the manifest following the JSON schema strictly. Write it to a file.
2. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
3. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run.

### Manifest Structure

```yaml
type: role
name: <unique-role-name>           # lowercase, 3-35 chars, letters/digits/hyphens
displayName: <Human Readable Name>
description: <What this role is for>
resourceType: tenant               # MUST be "tenant" for tenant-wide roles
permissions:
  - <resource-type>:<ActionInCamelCase>
  - <resource-type>:<ActionInCamelCase>
```

### Critical Rules

- `resourceType` MUST be `tenant`. Using `""` or `"platform"` causes `"Resource type is not supported"`.
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

**Role Bindings** connect subjects (users, teams, virtual accounts, or external identities) to roles on specific resources. While a **Role** defines *what* permissions exist, a **Role Binding** assigns *who* gets *which* role on *which* resource.

## Fetching Existing Role Bindings

Use the `list_role_bindings` tool to get all role bindings in the current account. Filter by `name` or `id` using query parameters. To check if a specific role binding already exists, use `check_role_binding_exists` with the binding name.

## Creating / Updating Role Bindings (Write Flow)

> **Important:** Role bindings do NOT use `get_manifest_json_schema`, `validate_schema.py`, or `apply_manifest`. Use the `create_or_update_role_binding` tool directly — its input body defines the schema.

### Phase 1: Gather Requirements

1. Ask the user:
   - **Who** should get access? (user email, team name, virtual account name, or external identity name)
   - **What role** should they get? Call `list_roles` to find valid role names.
   - **On which resource?** (resource type + resource FQN). Verify the resource exists by listing resources of that type (e.g., `list_workspaces`, `list_clusters`).

### Phase 2: Create or Update

1. Build the role binding payload following the manifest structure below.
2. Call `create_or_update_role_binding` directly as a tool (NOT from code mode) with `dryRun: true`.
3. If dry-run fails, fix and retry.
4. Once dry-run passes, call `create_or_update_role_binding` directly as a tool (NOT from code mode) without dry-run.

### Manifest Structure

```yaml
type: role-binding
name: <unique-binding-name>        # lowercase, 3-64 chars, letter start/end, hyphens allowed
subjects:
  - type: <subject-type>           # user | team | virtualaccount | external-identity
    name: <subject-name>           # email for user; name for team/virtualaccount/external-identity
permissions:
  - resourceType: <resource-type>  # cluster, workspace, secret-group, etc.
    resourceFqn: <resource-fqn>    # FQN of the specific resource
    role: <role-name>              # name of the role to assign
```

### Critical Rules

- `type` MUST be `role-binding`.
- `name` pattern: starts with a lowercase letter, ends with a letter or digit, 3–64 chars, only lowercase letters, digits, and hyphens.
- `subjects` MUST have at least 1 item.
- `permissions` MUST have at least 1 item.
- Subject `type` MUST be one of: `user`, `team`, `virtualaccount`, `external-identity`. Any other value is rejected.
- For subject type `user`, `name` is the user's **email address**. For `team`, `virtualaccount`, and `external-identity`, `name` is the entity's name.
- The `role` in each permission MUST match an existing role name (built-in or custom). Use `list_roles` to verify.
- The `resourceType` in each permission MUST match the role's own `resourceType`. A workspace role cannot be bound to a cluster resource.
- The `resourceFqn` MUST be the FQN of an existing resource. Use list tools to find the correct FQN.
- For tenant-scoped roles (e.g., `tenant-admin`), `resourceType` is `tenant` and `resourceFqn` is the tenant name.
- Matching is by `name` — if a role binding with the same name exists, it is updated. Otherwise a new one is created.

## Example: Grant Workspace Editor to a User

```yaml
type: role-binding
name: alice-dev-workspace-editor
subjects:
  - type: user
    name: alice@example.com
permissions:
  - resourceType: workspace
    resourceFqn: my-cluster:dev-workspace
    role: workspace-editor
```

## Example: Grant Multiple Roles to a Team

```yaml
type: role-binding
name: backend-team-access
subjects:
  - type: team
    name: backend-team
permissions:
  - resourceType: workspace
    resourceFqn: my-cluster:staging-workspace
    role: workspace-admin
  - resourceType: secret-group
    resourceFqn: staging-secrets
    role: secret-group-editor
```

## Deleting a Role Binding

Use the `delete_role_binding` tool with the role binding ID. First use `list_role_bindings` to find the binding by name, then delete by its `id`.

## Checklists

### Role Creation
- [ ] Did I call `get_manifest_json_schema` with type `role`?
- [ ] Is `resourceType` set to `tenant`?
- [ ] Are all permission strings in `{resource-type}:{ActionInCamelCase}` format?
- [ ] For Global Settings, did I use prefix `settings` (not `global-settings`)?
- [ ] Did I validate with `scripts/validate_schema.py` before dry-running?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before applying?
- [ ] Did I call `apply_manifest` directly as a tool (not from sandbox/code mode)?

### Role Binding
- [ ] Did I call `list_roles` to verify the role name exists?
- [ ] Does each subject have a valid `type` (`user`, `team`, `virtualaccount`, or `external-identity`)?
- [ ] For `user` subjects, is `name` an email address?
- [ ] Does each permission's `role` match an existing role from `list_roles`?
- [ ] Does each permission's `resourceType` match the role's resource type?
- [ ] Does each permission's `resourceFqn` point to an existing resource?
- [ ] Did I dry-run with `create_or_update_role_binding` (dryRun: true) before applying?
- [ ] Did I call `create_or_update_role_binding` directly as a tool (not from sandbox/code mode)?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about roles, permissions, and role bindings.
Search terms: "custom role permissions", "role manifest", "role binding", "assign role to user", "access control", "grant workspace access"
