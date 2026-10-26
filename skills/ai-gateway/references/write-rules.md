---
name: gateway-write-rules
description: Shared rules for every AI Gateway create, update or delete — the write steps, gateway config kinds, lists that replace everything, collaborators, and the UI link to show after applying.
---

# AI Gateway write rules

Read this file in the same batch as the entity's reference file whenever the user wants to create, add, set up, connect, configure, change or delete a Gateway entity or policy. The entity file says what to collect and shows the manifest; this file holds the rules every Gateway write shares.

## Contents
- Steps
- Gateway config kinds
- Lists that replace everything
- Collaborators
- After applying: UI links

## Steps

1. **Read** the entity's reference file and this file (one batch).
2. **Session context** — the current user's identity and `controlPlaneUrl` are in your instructions. Call `get_session_context` only if they are missing.
3. **Schema** — call `get_manifest_json_schema` for the entity type. The reference templates are simplified; the schema is the contract `validate_manifest` checks. Reuse the schema if it is still in the conversation; otherwise call it again. When editing a live manifest you just fetched, you can skip it and fix from `validate_manifest` errors. If the result is saved to a file, extract only the paths you need with one `jq`.
4. **Ask** for every decision with more than one valid answer (auth method, region, which models, create vs update) with `ask_user_question`. Guessing produces entities the user then has to find and fix. If you are a sub-agent and the tool is unavailable, stop and return the question.
5. **Fetch existing state** the entity file asks for (see the next two sections). Steps 1, 3 and 5 are independent: issue them together. Call `get_manifest_json_schema` for large types (`service`, `virtual-model`, guardrail groups) in its own batch, because large results batched together get saved to a file instead of shown.
6. **Build** the manifest as JSON, following the schema.
7. **Validate, then apply once.** Call `validate_manifest` directly. If the manifest is too large to write inline (a provider account with many models), build it with a program into a sandbox file and call `validate_manifest` from the sandbox on that file instead. Fix and re-validate until `valid: true`. Then call `apply_manifest` once, directly (it needs user approval), with the validated JSON — never in the same batch as validation. `apply_manifest` is an upsert: a manifest with an existing identity (its `name`; `type` alone for legacy singletons) replaces that entity's whole manifest. When the user asks to *create*, use a new unique name.
8. **Link** — show the UI page from "After applying" with the real `controlPlaneUrl`.

## Gateway config kinds

Policies come in two kinds, and they are written differently:

| Kind | Types | How to write |
| --- | --- | --- |
| Legacy singleton | `gateway-rate-limiting-config`, `gateway-budget-config` | One document per tenant, identified by `type`. Call `get_gateway_config` right before building, add your rule to its `rules`, and send the whole list back. Never rebuild the list from memory or a summary — a missing rule is deleted. `name` is optional and ignored. |
| Named policy | `gateway-guardrails-config`, `tenant-rate-limit-config/model`, `tenant-rate-limit-config/mcp`, `tenant-budget-config`, `team-budget-config` | One manifest per policy, identified by its required `name`. Applying a new name adds a policy and touches nothing else. Applying an existing name replaces that policy. |

- Existing budget policies: `list_gateway_budgets`. Existing guardrails and rate-limit V2 policies cannot be listed with the tools (`get_gateway_config` returns nothing for them): to change one, ask the user for its name and current YAML.
- `tenant-rate-limit-config/*` cannot be validated or applied through the tools today; send the user to the UI for those.
- **Never send a `rules` array in a `gateway-guardrails-config` manifest.** The platform treats it as the legacy combined format and deletes every guardrails policy not in the array.

## Lists that replace everything

On an update, these fields replace the entity's entire current value. Anything you leave out is removed — access revoked, members dropped, credentials deleted. Start from the entity's current manifest, change only what was asked, and show the user the final list before applying.

| Field | Entity | Safer path |
| --- | --- | --- |
| `collaborators` | Provider accounts, virtual models, MCP servers, guardrail groups | On updates, remove it from the fetched manifest (see Collaborators) |
| `permissions` | Virtual account | Omit it unless changing permissions; else send `get_virtual_account`'s full list with one change |
| `members`, `managers` | Team | `add_team_members` / `remove_team_members` / `add_team_managers` / `remove_team_managers` |
| `integrations` | Guardrail group, provider account | Start from `list_provider_accounts`' current manifest; a dropped integration is deleted with its credentials |
| `rules` | Legacy singleton configs | `get_gateway_config` immediately before writing |
| whole role | Role (by `name`) | Check `list_roles` with `roleName` first; never overwrite `member`, `team-member`, `team-manager` unless asked |

Updating an MCP server whose auth changed deletes every user's stored tokens. Pass `force: false` to `apply_manifest`, and if it reports auth records to delete, ask the user before retrying with `force: true`.

## Collaborators

Access is stored as grants, separately from the manifest; `collaborators` is only one way to write them.

- **Omitted:** existing grants are left untouched. **`[]`** removes them all.
- **Present:** replaces every grant on the resource made by a manifest or on its **Access Control** page. Role-binding grants are kept.
- A fetched manifest's `collaborators` is the list last applied, not current access: grants changed later on the Access Control page are not written back, so re-sending it revokes them. No tool lists a resource's current grants.

**On create**, include collaborators, or other users cannot see the resource (the creator becomes manager automatically):

- The current user as **manager**: `user:<email>` from the session context (if the session has no `email`, use `virtualaccount:<subjectSlug>`).
- `team:everyone` as **access**, unless the user gives their own list (still include the current user as manager).
- Subjects are `user:<email>`, `team:<name>` or `virtualaccount:<name>`.

| Entity | Manager `role_id` | Access `role_id` |
| --- | --- | --- |
| Provider account (models), virtual model, guardrail group | `provider-account-manager` | `provider-account-access` |
| MCP server | `mcp-server-manager` | `mcp-server-user` |

These role IDs are platform constants — use the table instead of looking them up. MCP servers also have `mcp-server-approver`. MCP server group provider accounts accept only `provider-account-manager`; do not add `team:everyone` there.

**On update**, delete `collaborators` from the fetched manifest before applying, and on provider accounts also each integration's `authorized_subjects` (per-model access, same rules). **To change access** on an existing resource, send the user to its Access Control page (tenant admins can also use a `role-binding`, see `access-management.md`); do not write `collaborators`.

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
