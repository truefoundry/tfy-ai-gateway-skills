---
name: metrics
description: Read for any aggregate Gateway question — requests, cost, tokens, latency, errors, cache, MCP calls, guardrail outcomes, rate-limit and budget blocks, load balancing, agents — per model, user, team, virtual account or metadata, over time. Explains how to query it with `query_llm_gateway_metrics` and link to the Metrics page.
---

## Gateway Metrics

`query_llm_gateway_metrics` aggregates Gateway metrics over a time range. Use it for every count, sum, rate, percentile or trend. It cannot list individual requests, show request or response contents, read feedback, or reach a data routing destination other than `default`: for those, read `observability.md` and use `gateway_execute_sql` on traces.

### Steps

1. Pick the datasource (table below) and build one request per question. Independent questions go in one parallel batch.
2. Read the numbers from the response (see Reading the response), sort and cut to top-N yourself.
3. Answer with the numbers, the time window used, and a Metrics page link.

### Datasources

| Question about | `datasource` |
| --- | --- |
| Model calls: requests, cost, tokens, latency, TTFT, errors, provider prompt-cache tokens, per real model | `realModelMetrics` |
| Traffic, cost or latency per virtual model, without a real-model breakdown | `virtualModelMetrics` (no cache or cost-savings columns) |
| Gateway cache (exact-match / semantic): hit rate, savings | `cacheMetrics` |
| MCP calls and tool calls | `mcpMetrics` |
| Guardrail checks and outcomes | `guardrailMetrics` (`guardrailPolicyMetrics` for per-policy counts) |
| Rate-limit, budget and load-balancing decisions | `configMetrics` |
| Agent runs | `agentMetrics` |
| Every incoming Gateway request by path, method, span type | `gatewayRequestMetrics` |

`modelMetrics` is deprecated; it reads the same rows as `realModelMetrics`. Virtual model → real model breakdown: `realModelMetrics` grouped by `virtualModel` and `modelName`.

Columns, group-by fields and filter fields differ per datasource and are listed in the tool's input schema. A field from another datasource, or an operator the field doesn't allow, returns 400 naming the problem; fix the request from the message.

### Request rules

- **Time.** `startTs` (inclusive) and `endTs` (exclusive, defaults to now) are ISO 8601; without an offset they are UTC. Default to the last 7 days when the user gives no window.
- **`type`.** `distribution` returns one row per group over the whole window. `timeseries` adds time buckets: set `interval` (`"1 hour"`, `"1 day"`, one unit only) when the user asks for a granularity, otherwise omit it and the server picks (≤1 hour → 2 min, ≤1 day → 1 hour, ≤7 days → 12 hours, ≤30 days → 1 day, ≤90 days → 3 days). Buckets start at `startTs`; the last one can extend past now. For daily or hourly trends, start at a UTC midnight or hour so buckets are calendar days or hours.
- **Counting requests.** Every row has `total`, the number of rows matched. Use it as the request count. `count` on a column counts only rows where that column is not NULL (`count` of `costInUSD` skips calls with no cost); use it for conditional counts, on a column every row has.
- **Conditional counts.** Put a `filterPredicate` on an aggregation to count a subset in the same query: `{"type":"count","column":"modelName","alias":"failures","filterPredicate":[{"fieldName":"isFailure","operator":"EQUAL","value":true}]}`.
- **Latency.** Never `avg` latency columns (`latencyMs`, `timeToFirstTokenMs`, `interTokenLatencyMs`, `cacheLookupLatencyMs`): use `p50`…`p99`. Default to `p95`; rank slow or fast by `p95` (`p99` for worst case); breakdowns use `p50`, `p75`, `p90`, `p95`, `p99`.
- **Percentage columns** (`isFailurePercentageFlag`, `cacheHitFlag`, `cacheReadInputPercentage`, `cacheWriteInputPercentage`) are 100 or 0 per row: only `avg` is meaningful, and it is already a percentage.
- **Present values.** "Has a value" is `NOT_IN [""]` (FE convention; `IS_NULL` is allowed only on a few fields). Add `modelName NOT_IN [""]` to model queries, `agentName NOT_IN [""]` to agent queries (otherwise requests with no agent come back as a `null` group), and `mcpServerName NOT_IN [""]` when grouping MCP calls by server.
- **No ordering or limit.** The API has no ORDER BY, LIMIT or HAVING, and returns every group. Sort and take top-N yourself; for high-cardinality group-bys (`userEmail`, `metadata.<key>`, `requestPath`) narrow with filters first. Ratios (error %, cost per request, share of total) are yours to compute from the returned sums and `total`.
- **OR groups** (`{"operator":"OR","filters":[...]}`) work on model datasources only. Elsewhere, use `IN`.
- Never send `exportFormat`.

### Who: users, keys, teams, metadata

- **Group-by names** for the caller: `userEmail` (users), `virtualaccount` (virtual accounts), `agentIdentity` (agent identities). Grouping by exactly one of them keeps only that subject type. For "who uses X" across all kinds, group by `["userEmail","agentIdentity","virtualaccount","createdBySubjectType"]`, and read `createdBySubjectSlug` with `createdBySubjectType` (`user`, `virtualaccount`, `serviceaccount`, `agent`, `system`).
- **Filter names**: `userEmail`, `virtualAccount` (capital A), `agentIdentity`, `createdBySubjectType`.
- **"My" usage** is a `userEmail EQUAL <the user's email>` filter (or `virtualAccount` for a key), not the whole tenant.
- **Teams.** Grouping by `team` counts a request once per team it belongs to and drops requests with no team; most requests also carry the team `everyone`. Drop the `everyone` row, and never add team rows together or to user rows — they double-count. Scope to teams with the filter `team ARRAY_HAS_ANY [...]`, exclude with `ARRAY_HAS_NONE`.
- **Metadata** (`x-tfy-metadata`): group by `metadata.<key>`; filter with `{"metadataKey":"<key>","operator":"IN","value":[...]}`. To find which keys exist, read `observability.md` (key discovery needs SQL on traces).
- **MCP agents** calling tools show as `tfyActorSlug` with `tfyActorType` `agent`.

### Reading the response

`{"data":{"dataPoints":[...],"intervalInSeconds":N}}`. Each point has `total`, each aggregation under its `alias` (default `<type><Column>`, e.g. `sumCostInUSD`, `p95LatencyMs`), each group-by value, and `startTimestamp`/`endTimestamp` (on timeseries these are the bucket). Timeseries fills empty buckets with `total: 0`.

Group-by values come back under the stored column name, not the request name:

| Grouped by | Response key |
| --- | --- |
| `userEmail`, `virtualaccount`, `agentIdentity` | `createdBySubjectSlug` |
| `virtualModel` | `virtualModelName` |
| `toolName` | `primitiveName` |
| `errorCode` | `httpStatusCode` |
| `ratelimitRuleId`, `budgetRuleId` | `ruleId` |
| `targetModel` | `model` |

Empty or small results can mean the caller's data-access rules hide the data, not that there is no traffic: say so and link `{controlPlaneUrl}/access-management?tab=data-access`.

### Recipes

All on the default 7-day window unless the user gives one. Shown as `datasource` · `groupBy` · aggregations · filters.

- **Spend, requests, tokens** — `realModelMetrics` · `[]` or `["modelName"]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens`; requests = `total` · `modelName NOT_IN [""]`.
- **Errors** — `realModelMetrics` · `["modelName"]` · `count modelName` with `filterPredicate isFailure EQUAL true`; error % = failures / `total`. Top error reasons: `groupBy ["errorDisplayLabel"]` with filter `isFailure EQUAL true` (values like `tfy-model-not-found`, `tfy-forbidden`, `tfy-rate-limit`, `tfy-budget-limit`, `HTTP: 429`). Both "model not found" and "forbidden" are HTTP 403: tell them apart by `errorDisplayLabel`, not `errorCode`.
- **Latency** — `realModelMetrics` · `["modelName"]` · `p50`/`p95`/`p99 latencyMs`, `p95 timeToFirstTokenMs` · `modelName NOT_IN [""]`.
- **Trend** — same as above with `type: timeseries` and `interval`.
- **Per-request totals for one trace** — `realModelMetrics` · `[]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens` · `traceId EQUAL <id>`, window from 5 minutes before the request to 5 minutes after it ends.
- **Provider prompt cache** — `realModelMetrics` · `sum cacheReadInputTokens`, `sum cacheCreationInputTokens`, `avg cacheReadInputPercentage`. `inputTokens` already includes cached tokens.
- **Gateway cache** — `cacheMetrics` · `["cacheType","cacheLookupStatus"]` (types `exact-match`, `semantic`; status `hit`, `miss`, `error`) · `avg cacheHitFlag` = hit %, `sum potentialCostSavings` = estimated savings.
- **MCP** — `mcpMetrics` · `["mcpServerName","toolName"]` · filter `method IN ["tools/call"]` for tool calls (other methods: `tools/list`, `initialize`, …) · `p95 latencyMs`; failures = `count method` with `filterPredicate isToolCallFailure EQUAL true` (includes tool execution errors; `isFailure` misses them). Error reasons: `groupBy ["toolErrorDisplayLabel"]`.
- **Guardrails** — `guardrailMetrics` · `["guardrailName"]` or `["guardrailResultCategory"]` · `guardrailName NOT_EQUAL ""`. `guardrailResult`: `flag` = blocked, `audit_mode_flag` = flagged but allowed (audit mode), `mutation` = content changed, `pass`, and `error` / `ignored_error` = the check itself failed. `guardrailResultCategory` folds these into `allowed`, `mutated`, `blocked`, `audit_mode_blocked`. `appliedOnEntityScope` is `input` or `output`. Per policy: `guardrailPolicyMetrics` · `["policyName"]`.
- **Rate-limit and budget blocks** — `configMetrics` · filter `configType EQUAL ratelimit` (or `budget`) · `groupBy ["ratelimitRuleId","configResultCategory"]` (or `budgetRuleId`), read rule as `ruleId`, outcome `allowed` / `blocked`. Who got blocked: add `userEmail` to `groupBy`. `status` is `blocked` on blocked rows, `all_model_failed` on load-balancing rows where every target failed, and NULL otherwise.
- **Load balancing** — `configMetrics` · filter `configType EQUAL loadbalance` · `["loadbalanceRuleId","requestedModel","targetModel"]` (read `model`); `p95 loadbalanceTargetAttemptCount`.
- **Agents** — `agentMetrics` · `["agentName"]` · `agentName NOT_IN [""]` · `count isFailure` with `filterPredicate isFailure EQUAL true`, `p50`/`p95 latencyMs`. `agentFramework`, `agentServerType` (`self-hosted`, `remote`) also group.

### Not here

- Budget usage against its limit: `get_budget_usage` / `get_my_budget_usage` (see `budget-limiting-v2.md`).
- Requests, prompts, responses, span details, errors of one request, feedback: `observability.md`.
- Joins across datasources (e.g. model cost of an agent run, guardrail outcome by model): not possible here; say so, or use SQL on traces if the span attributes cover it.

### Linking to the Metrics page

`{controlPlaneUrl}/monitoring/metrics?metricsV2Tab=<tab>&filters=<url-encoded JSON>`. Tabs: `overview`, `models`, `mcp`, `guardrails`, `agents`. The JSON is `{"rules":[{"field":"<filter field>","operator":"<op>","value":[...]}]}` with the API filter names: `modelName`, `userEmail`, `virtualAccount` with `IN`; `team` with `ARRAY_HAS_ANY`. Omit `filters` when nothing is filtered.

### Checklist

- [ ] Right datasource; request count from `total`.
- [ ] Time window stated in the answer; default 7 days.
- [ ] Latency as percentiles, percentage columns only with `avg`.
- [ ] Response keys read by their stored name (`createdBySubjectSlug`, `ruleId`, …).
- [ ] Sorted and cut client-side; team rows not summed.
- [ ] Empty result → data-access rules mentioned.
