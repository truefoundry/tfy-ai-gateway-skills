---
name: gateway_feedbacks
description: Stores user feedback (ratings, comments) linked to trace spans.
---

## CRITICAL

- Feedback is linked to traces via `TargetTraceId` and optionally to a specific span via `TargetSpanId`.
- Always include time-range filters on `"TargetCreatedAt"` to avoid full table scans.
- Feedback rows are versioned: an update or delete writes a new row with the same `FeedbackId`. Always keep only the latest row per `FeedbackId` (`ROW_NUMBER() OVER (PARTITION BY "FeedbackId" ORDER BY "CreatedAt" DESC) = 1`), then filter `"IsDeleted" = false`. Never filter `IsDeleted` before deduplicating — counts and averages are otherwise wrong with no error.
- Multiple feedbacks can exist for the same trace/span (e.g. different metrics like `rating`, `accuracy`, etc.).
- Traces and feedback for the same request are in the same destination. Pick it as described in observability.md (Writing SQL Queries).

## Schema

```
FeedbackId: TEXT
    Identifier of the feedback. Shared by all versions of the same feedback.
TenantName: TEXT
    Tenant that owns this feedback record.
TracingProjectId: TEXT
    Tracing project this feedback belongs to.
CreatedAt: TIMESTAMPTZ
    When this version of the feedback was written (UTC).
IsDeleted: BOOLEAN
    Whether this version marks the feedback as deleted. Only meaningful on the latest version per FeedbackId.
TargetTraceId: TEXT
    TraceId of the trace this feedback is about. Join key to the traces table.
TargetSpanId: TEXT
    SpanId of the specific span this feedback targets within the trace.
TargetMetadata: Map(Text, Text), nullable
    Metadata from the target span at the time feedback was recorded.
TargetCreatedAt: TIMESTAMPTZ
    Creation time of the target span (not the feedback itself). Use for time-range filtering.
Metadata: Map(Text, Text), nullable
    Arbitrary key-value metadata attached to the feedback itself.
Comment: TEXT, nullable
    Free-text comment provided with the feedback.
MetricName: TEXT
    Name of the feedback metric (e.g. 'rating', 'accuracy', 'relevance').
MetricValue: DOUBLE PRECISION
    Numeric value of the feedback metric.
CreatedBySubjectSlug: TEXT, nullable
    Slug of the subject who created the feedback. User email or virtual account name.
CreatedBySubjectType: TEXT, nullable
    Type of the subject who created the feedback. Common values: user, virtualaccount, agent. Do not assume the list is exhaustive.
TargetCreatedBySubjectId: TEXT, nullable
    Identifier of the subject who created the target span.
TargetCreatedBySubjectType: TEXT, nullable
    Type of the subject who created the target span.
TargetCreatedBySubjectSlug: TEXT, nullable
    Slug of the subject who created the target span.
TargetCreatedBySubjectTeams: Array(Text), nullable
    Teams of the subject who created the target span.
```

## Sample Queries

### Join traces with feedback (LEFT JOIN to include traces without feedback)

```sql
WITH f AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY "FeedbackId" ORDER BY "CreatedAt" DESC) AS rn
        FROM "{dataRoutingDestination}"."gateway_feedbacks"
        WHERE "TargetCreatedAt" > now() - INTERVAL '7 days'
    ) AS v
    WHERE rn = 1 AND "IsDeleted" = false
)
SELECT
    t."TraceId",
    t."SpanId",
    t."Timestamp",
    t."TfyGatewaySpanType",
    t."StatusCode",
    f."FeedbackId",
    f."MetricName",
    f."MetricValue",
    f."Comment",
    f."CreatedBySubjectSlug" AS "FeedbackBy",
    f."CreatedAt" AS "FeedbackUpdatedAt"
FROM "{dataRoutingDestination}"."{tracesTable}" t
LEFT JOIN f
    ON f."TargetTraceId" = t."TraceId"
    AND f."TargetSpanId" = t."SpanId"
WHERE t."Timestamp" > now() - INTERVAL '7 days'
AND t."TfyCreatedBySubjectSlug" = '<subject-slug>'
ORDER BY t."Timestamp" DESC
LIMIT 10
```

### Checklist

- [ ] Did I deduplicate by `FeedbackId` (latest `CreatedAt`) before filtering `"IsDeleted" = false`?
- [ ] When joining with traces, did I join on `"TargetTraceId"` and `"TargetSpanId"`?
- [ ] Did I use the same destination for both tables?
- [ ] Did I replace `{tracesTable}` with `tracesTable` from the session context (call `get_session_context` only if it is missing)?
