---
name: gateway-write-rules
description: Shared rules for every AI Gateway create, update or delete — the write steps, gateway config kinds, lists that replace everything, granting access, and the UI link to show after applying.
---

# AI Gateway write rules

Read this file in the same batch as the entity's reference file whenever the user wants to create, add, set up, connect, configure, change or delete a Gateway entity or policy. The entity file says what to collect and shows the manifest; this file holds the rules every Gateway write shares.

## Contents
- Steps
- Gateway config kinds
- Lists that replace everything
- Access
- After applying: UI links

## Steps

1. **Read** the entity's reference file and this file (one batch).
2. **Session context** — the current user's identity and `controlPlaneUrl` are in your instructions. Call `get_session_context` only if they are missing.
3. **Schema** — call `get_manifest_json_schema` for the entity type. The reference templates are simplified; the schema is the contract `validate_manifest` checks. Reuse the schema if it is still in the conversation; otherwise call it again. When editing a live manifest you just fetched, you can skip it and fix from `validate_manifest` errors. If the result is saved to a file, extract only the paths you need with one `jq`.
4. **Ask** for every decision with more than one valid answer (auth method, region, which models, create vs update) with `ask_user_question`. Guessing produces entities the user then has to find and fix. If you are a sub-agent and the tool is unavailable, stop and return the question.
5. **Fetch existing state** the entity file asks for (see the next two sections). Steps 1, 3 and 5 are independent: issue them together. Call `get_manifest_json_schema` for large types (`service`, `virtual-model`, guardrail groups) in its own batch, because large results batched together get saved to a file instead of shown.
6. **Build** the manifest as JSON, following the schema.
7. **Validate, then apply once.** Call `validate_manifest` directly. If the manifest is too large to write inline (a provider account with many models), build it with a program into a sandbox file and call `validate_manifest` from the sandbox on that file instead. Fix and re-validate until `valid: true`. Then call `apply_manifest` once, directly (it needs user approval), with the validated JSON — never in the same batch as validation. `apply_manifest` is an upsert: a manifest with an existing identity (its `name`; `type` alone for legacy singletons) replaces that entity's whole manifest. When the user asks to *create*, use a new unique name.
8. **Grant** — after a create, grant access (see Access).
9. **Link** — show the UI page from "After applying" with the real `controlPlaneUrl`.

## Gateway config kinds

Policies come in two kinds, and they are written differently:

| Kind | Types | How to write |
| --- | --- | --- |
| Legacy singleton | `gateway-rate-limiting-config`, `gateway-budget-config` | One document per tenant, identified by `type`. Call `get_gateway_config` right before building, add your rule to its `rules`, and send the whole list back. Never rebuild the list from memory or a summary — a missing rule is deleted. `name` is optional and ignored. |
| Named policy | `gateway-guardrails-config`, `tenant-rate-limit-config/model`, `tenant-rate-limit-config/mcp`, `tenant-budget-config`, `team-budget-config` | One manifest per policy, identified by its required `name`. Applying a new name adds a policy and touches nothing else. Applying an existing name replaces that policy. |

- Existing named policies: budgets `list_gateway_budgets`; guardrail policies and V2 rate limits `list_gateway_config_instances` with the policy `type` (one call per type). `get_gateway_config` returns nothing for these types.
- **Never send a `rules` array in a `gateway-guardrails-config` manifest.** The platform treats it as the legacy combined format and deletes every guardrails policy not in the array.

## Lists that replace everything

On an update, these fields replace the entity's entire current value. Anything you leave out is removed — access revoked, members dropped, credentials deleted. Start from the entity's current manifest, change only what was asked, and show the user the final list before applying.

| Field | Entity | Safer path |
| --- | --- | --- |
| `collaborators`, `authorized_subjects` | Provider accounts, virtual models, MCP servers, guardrail groups | Never send; use the grant tools (see Access) |
| `permissions` | Virtual account | Never send; use the grant tools (see Access) |
| `members`, `managers` | Team | `add_team_members` / `remove_team_members` / `add_team_managers` / `remove_team_managers` |
| `integrations` | Guardrail group, provider account | Start from `list_provider_accounts`' current manifest; a dropped integration is deleted with its credentials |
| `rules` | Legacy singleton configs | `get_gateway_config` immediately before writing |
| whole role | Role (by `name`) | Check `list_roles` with `roleName` first; never overwrite `member`, `team-member`, `team-manager` unless asked |

Updating an MCP server whose auth changed deletes every user's stored tokens. Pass `force: false` to `apply_manifest`, and if it reports auth records to delete, ask the user before retrying with `force: true`.

## Access

Access is stored as grants, and only the grant tools write it (`list_grants`, `create_grants`, `revoke_grant`; `access-management.md` → Access to one resource). **Never send `collaborators`, an integration's `authorized_subjects`, or a VA's `permissions` in a manifest, on create or update.** Delete them from every fetched manifest before applying.

- Omitted, they leave existing grants untouched. Present, they replace every grant on the resource made by a manifest or on its **Access Control** page.
- A fetched copy is the list last applied, not current access, so re-sending it revokes access granted since. Current access comes from `list_grants`.

**After creating**, the creator is already manager. Other users cannot see the resource until granted, so in one `create_grants` call after the apply succeeds:

- Grant `team:everyone` the access role, unless the user gives their own list. The everyone team's `id` comes from `list_teams_for_user` with `includeMembership=false`; other subject ids per `access-management.md` → Ids.
- Identify the new resource by its `fqn` or `id` from its list tool (`list_provider_accounts`, `list_mcp_servers`).
- If it fails, the resource exists with only the creator as manager: tell the user and retry the grants, never the apply.

| Entity | `resourceType` | Manager `roleId` | Access `roleId` |
| --- | --- | --- | --- |
| Provider account (models), virtual model, guardrail group | `provider-account` | `provider-account-manager` | `provider-account-access` |
| MCP server | `mcp-server` | `mcp-server-manager` | `mcp-server-user` |

These role IDs are platform constants — use the table instead of looking them up. MCP servers also have `mcp-server-approver`. MCP server group provider accounts accept only `provider-account-manager`; do not grant `team:everyone` there.

### Entities that still carry these lists

Every past apply that included them already wrote them as grants, so there is no access to move:

1. Treat `list_grants` as current access. Do not reconcile it with the old list: an entry missing from `list_grants` was revoked later, and re-granting it would restore access someone removed.
2. Delete the list on the next update and tell the user once that access is now managed with grants and is unchanged.
3. If the user asks to restore an entry from the old list, show the difference against `list_grants` and add only the entries they confirm with `create_grants`.
4. If the user keeps manifests in Git or CI with `collaborators`, every `tfy apply` of that file replaces the resource's inline grants. Have them delete `collaborators` from the files. If they want access kept as code, first apply a `role-binding` per subject and role (`access-management.md` → Role bindings); it takes over the matching inline grants, so nothing is duplicated or lost. Then remove the list.

## After applying: UI links

Append to `controlPlaneUrl`:

| Entity | Path |
| --- | --- |
| Model provider account | `/llm-gateway/models?provider={providerType}` (the account's `provider`, e.g. `openai`) |
| Virtual model | `/llm-gateway/virtual-models` |
| MCP server (including virtual) | `/llm-gateway/mcp-servers` |
| Guardrail group | `/guardrails/registry` |
| Guardrail policy | `/llm-gateway/policies/guardrails` |
| Rate limit (V2 / legacy V1) | `/llm-gateway/policies/rate-limiting-v2` / `/llm-gateway/policies/rate-limiting` |
| Budget (V2 / legacy V1) | `/llm-gateway/policies/budget-limiting-v2` / `/llm-gateway/policies/budget-limiting` |
| Team | `/access-management?tab=teams` |
| Virtual account | `/access-management?tab=service-accounts` |
| Role | `/access-management?tab=custom-roles` |
| Personal access token | `/access-management?tab=personal-access-token` |
