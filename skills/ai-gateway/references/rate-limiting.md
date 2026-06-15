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

## Generating Valid Manifests for Rate Limiting

### Phase 1: Research Rate Limit Config Schema

1. Use grep in `scripts/manifest_schemas.py` to understand schema of class `RateLimitConfig` and related classes.
  ```shell
    grep -A 20 -h -E 'class RateLimit.+' scripts/manifest_schemas.py
  ```

### Phase 2: Generate Valid Rate Limit Config Manifest

1. Using the discovered schema, write a YAML manifest to a file.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat the process until the manifest is valid.

## Creating/Updating Rate Limiting Rules (Write Flow)

> **CRITICAL**: The manifest **MUST** have a top-level `name` field. This field is NOT in the JSON schema, but `apply_manifest` requires it. Without it you will get: `"Manifest does not have a name field"`. Get the `name` from the existing config.

### Phase 1: Get Schema and Existing Config

1. Call `get_manifest_json_schema` with type `gateway-rate-limiting-config`.
2. Call `get_gateway_config` with `type: gateway-rate-limiting-config` to fetch the existing config. New rules must be merged with existing ones — never replace. Note the `name` field from the existing config — you will need it.

### Phase 2: Build and Validate

1. Build the complete manifest. **You MUST include the `name` field** from the existing config at the top level. Write it to a file.
2. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
3. Call `apply_manifest` with `dryRun: true` to validate against the live platform.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` without dry-run to update the config.

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

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I fetch the existing rate limiting config before making changes?
- [ ] Did I merge new rules with existing rules (not replace)?
- [ ] Did I include the `name` field in the manifest?
- [ ] Did I validate with `scripts/validate_schema.py` before dry-running?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before applying?

## Searching Docs for Additional Information

**Important**: This should be only used when other sources provide insufficient information.

Use `search_docs` to search for additional information about Gateway rate limits.  
Search terms: "Gateway Rate Limit Rules", "rate limiting", "token limits", "requests per minute"
