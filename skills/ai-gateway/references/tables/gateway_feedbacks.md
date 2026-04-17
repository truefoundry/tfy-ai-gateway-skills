---
name: gateway_feedbacks
description: Stores user feedback (ratings, comments) linked to trace spans.
---

## CRITICAL

- Feedback is linked to traces via `TargetTraceId` and optionally to a specific span via `TargetSpanId`.
- Always include time-range filters on `"TargetCreatedAt"` to avoid full table scans.
- A feedback record can be soft-deleted — always filter with `"IsDeleted" = false` unless specifically querying deleted feedback.
- Multiple feedbacks can exist for the same trace/span (e.g. different metrics like `rating`, `accuracy`, etc.).

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
    Type of the subject who created the feedback. Possible values: user, virtualaccount.
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
    f."CreatedAt" AS "FeedbackCreatedAt"
FROM "default"."traces" t
LEFT JOIN "default"."gateway_feedbacks" f
    ON f."TargetTraceId" = t."TraceId"
    AND f."TargetSpanId" = t."SpanId"
    AND f."IsDeleted" = false
WHERE t."Timestamp" > now() - INTERVAL '7 days'
AND t."TfyCreatedBySubjectSlug" = '<subject-slug>'
ORDER BY t."Timestamp" DESC
LIMIT 10
```

### Checklist

- [ ] Did I filter `"IsDeleted" = false` to exclude soft-deleted feedback?
- [ ] When joining with traces, did I join on `"TargetTraceId"` and `"TargetSpanId"`?
- [ ] When using LEFT JOIN, did I push `"IsDeleted"` into the JOIN condition (not WHERE)?
