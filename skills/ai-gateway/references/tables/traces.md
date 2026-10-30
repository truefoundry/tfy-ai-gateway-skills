---
name: traces
description: Stores OTEL spans with additional columns for gateway-specific information. One head span per request, child spans for model calls, MCP calls, guardrails and more.
---

## CRITICAL

- The physical table name varies by tenant. Query `"<destination>"."<tracesTable>"` with `tracesTable` from the session context. Never assume `traces`.
- Partitioned by `Date` and `Hour` (UTC strings from `Timestamp`). Always filter a `"Date"` literal range as well as `"Timestamp"`.
- `TfyGatewayInput` and `TfyGatewayOutput` hold the full request and response payloads: large, sensitive JSON. Select them only when the user asks for contents, and only for a few rows.
- Head span (the request itself): `COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId") = ''` (misses requests sent with the caller's own trace context). Its `TfyGatewaySpanType` is the request type (`ChatCompletion`, `Responses`, `Messages`, `MCPGateway`, `Embedding`, …). Child spans: `Model` (one per provider call), `MCP`, `Guardrail`, `CacheLookup`, `CacheWrite`, …. Spans with a NULL `TfyGatewaySpanType` are internal HTTP instrumentation; skip them. For other values, `SELECT DISTINCT "TfyGatewaySpanType"` over a short window; values are case sensitive.
- Errors: `StatusCode = 'Error'`. The error reason is on the `Model` span, which exists even when the request failed before reaching a model: `"SpanAttributesString"['tfy.error_type']` (e.g. `tfy-model-not-found`, `tfy-forbidden`, `tfy-rate-limit`, `tfy-budget-limit`, `tfy-input-guardrail`) and `"SpanAttributesString"['tfy.error_message']`. Both `tfy-model-not-found` and `tfy-forbidden` return 403 with the same "not authorized … or model does not exist" message: `tfy-model-not-found` means the provider account or model does not exist in the gateway, never missing access; `tfy-forbidden` means it exists and the caller lacks access.
- Model cost of a span: `"SpanAttributesNumber"['tfy.model.metric.cost_in_usd']`. Totals across requests come from the metrics API (`metrics.md`).
- Team filter: `array_has("SpanAttributesStringList"['tfy.request.created_by_subject_teams'], '<team>')`. A caller with no teams has the string `'[]'` in `SpanAttributesString` instead.
- Integer attributes are in `SpanAttributesNumber` as DOUBLE. Attributes that have their own column (input, output, span type, metadata, conversation ID, caller) are not in the maps.
- Calling client: every head span has `"SpanAttributesString"['user_agent.original']` (the caller's User-Agent, e.g. `claude-cli/…`) and `['client.address']` (the first `Forwarded`/`X-Forwarded-For` entry, which the caller can set, else the connection's address). Spans with a NULL `TfyGatewaySpanType` are the gateway's own outbound calls: their user agent (usually `node`, or a provider SDK) is not the caller's. A caller can send `node` too. Show IPs only when asked.
- Attribute keys: this file and the [span attributes](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes) docs. If neither names one, list the keys in use with `map_keys` (`observability.md` → Examples) before saying it is not recorded. `gen_ai.*` attributes are written only when [enabled](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes-genai#enabling-genai-attributes); don't rely on them.

## Schema

```
Timestamp: TIMESTAMPTZ
    Start time of the span, UTC, microsecond precision.
Date: TEXT
    Partition: UTC date 'YYYY-MM-DD' of Timestamp. Compare with string literals.
Hour: TEXT
    Partition: UTC hour 'HH' of Timestamp.
TraceId: TEXT
    Shared by every span of one request.
SpanId: TEXT
    Identifier of this span within the trace.
ParentSpanId: TEXT
    OTEL parent span ID; empty on a root span.
TfyParentSpanId: TEXT, nullable
    Gateway parent span ID. The effective parent is COALESCE(NULLIF("TfyParentSpanId", ''), "ParentSpanId").
SpanName: TEXT
    Operation name of the span.
SpanKind: TEXT
    Usually 'Server', 'Client' or 'Internal'; also 'Unspecified', 'Producer', 'Consumer'.
Duration: BIGINT
    Span duration in nanoseconds (divide by 1e6 for milliseconds).
StatusCode: TEXT, nullable
    'Ok', 'Error' or 'Unset'.
StatusMessage: TEXT, nullable
    Status message, often set on errors.
HttpStatusCode: INTEGER, nullable
    HTTP status of the response.
TfyGatewaySpanType: TEXT, nullable
    Gateway span type (see CRITICAL).
GenAIRequestModel: TEXT, nullable
    Head span: the model the client requested, real or virtual. Model span: the gateway model called (e.g. 'openai-main/gpt-4o').
TfyGatewayConversationID: TEXT, nullable
    Conversation identifier tying related calls together.
TfyGatewayMetadata: Map(Text, Text), nullable
    Request metadata: the x-tfy-metadata header merged with metadata overrides from gateway rules (the rule wins).
TfyGatewayInput: TEXT, nullable
    JSON request payload. Sensitive.
TfyGatewayOutput: TEXT, nullable
    JSON response payload. Sensitive. On Model spans, the full LLM response.
TfyCreatedBySubjectSlug: TEXT, nullable
    Caller: user email or virtual account name.
TfyCreatedBySubjectType: TEXT, nullable
    Caller type, e.g. user, virtualaccount, agent. Not exhaustive.
TfyCreatedBySubjectId: TEXT, nullable
    Stable identifier of the caller.
TfyCreatedBySubject: TEXT
    Caller as a JSON string {subjectId, subjectType, subjectSlug}; use the three columns above instead.
TfyActorSlug: TEXT, nullable
    Acting identity when an agent acts on behalf of the caller.
TfyActorType: TEXT, nullable
    Type of the acting identity, e.g. agent.
SpanAttributesString: Map(Text, Text), nullable
SpanAttributesNumber: Map(Text, DOUBLE), nullable
SpanAttributesBool: Map(Text, BOOLEAN), nullable
SpanAttributesStringList: Map(Text, Array(Text)), nullable
SpanAttributesNumberList: Map(Text, Array(DOUBLE)), nullable
SpanAttributesBoolList: Map(Text, Array(BOOLEAN)), nullable
    Span attributes by value type, keyed by attribute name ('tfy.…').
ResourceAttributesString: Map(Text, Text), nullable
ResourceAttributesNumber: Map(Text, DOUBLE), nullable
ResourceAttributesBool: Map(Text, BOOLEAN), nullable
ResourceAttributesStringList: Map(Text, Array(Text)), nullable
ResourceAttributesNumberList: Map(Text, Array(DOUBLE)), nullable
ResourceAttributesBoolList: Map(Text, Array(BOOLEAN)), nullable
    OTEL resource attributes of the emitting service.
EventTimes: Array(TIMESTAMP), nullable
EventNames: Array(Text), nullable
EventsAttributesString: Array(Map(Text, Text)), nullable
EventsAttributesNumber: Array(Map(Text, DOUBLE)), nullable
EventsAttributesBool: Array(Map(Text, BOOLEAN)), nullable
EventMetadata: Array(Map(Text, Text)), nullable
    Span events as parallel arrays: element i of each array is event i.
ServiceName: TEXT
    Emitting service, e.g. 'tfy-llm-gateway'.
ScopeName: TEXT
ScopeVersion: TEXT
    OTEL instrumentation scope.
TraceState: TEXT
    W3C trace state.
TfyTenantName: TEXT
    Tenant name.
TracingProjectId: TEXT
TracingProjectName: TEXT
TracingApplicationId: TEXT
TracingApplicationName: TEXT
    Tracing project and application; '' when not set.
RequestedTracingProjectId: TEXT, nullable
    Tracing project the sender asked for.
EnvironmentName: TEXT, nullable
    Environment name, when the sender sets it.
Tags: Array(Text), nullable
    Only 'LLM' (needs gen_ai attributes) and 'exception'.
Metadata: Map(Text, Text), nullable
    Ingestion type markers for attributes; not useful for queries. Request metadata is TfyGatewayMetadata.
TfyLogLevel: TEXT, nullable
    'info' or 'debug'. The traces UI hides debug spans.
IngestedAt: TIMESTAMPTZ, nullable
    When the span was stored.
```

There are no `Events` or `Links` columns.

## Checklist

- [ ] `"Date"` literal range and `"Timestamp"` range?
- [ ] Head-span filter when listing requests; NULL-type spans skipped?
- [ ] Payload columns only when needed?
- [ ] Attribute keys from this file or the span attributes docs, else from `map_keys`?
