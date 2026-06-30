---
name: ui-links
description: URL patterns, filters, and deep-link construction for TrueFoundry UI pages.
---

`{controlPlaneUrl}` is a placeholder — always replace with the actual value from `get_me`. Never show `{controlPlaneUrl}` literally to the user.

## URL patterns

- **Gateway entities**: `{controlPlaneUrl}/llm-gateway/{page}` — pages: `models`, `virtual-models`, `mcp-servers`, `settings`
- **Agents**: `{controlPlaneUrl}/agents/registry`
- **Guardrails**: `{controlPlaneUrl}/guardrails/{page}` — pages: `registry`, `policies`
- **Monitoring metrics**: `{controlPlaneUrl}/monitoring/metrics?monitorTab={tab}&viewBy={view}`
  - tab/view options: `metrics/modelName`, `mcp-metrics/mcpserver`, `guardrail-metrics/guardrails`, `routing-config/configs`, `cache-metrics/cache`, `agent-metrics/agent`
- **Request traces**: `{controlPlaneUrl}/monitoring/request-traces`
- **Data routing/access**: `{controlPlaneUrl}/monitoring/data-routing`, `.../data-access`
- **Access management**: `{controlPlaneUrl}/access-management?tab={tab}` — tabs: `users`, `teams`, `personal-access-token`, `service-accounts`, `default-roles`, `custom-roles`

## Filters (optional query param)

Append `&filters={url-encoded-json}` to metrics or traces URLs to pre-filter:
```
{"rules":[{"field":"<fieldName>","value":"<value>","operator":"<op>"}]}
```
Common operators: `IN`, `STRING_CONTAINS`. Common fields: `userEmail`, `modelName`, `teamName`.

Deep link to a specific trace:
```
{controlPlaneUrl}/monitoring/request-traces?filters={"rules":[{"field":"traceId","value":["<traceId>"],"operator":"IN"}]}
```
URL-encode the filters JSON when constructing links.

> **WARNING — response `id` ≠ trace ID.** The `id` field in a chat completion response (e.g. `chatcmpl-xxx`) is the **response ID**, NOT the trace ID. Never use it in trace links. To get the actual `TraceId`, query the `traces` table (e.g. filter by time range, model, or user) and use the `TraceId` column value.
