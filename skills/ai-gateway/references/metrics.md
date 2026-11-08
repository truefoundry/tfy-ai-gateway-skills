---
name: metrics
description: Aggregate Gateway questions — requests, cost, tokens, latency, errors, cache, MCP, guardrails, rate limits, agents — per model, user, team, virtual account or metadata. Query `query_llm_gateway_metrics` from the sandbox; link to Metrics.
---

## Gateway Metrics

`query_llm_gateway_metrics` aggregates over a time range. Use it for every count, sum, percentile or trend. It cannot list individual requests, show contents, read feedback, or reach a routing destination other than `default` — for those, read `observability.md`.

### Running a query

Group-by and timeseries can return hundreds of rows and the tool cannot sort or limit, so query from the sandbox in one program that sorts and prints only what is needed:

```python
r = await call_tool("<server>", "query_llm_gateway_metrics", body={
  "datasource": "realModelMetrics", "type": "distribution", "groupBy": ["modelName"],
  "startTs": "2026-10-29T00:00:00Z", "endTs": "2026-11-05T00:00:00Z",
  "aggregations": [{"type": "sum", "column": "costInUSD", "alias": "cost"},
    {"type": "count", "column": "modelName", "alias": "failures",
     "filterPredicate": [{"fieldName": "isFailure", "operator": "EQUAL", "value": True}]}],
  "filters": [{"fieldName": "userEmail", "operator": "EQUAL", "value": "<session email>"}]})
rows = r["data"]["dataPoints"]
```

- `filters` and `filterPredicate` are always lists of `{fieldName, operator, value}`. Batch independent queries with `asyncio.gather` (sandbox timeout 60s).
- Build requests from this file; never call `get_tool_info` on this tool. A 400 names the wrong field.
- Print the top 10–20 rows, sorted on what the question ranks by, plus an `other` row (count, sums) for the rest and the null-name row (failed before routing), so rows add up to the total.
- **Totals.** Print headline totals (requests, cost, tokens, failures) from a `groupBy: []` query in the same program; grouped rows double count teams and virtual → real models. Quote only what the program printed — numbers, %, shares, rankings ("highest") and absences ("none": print the 0) — never estimates; add what's missing to the program.

### Datasources

| Question about | `datasource` |
| --- | --- |
| Model calls: cost, tokens, latency, TTFT, errors, prompt-cache, per real model | `realModelMetrics` |
| Per virtual model | `virtualModelMetrics` |
| Gateway cache (exact-match / semantic): hit rate, savings | `cacheMetrics` |
| MCP calls and tool calls | `mcpMetrics` |
| Guardrail checks | `guardrailMetrics` (`guardrailPolicyMetrics` per policy) |
| Rate-limit, budget and load-balancing decisions | `configMetrics` |
| Agent runs | `agentMetrics` |
| Incoming requests by path, method, span type | `gatewayRequestMetrics` |

Virtual model → real model breakdown: `realModelMetrics` grouped by `virtualModel` and `modelName` (only calls routed through one). Filter by virtual model with `virtualModelName`; `virtualModel` is group-by only.

### Request rules

- **Scope.** "My", "I" or "me" means filter `userEmail EQUAL <session email>` on every query, the totals query included. No session email (a virtual account): ask whose data first.
- **Time.** `get_current_datetime` first, never in the query's batch. `startTs`/`endTs` are ISO 8601, both inclusive; without an offset they are UTC and must share the same offset. Default to the last 7 days when no window is given.
- **`type`.** `distribution` returns one row per group over the window. `timeseries` adds buckets: set `interval` (`"1 hour"`, `"1 day"`, one unit) when asked for granularity; else the server picks from the window. Buckets start at `startTs` (UTC midnight/hour for daily/hourly). Empty buckets: `total: 0`, null groups.
- **Counting requests.** Every row has `total` (row count = request count). `count` on a column skips NULLs (`count` of `costInUSD` skips calls without cost).
- **Conditional counts.** A `filterPredicate` on an aggregation counts a subset in the same query (`failures` above). Aliases must be unique.
- **Latency.** Never `avg` latency columns: use `p50`…`p99`. Default to and rank by `p95` (`p99` for worst case).
- **Percentage columns.** `isFailurePercentageFlag` and `cacheHitFlag` are 100 or 0 per row, so `avg` of them is the error % or hit %; never `sum` or `count` them. `cacheReadInputPercentage` is a per-call share; for the overall share see Recipes.
- **Rate types** (`ratePerMinute`, `rateSum`, `rateAvg`, `rateMin`, `rateMax`) need `type: timeseries`. `createdAt` takes only `min` and `max`.
- **Present values.** "Has a value" is `NOT_IN [""]`. Add `modelName NOT_IN [""]` to model queries, `agentName NOT_IN [""]` to agent queries, `mcpServerName NOT_IN [""]` when grouping MCP by server — **except failure counts** (pre-routing failures have no name; the filter drops them).
- **Operators.** `isFailure`, `traceId`, `configType`, `status`: only `EQUAL`. `cacheType`, `requestedModel`, `targetModel`, `ratelimitRuleId`, `budgetRuleId`: only `IN`/`NOT_IN`. OR groups on model datasources only.

### Who: users, keys, teams, metadata

- **Group-by** `userEmail` (users), `virtualaccount` (virtual accounts), `agentIdentity` (agents). Exactly one keeps only that subject type (`userEmail` alone hides virtual accounts). For "who" across all kinds: `["userEmail","virtualaccount","createdBySubjectType"]` (add `agentIdentity` except on `guardrailMetrics`, `configMetrics`, `gatewayRequestMetrics`); read `createdBySubjectSlug` with `createdBySubjectType`.
- **Filter** names: `userEmail`, `virtualAccount` (capital A), `agentIdentity`, `createdBySubjectType`.
- **Teams.** Grouping by `team` counts once per team of the caller and drops callers with no team; every user is in `everyone`. Drop that row; never add team rows to each other or to user rows. Scope `team ARRAY_HAS_ANY [...]`, exclude `ARRAY_HAS_NONE`.
- **Metadata** (`x-tfy-metadata`): group by `metadata.<key>`; filter `{"metadataKey":"<key>","operator":"IN","value":[...]}`. Keys: see `observability.md`.
- `tfyActorSlug`/`tfyActorType`: identity acting on the caller's behalf.

### Reading results

Each point has `total`, each aggregation under its `alias` (default `<type><Column>`, e.g. `sumCostInUSD`), and each group-by under its stored column name:

| Grouped by | Key |
| --- | --- |
| `userEmail`, `virtualaccount`, `agentIdentity` | `createdBySubjectSlug` |
| `virtualModel` | `virtualModelName` |
| `toolName` | `primitiveName` |
| `errorCode` | `httpStatusCode` |
| `ratelimitRuleId`, `budgetRuleId` | `ruleId` |
| `targetModel` | `model` |
| `providerAccountType`, `modelName`, `providerModelName` | same name |

Failures before routing leave group values null — models: `providerAccountType`/`modelName` (not found, forbidden, rate-limited); agents: `agentName`; load-balance: `targetModel` (key `model`) when every target failed. Explain with a second failure query — models/agents: `groupBy ["errorDisplayLabel"]` + `isFailure EQUAL true` (`errorType` is a filter only, never group-by); MCP tool failures: `toolErrorDisplayLabel` + `isToolCallFailure`. Run it; don't guess.

Data-access rules filter every query; with no matching rule it returns nothing. An empty or small result can mean no access: say so and link `{controlPlaneUrl}/access-management?tab=data-access` ([data access](https://www.truefoundry.com/docs/ai-gateway/data-access)).

### Recipes

Shown as `datasource` · `groupBy` · aggregations · filters.

- **Spend, requests, tokens** — `realModelMetrics` · `[]` or `["modelName"]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens`; requests = `total` · `modelName NOT_IN [""]`. Cost: [cost tracking](https://www.truefoundry.com/docs/ai-gateway/cost-tracking#how-cost-is-calculated).
- **Per virtual model** — `virtualModelMetrics` · `["virtualModel"]` · `sum costInUSD`; failures = `count modelName` with `filterPredicate isFailure EQUAL true`. Not `realModelMetrics`: it counts each real call (retries, fallbacks).
- **By provider and model** — `realModelMetrics` · `["providerAccountType","modelName"]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens`; requests = `total`. Keys `providerAccountType`, `modelName` (nullable — see Reading results).
- **Errors** — `realModelMetrics` · `["modelName"]` · `count modelName` with `filterPredicate isFailure EQUAL true`; print error % = failures / `total`. Not found vs forbidden: filter `errorType IN ["tfy-model-not-found"]` or `["tfy-forbidden"]`, never `errorCode` ([why](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#authorization-vs-missing-model)).
- **Latency** — `realModelMetrics` · `["modelName"]` · `p50`/`p95`/`p99 latencyMs`, `p95 timeToFirstTokenMs` · `modelName NOT_IN [""]`.
- **One request's totals** — `realModelMetrics` · `[]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens` · `traceId EQUAL <id>`, window from 5 minutes before the request to 5 minutes after it ends.
- **Provider prompt cache** — `realModelMetrics` · `sum cacheReadInputTokens`, `sum cacheCreationInputTokens`, `sum inputTokens`; print cached share = read / input.
- **Gateway cache** — `cacheMetrics` · `["cacheType"]` (`exact-match`/`semantic`) · `avg cacheHitFlag` (hit %), `sum potentialCostSavings` ([how savings are computed](https://www.truefoundry.com/docs/ai-gateway/cost-savings#how-each-figure-is-calculated)). Group by `cacheLookupStatus` only to count `hit`/`miss`/`error`; it makes each row's hit % 0 or 100. No row for a type = no lookups, not 0%.
- **MCP** — `mcpMetrics` · `["mcpServerName","toolName"]` · filter `method IN ["tools/call"]` · `p95 latencyMs`; failures = `count method` with `filterPredicate isToolCallFailure EQUAL true` (`isFailure` misses tool execution errors).
- **Guardrails** — `guardrailMetrics` · `["guardrailName","guardrailResult"]` · `guardrailName NOT_EQUAL ""`. Per guardrail, print and report blocked (`flag`), flagged in audit mode (`audit_mode_flag`), mutated (`mutation`) and failed to run (`error`, `ignored_error`) separately, 0 when absent; say which you count as failed. Meanings: [guardrail result values](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#guardrail-result-values). Not `guardrailResultCategory`: its `allowed` includes `error` and `ignored_error`. Per policy: `guardrailPolicyMetrics` · `["policyName"]`.
- **Rate-limit and budget blocks** — `configMetrics` · filter `configType EQUAL ratelimit` (or `budget`) · `["ratelimitRuleId","configResultCategory"]` (or `budgetRuleId`); rule in `ruleId`, outcome `allowed`/`blocked`. Who was blocked: add `userEmail` and `virtualaccount`.
- **Load balancing** — `configMetrics` · filter `configType EQUAL loadbalance` · `["loadbalanceRuleId","requestedModel","targetModel"]` · `p95 loadbalanceTargetAttemptCount`.
- **Agents** — `agentMetrics` · `["agentName"]` · `agentName NOT_IN [""]` · `count isFailure` with `filterPredicate isFailure EQUAL true`, `p50`/`p95 latencyMs`.

### Not here

- Budget vs limit: `get_budget_usage` / `get_my_budget_usage` (`budget-limiting-v2.md`).
- Joins across datasources: not possible; say so.

### Linking to the Metrics page

`{controlPlaneUrl}/monitoring/metrics?metricsV2Tab=<tab>&filters=<url-encoded JSON>`, tabs `overview`, `models`, `mcp`, `guardrails`, `agents`. JSON: `{"rules":[{"field":"<f>","operator":"IN","value":[...],"apiKey":"fieldName","apiKeyValue":"<f>"}]}` (`modelName`, `userEmail`, `virtualAccount`; `team`+`ARRAY_HAS_ANY`; metadata uses `"apiKey":"metadataKey"`). Both `apiKey` fields required. Page opens on last 7 days: say so when your window differs.

### Checklist

- [ ] "My"/"I"/"me" → `userEmail` on every query including totals; failure counts omit name `NOT_IN [""]`.
- [ ] Request count from `total`; latency as percentiles; flags with `avg` only.
- [ ] Numbers, %, rankings and "none" from program output; window stated; Metrics page linked; empty → data-access.
