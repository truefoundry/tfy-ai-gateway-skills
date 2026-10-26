---
name: traces
description: Stores OTEL compliant spans with additional columns for gateway specific information.
---

## CRITICAL

- The physical table name varies by tenant. Query `"{dataRoutingDestination}"."{tracesTable}"` with `tracesTable` from the session context (call `get_session_context` only if it is missing). Never assume `traces`.
- `TfyGatewayInput` and `TfyGatewayOutput` columns store the request and response payloads of the gateway. These are huge json serialized payloads that contain sensitive data. Only fetch these when necessary.
- To filter by team use `array_has("SpanAttributesStringList"['tfy.request.created_by_subject_teams'], '<team>')`. On metrics tables use `array_has("Teams", '<team>')`.
- Enum-like columns (`SpanKind`, `StatusCode`, `TfyGatewaySpanType`) are case-sensitive.
- When working with `SpanAttributes.*` columns, use `get_section_content` on https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs-span-attributes to get the full list of attribute keys and their meanings.

## Schema

```
Timestamp: TIMESTAMPTZ
    Start time of the span in UTC (microsecond precision).
TraceId: TEXT
    W3C trace identifier linking all spans in one distributed request.
SpanId: TEXT
    Unique identifier for this span within the trace.
ParentSpanId: TEXT
    Span ID of the parent span; empty when this is a root span.
TfyParentSpanId: TEXT, nullable
    Parent span within the gateway's own span tree; use this (not ParentSpanId) to build the gateway span hierarchy.
SpanName: TEXT
    Operation name for the span (e.g. HTTP route or RPC method).
SpanKind: TEXT
    OpenTelemetry span kind: 'Server', 'Client', 'Internal', 'Producer', 'Consumer', 'Unspecified' (case-sensitive).
Duration: BIGINT
    Span duration in nanoseconds (divide by 1e6 for milliseconds).
StatusCode: TEXT, nullable
    OpenTelemetry span status code (Unset, Ok, Error).
StatusMessage: TEXT, nullable
    Optional human-readable message for span status, often on errors.
HttpStatusCode: INTEGER, nullable
    HTTP response status code when the span represents an HTTP operation.
GenAIRequestModel: TEXT, nullable
    Model identifier from GenAI-related request telemetry when present.
TfyGatewayConversationID: TEXT, nullable
    AI Gateway conversation identifier tying multi-turn or related gateway calls.
TfyGatewayMetadata: Map(Text, Text), nullable
    TrueFoundry Gateway Metadata - contains both user supplied and system generated metadata
TfyGatewayInput: TEXT, nullable
    JSON serialized gateway input payload. Contains sensitive data
TfyGatewayOutput: TEXT, nullable
    JSON serialized gateway output payload. Contains sensitive data.
    For Model spans (TfyGatewaySpanType = 'Model'), this contains the full LLM response JSON
TfyGatewaySpanType: TEXT, nullable
    Gateway span type (case-sensitive). Common values: 'Model' (one per provider call), 'ChatCompletion', 'Responses', 'Messages', 'Embedding', 'Rerank', 'MCPGateway', 'MCP', 'Guardrail', 'Hook', 'Proxy', 'AgentResponse', 'CacheLookup', 'CacheWrite'.
SpanAttributesString: Map(Text, Text), nullable
    String-valued OpenTelemetry span attributes as a key–value map.
SpanAttributesNumber: Map(Text, DOUBLE PRECISION), nullable
    Numeric span attributes (stored as float64) as a key–value map.
SpanAttributesBool: Map(Text, BOOLEAN), nullable
    Boolean span attributes as a key–value map.
SpanAttributesStringList: Map(Text, Array(Text)), nullable
    Span attributes whose values are lists of strings.
SpanAttributesNumberList: Map(Text, Array(DOUBLE PRECISION)), nullable
    Span attributes whose values are lists of numbers.
SpanAttributesBoolList: Map(Text, Array(BOOLEAN)), nullable
    Span attributes whose values are lists of booleans.
TfyCreatedBySubjectSlug: TEXT, nullable
    URL-safe slug for the TrueFoundry subject that created the span. User email or virtual account name
TfyCreatedBySubjectType: TEXT, nullable
    Type of the requesting subject. Common values: user, virtualaccount, agent. Do not assume the list is exhaustive.
TfyCreatedBySubjectId: TEXT, nullable
    Stable identifier of the TrueFoundry subject.
TfyCreatedBySubject: TEXT
    Identity of the caller or principal attributed to the span (TrueFoundry subject).
TfyActorSlug: TEXT, nullable
    Slug of the acting identity when an agent acts on behalf of the subject.
TfyActorType: TEXT, nullable
    Type of that acting identity.
Date: TEXT
    Partition column, UTC date 'YYYY-MM-DD' of Timestamp. Filter on it in scans so partitions are pruned.
```

## Checklist

- [ ] Did I use `get_section_content` on the span attributes docs page to look up attribute keys?
