---
name: rate-limiting
description: Rate limiting policies control request and token throughput for Gateway traffic scoped by subject, model, and metadata.
---

**Rate Limiting Config** defines **Rate Limit Rules** that cap usage using `when` matchers (subjects, models, metadata), `limit_to`, `unit`, and optional `rate_limit_applies_per` for per-entity buckets.

## Fetching existing rate limiting configuration

Use the `gateway_get_config` tool to get the rate limiting config manifest. The response would look like this:

```yaml
result:
  manifest:
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

## Searching Docs for Additional Information

**Important**: This should be only used when other sources provide insufficient information.

Use `search_true_foundry_docs` to search for additional information about Gateway rate limits.  
Search terms: "Gateway Rate Limit Rules", "rate limiting", "token limits", "requests per minute"

## Checklist
- [ ] Did I validate the manifest using `scripts/validate_schema.py`?