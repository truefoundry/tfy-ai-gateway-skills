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

These rules apply universally — keep them in mind regardless of which product the question is about. The reason they exist is that TrueFoundry features evolve quickly and the customer's tenant has live state — answering from prior knowledge alone is often wrong.

- **Read, collect, analyze, then answer.** For any non-trivial question, read the relevant reference file, search docs, and fetch live data via tools, then provide actionable insights and prioritized next steps.
- **Don't explain features in detail — link to the canonical doc page instead.** Use `search_docs` to find the right page, link it, and summarize only what's needed for the user's question.
- **Don't offer best practices or tips unsolicited.** Only mention them when they are directly explaining a specific product feature the user asked about.
- **Validate every manifest before suggesting it.** Run `scripts/validate_schema.py --file-path <file.yaml>`. Invalid schemas fail at apply time and waste the user's iteration time. The script checks structure only — it does not verify that referenced entities (models, users, teams, workspaces, secrets) exist.
- **For AI Engineering manifests, explore `scripts/manifest_schemas.py` BEFORE generating YAML.** It is the source-of-truth Pydantic schema for every manifest type. For Gateway write operations, use the `get_manifest_json_schema` tool instead (see § Creating and Modifying Entities).
- **`tfy apply` CLI command is not allowed.** You must never run `tfy apply` in the terminal. For Gateway entities, use the `apply_manifest` tool. For AI Engineering entities, give the manifest to the user and ask them to run `tfy apply` themselves.

## Creating and Modifying Entities (Write Operations)

### Gateway Entities

When creating or modifying Gateway entities (models, MCP servers, virtual models, guardrails, rate limits, budgets, teams, virtual accounts), follow this workflow:

1. **Get the JSON schema** — use `get_manifest_json_schema` to retrieve the schema for the entity type you want to create/modify. This is the source of truth for required and optional fields.
2. **Ask user for required inputs** — use `ask_user_question` to collect decisions (auth method, permissions, etc.) when multiple options exist. Never guess — always confirm.
3. **Fetch existing state when needed** — for gateway configs (rate limiting, budget, guardrails), always fetch the existing config first. Your new rules must be merged with existing rules, never replace them.
4. **Construct the manifest** — write a YAML manifest to a file, following the JSON schema strictly. **Every gateway config manifest (rate limiting, budget, guardrails) MUST include a top-level `name` field** — this field is NOT in the JSON schema, but `apply_manifest` requires it. Get the name from the existing config fetched in step 3.
5. **Validate locally** — run `python scripts/validate_schema.py --file-path <manifest.yaml>` to check structure. Fix and repeat until valid. **Exception**: skip this step for gateway config types (rate limiting, budget, guardrails) — their schemas use `extra = forbid` and reject the required `name` field. For those, rely on dry-run (step 6) for validation.
6. **Dry-run** — call `apply_manifest` with `dryRun: true` to validate against the live platform.
7. **Apply** — once dry-run passes, call `apply_manifest` without dry-run to create/update the entity. `apply_manifest` is idempotent — calling it with the same `name` updates the existing entity rather than creating a duplicate.

Collaborators:
- Ask the user if they want to add any collaborators. If none specified, default to adding only the current user (from `get_me`) as manager. Do NOT add anyone else by default.
- If the user provides specific collaborators, use exactly what they specified.

Critical tool-call requirements (do NOT skip these):
- For **MCP servers with OAuth**: you MUST call `get_mcp_server_oauth_config` to get the authorization server metadata before building the manifest.
- For **model provider accounts**: you MUST call `list_providers` to get the catalog of supported models and regions before building the manifest.

> **WARNING**: `apply_manifest` is a destructive MCP tool. You MUST call it directly as a tool so it goes through the user approval flow. NEVER call it from code mode, sandbox, or a script — it will be blocked.

Key Gateway write tools:
- `get_manifest_json_schema` — retrieve the JSON schema for any manifest type
- `apply_manifest` — create or update an entity (supports `dryRun` for validation)
- `get_mcp_server_oauth_config` — get OAuth 2.0 Authorization Server Metadata for MCP server auth setup
- `list_providers` — platform catalog of all supported providers, models, pricing, and regions (NOT existing configs)
- `create_personal_access_token` — create a PAT for the current user
- `ask_user_question` — collect structured choices from the user

### AI Engineering Entities

For AI Engineering entities (services, async services, jobs, notebooks, SSH servers, workflows, helm charts, volumes):

1. **Look up the schema** — find the type in `scripts/manifest_schemas.py` (e.g. `Literal["service"]`, `Literal["job"]`).
2. **Construct the manifest** — write YAML matching the schema exactly.
3. **Validate locally** — run `python scripts/validate_schema.py --file-path <manifest.yaml>`.
4. **Hand off to the user** — give them the manifest and ask them to run `tfy apply -f <manifest.yaml>`. You must NOT run `tfy apply` yourself.

For CLI install, auth, dry-run, environment override, and CI/CD usage → https://www.truefoundry.com/docs/using-tfy-apply.

## Using docs proactively

The reference files in this skill cover the most-asked structural topics, but they don't cover every detail. For conceptual questions, setup guides, integration steps, or anything not directly addressed by the references — search the docs first. **Never make up an answer** about TrueFoundry behavior; if the docs don't confirm it, say so.

- `search_docs` — find relevant doc pages.
- `extract` — pull specific info out of a known docs URL.

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

These entities and conventions are shared between AI Gateway and AI Engineering. When a user asks about them, the answer often spans both products.

## Integrations

Integrations connect TrueFoundry to external services and clouds. Each integration is configured on a **Provider Account** (the parent entity that holds credentials and access control); the provider account then exposes one or more concrete integrations.

| Provider | Integration Types |
| --- | --- |
| AWS | S3 (blob), ECR (registry), SSM / Secrets Manager (secrets), EKS (cluster) |
| GCP | GCS (blob), GCR (registry), GSM (secrets), GKE (cluster) |
| Azure | ABS (blob), ACR (registry), AKS (cluster) |
| Github / Gitlab / Bitbucket / Azure Repos | source code |
| DockerHub / JFrog / Quay | docker registry |
| Slack / PagerDuty | notifications |

Each integration can be scoped to specific users and teams who can view/use it.

For provider-specific setup steps, supported services per provider, and troubleshooting → https://www.truefoundry.com/docs/integrations-overview, then `search_docs` for the per-provider page (e.g. `integration-provider-aws`, `github-integration-set-up`).

## Users, Teams, and Virtual Accounts

Identity concepts are shared across both products:

- **User** — a human with email + Personal Access Tokens (PATs). PATs are tied to the user; they become invalid when the user leaves the org. Use PATs for development only.
- **Team** — group of users; can be synced from SSO groups. An implicit `everyone` team includes all users in the tenant (but not virtual accounts).
- **Virtual Account (VA)** — non-human identity for an application or service, with its own Virtual Account Tokens (VATs). Recommend one VA per application. Use VATs for production / CI / shared apps.
- **External Identity** — JWT-based auth via external IdPs (Okta, Azure AD) without a TrueFoundry user account; useful for B2B.

Where access control is enforced differs by product:

- **AI Gateway** — access is granted at the **Provider Account** level (Manager / User roles); VAs can be scoped to specific models, provider accounts, and MCP servers. Read `ai-gateway/references/access-management.md` for the full model, including VAT auto-rotation, secret-store sync, and rotation notifications.
- **AI Engineering** — RBAC is enforced at the **Cluster** and **Workspace** level. For role assignment, granting workspace access, and SSO/team management → https://www.truefoundry.com/docs/collaboration-and-access-control and https://www.truefoundry.com/docs/platform/manage-user-roles-and-permissions.

## Secrets

Sensitive values (API keys, DB passwords, third-party tokens) are stored in **Secret Groups** backed by a secret-store integration (AWS SSM / Secrets Manager, GCP Secret Manager, Azure Vault, HashiCorp Vault). Secrets are referenced by FQN of the form:

```
tfy-secret://<owner>:<secret-group>:<secret-key>
```

The platform resolves the FQN at runtime, so the manifest never contains the raw value.

Used by both products:
- **AI Engineering** — env-var values in Service / Job / Notebook deployment specs.
- **AI Gateway** — provider credentials (e.g. OpenAI API key), VAT secret-store sync targets.

For creating, organizing, and rotating secrets → https://www.truefoundry.com/docs/manage-secrets and https://www.truefoundry.com/docs/environment-variables-and-secrets.

## Audit Logs

Every state-changing action (manifest apply, login, permission grant, deployment trigger, secret create/update) is recorded in audit logs. Use them to answer "who did what when" and for compliance reporting.

The available filters, retention, and export options are documented — `search_docs` for "audit logs" rather than guessing column names or query syntax.

# AI Gateway

TrueFoundry AI Gateway is the proxy layer that sits between applications and the AI model providers and MCP Servers.

## Understanding Manifests for Gateway Entities and Policies

> **Note**: `policy` and `configuration` are used interchangeably.

- Entities are integrations that can be used via the Gateway. E.g.
  - Models from vendors like OpenAI, Anthropic, etc
  - Virtual Models allow routing and fallback to one of the target models based on priority, weight, latency SLAs
  - Remote MCP Servers from products like Github, Linear or Self Managed MCP Servers
  - Virtual MCP Servers allow combining tools from several Remote MCP Servers
  - Guardrail Integrations from third party vendors or managed by TrueFoundry
  - Models/Virtual Models/Guardrails always need to identified by: model_id of the format `{accountName}/{integrationName}`. This alone should be sufficient to identify the entity.
  - MCP servers always need to be identified by their names. Names are unique in a tenant.

- Policies are Gateway level rules that activate while using the entities. E.g.
  - Rate Limiting Policy decides when requests to a set of models from a set of users should be rate limited
  - Budget Limiting Policy decides when requests to a set of models from a set of users should be budget limited
  - Load Balancing Policy (aka Routing Config) decides when requests to a set of models should be load balanced. This feature has been deprecated in favor of Virtual Models.

The following table lists the file path for each entity and policy which describes how to fetch existing data and how to write new valid manifests:

| **Entity** or Policy                                         | Filepath                                        |
| ------------------------------------------------------------ | ----------------------------------------------- |
| Models                                                       | `ai-gateway/references/models.md`               |
| Virtual Models                                               | `ai-gateway/references/virtual-models.md`       |
| MCP Servers and Virtual MCP Servers                          | `ai-gateway/references/mcp-servers.md`          |
| Guardrail Integrations and Guardrail Policy                  | `ai-gateway/references/guardrails.md`           |
| Rate Limiting Policy                                         | `ai-gateway/references/rate-limiting.md`        |
| Budget Limiting Policy                                       | `ai-gateway/references/budget-limiting.md`      |
| Load Balancing Policy (Deprecated)                           | `ai-gateway/references/load-balancing.md`       |
| Users, Teams, Virtual Accounts and Access Control            | `ai-gateway/references/access-management.md`    |
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

- **Gateway Caching** (Semantic + Exact Match) is a policy configured at the Gateway level. Data lives in `gateway_model_metrics` via `CacheHit`, `CacheType`, `CacheLookupStatus`, and related columns.
- **Provider Caching** is provider-side prompt caching reflected in token usage (e.g. `cache_read_input_tokens`). Tokens are available in `SpanAttributesNumber` on `Model` spans in the `traces` table via `tfy.model.metric.cache_read_input_tokens` and `tfy.model.metric.cache_creation_input_tokens` — cheaper to query than parsing the `TfyGatewayOutput` JSON.

## Checklist Before Responding to a Gateway Question

- [ ] Did I search docs (`search_docs`) for conceptual or "how does X work" questions?
- [ ] Did I resolve the user's identity with `get_me` when the query uses "my"/"I"/"mine"?
- [ ] Did I look up entities (model, MCP server, team, VA) by name before assuming they don't exist?
- [ ] Did I explore the entities and configurations related to the question?
- [ ] Did I analyze the queried data before arriving at conclusions?
- [ ] Did I use `get_manifest_json_schema` BEFORE constructing any manifest for write operations?
- [ ] Did I validate generated manifests with `scripts/validate_schema.py` before dry-running? (Skip for gateway configs — they reject the required `name` field.)
- [ ] Did I dry-run with `apply_manifest` using `dryRun: true` before applying?
- [ ] For gateway configs (rate limit, budget, guardrails), did I fetch existing rules and merge rather than replace?
- [ ] Did I ask the user for auth method choice when multiple options exist?
- [ ] Does my answer cite observation/data behind any claims?
- [ ] Does my answer contain actionable next steps in priority order, plus a follow-up suggestion?

# AI Engineering

AI Engineering covers everything around deploying and managing AI workloads on the customer's own Kubernetes infrastructure, plus the artifacts produced by training and inference.

It has two parts:
1. **Deployments** — services, async services, jobs, notebooks, SSH servers, workflows, helm charts, volumes.
2. **Repositories** — ML Repos for storing experiments, metrics, model artifacts and metadata; Model Registry for versioned model serving.

## Deployment Concepts

Entity hierarchy: `Cluster → Workspace → Application`.

- **Cluster** — an actual Kubernetes cluster connected via the Cluster integration. Customers bring their own cluster; TrueFoundry doesn't provide compute.
- **Workspace** — abstraction over a Kubernetes namespace; the unit of access control alongside the cluster.
- **Application** — what the user deploys; always lives inside a workspace. Each version of an application is a "deployment"; an application has at most one active deployment at a time (typically the latest, unless rollout failed).
- The deployment manifest is converted to a set of Kubernetes manifests under the hood. The applied K8s manifests are inspectable via the truefoundry MCP / UI.

RBAC is enforced at the cluster and workspace level — see Common Concepts → Users, Teams, and Virtual Accounts.

## Application Types

| Type | Purpose | Docs |
| --- | --- | --- |
| Service | Long-running app serving traffic (REST, gRPC, Streamlit, FastAPI, …) | https://www.truefoundry.com/docs/introduction-to-a-service |
| Async Service | Long-running app processing messages from a queue | https://www.truefoundry.com/docs/introduction-to-async-service |
| Job | One-off or cron-scheduled task; can have multiple runs | https://www.truefoundry.com/docs/introduction-to-a-job |
| Notebook | Hosted Jupyter notebook for experimentation | https://www.truefoundry.com/docs/launch-notebooks |
| SSH Server | Remote pod for VSCode/Cursor SSH-based development | https://www.truefoundry.com/docs/launch-an-ssh-server |
| Workflow | DAG of tasks (Flyte-based) | https://www.truefoundry.com/docs/introduction-to-workflow |
| Helm | A Helm chart deployment | https://www.truefoundry.com/docs/deploy-helm-charts |
| Volume | Persistent storage attached to other apps | https://www.truefoundry.com/docs/introduction-to-volume |

For type-specific config (resources, autoscaling, ports/domains, probes, rollout strategy, secrets, mounted volumes, CI/CD), follow the doc link above and `search_docs` for the specific feature (e.g. "autoscaling overview", "scale to zero", "canary rollout", "ports and domains", "setting up cicd").

## Deployment Manifests

1. Look up `Literal["<type>"]` in `scripts/manifest_schemas.py` (e.g. `service`, `async-service`, `job`, `notebook`, `ssh-server`, `workflow`, `helm`, `volume`).
2. Write the YAML, copying field names exactly from the schema.
3. Validate: `python scripts/validate_schema.py --file-path <manifest.yaml>`.
4. Give the manifest to the user to apply with `tfy apply -f <manifest.yaml>`.

For CLI install, auth, dry-run, environment override, and CI/CD usage → https://www.truefoundry.com/docs/using-tfy-apply.

For programmatic deployment (Python SDK, raw API), search docs: `deploy-service-programatically`, `deploy-job-using-python-sdk`.

## ML Repositories, Model Registry, Artifacts

ML Repos are versioned stores for experiments, metrics, model artifacts, and metadata. They live on the customer's own blob storage.

- ML Repo intro → https://www.truefoundry.com/docs/introduction-to-ml-repo
- Logging models → https://www.truefoundry.com/docs/log-models
- Model Registry → https://www.truefoundry.com/docs/model-registry

For experiment tracking SDK usage, model versioning, stages, lineage, and artifact retrieval → `search_docs`.

## Operations: Status, Logs, Metrics, Alerts

For deployed applications, status / events / logs / metrics are visible in the UI and via the truefoundry MCP. Each application has a `status` reflecting the active deployment.

- Monitoring a service → https://www.truefoundry.com/docs/monitor-your-service
- Autoscaling → https://www.truefoundry.com/docs/autoscaling-overview
- Alerts (require Slack or PagerDuty integration) → `search_docs` for "alerts" / "slack-bot-integration" / "pagerduty-integration"

For any operational question (rollout failure, OOM, autoscaling not triggering, health probe failing), prefer pulling actual logs/events via the MCP rather than guessing — surface the real error message, then point to the relevant doc.

## Checklist Before Responding to an AI Engineering Question

- [ ] Did I identify the application type (service, job, notebook, …) and the target workspace/cluster?
- [ ] Did I look up the actual application/workspace by name before assuming it doesn't exist?
- [ ] Did I search docs (`search_docs`) for setup steps or feature behavior I'm unsure of?
- [ ] Did I check `scripts/manifest_schemas.py` BEFORE writing YAML?
- [ ] Did I validate the manifest with `scripts/validate_schema.py`?
- [ ] For operational issues, did I pull actual logs / events / metrics instead of guessing?
- [ ] Does my answer contain actionable next steps in priority order, plus a follow-up suggestion?
