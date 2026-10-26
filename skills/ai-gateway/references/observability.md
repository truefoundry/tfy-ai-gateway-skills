---
name: observability
description: Read for any question about Gateway usage, cost, latency, errors, cache, guardrail outcomes, traces or feedback. Explains which table holds what and how to query it with `gateway_execute_sql`, plus how to link to traces and metrics in the UI.
---

## Querying Gateway Observability Data

Gateway emits traces (OTEL spans) and metrics for each request, stored in several tables.
A single request may involve multiple model calls, MCP calls, guardrail evaluations, etc. and so can produce multiple spans and metric rows.
All spans and metrics of a user's request have the same `TraceId`.

### Tables

Each table has a schema file `ai-gateway/references/tables/<table-name>.md`.

- `traces` - OTEL spans enriched with AI Gateway columns (the physical name varies, see below)
- `gateway_model_metrics` - model calls: tokens, cost, latency, failures, gateway cache, provider cache tokens
- `gateway_mcp_metrics` - MCP calls
- `gateway_guardrail_metrics` - guardrail evaluations
- `gateway_config_metrics` - applied rate limits, budget limits and load balancing rules
- `gateway_request_metrics` - every incoming request to the gateway (overall usage)
- `gateway_feedbacks` - user feedback (ratings, comments) linked to trace spans

No other tables are queryable (e.g. `gateway_agent_metrics` fails).

### Steps

1. Pick the one or two tables the question needs. In one parallel batch, read their schema files (skip any whose contents are still in the conversation) and, if the query touches `traces` or `gateway_feedbacks`, call `list_data_routing_destinations` (reuse its result if it is still in the conversation).
2. Write one query following the rules below, and run it with `gateway_execute_sql`. If the result is large and saved to a sandbox file, extract only the fields you need with one `jq`/program.
3. Answer with the numbers and a UI link (see Linking to Traces and Metrics).

### Writing SQL Queries

- Use the DataFusion SQL dialect. It is not ClickHouse or Postgres: use `array_has`, `map_keys`, `unnest`, `"Map"['key']`, `INTERVAL '7 days'`, `approx_percentile_cont`; there is no `has()`, `quantile()`, `JSONExtract` or `->>`.
- Quote table and column names; column names are case sensitive.
- Never guess column names; take them from the table's schema file.
- Address tables as `"{dataRoutingDestination}"."{tableName}"`.
- The traces table name varies by tenant: take it from `tracesTable` in the session context (call `get_session_context` only if it is missing). Never assume it is `traces`. In this skill, "the `traces` table" means that table. All other table names are fixed.
- `*_metrics` tables always live in the `"default"` destination; use `"default"` without looking anything up.
- For `traces` and `gateway_feedbacks` the destination varies. Use the result of `list_data_routing_destinations`: if there is only one, use it; if there are several, ask the user which one they mean.
- Always add a time range filter. Larger ranges are fine for metrics aggregations; keep scans small, especially on `traces`. Default to the last 7 days for metrics when no time is given. For `traces` scans also add `"Date" >= 'YYYY-MM-DD'` (UTC date string) so partitions are pruned.
- The tool has no row limit. Add `LIMIT` to every non-aggregate query (default 50).
- Select only the columns the task needs; never `SELECT *` on `traces` (it pulls the large, sensitive `TfyGatewayInput`/`TfyGatewayOutput` payloads).
- Results are filtered by the caller's Gateway data-access rules. An empty or small result can mean the user lacks access, not that there is no traffic. When a query returns nothing, say so and point to `{controlPlaneUrl}/access-management?tab=data-access`.

#### Examples

- Traces in a time range:

```sql
SELECT "TraceId", "SpanId", "Timestamp", "TfyGatewaySpanType", "SpanName", "StatusCode", "TfyCreatedBySubjectSlug"
FROM "chosen-destination"."{tracesTable}"
WHERE "Timestamp" > '2026-03-13T10:00:00Z' AND "Timestamp" < '2026-03-13T11:00:00Z'
  AND "Date" >= '2026-03-13'
ORDER BY "Timestamp" DESC
LIMIT 50
```

- Map-type columns (e.g. `"Metadata"`). Distinct values for a known key:

```sql
SELECT DISTINCT "Metadata"['your_key'] AS value
FROM "default"."gateway_model_metrics"
WHERE "CreatedAt" > NOW() - INTERVAL '7 days'
  AND "VirtualModelName" IS NULL
LIMIT 50
```

- Discover all keys present, with `map_keys()` + `unnest()`:

```sql
SELECT DISTINCT key
FROM (
  SELECT unnest(map_keys("Metadata")) AS key
  FROM "default"."gateway_model_metrics"
  WHERE "CreatedAt" > NOW() - INTERVAL '7 days'
    AND "VirtualModelName" IS NULL
)
LIMIT 50
```

- Filter by team: on metrics tables `array_has("Teams", '<team>')`; on `traces` `array_has("SpanAttributesStringList"['tfy.request.created_by_subject_teams'], '<team>')`.

### Latency Reporting Rules

- Never use `AVG()` for latency columns (`LatencyMs`, `TimeToFirstTokenMs`, `InterTokenLatencyMs`, `CacheLookupLatencyMs`): averages hide tail latency.
- Aggregate latency with `approx_percentile_cont`. Default to P95 unless the user asks for a specific percentile; rank slow/fast models or requests by P95 (P99 for worst case).
- For latency breakdowns include P50, P75, P90, P95 and P99.
- Filter `"IsFailure" = false`, because failed calls have NULL latency.

```sql
SELECT "ModelName",
  approx_percentile_cont("LatencyMs", 0.5) AS "P50LatencyMs",
  approx_percentile_cont("LatencyMs", 0.75) AS "P75LatencyMs",
  approx_percentile_cont("LatencyMs", 0.9) AS "P90LatencyMs",
  approx_percentile_cont("LatencyMs", 0.95) AS "P95LatencyMs",
  approx_percentile_cont("LatencyMs", 0.99) AS "P99LatencyMs",
  COUNT(*) AS "RequestCount"
FROM "default"."gateway_model_metrics"
WHERE "CreatedAt" > NOW() - INTERVAL '7 days'
  AND "VirtualModelName" IS NULL
  AND "IsFailure" = false
GROUP BY "ModelName"
ORDER BY "P95LatencyMs" DESC
```

### Common Query Patterns

- **Provider Cache Token Usage**: `SUM("CacheReadInputTokens")` and `SUM("CacheCreationInputTokens")` from `"default"."gateway_model_metrics"` with `"VirtualModelName" IS NULL`. Cache read ratio = `SUM("CacheReadInputTokens") * 1.0 / SUM("InputTokens")`.
- **Gateway Cache Hit Rates**: use `CacheLookupStatus` (`hit`/`miss`/`error`) and `CacheType` in `gateway_model_metrics`. Hit rate = `SUM(CASE WHEN "CacheLookupStatus" = 'hit' THEN 1 ELSE 0 END) * 1.0 / COUNT(*)` with `WHERE "CacheLookupStatus" IS NOT NULL`. This is gateway semantic/exact-match caching, not provider prompt caching.
- **Guardrail counts and failure rates**: filter `("RecordType" = 'guardrail' OR "RecordType" IS NULL)` in `gateway_guardrail_metrics`, otherwise policy copies inflate the numbers (see its schema file).
- **Feedback on Traces**: feedback is in `gateway_feedbacks`, linked via `TargetTraceId` and `TargetSpanId`; LEFT JOIN it with `traces` in the same destination. Deduplicate by `FeedbackId` first, then filter `"IsDeleted" = false` (see `ai-gateway/references/tables/gateway_feedbacks.md` for the sample join).

### Getting a Trace Link

Get the `TraceId` by querying the `traces` table with appropriate filters (time range, model, user, etc.), then build the link as in the next section.

> **WARNING — response `id` ≠ trace ID.** The `id` field in a chat completion response (e.g. `chatcmpl-xxx`) is the **response ID**, NOT the trace ID. Never use it in trace links. Always query the `traces` table to get the actual `TraceId`.

### Linking to Traces and Metrics

Always give a direct link when showing trace or metrics results. Base paths: `{controlPlaneUrl}/monitoring/request-traces` and `{controlPlaneUrl}/monitoring/metrics`.

Pre-filter with `?filters=<url-encoded JSON>`, where the JSON is `{"rules":[{"field":"<field>","operator":"<op>","value":[...]}]}`:
- Request traces: `traceId`, `userEmail`, `genAIRequestModel`, `virtualAccount`, `spanType` — operator `IN`, value an array. Example: `{"rules":[{"field":"traceId","operator":"IN","value":["<id>"]}]}`.
- Metrics: `modelName`, `userEmail`, `virtualAccount` with `IN`; `team` with `ARRAY_HAS_ANY`.
- Other fields: `search_docs` with "request logs filtering".

### Checklist For SQL Queries

- [ ] Did I read the table schema and use the correct column names?
- [ ] Did I quote the table name and column names?
- [ ] For traces, did I use `tracesTable` from the session context instead of assuming `traces`?
- [ ] Did I use `"default"` for metrics tables and the chosen destination for traces/feedback?
- [ ] Did I add a time range, and `LIMIT` on non-aggregate queries?
- [ ] Did I only include the columns that are relevant to the task at hand?
- [ ] Did I use `approx_percentile_cont` instead of `AVG` for any latency columns?
- [ ] If the result was empty, did I mention data-access rules?
