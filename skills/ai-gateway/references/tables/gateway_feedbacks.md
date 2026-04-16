---
name: gateway_feedbacks
description: Stores user feedback (ratings, comments) linked to trace spans.
---

## CRITICAL

- Feedback is linked to traces via `TargetTraceId` and optionally to a specific span via `TargetSpanId`.
- `Date` and `Hour` are **partition columns** derived from the target span's creation time (`TargetCreatedAt`), NOT the feedback creation time. Always include `"Date"` filters to avoid full table scans.
- A feedback record can be soft-deleted — always filter with `"IsDeleted" = false` unless specifically querying deleted feedback.
- Multiple feedbacks can exist for the same trace/span (e.g. different metrics like `rating`, `accuracy`, etc.).
- The `gateway_feedbacks` table exists in the `"default"` data routing destination.

## Schema

```
FeedbackId: TEXT
    Unique identifier for this feedback record.
TenantName: TEXT
    Tenant that owns this feedback record.
TracingProjectId: TEXT
    Tracing project this feedback belongs to.
CreatedAt: TIMESTAMPTZ
    When the feedback was created (UTC).
IsDeleted: BOOLEAN
    Whether this feedback has been soft-deleted. Always filter with false unless querying deletions.
TargetTraceId: TEXT
    TraceId of the trace this feedback is about. Join key to the traces table.
TargetSpanId: TEXT
    SpanId of the specific span this feedback targets within the trace.
TargetMetadata: Map(Text, Text), nullable
    Metadata from the target span at the time feedback was recorded.
TargetCreatedAt: TIMESTAMPTZ
    Creation time of the target span (not the feedback itself).
Date: TEXT
    Partition column — date string derived from TargetCreatedAt (e.g. '2026-04-16'). Always filter on this.
Hour: TEXT
    Partition column — hour string derived from TargetCreatedAt (e.g. '08').
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
    Type of the subject who created the feedback. Possible values: user, virtualaccount.
TargetCreatedBySubjectId: TEXT, nullable
    Identifier of the subject who created the target span.
TargetCreatedBySubjectType: TEXT, nullable
    Type of the subject who created the target span.
TargetCreatedBySubjectSlug: TEXT, nullable
    Slug of the subject who created the target span.
RequestedTracingProjectId: TEXT, nullable
    Tracing project ID as requested by the client.
TargetCreatedBySubjectTeams: Array(Text), nullable
    Teams of the subject who created the target span.
```

## Sample Queries

### Fetch recent feedbacks

```sql
SELECT
    "FeedbackId", "TargetTraceId", "TargetSpanId",
    "MetricName", "MetricValue", "Comment",
    "CreatedAt", "CreatedBySubjectSlug", "IsDeleted"
FROM "default"."gateway_feedbacks"
WHERE "Date" >= '2026-04-01'
AND "IsDeleted" = false
ORDER BY "CreatedAt" DESC
LIMIT 10
```

### Join traces with feedback (LEFT JOIN to include traces without feedback)

```sql
SELECT
    t."TraceId",
    MIN(t."Timestamp") AS "StartTime",
    COUNT(*) AS "SpanCount",
    array_agg(DISTINCT t."TfyGatewaySpanType") AS "SpanTypes",
    array_agg(DISTINCT t."StatusCode") AS "StatusCodes",
    f."FeedbackId",
    f."TargetSpanId",
    f."MetricName",
    f."MetricValue",
    f."Comment",
    f."CreatedBySubjectSlug" AS "FeedbackBy",
    f."CreatedAt" AS "FeedbackCreatedAt",
    f."IsDeleted" AS "FeedbackIsDeleted"
FROM "default"."traces" t
LEFT JOIN "default"."gateway_feedbacks" f
    ON f."TargetTraceId" = t."TraceId"
    AND f."Date" >= '2026-04-01'
    AND f."IsDeleted" = false
WHERE t."Timestamp" > now() - INTERVAL '7 days'
AND t."TfyCreatedBySubjectSlug" = '<subject-slug>'
GROUP BY
    t."TraceId",
    f."FeedbackId", f."TargetSpanId", f."MetricName",
    f."MetricValue", f."Comment", f."CreatedBySubjectSlug",
    f."CreatedAt", f."IsDeleted"
ORDER BY "StartTime" DESC
LIMIT 10
```

### Checklist

- [ ] Did I include `"Date"` partition filter to avoid full table scans?
- [ ] Did I filter `"IsDeleted" = false` to exclude soft-deleted feedback?
- [ ] When joining with traces, did I push `"Date"` and `"IsDeleted"` into the JOIN condition (not WHERE) for LEFT JOINs?
