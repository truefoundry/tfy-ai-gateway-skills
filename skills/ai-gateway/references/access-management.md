---
name: access-management
description: Identity types, authentication tokens (PATs/VATs), access control, and virtual account token management.
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

**MUST follow**: You MUST NOT suggest using PATs for applications. Always recommend Virtual Accounts for any production, CI/CD, or shared application use case. PATs become invalid if the user leaves the organization.

## Access Control

Access to models is managed at the **provider account** level. Two permission levels:

- **Provider Account Manager**: Can modify settings, add/remove models, manage permissions for others.
- **Provider Account User**: Can use all models in the account. Cannot change settings or permissions.

Permissions can be granted to users, teams, or virtual accounts.

Tenant admins automatically have access to all models without needing explicit collaborator assignment.

## Virtual Account Token Management

Virtual accounts support:

- **Auto-rotation**: Automatically rotate tokens at a configured interval. Old tokens remain valid for a configurable grace period.
- **Secret store sync**: Sync tokens to AWS Parameter Store, AWS Secrets Manager, Google Secret Manager, HashiCorp Vault, Azure Vault, etc. Tokens auto-sync on rotation.
- **Rotation notifications**: Get notified via email or Slack when tokens rotate.

## Roles and Permissions

- **Admin**: Full control over all resources, users, and settings. Should be limited to a few users.
- **Member**: No default resource access. Must be explicitly granted access.
- **Custom Roles**: Admins can create custom roles with fine-grained permissions scoped to specific resource types (provider accounts, MCP servers, virtual accounts, teams, etc.).

Roles are assigned per user. Use `search_true_foundry_docs` for detailed permission tables.

## Searching Docs for Additional Information

**Important**: This should be only used when other sources provide insufficient information.

Use `search_true_foundry_docs` to search for additional information about access management.
Search terms: "authentication PAT VAT", "virtual account management", "access control provider account", "team management", "external identity", "user roles permissions", "token rotation", "secret store sync"
