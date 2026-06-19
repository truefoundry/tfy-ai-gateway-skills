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

TrueFoundry features evolve quickly and the customer's tenant has live state — answering from prior knowledge alone is often wrong.

- **Read, collect, analyze, then answer.** For any non-trivial question, read the relevant reference file, search docs, and fetch live data via tools, then provide actionable insights and prioritized next steps.
- **Don't explain features in detail — link to the canonical doc page instead.** Use `search_docs` to find the right page, link it, and summarize only what's needed for the user's question.
- **Don't offer best practices or tips unsolicited.** Only mention them when they are directly explaining a specific product feature the user asked about.
- **Validate every manifest before applying it.** Call `validate_manifest` with the manifest type and JSON body. Fix any errors and re-validate until it passes.
- **`tfy apply` CLI command is not allowed.** You must never run `tfy apply` in the terminal. For Gateway entities, use the `apply_manifest` tool. For AI Engineering entities, give the manifest to the user and ask them to run `tfy apply` themselves.

## Creating and Modifying Entities (Write Operations)

### Gateway Entities

When creating or modifying Gateway entities (models, MCP servers, virtual models, guardrails, rate limits, budgets, teams, virtual accounts, roles), follow this workflow:

1. **Get the JSON schema** — use `get_manifest_json_schema` to retrieve the schema for the entity type you want to create/modify. This is the source of truth for required and optional fields.
2. **Ask user for required inputs** — use `ask_user_question` to collect decisions (auth method, permissions, etc.) when multiple options exist. Never guess — always confirm.
3. **Fetch existing state when needed** — for gateway configs (rate limiting, budget, guardrails), always fetch the existing config first. Your new rules must be merged with existing rules, never replace them.
4. **Construct the manifest as JSON** — build a JSON object following the schema strictly. **Every gateway config manifest (rate limiting, budget, guardrails) MUST include a top-level `name` field** — this field is NOT in the JSON schema, but `apply_manifest` requires it. Get the name from the existing config fetched in step 3.
5. **Validate** — call `validate_manifest` with the manifest type and JSON body. Fix any errors and re-validate until it passes.
6. **Apply** — call `apply_manifest` with the JSON body to create/update the entity. `apply_manifest` is idempotent — calling it with the same `name` updates the existing entity rather than creating a duplicate.

> **CRITICAL**: Both `validate_manifest` and `apply_manifest` take a **JSON** object — NOT YAML, NOT a string. The manifest examples in reference files are shown in YAML for readability, but you MUST convert to JSON before passing to these tools. Do NOT pass `dryRun: true` to `apply_manifest` — validation is already handled by `validate_manifest`.

Collaborators — **MANDATORY** for every entity that supports them (models, virtual models, guardrails, MCP servers):
- Call `get_me` to resolve the current user's identity.
- Every manifest MUST include collaborators. Never omit them.
- Always add the current user (from `get_me`) as **manager**.
- Always add `team:everyone` as **access**.
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

Critical tool-call requirements (do NOT skip these):
- For **MCP servers**: you MUST call `list_mcp_catalogue` first to check if the server is TFY-managed or a known integration. Only call `get_mcp_server_oauth_config` when the user chooses OAuth2 auth for a remote server.
- For **model provider accounts**: you MUST call `list_providers` to get the catalog of supported models and regions before building the manifest. NEVER use your own knowledge for model names, IDs, or supported modes — only use what `list_providers` returns.
- For **model integrations**: `cost: metric: public_cost` ONLY for `chat`, `completion`, `embedding`, `responses` modes. Omit `cost` entirely for all other modes.
- For **model integrations**: integration `name` MUST equal `model_id` for `realtime`, `audio_transcription`, `audio_translation`, `text_to_speech` modes.

> **CRITICAL**: Tools that create, update, or delete anything (e.g. `apply_manifest`) MUST be called directly as tool calls — never from sandbox. They need to go through the user approval flow. Read-only tools can be called from sandbox.

Key Gateway write tools:
- `get_manifest_json_schema` — retrieve the JSON schema for any manifest type
- `validate_manifest` — validate a manifest before applying (takes type and JSON body)
- `apply_manifest` — create or update an entity
- `list_mcp_catalogue` — catalog of TFY-managed and known integration MCP servers (call FIRST when creating any MCP server)
- `get_mcp_server_oauth_config` — get OAuth 2.0 Authorization Server Metadata (only needed when OAuth2 is selected for a remote server)
- `list_providers` — platform catalog of all supported providers, models, pricing, and regions (NOT existing configs)
- `create_personal_access_token` — create a PAT for the current user
- `list_roles` — list all roles (built-in and custom)
- `ask_user_question` — collect structured choices from the user

### AI Engineering Entities

For deploying services, jobs, notebooks, etc. — use `get_manifest_json_schema` for the schema, `validate_manifest` to validate, then hand the manifest to the user to run `tfy apply -f <manifest.yaml>`. Docs: https://www.truefoundry.com/docs/using-tfy-apply.

## Using docs proactively

For anything not covered by the reference files, search the docs. **Never make up an answer** — if the docs don't confirm it, say so.

- `search_docs` — find relevant doc pages.
- `extract_text` — pull specific info out of a known docs URL.

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

# AI Gateway

## Entities and Policies

> **Note**: `policy` and `configuration` are used interchangeably.

- **Entities**: Models, Virtual Models, MCP Servers, Guardrail Integrations.
  - Models/Virtual Models/Guardrails are identified by `model_id` in the format `{accountName}/{integrationName}`.
  - MCP Servers are identified by their `name` (unique in a tenant).
- **Policies**: Rate Limiting, Budget Limiting, Guardrails Config, Load Balancing (deprecated → use Virtual Models).

The following table lists the file path for each entity and policy which describes how to fetch existing data and how to write new valid manifests:

| **Entity** or Policy                                         | Filepath                                        |
| ------------------------------------------------------------ | ----------------------------------------------- |
| Models                                                       | `ai-gateway/references/models.md`               |
| Virtual Models                                               | `ai-gateway/references/virtual-models.md`       |
| MCP Servers (Remote and Stdio)                               | `ai-gateway/references/mcp-servers.md`          |
| Guardrail Integrations and Guardrail Policy                  | `ai-gateway/references/guardrails.md`           |
| Rate Limiting Policy                                         | `ai-gateway/references/rate-limiting.md`        |
| Budget Limiting Policy                                       | `ai-gateway/references/budget-limiting.md`      |
| Load Balancing Policy (Deprecated)                           | `ai-gateway/references/load-balancing.md`       |
| Users, Teams, Virtual Accounts and Access Control            | `ai-gateway/references/access-management.md`    |
| Teams (Create/Manage)                                        | `ai-gateway/references/teams.md`                |
| Virtual Accounts (Create/Manage)                             | `ai-gateway/references/virtual-accounts.md`     |
| Roles (Create/Manage)                                        | `ai-gateway/references/roles.md`                |
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
- [ ] Did I resolve the user's identity with `get_me` when the query uses "my"/"I"/"mine"?
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
