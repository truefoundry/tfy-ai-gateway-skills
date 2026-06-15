---
name: rate-limiting
description: Rate limiting policies control request and token throughput for Gateway traffic scoped by subject, model, and metadata.
---

**Rate Limiting Config** defines **Rate Limit Rules** that cap usage using `when` matchers (subjects, models, metadata), `limit_to`, `unit`, and optional `rate_limit_applies_per` for per-entity buckets.

## Fetching existing rate limiting configuration

Use the `get_gateway_config` tool with `type: gateway-rate-limiting-config` to get the rate limiting config manifest. The response is shaped like:

```yaml
id: ...
tenantName: ...
type: gateway-rate-limiting-config
manifest:
  name: platform-rate-limits
  type: gateway-rate-limiting-config
  rules:
    - id: per-user-rpm
      when:
        subjects: []
        models:
          - my-openai/gpt-4o
        metadata: {}
      limit_to: 100
      unit: requests_per_minute
      rate_limit_applies_per:
        - user
    - # more rules
createdBySubject: { ... }
createdAt: ...
updatedAt: ...
```

## Creating/Updating Rate Limiting Rules (Write Flow)

> **CRITICAL**: The manifest **MUST** have a top-level `name` field. This field is NOT in the JSON schema, but `apply_manifest` requires it. Without it you will get: `"Manifest does not have a name field"`. Get the `name` from the existing config.

### Phase 1: Get Schema and Existing Config

1. Call `get_manifest_json_schema` with type `gateway-rate-limiting-config`.
2. Call `get_gateway_config` with `type: gateway-rate-limiting-config` to fetch the existing config. New rules must be merged with existing ones — never replace. Note the `name` field from the existing config — you will need it.

### Phase 2: Build and Validate

1. Build the complete manifest. **You MUST include the `name` field** from the existing config at the top level. Write it to a file.
2. **Do NOT run `validate_schema.py`** — the rate-limiting schema uses `extra = forbid` and rejects the `name` field, so local validation will fail. Use dry-run as the sole validation step.
3. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run to update the config.

### Manifest Structure

```yaml
name: <config-name>
type: gateway-rate-limiting-config
rules:
  - id: <unique-rule-id>
    unit: <requests_per_minute|requests_per_hour|requests_per_day|tokens_per_minute|tokens_per_hour|tokens_per_day>
    when:
      subjects:
        - <user:email or team:name>
      models:
        - <account-name/model-name>
      metadata:
        <key>: <value>
    limit_to: <numeric-limit>
    rate_limit_applies_per:
      - <user|model|metadata.key>
```

### Checklist

- [ ] Called `get_manifest_json_schema` with type `gateway-rate-limiting-config`?
- [ ] Fetched existing config and merged rules (not replaced)?
- [ ] Included the `name` field from existing config?
- [ ] Skipped `validate_schema.py` (it rejects `name`)?
- [ ] Dry-run with `apply_manifest` (dryRun: true) passed?
- [ ] Applied with `apply_manifest` (direct tool call, not sandbox)?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about Gateway rate limits.
Search terms: "Gateway Rate Limit Rules", "rate limiting", "token limits", "requests per minute"
