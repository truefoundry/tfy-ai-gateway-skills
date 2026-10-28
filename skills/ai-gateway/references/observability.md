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

1. In one parallel batch, read the schema file of each table you need (skip any whose contents are still in the conversation). Query only the `default` destination unless the user names another; never try other destinations on your own. Call `list_data_routing_destinations` only when the user names one or the data is not in `default` (then ask which one).
2. Write one query following the rules below and run it with `gateway_execute_sql`. If the result is saved to a sandbox file, extract only the fields you need with one `jq`/program.
3. Answer with the result and a trace link (see Linking to traces).

**Why did a trace fail, or did it succeed.** Run the every-span query (Examples) for the trace ID; it covers the last 7 days with `now()`, so it needs no `get_current_datetime`. The request failed if any span has `StatusCode = 'Error'`, even when the head span is `Ok` with HTTP 200 (MCP and guardrail spans fail this way). Report the failing span's `tfy.error_type` and `tfy.error_message` (the `Model` span for model errors), `HttpStatusCode`, model, caller and time, what the message means for the caller, and the trace link. `tfy-model-not-found` means the model or provider account does not exist in the gateway: tell the caller to check the model name, never to get access. If no rows come back, stop: don't widen the window or try another destination. Ask the user roughly when the request was made and which destination it went to.

**Errors from `gateway_execute_sql`.** A 400 or 404 names the problem: fix the query. `Delta table not found` means that destination has no traces table. A 504 means the query timed out: narrow the window. Any other 5xx means the query service failed, not the SQL: retry the same query once, and if it fails again, stop. Tell the user trace queries are failing right now, give the trace link (no time window), and offer a support ticket. Never change the query or destination, or search the docs, to work around a 5xx.

### Writing SQL

- The dialect is DataFusion, not ClickHouse or Postgres: use `array_has`, `map_keys`, `unnest`, `"Map"['key']`, `INTERVAL '7 days'`, `approx_percentile_cont`, `date_trunc`, `COUNT(*) FILTER (WHERE …)`. There is no `has()`, `quantile()`, `JSONExtract` or `->>`. `SHOW TABLES` and `information_schema` are disabled.
- Quote table and column names; column names are case sensitive. Take them from the schema file, never guess.
- Address a table as `"<destination>"."<table>"`. An unqualified name fails with `Invalid schema public`.
- **Time range on every query, twice:** a `"Date"` range for partition pruning and a `"Timestamp"` range for the exact window. `"Date"` is a UTC `'YYYY-MM-DD'` string and `"Hour"` a `'HH'` string: compare them with string literals (`"Date" >= '2026-10-20'`), or `to_char(now() - INTERVAL '7 days', '%Y-%m-%d')`. `CAST(current_date() - 7 AS VARCHAR)` fails. Default to the last 24 hours when the user gives no window; keep scans small.
- **Head spans** (one per request): `COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId") = ''`. Add it when listing requests, otherwise child spans repeat each request. It misses the few requests sent with their caller's own trace context, whose parent is outside the gateway; the UI also counts a span whose parent is not in the table as a head.
- `LIMIT` every non-aggregate query (default 50): there is no row cap, and the whole result is returned at once.
- Select only the columns you need. Never `SELECT *` on traces: it pulls the large, sensitive `TfyGatewayInput`/`TfyGatewayOutput` and every attribute map.
- `Duration` is in nanoseconds: `"Duration" / 1e6` is milliseconds.
- The query times out after 60 seconds. Don't reference one CTE more than once (it is re-executed each time).
- Spans from the last few minutes (up to about three) may not be queryable yet.
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

- Failed model calls with their error. The head span of a failed model request has `StatusCode = 'Error'` and `tfy.error_message`, but `tfy.error_type` is on the `Model` span (only `client-disconnected` is on the head span; MCP and guardrail errors are on their own spans). Error type values: [span attributes](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#core-span-attributes).

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
SELECT "SpanId", COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId") AS "ParentId", "Timestamp", "TfyGatewaySpanType", "SpanName",
  "StatusCode", "HttpStatusCode", "GenAIRequestModel", "TfyCreatedBySubjectSlug", "Duration" / 1e6 AS "DurationMs",
  "SpanAttributesString"['tfy.error_type'] AS "ErrorType", "SpanAttributesString"['tfy.error_message'] AS "ErrorMessage",
  "SpanAttributesNumber"['tfy.model.metric.cost_in_usd'] AS "CostUsd",
  CAST(to_unixtime("Timestamp") * 1000 AS BIGINT) - 1000 AS "LinkStartMs", CAST(to_unixtime("Timestamp") * 1000 AS BIGINT) + 3600000 AS "LinkEndMs"
FROM "dest"."traces_v2"
WHERE "TraceId" = '<trace-id>' AND "Date" >= to_char(now() - INTERVAL '7 days', '%Y-%m-%d') AND "Timestamp" >= now() - INTERVAL '7 days'
  AND "TfyGatewaySpanType" IS NOT NULL
ORDER BY "Timestamp"
LIMIT 50
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
- Guardrail outcome of a request: the head span carries the worst result in `"SpanAttributesString"['tfy.guardrail.result']` only for some request types; see [triggered guardrails](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#triggered-guardrails-on-request-spans), or query the `Guardrail` child spans.
- Feedback on traces: see the sample join in `tables/gateway_feedbacks.md`. Deduplicate by `FeedbackId` before filtering `"IsDeleted" = false`.

### Getting a trace ID

Find the `TraceId` by querying the traces table with filters (time, user, model, …).

> **WARNING — response `id` ≠ trace ID.** The `id` in a chat completion response (e.g. `chatcmpl-xxx`) is the response ID, not the trace ID. Never use it in trace links.

### Linking to traces

Always link the traces you show: `{controlPlaneUrl}/monitoring/request-traces?filters=<url-encoded JSON>`, where the JSON is `{"rules":[{"field":"<field>","operator":"IN","value":[...]}]}`.

- Fields: `traceId`, `userEmail`, `virtualAccount`, `agentIdentity`, `genAIRequestModel` (the model the client requested, real or virtual), `mcpServerName`.
- A span attribute: `{"field":"<attribute>","operator":"IN","value":[...],"type":"string","apiKey":"spanAttributeKey","apiKeyValue":"<attribute>"}`, e.g. `tfy.guardrail.fqn`.
- Time window: append `&lm_lfsts=<start epoch ms>&lm_lfets=<end epoch ms>`. For one trace, use its start minus 1 second to start plus 1 hour: the head span's `LinkStartMs` and `LinkEndMs` from the every-span query. Never convert a timestamp to epoch milliseconds by hand; select `CAST(to_unixtime("Timestamp") * 1000 AS BIGINT)` or compute it in the sandbox.
- Always append `&dId=<destination>` (`default` too): without it the page opens its first listed destination.

### Checklist

- [ ] Aggregate question? Then `metrics.md`, not SQL.
- [ ] Table name from `tracesTable`, destination `default` unless the user named another, both quoted.
- [ ] Any span with `StatusCode = 'Error'` → the request failed.
- [ ] `"Date"` literal range plus `"Timestamp"` range; `LIMIT` on non-aggregate queries.
- [ ] Head-span filter when listing requests; only the needed columns.
- [ ] Empty result → data-access rules mentioned.
- [ ] 5xx → one retry of the same query, then stop and report.
