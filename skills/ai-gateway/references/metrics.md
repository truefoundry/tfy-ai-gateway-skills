---
name: metrics
description: Aggregate Gateway questions — requests, cost, tokens, latency, errors, cache, MCP, guardrails, rate limits, agents — per model, user, team, VA or metadata. How to query `query_llm_gateway_metrics` from the sandbox and link to Metrics.
---

## Gateway Metrics

`query_llm_gateway_metrics` aggregates over a time range. Use it for every count, sum, percentile or trend. It cannot list individual requests, show request/response contents, read feedback, or reach a routing destination other than `default`: for those, read `observability.md`.

### Running a query

Group-by and timeseries can run to hundreds of rows; the tool cannot sort or limit. Run those from the sandbox with one program that calls the tool, sorts, cuts to what the question needs and prints only that. A single `call_tool` (no sandbox program) is enough only for no `groupBy` and `type: distribution` (one row).

- From code: `result = await call_tool("<server>", "query_llm_gateway_metrics", body={...})`, on the Code Mode server hosting the tool. Independent queries can use `asyncio.gather`; sandbox timeout is 60s by default, so keep to a few queries.
- `call_tool` returns `{"data": {"dataPoints": [...], "intervalInSeconds": N}}`. Don't call to infer this shape. A 400's message is the server's.
- Build requests from this file — not the input schema or `get_tool_info` (schema merges all datasources; this file has every field, operator and recipe). Never call `get_tool_info` on `query_llm_gateway_metrics`. A wrong field/operator returns a 400 naming it.
- Print the top 10–20 rows as a compact table.
- **Totals.** Print headline totals (requests, cost, tokens, failures) from a `groupBy: []` query in the same program; grouped rows double count teams and virtual → real models (one row per fallback target). Quote only numbers the program printed.

### Datasources

| Question about | `datasource` |
| --- | --- |
| Model calls: requests, cost, tokens, latency, TTFT, errors, prompt-cache tokens, per real model | `realModelMetrics` |
| Traffic/cost/latency per virtual model (no real-model breakdown; no gateway-cache cols) | `virtualModelMetrics` |
| Gateway cache (exact-match / semantic): hit rate, savings | `cacheMetrics` |
| MCP calls and tool calls | `mcpMetrics` |
| Guardrail checks and outcomes | `guardrailMetrics` (`guardrailPolicyMetrics` per policy) |
| Rate-limit, budget and load-balancing decisions | `configMetrics` |
| Agent runs | `agentMetrics` |
| Incoming Gateway requests by path, method, span type | `gatewayRequestMetrics` |

`modelMetrics` = same rows as `realModelMetrics`; use `realModelMetrics`. Virtual → real breakdown: `realModelMetrics` grouped by `virtualModel` and `modelName` (only calls via a virtual model).

### Request rules

- **Scope.** "My", "I" or "me" → filter `userEmail EQUAL <session email>` on every query, totals included. Without it, a caller who can see other users gets everyone's numbers.
- **Time.** Get `get_current_datetime` before building the window, never alongside the query. `startTs`/`endTs` are ISO 8601, both inclusive; without an offset they are UTC and must share the same offset. `endTs` defaults to now; a future value is clamped. Default last 7 days when no window given; state the window in the answer.
- **`type`.** `distribution` = one row per group over the window. `timeseries` adds buckets: set `interval` (`"1 hour"`, `"1 day"`, one unit) when the user asks for granularity; else the server picks from the window. Buckets start at `startTs` (use UTC midnight/hour for daily/hourly). Empty buckets: `total: 0`, null groups.
- **Counting requests.** Every row has `total` (row count = request count). `count` on a column skips NULLs (`count` of `costInUSD` skips calls without cost).
- **Conditional counts.** A `filterPredicate` on an aggregation counts a subset: `{"type":"count","column":"modelName","alias":"failures","filterPredicate":[{"fieldName":"isFailure","operator":"EQUAL","value":true}]}`. Aliases must be unique.
- **Latency.** Never `avg` latency (`latencyMs`, `timeToFirstTokenMs`, `interTokenLatencyMs`, `timePerOutputTokenLatencyMs`, `cacheLookupLatencyMs`): use `p50`…`p99`. Default/rank by `p95` (`p99` for worst case).
- **Percentage columns.** `isFailurePercentageFlag` and `cacheHitFlag` are 100 or 0 per row, so `avg` is the error % or hit %; never `sum`/`count`. Overall cached share = `sum cacheReadInputTokens` / `sum inputTokens`.
- **Rate types** (`ratePerMinute`, `rateSum`, `rateAvg`, `rateMin`, `rateMax`) need `type: timeseries`. `createdAt` takes only `min`/`max`.
- **Present values.** "Has a value" is `NOT_IN [""]`. Add `modelName NOT_IN [""]` to model queries, `agentName NOT_IN [""]` to agent queries, `mcpServerName NOT_IN [""]` when grouping MCP by server — **except failure counts** (pre-routing failures have no name; the filter drops them).
- **Operators.** `isFailure`, `traceId`, `configType`, `status` take only `EQUAL`; `cacheType`, `requestedModel`, `targetModel`, `ratelimitRuleId`, `budgetRuleId` only `IN`/`NOT_IN`. OR groups (`{"operator":"OR","filters":[...]}`) on model datasources only.
- Never send `exportFormat`.

### Who: users, keys, teams, metadata

- **Group-by** `userEmail` (users), `virtualaccount` (VAs), `agentIdentity` (agents). Exactly one keeps only that subject type (`userEmail` alone hides VAs). For "who" across kinds: `["userEmail","virtualaccount","createdBySubjectType"]` (add `agentIdentity` except on `guardrailMetrics`, `configMetrics`, `gatewayRequestMetrics`); read `createdBySubjectSlug` with `createdBySubjectType`.
- **Filter** names: `userEmail`, `virtualAccount` (capital A), `agentIdentity`, `createdBySubjectType`.
- **Teams.** Grouping by `team` counts once per team of the caller and drops callers with no team; everyone is in `everyone`. Drop that row; never add team rows together or to user rows. Scope `team ARRAY_HAS_ANY [...]`, exclude `ARRAY_HAS_NONE`.
- **Metadata** (`x-tfy-metadata`): group by `metadata.<key>`; filter `{"metadataKey":"<key>","operator":"IN","value":[...]}`. Keys: metadata query in `observability.md`.
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

Failures before routing leave group values null — models: `providerAccountType`/`modelName` (not found, forbidden, rate-limited); MCP: `mcpServerName`; agents: `agentName`; load-balance: `targetModel`→`model` when every target failed. Read with `p.get(k) or ""`. Explain those rows with a second failure query — models: `errorType` + `isFailure EQUAL true`; MCP: `toolErrorDisplayLabel` + `isToolCallFailure`; agents: `errorDisplayLabel` + `isFailure`. Don't guess.

Data-access rules filter every query; with no matching rule it returns nothing. Empty/small result can mean no access: say so and link `{controlPlaneUrl}/access-management?tab=data-access` ([data access](https://www.truefoundry.com/docs/ai-gateway/data-access)).

### Recipes

Shown as `datasource` · `groupBy` · aggregations · filters.

- **Spend, requests, tokens** — `realModelMetrics` · `[]` or `["modelName"]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens`; requests = `total` · `modelName NOT_IN [""]`. Cost: [cost tracking](https://www.truefoundry.com/docs/ai-gateway/cost-tracking#how-cost-is-calculated).
- **By provider and model** — `realModelMetrics` · `["providerAccountType","modelName"]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens`; requests = `total`. Keys `providerAccountType`, `modelName` (nullable — see Reading results).
- **Errors** — `realModelMetrics` · `["modelName"]` · `count modelName` with `filterPredicate isFailure EQUAL true`; error % = failures / `total`. Reasons: `groupBy ["errorDisplayLabel"]` + `isFailure EQUAL true`. Not found vs forbidden: `errorType IN ["tfy-model-not-found"]` or `["tfy-forbidden"]`, never `errorCode` ([why](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#authorization-vs-missing-model)).
- **Latency** — `realModelMetrics` · `["modelName"]` · `p50`/`p95`/`p99 latencyMs`, `p95 timeToFirstTokenMs` · `modelName NOT_IN [""]`.
- **One request's totals** — `realModelMetrics` · `[]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens` · `traceId EQUAL <id>`, window ±5 minutes around the request.
- **Provider prompt cache** — `realModelMetrics` · `sum cacheReadInputTokens`, `sum cacheCreationInputTokens`, `sum inputTokens`.
- **Gateway cache** — `cacheMetrics` · `["cacheType","cacheLookupStatus"]` (`exact-match`/`semantic`; `hit`/`miss`/`error`) · `avg cacheHitFlag`, `sum potentialCostSavings` ([savings](https://www.truefoundry.com/docs/ai-gateway/cost-savings#how-each-figure-is-calculated)).
- **MCP** — `mcpMetrics` · `["mcpServerName","toolName"]` · `method IN ["tools/call"]` · `p95 latencyMs`; failures = `count method` with `filterPredicate isToolCallFailure EQUAL true` (`isFailure` misses tool errors). `mcpServerName` nullable (pre-routing) — see Reading results. Reasons: `groupBy ["toolErrorDisplayLabel"]`.
- **Guardrails** — `guardrailMetrics` · `["guardrailName","guardrailResult"]` · `guardrailName NOT_EQUAL ""`. Report `flag`, `audit_mode_flag`, `mutation`, `error`, `ignored_error` separately ([values](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#guardrail-result-values)). `guardrailResultCategory` folds into `blocked`/`audit_mode_blocked`/`mutated`/`allowed` (includes errors). Per policy: `guardrailPolicyMetrics` · `["policyName"]`.
- **Rate-limit and budget blocks** — `configMetrics` · `configType EQUAL ratelimit` (or `budget`) · `["ratelimitRuleId","configResultCategory"]` (or `budgetRuleId`); rule in `ruleId`, outcome `allowed`/`blocked`. Who: add `userEmail`, `virtualaccount`. `status` is `blocked` when blocked, `all_model_failed` when every LB target failed, else NULL.
- **Load balancing** — `configMetrics` · `configType EQUAL loadbalance` · `["loadbalanceRuleId","requestedModel","targetModel"]` (target in `model`, NULL if all failed) · `p95 loadbalanceTargetAttemptCount`.
- **Agents** — `agentMetrics` · `["agentName"]` · `agentName NOT_IN [""]` · `count isFailure` with `filterPredicate isFailure EQUAL true`, `p50`/`p95 latencyMs`. Null/empty `agentName` = pre-routing — see Reading results.

### Not here

- Budget vs limit: `get_budget_usage` / `get_my_budget_usage` (`budget-limiting-v2.md`).
- Requests, contents, spans, feedback: `observability.md`.
- Joins across datasources: not possible; say so.

### Linking to the Metrics page

`{controlPlaneUrl}/monitoring/metrics?metricsV2Tab=<tab>&filters=<url-encoded JSON>`, tabs `overview`, `models`, `mcp`, `guardrails`, `agents`. JSON: `{"rules":[{"field":"<f>","operator":"IN","value":[...],"apiKey":"fieldName","apiKeyValue":"<f>"}]}` (`modelName`, `userEmail`, `virtualAccount`; `team` with `ARRAY_HAS_ANY`); metadata: `"apiKey":"metadataKey","apiKeyValue":"<key>"`. Rules need both `apiKey` keys. Page always opens on last 7 days: say so when your window differs.

### Checklist

- [ ] "My"/"I"/"me" → `userEmail` filter on every query including totals.
- [ ] Failure counts omit name `NOT_IN [""]` filters; null groups via `p.get`.
- [ ] Grouped/timeseries from sandbox; no `get_tool_info`.
- [ ] Request count from `total`; latency as percentiles; flags only with `avg`.
- [ ] Numbers from program output; window stated; empty → data-access rules.
