---
name: gateway_feedbacks
description: Stores user feedback (ratings, comments) linked to trace spans.
---

## CRITICAL

- Feedback targets one span: `TargetTraceId` and `TargetSpanId` are always set. It is usually the request's head span (sent with the `x-tfy-feedback-target-id` response header), but feedback given with an explicit trace and span ID can target any span. You see feedback on the requests your traces access rules let you see.
- Partitioned by `Date` and `Hour`, taken from `TargetCreatedAt` (the target span's time, not the feedback's). Always filter a `"Date"` literal range and a `"TargetCreatedAt"` range; the same `"Date"` range prunes the traces table in a join.
- Feedback rows are versioned: an update or delete writes a new row with the same `FeedbackId`. Always keep only the latest row per `FeedbackId` (`ROW_NUMBER() OVER (PARTITION BY "FeedbackId" ORDER BY "CreatedAt" DESC) = 1`), then filter `"IsDeleted" = false`. Never filter `IsDeleted` before deduplicating — counts and averages are otherwise wrong with no error.
- `MetricName` is `rating` (1–5) for feedback from the Gateway feedback API. Several feedbacks can exist for one span.
- Query feedback in the same destination as the traces it targets; pick it as described in `observability.md`.

## Schema

```
FeedbackId: TEXT
    Identifier of the feedback. Shared by all versions of the same feedback.
TenantName: TEXT
    Tenant that owns this feedback record.
TracingProjectId: TEXT
    Always ''.
RequestedTracingProjectId: TEXT, nullable
    Tracing project the sender asked for.
CreatedAt: TIMESTAMPTZ
    When this version of the feedback was written (UTC).
IsDeleted: BOOLEAN
    Whether this version marks the feedback as deleted. Only meaningful on the latest version per FeedbackId.
TargetTraceId: TEXT
    TraceId of the target span. Join key to the traces table.
TargetSpanId: TEXT
    SpanId of the target span. Join key to the traces table.
TargetMetadata: Map(Text, Text), nullable
    Request metadata of the target span when the feedback was recorded.
TargetCreatedAt: TIMESTAMPTZ
    Creation time of the target span (not the feedback). Use for time-range filtering.
Date: TEXT
    Partition: UTC date 'YYYY-MM-DD' of TargetCreatedAt.
Hour: TEXT
    Partition: UTC hour 'HH' of TargetCreatedAt.
Metadata: Map(Text, Text), nullable
    Metadata attached to the feedback itself.
Comment: TEXT, nullable
    Free-text comment provided with the feedback.
MetricName: TEXT
    Name of the feedback metric, e.g. 'rating'.
MetricValue: DOUBLE PRECISION
    Numeric value of the feedback metric.
CreatedBySubjectSlug: TEXT
    Who gave the feedback: user email or virtual account name.
CreatedBySubjectType: TEXT
    Type of that subject, e.g. user, virtualaccount. Not exhaustive.
TargetCreatedBySubjectId: TEXT, nullable
    Identifier of the caller of the target request.
TargetCreatedBySubjectType: TEXT, nullable
    Type of the caller of the target request.
TargetCreatedBySubjectSlug: TEXT, nullable
    Slug of the caller of the target request.
TargetCreatedBySubjectTeams: Array(Text), nullable
    Teams of the caller of the target request.
```

## Sample Queries

### Join traces with feedback (LEFT JOIN to include traces without feedback)

```sql
WITH f AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY "FeedbackId" ORDER BY "CreatedAt" DESC) AS rn
        FROM "<destination>"."gateway_feedbacks"
        WHERE "Date" >= '2026-10-20' AND "TargetCreatedAt" >= TIMESTAMP '2026-10-20T00:00:00Z'
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
FROM "<destination>"."<tracesTable>" t
LEFT JOIN f
    ON f."TargetTraceId" = t."TraceId"
    AND f."TargetSpanId" = t."SpanId"
WHERE t."Date" >= '2026-10-20' AND t."Timestamp" >= TIMESTAMP '2026-10-20T00:00:00Z'
AND t."TfyCreatedBySubjectSlug" = '<subject-slug>'
AND COALESCE(NULLIF(t."TfyParentSpanId", ''), t."ParentSpanId") = ''
ORDER BY t."Timestamp" DESC
LIMIT 10
```

### Checklist

- [ ] Did I deduplicate by `FeedbackId` (latest `CreatedAt`) before filtering `"IsDeleted" = false`?
- [ ] When joining with traces, did I join on `"TargetTraceId"` and `"TargetSpanId"`?
- [ ] Did I filter `"Date"` on both tables, and use the same destination for both?
- [ ] Did I replace `<tracesTable>` with `tracesTable` from the session context?
