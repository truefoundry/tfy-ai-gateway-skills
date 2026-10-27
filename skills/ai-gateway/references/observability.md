---
name: observability
description: Read for questions about individual Gateway requests and traces — find requests, see a request's spans, errors, prompt or response, metadata keys, feedback — and for trace links. Explains how to query traces and feedback with `gateway_execute_sql`. For counts, cost, latency or any aggregate, read `metrics.md` instead.
---

## Traces and Feedback

Gateway records every request as a trace of OTEL spans: one head span for the request, with child spans for each model call, MCP call, guardrail check and so on. All spans of a request share a `TraceId`.

Use SQL on traces only for what the metrics API cannot do: listing or finding requests, one request's spans and attributes, request or response contents, metadata key discovery, feedback, and data in a routing destination other than `default`. Every aggregate (requests, cost, tokens, latency, errors, cache, guardrail, MCP, rate-limit, budget, agent numbers) comes from `query_llm_gateway_metrics`: read `metrics.md`. Don't query the `gateway_*_metrics` tables.

### Tables

- The traces table — its name varies by tenant: take `tracesTable` from the session context (call `get_session_context` only if it is missing); never assume `traces`. In this skill, "the `traces` table" means that table. Schema: `ai-gateway/references/tables/traces.md`.
- `gateway_feedbacks` — feedback (ratings, comments) on spans. Schema: `ai-gateway/references/tables/gateway_feedbacks.md`.

### Steps

1. In one parallel batch, read the schema file of each table you need (skip any whose contents are still in the conversation) and call `list_data_routing_destinations` (reuse its result if it is still in the conversation). If there is one destination, use it; if there are several, ask the user which one.
2. Write one query following the rules below and run it with `gateway_execute_sql`. If the result is saved to a sandbox file, extract only the fields you need with one `jq`/program.
3. Answer with the result and a trace link (see Linking to traces).

### Writing SQL

- The dialect is DataFusion, not ClickHouse or Postgres: use `array_has`, `map_keys`, `unnest`, `"Map"['key']`, `INTERVAL '7 days'`, `approx_percentile_cont`, `date_trunc`, `COUNT(*) FILTER (WHERE …)`. There is no `has()`, `quantile()`, `JSONExtract` or `->>`. `SHOW TABLES` and `information_schema` are disabled.
- Quote table and column names; column names are case sensitive. Take them from the schema file, never guess.
- Address a table as `"<destination>"."<table>"`. An unqualified name fails with `Invalid schema public`.
- **Time range on every query, twice:** a `"Date"` range for partition pruning and a `"Timestamp"` range for the exact window. `"Date"` is a UTC `'YYYY-MM-DD'` string and `"Hour"` a `'HH'` string: compare them with string literals (`"Date" >= '2026-10-20'`), or `to_char(now() - INTERVAL '7 days', '%Y-%m-%d')`. `CAST(current_date() - 7 AS VARCHAR)` fails. Default to the last 24 hours when the user gives no window; keep scans small.
- **Head spans** (one per request): `COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId") = ''`. Add it when listing requests, otherwise child spans repeat each request.
- `LIMIT` every non-aggregate query (default 50): there is no row cap, and the whole result is returned at once.
- Select only the columns you need. Never `SELECT *` on traces: it pulls the large, sensitive `TfyGatewayInput`/`TfyGatewayOutput` and every attribute map.
- `Duration` is in nanoseconds: `"Duration" / 1e6` is milliseconds.
- The query times out after 60 seconds. Narrow the window rather than retrying, and don't reference one CTE more than once (it is re-executed each time).
- Spans from the last one to two minutes may not be queryable yet.
- Results are filtered by the caller's data-access rules for traces, which are separate from metrics rules. An empty result can mean no access, not no traffic: say so and link `{controlPlaneUrl}/access-management?tab=data-access`.

#### Examples

Replace `"dest"` with the destination and `"traces_v2"` with `tracesTable`.

- Recent requests by a user:

```sql
SELECT "TraceId", "Timestamp", "TfyGatewaySpanType", "GenAIRequestModel", "StatusCode", "HttpStatusCode", "Duration" / 1e6 AS "DurationMs"
FROM "dest"."traces_v2"
WHERE "Date" >= '2026-10-26' AND "Timestamp" >= TIMESTAMP '2026-10-26T00:00:00Z'
  AND "TfyCreatedBySubjectSlug" = 'alice@example.com'
  AND COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId") = ''
ORDER BY "Timestamp" DESC
LIMIT 50
```

- Failed model calls with their error (errors are on the `Model` span, not the head span):

```sql
SELECT "TraceId", "Timestamp", "GenAIRequestModel", "HttpStatusCode",
  "SpanAttributesString"['tfy.error_type'] AS "ErrorType", "SpanAttributesString"['tfy.error_message'] AS "ErrorMessage"
FROM "dest"."traces_v2"
WHERE "Date" >= '2026-10-26' AND "Timestamp" >= TIMESTAMP '2026-10-26T00:00:00Z'
  AND "TfyGatewaySpanType" = 'Model' AND "StatusCode" = 'Error'
ORDER BY "Timestamp" DESC
LIMIT 50
```

- Every span of one trace:

```sql
SELECT "SpanId", COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId") AS "ParentId", "TfyGatewaySpanType", "SpanName", "StatusCode",
  "Duration" / 1e6 AS "DurationMs", "SpanAttributesNumber"['tfy.model.metric.cost_in_usd'] AS "CostUsd"
FROM "dest"."traces_v2"
WHERE "TraceId" = '<trace-id>' AND "Date" BETWEEN '2026-10-26' AND '2026-10-27'
ORDER BY "Timestamp"
```

- Request metadata keys in use (`x-tfy-metadata`), then the values of one key with `"TfyGatewayMetadata"['<key>']`:

```sql
SELECT key, COUNT(*) AS "Requests"
FROM (
  SELECT unnest(map_keys("TfyGatewayMetadata")) AS key
  FROM "dest"."traces_v2"
  WHERE "Date" >= '2026-10-20' AND "Timestamp" >= TIMESTAMP '2026-10-20T00:00:00Z'
    AND COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId") = ''
)
GROUP BY key
ORDER BY "Requests" DESC
LIMIT 50
```

- Filter by team: `array_has("SpanAttributesStringList"['tfy.request.created_by_subject_teams'], '<team>')`.
- Feedback on traces: see the sample join in `tables/gateway_feedbacks.md`. Deduplicate by `FeedbackId` before filtering `"IsDeleted" = false`.

### Getting a trace ID

Find the `TraceId` by querying the traces table with filters (time, user, model, …).

> **WARNING — response `id` ≠ trace ID.** The `id` in a chat completion response (e.g. `chatcmpl-xxx`) is the response ID, not the trace ID. Never use it in trace links.

### Linking to traces

Always link the traces you show: `{controlPlaneUrl}/monitoring/request-traces?filters=<url-encoded JSON>`, where the JSON is `{"rules":[{"field":"<field>","operator":"IN","value":[...]}]}`.

- Fields: `traceId`, `userEmail`, `virtualAccount`, `agentIdentity`, `genAIRequestModel` (real model), `virtualModelName`.
- A span attribute: `{"field":"<attribute>","operator":"IN","value":[...],"type":"string","apiKey":"spanAttributeKey","apiKeyValue":"<attribute>"}`, e.g. `tfy.mcp_server.name`.
- Time window: append `&lm_lfsts=<start epoch ms>&lm_lfets=<end epoch ms>`. For one trace, use its start minus 1 second to start plus 1 hour.

### Checklist

- [ ] Aggregate question? Then `metrics.md`, not SQL.
- [ ] Table name from `tracesTable`, destination from `list_data_routing_destinations`, both quoted.
- [ ] `"Date"` literal range plus `"Timestamp"` range; `LIMIT` on non-aggregate queries.
- [ ] Head-span filter when listing requests; only the needed columns.
- [ ] Empty result → data-access rules mentioned.
