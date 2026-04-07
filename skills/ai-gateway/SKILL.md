---
name: ai-gateway
description: Answer questions about AI Gateway features, usage insights and recommendations by analyzing existing configurations and observability data
---

# AI Gateway

TrueFoundry AI Gateway is the proxy layer that sits between applications and the AI model providers and MCP Servers.

- When handling any user question, you would need to read relevant content, collect data, analyze it and then provide actionable insights and next steps.
- You MUST NOT explain product features in detail, link to docs pages instead.
- You MUST NOT offer best practices or tips unless explaining a product feature.
- For applying manifests, recommend `tfy apply` command. You MUST NOT suggest using any other SDK.

## Understanding Manifests for Gateway Entities and Policies

> **Note**: `policy` and `configuration` are used interchangeably. 

- Entities are integrations that can be used via the Gateway. E.g.
  - Models from vendors like OpenAI, Anthropic, etc
  - Virtual Models allow routing and fallback to one of the target models based on priority, weight, latency SLAs
  - Remote MCP Servers from products like Github, Linear or Self Managed MCP Servers
  - Virtual MCP Servers allow combining tools from several Remote MCP Servers
  - Guardrail Integrations from third party vendors or managed by TrueFoundry
  - Models/Virtual Models/Guardrails always need to identified by `{accountName}/{integrationName}` format. You should always use this format in your responses.
  - MCP servers always need to be identified by their names. Names are unique in a tenant.

- Policies are Gateway level rules that activate while using the entities. E.g.
  - Rate Limiting Policy decides when requests to a set of models from a set of users should be rate limited
  - Budget Limiting Policy decides when requests to a set of models from a set of users should be budget limited
  - Load Balancing Policy (aka Routing Config) decides when requests to a set of models should be load balanced. This feature has been deprecated in favor of Virtual Models.


Following table lists the file path for each entity and policy which describes how to fetch existing data and how to write new valid  manifests

| **Entity** or Policy                                         | Filepath                        |
| ------------------------------------------------------------ | ------------------------------- |
| Models                                                       | `references/models.md`          |
| Virtual Models                                               | `references/virtual-models.md`  |
| MCP Servers and Virtual MCP Servers                          | `references/mcp-servers.md`     |
| Guardrail Integrations and Guardrail Policy                  | `references/guardrails.md`      |
| Rate Limiting Policy                                         | `references/rate-limiting.md`   |
| Budget Limiting Policy                                       | `references/budget-limiting.md` |
| Load Balancing Policy (Deprecated)                           | `references/load-balancing.md`  |
| Users, Teams, Virtual Accounts and Access Control            | `references/access-management.md` |


## Understanding Users, Teams and Virtual Accounts

- Read `references/access-management.md` for identity types, authentication, access control, and token management.

**Note**: Application/App/Use-Case might be used to refer to virtual accounts.

## Querying Gateway Usage Data

- Read `references/observability.md` file to understand how to query traces and metrics

## Integration with Tools/Libraries/Frameworks
- Read `references/integrations.md` file to understand how to use models already configured in the Gateway with different tools/libraries/frameworks.

## Using Docs

**Important**: This should be only used when other sources provide insufficient information.

- Use `search_true_foundry_docs` tool to search and understand product features.
- Use `extract` tool to extract specific information from the docs links.

## Checklist Before Responding

- [ ] Did I explore the entities and configurations related to the question?
- [ ] Did I analyze the queried data before arriving at conclusions?
- [ ] Did I explore`scripts/manifest_schemas.py` BEFORE generating yaml manifests?
- [ ] Did I validate my generated manifests using the script in `scripts/validate_schema.py`?
- [ ] Does my answer contain observation and reasoning for any claims being made?
- [ ] Does my answer contain actionable next steps in order of priority ?
- [ ] Have I offered follow up next steps?
