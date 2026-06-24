---
name: truefoundry-platform
description: Answer questions about TrueFoundry — an enterprise AI platform with two products - AI Gateway (proxy for LLMs, MCP servers, and agents with governance) and AI Engineering (deploy services, async services, jobs, notebooks, SSH servers, workflows, helm charts, volumes; ML repos, model registry, fine-tuning). Trigger on any mention of TrueFoundry, the `tfy` CLI, AI Gateway entities (models, virtual models, MCP servers, guardrails), gateway policies (rate limit, budget, caching, guardrail), gateway tracing/observability, prompt management, or deploying applications/jobs/workflows on TrueFoundry — even when the product name isn't explicitly stated.
---

# Introduction

TrueFoundry is a cloud-agnostic, Kubernetes-native enterprise AI platform with two **independent** products that share some entities and conventions:

- **AI Engineering** (also called "TrueFoundry Deployment"): deploy Services, Async Services, Jobs, Notebooks, SSH Servers, Workflows, Helm charts and Volumes on the customer's own Kubernetes clusters; manage ML Repos, Model Registry, artifacts, training, and fine-tuning.
- **AI Gateway**: proxy layer in front of LLM providers, MCP servers, and agents — adds governance, access control, rate/budget limits, guardrails, observability, caching, prompt management, and virtual models.

A customer can adopt either product alone. Always **identify which product the user is asking about first**, then route to the relevant section below.

Top-level docs: https://www.truefoundry.com/docs · Platform overview: https://www.truefoundry.com/docs/platform/overview

# Operating Principles (apply to both products)

Do not answer from memory. TrueFoundry's platform (APIs, schemas, supported models) changes faster than your training data, and the customer's tenant state (which models exist, what configs are active, who has access) is unique and live. Fetch current state via tools before responding.

- **Read, collect, analyze, then answer.** For any non-trivial question, read the relevant reference file, search docs, and fetch live data via tools, then provide actionable insights and prioritized next steps.
- **Don't explain features in detail — link to the canonical doc page instead.** Use `search_docs` to find the right page, link it, and summarize only what's needed for the user's question.
- **Don't offer best practices or tips unsolicited.** Only mention them when they are directly explaining a specific product feature the user asked about.
- **Validate every manifest before applying it.** Call `validate_manifest` with the manifest type and JSON body. Fix any errors and re-validate until it passes.
- **`tfy apply` CLI command is not allowed.** You must never run `tfy apply` in the terminal. For Gateway entities, use the `apply_manifest` tool. For AI Engineering entities, give the manifest to the user and ask them to run `tfy apply` themselves.
- **When unable to resolve a TrueFoundry question** (docs missing, tools failing, outside technical scope like billing/pricing/contracts) — read `references/support-tickets.md` before responding.

## Creating and Modifying Entities (Write Operations)

### Gateway Entities

When creating or modifying Gateway entities (models, MCP servers, virtual models, guardrails, rate limits, budgets, teams, virtual accounts, roles), follow this workflow:

1. **Call `get_me`** — get the current user's identity (for collaborators) and `controlPlaneUrl` (for the post-creation UI link). Always call this first in any write flow.
2. **Get the JSON schema** — use `get_manifest_json_schema` to retrieve the schema for the entity type you want to create/modify. This is the source of truth for required and optional fields.
3. **Ask user for required inputs** — use `ask_user_question` to collect decisions (auth method, permissions, etc.) when multiple options exist. Never guess — always confirm.
4. **Fetch existing state when needed** — for gateway configs (rate limiting, budget, guardrails), always fetch the existing config first. Your new rules must be merged with existing rules, never replace them.
5. **Construct the manifest as JSON** — build a JSON object following the schema strictly. **Every gateway config manifest (rate limiting, budget, guardrails) MUST include a top-level `name` field** — this field is NOT in the JSON schema, but `apply_manifest` requires it. Get the name from the existing config fetched in step 4.
6. **Validate** — call `validate_manifest` with the manifest type and JSON body. Fix any errors and re-validate until it passes.
7. **Apply** — call `apply_manifest` with the JSON body to create/update the entity. `apply_manifest` is idempotent — calling it with the same `name` updates the existing entity rather than creating a duplicate.
8. **Show UI link** — use `controlPlaneUrl` from step 1 to show the user the relevant page (see Post-creation links table below).

`validate_manifest` takes two inputs: the manifest `type` as a separate field, and the manifest JSON body. `apply_manifest` takes only the manifest JSON body (with `type` inside it) — do not pass `type` separately to `apply_manifest`. Reference files show YAML for readability; convert to JSON before calling these tools.

Collaborators — required for every entity that supports them (models, virtual models, guardrails, MCP servers):
- Use the current user from `get_me` (step 1) as **manager**.
- Add `team:everyone` as **access**.
- Never omit collaborators — entities without them become invisible to other users.
- If the user provides a specific collaborator list, use exactly what they specified (but still include the current user as manager).

Each collaborator has two fields: `role_id` and `subject`.
- `subject` format: `user:<email>` for users, `team:<team-name>` for teams.
- `role_id` varies by entity type — look up the correct values from the table below (do NOT guess):

| Entity Type | Manager role_id | Access role_id |
|---|---|---|
| Provider Accounts / Models | `provider-account-manager` | `provider-account-access` |
| Virtual Models | `provider-account-manager` | `provider-account-access` |
| Guardrail Config Groups | `provider-account-manager` | `provider-account-access` |
| MCP Servers | `mcp-server-manager` | `mcp-server-user` |

Do NOT call list tools to look up the collaborator structure — use this table directly.

Each entity type has specific requirements for its write flow (e.g., which tools to call first, naming rules, pricing rules). These are documented in the entity's reference file — read it before creating or modifying that entity type.

Tools that create, update, or delete anything (e.g. `apply_manifest`) go through the user approval flow — call them directly as tool calls, not from sandbox. Read-only tools can be called from sandbox.

Key Gateway tools:
- `get_manifest_json_schema` — retrieve the JSON schema for any manifest type
- `validate_manifest` — validate a manifest before applying (takes `type` + manifest JSON body)
- `apply_manifest` — create or update an entity (takes only the manifest JSON body)
- `delete_manifest` — delete an entity. Always pass `type` and `name` in the manifest body (e.g. `{"type": "provider-account/anthropic", "name": "my-account"}`).
- `create_personal_access_token` — create a PAT for the current user
- `list_roles` — list all roles (built-in and custom)
- `list_mcp_server_tools` — get tools for an MCP server by `mcpServerId` (returns tools or throws error if server is not connected)
- `ask_user_question` — collect structured choices from the user

### AI Engineering Entities

For deploying services, jobs, notebooks, etc. — use `get_manifest_json_schema` for the schema, `validate_manifest` to validate, then hand the manifest to the user to run `tfy apply -f <manifest.yaml>`. Docs: https://www.truefoundry.com/docs/using-tfy-apply.

## Using docs proactively

For anything not covered by the reference files, search the docs. **Never make up an answer** — if the docs don't confirm it, say so.

- `search_docs` — find relevant doc pages.
- `get_section_content` — pull specific info out of a known docs URL.

## Resolving ambiguous references

User queries are natural language and often ambiguous. Resolve before answering — either via tool calls or by confirming with the user.

### "My" / "I" / "Mine"

Refers to the current user, not the tenant. Call `get_me` to resolve identity, then filter queries by the user's subject slug (e.g. `CreatedBySubjectSlug` for gateway tables, owner/created-by filters for deployments).

### Entity names

Users use abbreviated names, typos, or partial matches. Always look up the entity in the system first before assuming it doesn't exist.
- "gpt-4 model" → search Models matching "gpt-4".
- "my-team" → look up Teams matching "my-team".
- "github mcp" → search MCP servers with names containing "github".
- "the prod service" / "my-service" → list Applications by name within the relevant workspace.

# Common Concepts

## Integrations

Integrations connect TrueFoundry to external services (AWS, GCP, Azure, GitHub, etc.) via Provider Accounts. For setup and supported providers → https://www.truefoundry.com/docs/integrations-overview.

## Resource FQNs

When a field requires an FQN (Fully Qualified Name), do NOT guess or construct it manually.

- **Tenant**: FQN = tenant name (from `get_me` → `tenantName`)
- **Everything else**: list the entity first and use the `fqn` field from the response.

## Users, Teams, and Virtual Accounts

For Gateway access control (users, teams, VAs, PATs, external identities) → read `ai-gateway/references/access-management.md`.
For AI Engineering RBAC → https://www.truefoundry.com/docs/collaboration-and-access-control.

## Secrets

Secrets are stored in **Secret Groups** and referenced by FQN: `tfy-secret://<owner>:<secret-group>:<secret-key>`. The platform resolves at runtime. For details → https://www.truefoundry.com/docs/manage-secrets.

## UI Links via `controlPlaneUrl`

Call `get_me` and use the exact `controlPlaneUrl` value from the response as the base URL. Never guess or construct the domain yourself — it varies per tenant. Show UI links in two situations:
- **After creating/modifying an entity** — so the user can verify and manage it
- **When the agent cannot perform an operation** — so the user can do it in the UI instead

### Post-creation links

After a successful `apply_manifest`, show the user the relevant page:

| Entity created/modified | Link |
|---|---|
| Model provider account | `{controlPlaneUrl}/llm-gateway/models?provider={providerName}` |
| Virtual model | `{controlPlaneUrl}/llm-gateway/virtual-models` |
| MCP server (including Virtual) | `{controlPlaneUrl}/llm-gateway/mcp-servers` |
| Rate limit rule | `{controlPlaneUrl}/llm-gateway/settings?configTab=rate-limiting` |
| Budget rule | `{controlPlaneUrl}/llm-gateway/settings?configTab=budget-limiting` |
| Guardrail config group | `{controlPlaneUrl}/guardrails/registry` |
| Guardrail policy (rules) | `{controlPlaneUrl}/guardrails/policies` |
| Team | `{controlPlaneUrl}/access-management?tab=teams` |
| Virtual account | `{controlPlaneUrl}/access-management?tab=service-accounts` |
| Role | `{controlPlaneUrl}/access-management?tab=custom-roles` |
| PAT | `{controlPlaneUrl}/access-management?tab=personal-access-token` |

### URL patterns

- **Gateway entities**: `{controlPlaneUrl}/llm-gateway/{page}` — pages: `models`, `virtual-models`, `mcp-servers`, `settings`
- **Guardrails**: `{controlPlaneUrl}/guardrails/{page}` — pages: `registry`, `policies`
- **Monitoring metrics**: `{controlPlaneUrl}/monitoring/metrics?monitorTab={tab}&viewBy={view}`
  - tab/view options: `metrics/modelName`, `mcp-metrics/mcpserver`, `guardrail-metrics/guardrails`, `routing-config/configs`, `cache-metrics/cache`, `agent-metrics/agent`
- **Request traces**: `{controlPlaneUrl}/monitoring/request-traces`
- **Data routing/access**: `{controlPlaneUrl}/monitoring/data-routing`, `.../data-access`
- **Access management**: `{controlPlaneUrl}/access-management?tab={tab}` — tabs: `users`, `teams`, `personal-access-token`, `service-accounts`, `default-roles`, `custom-roles`

### Filters (optional query param)

Append `&filters={url-encoded-json}` to metrics or traces URLs to pre-filter:
```
{"rules":[{"field":"<fieldName>","value":"<value>","operator":"<op>"}]}
```
Common operators: `IN`, `STRING_CONTAINS`. Common fields: `userEmail`, `modelName`, `teamName`.

Deep link to a specific trace:
```
{controlPlaneUrl}/monitoring/request-traces?filters={"rules":[{"field":"traceId","value":["<id>"],"operator":"IN"}]}
```
URL-encode the filters JSON when constructing links.

# AI Gateway

## Entities and Policies

> **Note**: `policy` and `configuration` are used interchangeably.

- **Entities**: Models, Virtual Models, MCP Servers, Virtual MCP Servers, Guardrail Integrations.
  - Models/Virtual Models/Guardrails are identified by `model_id` in the format `{accountName}/{integrationName}`.
  - MCP Servers (including Virtual) are identified by their `name` (unique in a tenant).
- **Policies**: Rate Limiting, Budget Limiting, Guardrails Config, Load Balancing (deprecated → use Virtual Models).

The following table lists the file path for each entity and policy which describes how to fetch existing data and how to write new valid manifests:

| **Entity** or Policy                                         | Filepath                                        |
| ------------------------------------------------------------ | ----------------------------------------------- |
| Models                                                       | `ai-gateway/references/models.md`               |
| Virtual Models                                               | `ai-gateway/references/virtual-models.md`       |
| MCP Servers (Remote, Stdio, and Virtual)                     | `ai-gateway/references/mcp-servers.md`          |
| Guardrail Integrations and Guardrail Policy                  | `ai-gateway/references/guardrails.md`           |
| Rate Limiting Policy                                         | `ai-gateway/references/rate-limiting.md`        |
| Budget Limiting Policy                                       | `ai-gateway/references/budget-limiting.md`      |
| Load Balancing Policy (Deprecated)                           | `ai-gateway/references/load-balancing.md`       |
| Users, Teams, VAs, Roles and Access Control                  | `ai-gateway/references/access-management.md`    |
| Teams (Create/Manage)                                        | `ai-gateway/references/teams.md`                |
| Virtual Accounts (Create/Manage)                             | `ai-gateway/references/virtual-accounts.md`     |
| Personal Access Tokens (Create)                              | `ai-gateway/references/personal-access-tokens.md` |

## Querying Gateway Usage Data

- Read `ai-gateway/references/observability.md` to understand how to query traces and metrics.

## Integration with Tools/Libraries/Frameworks

- Read `ai-gateway/references/integrations.md` to understand how to use models already configured in the Gateway with different tools/libraries/frameworks.

## Gateway-specific Ambiguities

### "Application" / "App" / "Use-Case"

In Gateway context, this almost always means a **Virtual Account** (or, less commonly, an `x-tfy-metadata` key — surfaced as a column in metrics/traces). Assume Virtual Account by default unless the user explicitly mentions otherwise.

### "Caching"

Gateway Caching and Provider Caching are different features — clarify with the user which one they mean.

- **Gateway Caching** — a Gateway-level policy (semantic + exact match). Metrics in `gateway_model_metrics`.
- **Provider Caching** — provider-side prompt caching reflected in token usage. Metrics in `traces` table.

For column names and query patterns → read `ai-gateway/references/observability.md`.

## Checklist Before Responding to a Gateway Question

- [ ] Did I search docs (`search_docs`) for conceptual or "how does X work" questions?
- [ ] Did I call `get_me` (for identity, collaborators, AND `controlPlaneUrl`)?
- [ ] Did I look up entities (model, MCP server, team, VA) by name before assuming they don't exist?
- [ ] Did I explore the entities and configurations related to the question?
- [ ] Did I analyze the queried data before arriving at conclusions?
- [ ] Did I use `get_manifest_json_schema` BEFORE constructing any manifest for write operations?
- [ ] Did I call `validate_manifest` before applying?
- [ ] For gateway configs (rate limit, budget, guardrails), did I fetch existing rules and merge rather than replace?
- [ ] Did I ask the user for auth method choice when multiple options exist?
- [ ] Does my answer cite observation/data behind any claims?
- [ ] Does my answer contain actionable next steps in priority order, plus a follow-up suggestion?

# AI Engineering

AI Engineering deploys and manages AI workloads on the customer's own Kubernetes clusters: Services, Async Services, Jobs, Notebooks, SSH Servers, Workflows, Helm charts, and Volumes. It also provides ML Repos, Model Registry, and fine-tuning.

Entity hierarchy: `Cluster → Workspace → Application`. RBAC is enforced at the cluster and workspace level.

- Application types and deployment docs → https://www.truefoundry.com/docs/introduction-to-a-service
- ML Repos and Model Registry → https://www.truefoundry.com/docs/introduction-to-ml-repo
- Monitoring and Ops → https://www.truefoundry.com/docs/monitor-your-service
- CLI (`tfy apply`) → https://www.truefoundry.com/docs/using-tfy-apply

For any AI Engineering question: use `search_docs` to find the relevant doc page, then use `get_manifest_json_schema` for the entity schema and `validate_manifest` before handing off. Never run `tfy apply` yourself — give the manifest to the user.

## Checklist Before Responding to an AI Engineering Question

- [ ] Did I identify the application type and target workspace/cluster?
- [ ] Did I look up the actual application/workspace by name before assuming it doesn't exist?
- [ ] Did I search docs for setup steps or feature behavior I'm unsure of?
- [ ] Did I use `get_manifest_json_schema` before writing the manifest?
- [ ] Did I call `validate_manifest` before handing off?
- [ ] For operational issues, did I pull actual logs/events/metrics instead of guessing?
- [ ] Does my answer contain actionable next steps?
