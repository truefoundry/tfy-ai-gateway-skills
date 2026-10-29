---
name: truefoundry-platform
description: Answer questions about TrueFoundry, an enterprise AI platform. Covers two products — AI Gateway (LLM proxy, MCP servers, agents, governance) and AI Engineering (deploy services, jobs, notebooks, workflows; deploy HuggingFace/catalogue models with vLLM/SGLang/etc.; ML repos, model registry, fine-tuning). Triggers on TrueFoundry, tfy CLI, Gateway entities/policies, tracing/observability, prompt management, or deploying applications and models — even when the product name isn't stated. Read this file whole with one `cat`.
---

# TrueFoundry

TrueFoundry has two independent products; a customer may use either alone.

- **AI Gateway** — a proxy in front of LLM providers, MCP servers and agents: access control, rate and budget limits, guardrails, observability, virtual models.
- **AI Engineering** — deploy services, jobs, notebooks, models, Helm charts and more on the customer's own Kubernetes clusters (`Cluster → Workspace → Application`).

## How to use this skill

1. Read this whole file first (`cat`, never `head`): the intent tables run to its end. Decide which product the question is about.
2. Find the user's intent in that product's table below and read the file it names. Read every file you need in **one batch**, together with your first other calls: one `cat` per file, in full (never `head` or a grep: the rules are spread through it), because a single result over 24,000 characters is saved to a file instead of shown. Keep a batch of file reads under ~35,000 characters.
3. Follow that file. It says what to fetch, what to ask, and what to build.

Read an entity's file before any write or data query for it — the files hold the rules that tool errors never explain. A conceptual or "where is the doc" question needs only `search_docs`.

## Ground rules

- **Live state over memory.** The platform changes faster than your training data, and every tenant is different. Fetch state with tools before answering; if the docs don't confirm something, say so. Dates too: get `get_current_datetime`'s result before building a time range.
- **Docs.** `search_docs` finds pages; `get_page_layout` shows a page's headings; `get_section_content` returns a page or one `#section`. Fetch only URLs and anchors from those tools or this skill. Search before saying a topic is not covered. Link the doc page and summarize only what the question needs; don't volunteer best practices.
- **Session context** (identity, tenant, `controlPlaneUrl`, `tracesTable`) is in your instructions under "Session context". Only if it is missing, call `get_session_context`; reuse its result while it is in the conversation.
- **Real URLs only.** Never show a placeholder such as `{controlPlaneUrl}` or `{gatewayBaseURL}`, even inside snippets copied from docs. `controlPlaneUrl` builds UI links. The gateway base URL (API calls, SDK `baseURL`, MCP endpoints) is `manifest.url` of the `isDefault: true` installation from `list_gateway_installations`, unless the user names another.
- **Tool arguments.** Send only parameters in the tool's input schema; filters differ between list tools. `list_provider_accounts` has no name filter: list, then match `name` yourself.
- **Tool errors.** If a platform tool fails, tell the user the error and what it blocks. Never work around it through environment variables, process files, the MCP client, raw HTTP calls or other credentials.
- **FQNs.** Never construct one. The tenant FQN is `tenantName`; for anything else, list the entity and use its `fqn`.
- **Can't answer** → read `references/support-tickets.md` and follow it, instead of suggesting the user contact someone.

## Writes

Every create, update and delete goes through a manifest tool, which asks the user for approval before it runs.

- The reference file and `get_manifest_json_schema` are a write's contract: don't `search_docs` during it. Cite a doc page in the reply only.
- `validate_manifest`, `apply_manifest` and `delete_manifest` take `{"manifest": {...}}`. Reference files show YAML; send JSON.
- Call `validate_manifest` directly. For a manifest too large to write inline (a provider account with many models), build it with a program into a sandbox file and call `validate_manifest` from the sandbox on that file. Fix and re-validate until `valid: true`, then call `apply_manifest` once, directly, with the validated JSON — never in the same batch as validation.
- `delete_manifest` needs `type` and `name`, plus `workspace_fqn` for applications and `cluster_fqn` for workspaces. Legacy singletons need only `type`.
- Applying an existing identity **replaces the whole entity**, and several list fields replace everything on update (team members, integrations, rules). Change a live entity by fetching its current manifest and editing it, never by rebuilding it.
- Grant access only with the grant tools (`list_grants`, `create_grants`, `revoke_grant`), never in a manifest: remove `collaborators`, `authorized_subjects` and a VA's `permissions` before every apply, on create too. A fetched copy can be stale, and re-sending it revokes access granted since.
- If validation fails, fix and re-validate. If apply fails, show the error; if it persists or is unclear, offer a ticket. Don't silently retry or give up.
- Call `apply_manifest`, `delete_manifest` and every other write tool directly, not from the sandbox, so they go through approval. Never run `tfy apply` — it is the same write without the approval step. Deploying from local source is the one exception: `tfy deploy` with `build_source: local`.

## Ambiguous references

- **"My", "I", "mine"** mean the current user, not the tenant. Filter by their identity: `userEmail` on gateway metrics, `TfyCreatedBySubjectSlug` on traces, owner filters for deployments.
- **Entity names** are often partial or misspelt. Look the entity up before saying it doesn't exist ("github mcp" → MCP servers containing "github"). An application is identified by workspace and name together; if several match, ask which.
- **"Application", "app", "use case"** in a Gateway context means a virtual account (occasionally an `x-tfy-metadata` key).
- **"API key", "token"**: present both — a personal access token (tied to a user) and a virtual account token (recommended for production). Details in `ai-gateway/references/access-management.md`.
- **"Caching"**: ask whether they mean Gateway caching (a Gateway policy) or provider prompt caching (shows in token usage).

## AI Gateway

Models, virtual models and guardrails are addressed by the gateway model ID `{providerAccountName}/{integrationName}` (e.g. `openai-main/gpt-4o`) — not the integration's `model_id` field, which is the provider's own name (`gpt-4o`). MCP servers are addressed by `name`. "Policy" and "config" mean the same thing.

Files are under `ai-gateway/references/`. **For any create, update or delete, also read `write-rules.md` in the same batch.**

| The user wants to… | Read |
| --- | --- |
| Create or add a provider account (OpenAI, Bedrock, Azure, Vertex, …), add all or some models, add or remove models, ask whether a model or provider is supported, set model pricing | `models.md` |
| Route, fall back or load-balance across models | `virtual-models.md` (`load-balancing.md` only for the deprecated policy) |
| Add, connect or troubleshoot an MCP server or virtual MCP server | `mcp-servers.md` |
| Guardrails — PII, content safety, prompt injection; guardrail groups or policies | `guardrails.md` |
| Rate limits — any new limit, MCP tool-call limits, "what rate limits exist" | `rate-limiting-v2.md` (`rate-limiting.md` for legacy V1 rules and migration) |
| Budgets, spend limits | `budget-limiting-v2.md` (`budget-limiting.md` for legacy V1 rules) |
| Who can access what, give or remove access, roles, role bindings, identity providers, API keys | `access-management.md` |
| Add, invite, deactivate or delete users | `users.md` |
| Create or change a team | `teams.md` |
| Create or change a virtual account | `virtual-accounts.md` |
| Create a personal access token | `personal-access-tokens.md` |
| Who changed or deleted something, what someone did; audit logs | `audit-logs.md` |
| Numbers: usage, cost, latency, errors, cache, MCP, guardrails, rate limits, agents | `metrics.md` |
| Single requests, spans, contents, metadata keys, feedback, trace links | `observability.md` |
| Call a Gateway model from code or a tool — base URL, SDK, snippet | `using-models-from-code.md` |

Other platform topics: integrations with cloud accounts → https://www.truefoundry.com/docs/integrations-overview · secrets are referenced as `tfy-secret://<tenant>:<secret-group>:<key>` (the `fqn` from `list_secrets` has no scheme; add the prefix) → https://www.truefoundry.com/docs/manage-secrets.

## AI Engineering

Files are under `ai-engineering/references/`. Read the file for what you are about to do, before you do it — it covers what the schema cannot: which path applies, what to check first, and how to tell a real failure from a tool that cannot see.

| The user wants to… | Read |
| --- | --- |
| Deploy from a git repo or local code (service, async-service, job) | `deploy-from-source.md` |
| Deploy a prebuilt image | `deploy-from-image.md` |
| Deploy a Helm chart | `helm-deploy.md` |
| Deploy a model — HuggingFace or registry transformers model (vLLM, SGLang, TEI, Infinity, …) | `model-deploy.md` |
| Deploy an NVIDIA NIM or a sklearn/XGBoost model | `model-deploy-nim-classical.md` |
| Deploy a `notebook`, `rstudio` or `ssh-server` | `notebook-ssh.md` |
| Change an existing application; rules shared by every deploy | `deploy-common.md` |
| Autoscaling, scale-to-zero, right-sizing | `autoscaling.md` |
| Endpoints, sticky sessions, SSL, custom domains, connectivity | `networking.md` |
| Secrets, HuggingFace tokens, registry credentials | `secrets.md` |
| Rollout strategy, canary, blue-green, downtime on a change | `rollout-strategy.md` |
| How model serving works — vLLM, GPUs, weight download, upgrades | `model-serving-faq.md` |
| Add a cluster, or a cluster-wide problem (disconnected, addons, many apps failing) | `cluster-onboard.md` |
| Build logs, a failed build | `builds.md` |
| **Anything about a deployed application** — logs, events, metrics, health, crashes, Pending pods, stuck rollout, broken model server, what changed | `troubleshooting.md` — before any read tool, because an empty result means the tool could not see, not that nothing is wrong |
| `volume`, `workflow`, `spark-job`, `application-set`, ML repos, model registry | No file — work from `get_manifest_json_schema` and `search_docs`, and say so |

- `redis`, `postgres`, `kafka` and similar exist as both an image and a chart; they are not interchangeable (a chart brings persistence and replication). Ask which, never infer from the name.
- Deploying under an existing name replaces the whole manifest. A fresh manifest silently drops the app's env vars, secrets, limits and replicas, and still reports success — fetch the deployed manifest and edit it.
- Docs: [applications](https://www.truefoundry.com/docs/introduction-to-a-service) · [repositories](https://www.truefoundry.com/docs/platform/repositories) · [monitoring](https://www.truefoundry.com/docs/monitor-your-service)

## Before you respond

- [ ] Every URL uses real values from the session context or `list_gateway_installations`.
- [ ] Every claim cites the data or doc it came from; entities were looked up before being called missing.
- [ ] Gateway writes: validated before applying, no `collaborators` in the manifest, access granted with `create_grants` after a create, UI link shown.
- [ ] AI Engineering: identified the application type; started a model from `get_model_deployment_specs`; read pod state and real logs or events instead of trusting `DEPLOY_SUCCESS`; edited from the live manifest; printed links per `ai-engineering/references/deployment-links.md`.
