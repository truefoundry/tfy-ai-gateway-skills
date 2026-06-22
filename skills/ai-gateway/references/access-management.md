---
name: access-management
description: Identity types, authentication tokens (PATs/VATs), access control, roles, permissions, and virtual account token management.
---

**Access Management** covers the identity types, authentication mechanisms, access control, and token management for the Gateway.

## Identity Types

- **Users**: Individuals who can log in to the platform. Each user has an email and can create Personal Access Tokens (PATs).
- **Teams**: Groups of users. Granting a team access to a resource automatically grants access to all members. Teams can be managed manually or synced via SSO groups.
- **Virtual Accounts**: Non-user identities for applications and services. Each virtual account has its own token (VAT) and can be scoped to minimum required permissions. One virtual account per application is recommended.
- **External Identity**: Allows authentication via external identity providers (Okta, Azure AD) using JWT tokens, without requiring TrueFoundry user accounts. Useful for B2B applications.

**Note**: There is an 'everyone' team which includes all users in the tenant. (not virtual accounts)

## Authentication

Gateway uses TrueFoundry API keys, not provider keys (OpenAI, Anthropic, etc.). Pass the key as a Bearer token:

```
Authorization: Bearer <truefoundry-api-key>
```

Or via OpenAI SDK environment variables:

```bash
export OPENAI_BASE_URL="https://<gateway-host>"
export OPENAI_API_KEY="<truefoundry-api-key>"
```

Two token types exist:

| Token Type | Tied To | Best For |
|---|---|---|
| **Personal Access Token (PAT)** | A user | Development and testing |
| **Virtual Account Token (VAT)** | A virtual identity | Production applications, CI/CD, shared apps |

Always recommend Virtual Accounts for production, CI/CD, or shared application use cases — PATs are tied to individual users and become invalid if the user leaves the organization, which makes them unsuitable for long-lived application credentials.

## Access Control

Access to models users/teams is managed at the **provider account** level. You can find collaborators in the provider account manifest. Two permission levels:

- **Provider Account Manager**: Can modify settings, add/remove models, manage permissions for others.
- **Provider Account User**: Can use all models in the account. Cannot change settings or permissions.

Permissions can be granted to users, teams from collaborator section in the provider account manifest.

Tenant admins automatically have access to all models without needing explicit collaborator assignment.

Virtual Account can have permissions to models, provider accounts, mcp servers. These permissions are present in the virtual account manifest and managed from the virtual account manifest.

## Virtual Account Token Management

Virtual accounts support:

- **Auto-rotation**: Automatically rotate tokens at a configured interval. Old tokens remain valid for a configurable grace period.
- **Secret store sync**: Sync tokens to AWS Parameter Store, AWS Secrets Manager, Google Secret Manager, HashiCorp Vault, Azure Vault, etc. Tokens auto-sync on rotation.
- **Rotation notifications**: Get notified via email or Slack when tokens rotate.

## Roles and Permissions

- **Admin**: Full control over all resources, users, and settings. Should be limited to a few users.
- **Member**: No default resource access. Must be explicitly granted access.
- **Custom Roles**: Admins can create custom roles with fine-grained permissions scoped to specific resource types (provider accounts, MCP servers, virtual accounts, teams, etc.).

Roles are assigned per user.

### Access Control Strategy

There are two ways to grant access in TrueFoundry:

1. **Custom role + tenant-scoped role binding** — for granting broad permissions across the entire tenant (e.g., "this user can create provider accounts and MCP servers"). Create a custom role with the permissions needed, then bind it at the tenant level.
2. **Collaborators on the entity** — for granting access to a *specific* resource (e.g., "this user can manage this particular provider account"). Add the user or team as a collaborator in the entity's manifest, or add them to a team that already has access.

When to use which:
- Need to grant someone broad platform-level capabilities? → Custom role + tenant binding
- Need to give someone access to a specific provider account, MCP server, workspace, etc.? → Add them as a collaborator on that entity, or add them to an appropriate team

### Fetching Existing Roles

Use the `list_roles` tool to get all roles (built-in and custom).

Each role in the response has two permission representations:
- `manifest.permissions`: `["account:ReadAccount", "cluster:ReadCluster"]` — this is the correct format to use when creating roles
- `permissionSetsV2[].permissions`: `["READ_ACCOUNT", "READ_CLUSTER"]` — internal expanded format, do not copy this

When creating custom roles, use the `{resource-type}:{ActionInCamelCase}` format (as seen in `manifest.permissions`). The `SCREAMING_SNAKE_CASE` format from `permissionSetsV2` is an internal representation — using it in manifests causes validation errors.

### Creating Custom Roles (Write Flow)

#### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `role`.

#### Phase 2: Determine Permissions

1. Ask the user what actions the role should allow.
2. Use the verified permission reference table below to map user intent → permission strings.
3. If the needed permission is not in the table, use `search_docs` with terms like "role permissions", "access control permissions list".

#### Phase 3: Validate and Apply

Build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

#### Manifest Structure

```yaml
type: role
name: <unique-role-name>           # lowercase, 3-35 chars, letters/digits/hyphens
displayName: <Human Readable Name>
description: <What this role is for>
resourceType: tenant               # always "tenant" for custom roles
permissions:
  - <resource-type>:<ActionInCamelCase>
  - <resource-type>:<ActionInCamelCase>
```

#### Important Constraints

- Set `resourceType` to `tenant` for custom roles — other values (`provider-account`, `workspace`, `cluster`) are reserved for built-in roles and will return `"Resource type is not supported"`.
- Permission strings must follow `{resource-type}:{ActionInCamelCase}` format (e.g., `provider-account:CreateProviderAccount`). The SCREAMING_SNAKE_CASE format is internal and gets rejected by validation.
- `name` pattern: `^[a-z][a-z0-9\-]{1,33}[a-z0-9]$` (starts with letter, ends with letter/digit, 3–35 chars).
- The **Global Settings** resource prefix is `settings` (not `global-settings`) — this is a common source of validation failures.

### Verified Permission Strings

Format: `{resource-type}:{ActionInCamelCase}`

#### Provider Accounts / Models / Guardrails

| Permission String | Description |
|---|---|
| `provider-account:CreateProviderAccount` | Create Provider Account |
| `provider-account:ReadProviderAccount` | Read Provider Account |
| `provider-account:UseIntegrations` | Use Integrations |
| `provider-account:ManageProviderAccount` | Manage Provider Account |
| `provider-account:DeleteProviderAccount` | Delete Provider Account |

#### MCP Server

| Permission String | Description |
|---|---|
| `mcp-server:CreateMcpServer` | Create MCP Server |
| `mcp-server:ReadMcpServer` | Read MCP Server |
| `mcp-server:UseMcpServer` | Use MCP Server |
| `mcp-server:ManageMcpServer` | Manage MCP Server |
| `mcp-server:DeleteMcpServer` | Delete MCP Server |

#### Agent

| Permission String | Description |
|---|---|
| `agent:CreateAgent` | Create Agent |
| `agent:ReadAgent` | Read Agent |
| `agent:ManageAgent` | Manage Agent |
| `agent:DeleteAgent` | Delete Agent |

#### Gateway Controls

| Permission String | Description |
|---|---|
| `gateway-controls:ManageGatewayControls` | Manage Gateway Controls |
| `gateway-controls:ListGatewayControls` | List Gateway Controls |

#### Tenant

| Permission String | Description |
|---|---|
| `tenant:AssignRole` | Assign Role |

#### Cluster

| Permission String | Description |
|---|---|
| `cluster:CreateCluster` | Create Cluster |
| `cluster:ReadCluster` | Read Cluster |
| `cluster:ManageClusters` | Manage Clusters |
| `cluster:DeleteCluster` | Delete Cluster |

#### Workspace

| Permission String | Description |
|---|---|
| `workspace:CreateWorkspace` | Create Workspace |
| `workspace:ReadWorkspace` | Read Workspace |
| `workspace:ManageWorkspace` | Manage Workspace |
| `workspace:DeleteWorkspace` | Delete Workspace |
| `workspace:ListWorkspaces` | List Workspaces |

#### Application

| Permission String | Description |
|---|---|
| `application:ListApplications` | List Applications |
| `application:ManageApplications` | Manage Applications |

#### Repository

| Permission String | Description |
|---|---|
| `repository:CreateRepository` | Create Repository |
| `repository:ReadRepository` | Read Repository |
| `repository:ReadData` | Read Data |
| `repository:WriteData` | Write Data |
| `repository:DeleteData` | Delete Data |
| `repository:ManageRepository` | Manage Repository |
| `repository:DeleteRepository` | Delete Repository |

#### Secret Group

| Permission String | Description |
|---|---|
| `secret-group:CreateSecretGroup` | Create Secret Group |
| `secret-group:ReadSecretGroup` | Read Secret Group |
| `secret-group:ReadData` | Read Data |
| `secret-group:WriteData` | Write Data |
| `secret-group:ManageSecretGroup` | Manage Secret Group |
| `secret-group:DeleteSecretGroup` | Delete Secret Group |

#### Tracing Project

| Permission String | Description |
|---|---|
| `tracing-project:CreateTracingProject` | Create Tracing Project |
| `tracing-project:ReadTracingProject` | Read Tracing Project |
| `tracing-project:ReadData` | Read Data |
| `tracing-project:WriteData` | Write Data |
| `tracing-project:ManageTracingProject` | Manage Tracing Project |
| `tracing-project:DeleteTracingProject` | Delete Tracing Project |

#### User

| Permission String | Description |
|---|---|
| `user:ManageUsers` | Manage Users |
| `user:ListUsers` | List Users |

#### Team

| Permission String | Description |
|---|---|
| `team:CreateTeam` | Create Team |
| `team:ReadTeam` | Read Team |
| `team:ManageTeam` | Manage Team |
| `team:DeleteTeam` | Delete Team |

#### Virtual Account

| Permission String | Description |
|---|---|
| `virtual-account:CreateVirtualAccount` | Create Virtual Account |
| `virtual-account:ReadVirtualAccount` | Read Virtual Account |
| `virtual-account:ManageVirtualAccount` | Manage Virtual Account |
| `virtual-account:DeleteVirtualAccount` | Delete Virtual Account |

#### External Identity

| Permission String | Description |
|---|---|
| `external-identity:ListExternalIdentities` | List External Identities |
| `external-identity:ManageExternalIdentities` | Manage External Identities |

#### Role

| Permission String | Description |
|---|---|
| `role:ManageRoles` | Manage Roles |
| `role:ListRoles` | List Roles |

#### Global Settings

Resource prefix is `settings`, not `global-settings`.

| Permission String | Description |
|---|---|
| `settings:ListSettings` | List Settings |
| `settings:ManageSettings` | Manage Settings |

#### Environment

| Permission String | Description |
|---|---|
| `environment:ManageEnvironments` | Manage Environments |
| `environment:ListEnvironments` | List Environments |

#### Policy

| Permission String | Description |
|---|---|
| `policy:ManagePolicies` | Manage Policies |
| `policy:ListPolicies` | List Policies |

### Example: Gateway Config Creator Role

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

### Custom Role Checklist

- [ ] Did I confirm no built-in role covers the user's needs?
- [ ] Did I call `get_manifest_json_schema` with type `role`?
- [ ] Is `resourceType` set to `tenant` (not `provider-account`, `workspace`, etc.)?
- [ ] Are all permission strings in `{resource-type}:{ActionInCamelCase}` format?
- [ ] For Global Settings, did I use prefix `settings` (not `global-settings`)?

For more info: `search_docs` with "authentication PAT VAT", "virtual account management", "access control provider account", "custom role permissions".
