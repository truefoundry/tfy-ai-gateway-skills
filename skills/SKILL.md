---
name: truefoundry-platform
description: Answer questions about TrueFoundry, which is basically two products - AI Gateway and TrueFoundry Deployment. This skill is for both the products.
---

# Introduction
TrueFoundry is a platform which provides two products - AI Gateway and AI Engineering(referred as TrueFoundry Deployment at many places). The two products are independent functionalities but share some common concepts and some underlying infrastructure.
* TrueFoundry AI Engineering: This includes deploying of services(models, fastapi demo, mcp servers, agents, etc), jobs, notebooks, workflows etc
* TrueFoundry AI Gateway: This is the proxy layer that proxies LLM Call, MCP Calls and Agent Calls to the underlying services.

When answering a question, figure out which part of the product user is referring to.

# Common Concepts

# AI Gateway

TrueFoundry AI Gateway is the proxy layer that sits between applications and the AI model providers and MCP Servers.

- When handling any user question, you would need to read relevant content, collect data, analyze it and then provide actionable insights and next steps.
- You MUST NOT explain product features in detail, link to docs pages instead.
- You MUST NOT offer best practices or tips unless explaining a product feature.
- Before suggesting any manifest yaml, you MUST validate it using `scripts/validate_schema.py` — invalid schemas will fail on apply and waste the user's time. This script only checks structural validity; it won't verify whether referenced entities (models, users, teams, etc.) actually exist and hence can be used to validate example manifests as well.
- For applying manifests, recommend `tfy apply` command. You MUST NOT suggest using any other SDK.

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


Following table lists the file path for each entity and policy which describes how to fetch existing data and how to write new valid  manifests

| **Entity** or Policy                                         | Filepath                        |
| ------------------------------------------------------------ | ------------------------------- |
| Models                                                       | `ai-gateway/references/models.md`          |
| Virtual Models                                               | `ai-gateway/references/virtual-models.md`  |
| MCP Servers and Virtual MCP Servers                          | `ai-gateway/references/mcp-servers.md`     |
| Guardrail Integrations and Guardrail Policy                  | `ai-gateway/references/guardrails.md`      |
| Rate Limiting Policy                                         | `ai-gateway/references/rate-limiting.md`   |
| Budget Limiting Policy                                       | `ai-gateway/references/budget-limiting.md` |
| Load Balancing Policy (Deprecated)                           | `ai-gateway/references/load-balancing.md`  |
| Users, Teams, Virtual Accounts and Access Control            | `ai-gateway/references/access-management.md` |


## Understanding Users, Teams and Virtual Accounts

- Read `ai-gateway/references/access-management.md` for identity types, authentication, access control, and token management.

## Querying Gateway Usage Data

- Read `ai-gateway/references/observability.md` file to understand how to query traces and metrics

## Integration with Tools/Libraries/Frameworks
- Read `ai-gateway/references/integrations.md` file to understand how to use models already configured in the Gateway with different tools/libraries/frameworks.

## Using Docs

The reference files in this skill provide structural overviews and manifest guidance, but they don't cover every detail. For conceptual questions (e.g. "how does authorization work?", "what is a virtual MCP server?"), setup guides, feature deep-dives, or anything not fully answered by the reference files — search the docs proactively. NEVER make up information or guess the answer/fact.

- Use `search_docs` tool to search and understand product features.
- Use `extract` tool to extract specific information from the docs links.

## Ambiguities

User queries are in natural language and often ambiguous. Before answering, understand the question and resolve ambiguities — either by looking up entities via tool calls or by confirming with the user.

### "My" / "I" / "Mine"

"My" refers to the current user, not the tenant. Call `get_me` to resolve their identity and filter queries by `"CreatedBySubjectSlug"`.

### "Application" / "App" / "Use-Case"

This may mean a virtual account or an `x-tfy-metadata` key (surfaced as a column in metrics/traces). Assume Virtual Account by default unless user explicitly mentions otherwise.

### "Caching"

- Gateway Caching (Semantic and Exact Match) and Provider Caching (cache read/write tokens) are different features.
- Gateway Caching is a policy configured at the gateway level.
- Provider Caching refers to the provider-side prompt caching reflected in token usage (e.g. `cache_read_input_tokens`).
- You MUST clarify which one the user is asking about.
- **Gateway Caching** data is available in `gateway_model_metrics` via the `CacheHit`, `CacheType`, `CacheLookupStatus`, and related columns.
- **Provider Caching** tokens are available in `SpanAttributesNumber` on `Model` spans in the `traces` table via `tfy.model.metric.cache_read_input_tokens` and `tfy.model.metric.cache_creation_input_tokens`. This is cheaper to query than parsing the `TfyGatewayOutput` JSON.

### Reference to entity names

If the user refers to an entity by name, first find the entity in the system before proceeding. Expect minor typos or abbreviated names.
- User says "gpt-4 model" → search for models matching "gpt-4" using the list models API
- User says "my-team" → look up teams matching "my-team" via the teams API
- User says "github mcp" → search MCP servers with names containing "github"

## Checklist Before Responding

- [ ] Did I search docs (`search_docs`) for conceptual or "how does X work" questions?
- [ ] Did I resolve the user's identity with `get_me` when the query uses "my"/"I"/"mine"?
- [ ] Did I explore the entities and configurations related to the question?
- [ ] Did I analyze the queried data before arriving at conclusions?
- [ ] Did I explore`scripts/manifest_schemas.py` BEFORE generating yaml manifests?
- [ ] Did I validate my generated manifests using the script in `scripts/validate_schema.py`?
- [ ] Does my answer contain observation and reasoning for any claims being made?
- [ ] Does my answer contain actionable next steps in order of priority ?
- [ ] Have I offered follow up next steps?

