---
name: metrics
description: Read for any aggregate Gateway question — requests, cost, tokens, latency, errors, cache, MCP calls, guardrail outcomes, rate-limit and budget blocks, load balancing, agents — per model, user, team, virtual account or metadata, over time. Explains how to query `query_llm_gateway_metrics` from the sandbox and link to the Metrics page.
---

## Gateway Metrics

`query_llm_gateway_metrics` aggregates Gateway metrics over a time range. Use it for every count, sum, percentile or trend. It cannot list individual requests, show request or response contents, read feedback, or reach a data routing destination other than `default`: for those, read `observability.md`.

### Running a query

Group-by and timeseries results can run to hundreds of rows, and the tool cannot sort or limit them. Run those queries from the sandbox with one program that calls the tool, sorts, cuts to what the question needs and prints only that. Call the tool directly only for a query with no `groupBy` and `type: distribution` (one row).

- From code: `result = await call_tool("<server>", "query_llm_gateway_metrics", body={...})`, on the Code Mode server hosting the tool. Independent queries can go in one program with `asyncio.gather`; a sandbox command times out after 60 seconds by default, so keep to a few queries.
- `call_tool` returns the response body as a dict, `{"data": {"dataPoints": [...], "intervalInSeconds": N}}`. The tool has no output schema; this is its shape, so don't run a call just to infer it. A 400 raises an error whose message is the server's.
- Build requests from this file, not the input schema: it merges all datasources' fields, so it can't tell which one accepts a field. A wrong field or operator returns a 400 naming it.
- Print a compact table (top 10–20 rows unless asked for more), with the total across all rows when shares matter.

### Datasources

| Question about | `datasource` |
| --- | --- |
| Model calls: requests, cost, tokens, latency, TTFT, errors, provider prompt-cache tokens, per real model | `realModelMetrics` |
| Traffic, cost or latency per virtual model, without a real-model breakdown | `virtualModelMetrics` (no gateway-cache columns) |
| Gateway cache (exact-match / semantic): hit rate, savings | `cacheMetrics` |
| MCP calls and tool calls | `mcpMetrics` |
| Guardrail checks and outcomes | `guardrailMetrics` (`guardrailPolicyMetrics` for per-policy counts) |
| Rate-limit, budget and load-balancing decisions | `configMetrics` |
| Agent runs | `agentMetrics` |
| Every incoming Gateway request by path, method, span type | `gatewayRequestMetrics` |

`modelMetrics` reads the same rows as `realModelMetrics`; use `realModelMetrics`. Virtual model → real model breakdown: `realModelMetrics` grouped by `virtualModel` and `modelName` (only calls routed through a virtual model).

### Request rules

- **Time.** Get `get_current_datetime`'s result before building the window, never alongside the query. `startTs` and `endTs` are ISO 8601, both inclusive; without an offset they are UTC, and both must use the same offset. `endTs` defaults to now, and a future `endTs` is clamped to now. Default to the last 7 days when the user gives no window, and state the window in the answer.
- **`type`.** `distribution` returns one row per group over the window. `timeseries` adds buckets: set `interval` (`"1 hour"`, `"1 day"`, one unit only) when the user asks for a granularity; otherwise the server picks one from the window (≤1 hour → 2 minutes, ≤3 hours → 10 minutes, ≤12 hours → 30 minutes, ≤1 day → 1 hour, ≤7 days → 12 hours, ≤30 days → 1 day, ≤90 days → 3 days). Buckets start at `startTs`: for daily or hourly trends start at a UTC midnight or hour. Empty buckets come back with `total: 0` and null group values.
- **Counting requests.** Every row has `total`, the number of rows matched: that is the request count. `count` on a column counts only rows where it is not NULL (`count` of `costInUSD` skips calls without cost).
- **Conditional counts.** A `filterPredicate` on an aggregation counts a subset in the same query: `{"type":"count","column":"modelName","alias":"failures","filterPredicate":[{"fieldName":"isFailure","operator":"EQUAL","value":true}]}`. Aliases must be unique.
- **Latency.** Never `avg` latency (`latencyMs`, `timeToFirstTokenMs`, `interTokenLatencyMs`, `timePerOutputTokenLatencyMs`, `cacheLookupLatencyMs`): use `p50`…`p99`. Default to and rank by `p95` (`p99` for worst case).
- **Percentage columns.** `isFailurePercentageFlag` and `cacheHitFlag` are 100 or 0 per row, so `avg` of them is the error % or hit %; never `sum` or `count` them. `cacheReadInputPercentage` is a per-call share; for the overall cached share, divide `sum cacheReadInputTokens` by `sum inputTokens`.
- **Rate types** (`ratePerMinute`, `rateSum`, `rateAvg`, `rateMin`, `rateMax`) need `type: timeseries`. `createdAt` takes only `min` and `max`.
- **Present values.** "Has a value" is `NOT_IN [""]`. Add `modelName NOT_IN [""]` to model queries, `agentName NOT_IN [""]` to agent queries, and `mcpServerName NOT_IN [""]` when grouping MCP calls by server.
- **Operators.** Fields allow different operators: `isFailure`, `traceId`, `configType` and `status` take only `EQUAL`; `cacheType`, `requestedModel`, `targetModel`, `ratelimitRuleId` and `budgetRuleId` only `IN`/`NOT_IN`. OR groups (`{"operator":"OR","filters":[...]}`) work on model datasources only.
- Never send `exportFormat`.

### Who: users, keys, teams, metadata

- **Group-by** `userEmail` (users), `virtualaccount` (virtual accounts), `agentIdentity` (agent identities). Grouping by exactly one of them keeps only that subject type, so `userEmail` alone hides virtual accounts. For "who" across all kinds, group by `["userEmail","virtualaccount","createdBySubjectType"]` (add `agentIdentity` except on `guardrailMetrics`, `configMetrics` and `gatewayRequestMetrics`) and read `createdBySubjectSlug` with `createdBySubjectType`.
- **Filter** names: `userEmail`, `virtualAccount` (capital A), `agentIdentity`, `createdBySubjectType`. "My" usage is `userEmail EQUAL <the user's email>`.
- **Teams.** Grouping by `team` counts a request once per team of its caller and drops requests whose caller has no team; every user is in the team `everyone`. Drop the `everyone` row, and never add team rows together or to user rows. Scope with `team ARRAY_HAS_ANY [...]`, exclude with `ARRAY_HAS_NONE`.
- **Metadata** (`x-tfy-metadata`): group by `metadata.<key>`; filter `{"metadataKey":"<key>","operator":"IN","value":[...]}`. To find which keys exist, use the metadata keys query in `observability.md`.
- `tfyActorSlug`/`tfyActorType`: the identity acting on the caller's behalf (an agent calling for a user).

### Reading results

Each point has `total`, each aggregation under its `alias` (default `<type><Column>`, e.g. `sumCostInUSD`), and each group-by value under its stored column name:

| Grouped by | Key |
| --- | --- |
| `userEmail`, `virtualaccount`, `agentIdentity` | `createdBySubjectSlug` |
| `virtualModel` | `virtualModelName` |
| `toolName` | `primitiveName` |
| `errorCode` | `httpStatusCode` |
| `ratelimitRuleId`, `budgetRuleId` | `ruleId` |
| `targetModel` | `model` |

Data-access rules filter every query, and with no matching rule it returns nothing. An empty or small result can mean the caller lacks access: say so and link `{controlPlaneUrl}/access-management?tab=data-access` ([data access](https://www.truefoundry.com/docs/ai-gateway/data-access)).

### Recipes

Shown as `datasource` · `groupBy` · aggregations · filters.

- **Spend, requests, tokens** — `realModelMetrics` · `[]` or `["modelName"]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens`; requests = `total` · `modelName NOT_IN [""]`. How cost and cached tokens are counted: [cost tracking](https://www.truefoundry.com/docs/ai-gateway/cost-tracking#how-cost-is-calculated).
- **Errors** — `realModelMetrics` · `["modelName"]` · `count modelName` with `filterPredicate isFailure EQUAL true`; error % = failures / `total`. Reasons: `groupBy ["errorDisplayLabel"]` with filter `isFailure EQUAL true`. Model not found vs not allowed: filter `errorType IN ["tfy-model-not-found"]` or `["tfy-forbidden"]`, never `errorCode` ([why](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#authorization-vs-missing-model)).
- **Latency** — `realModelMetrics` · `["modelName"]` · `p50`/`p95`/`p99 latencyMs`, `p95 timeToFirstTokenMs` · `modelName NOT_IN [""]`.
- **One request's totals** — `realModelMetrics` · `[]` · `sum costInUSD`, `sum inputTokens`, `sum outputTokens` · `traceId EQUAL <id>`, window from 5 minutes before the request to 5 minutes after it ends.
- **Provider prompt cache** — `realModelMetrics` · `sum cacheReadInputTokens`, `sum cacheCreationInputTokens`, `sum inputTokens`.
- **Gateway cache** — `cacheMetrics` · `["cacheType","cacheLookupStatus"]` (`exact-match`/`semantic`; `hit`/`miss`/`error`) · `avg cacheHitFlag`, `sum potentialCostSavings` ([how savings are computed](https://www.truefoundry.com/docs/ai-gateway/cost-savings#how-each-figure-is-calculated)).
- **MCP** — `mcpMetrics` · `["mcpServerName","toolName"]` · filter `method IN ["tools/call"]` · `p95 latencyMs`; failures = `count method` with `filterPredicate isToolCallFailure EQUAL true` (`isFailure` misses tool execution errors). Reasons: `groupBy ["toolErrorDisplayLabel"]`.
- **Guardrails** — `guardrailMetrics` · `["guardrailName","guardrailResult"]` · `guardrailName NOT_EQUAL ""`. Report blocked (`flag`), flagged in audit mode (`audit_mode_flag`), mutated (`mutation`) and failed to run (`error`, `ignored_error`) separately; meanings: [guardrail result values](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes#guardrail-result-values). `guardrailResultCategory` folds them into `blocked`, `audit_mode_blocked`, `mutated` and `allowed` — which includes `error` and `ignored_error`. Per policy: `guardrailPolicyMetrics` · `["policyName"]`.
- **Rate-limit and budget blocks** — `configMetrics` · filter `configType EQUAL ratelimit` (or `budget`) · `["ratelimitRuleId","configResultCategory"]` (or `budgetRuleId`); rule in `ruleId`, outcome `allowed`/`blocked`. Who was blocked: add `userEmail` and `virtualaccount`. `status` is `blocked` on blocked rows, `all_model_failed` when every load-balancing target failed, NULL otherwise.
- **Load balancing** — `configMetrics` · filter `configType EQUAL loadbalance` · `["loadbalanceRuleId","requestedModel","targetModel"]` (target in `model`, NULL when all targets failed) · `p95 loadbalanceTargetAttemptCount`.
- **Agents** — `agentMetrics` · `["agentName"]` · `agentName NOT_IN [""]` · `count isFailure` with `filterPredicate isFailure EQUAL true`, `p50`/`p95 latencyMs`.

### Not here

- Budget usage against its limit: `get_budget_usage` / `get_my_budget_usage` (see `budget-limiting-v2.md`).
- Requests, contents, span details, feedback: `observability.md`.
- Joins across datasources (e.g. model cost of an agent run): not possible; say so.

### Linking to the Metrics page

`{controlPlaneUrl}/monitoring/metrics?metricsV2Tab=<tab>&filters=<url-encoded JSON>`, tabs `overview`, `models`, `mcp`, `guardrails`, `agents`. The JSON is `{"rules":[{"field":"<f>","operator":"IN","value":[...],"apiKey":"fieldName","apiKeyValue":"<f>"}]}` with `<f>` an API filter name (`modelName`, `userEmail`, `virtualAccount`; `team` with `ARRAY_HAS_ANY`); for metadata, `"apiKey":"metadataKey","apiKeyValue":"<key>"`. A rule without `apiKey` and `apiKeyValue` is ignored. The page always opens on the last 7 days: say so when your window differs.

### Checklist

- [ ] Grouped or timeseries query run from the sandbox, printing only the needed rows.
- [ ] Request count from `total`; latency as percentiles; flags only with `avg`.
- [ ] Window stated; empty result → data-access rules mentioned.
