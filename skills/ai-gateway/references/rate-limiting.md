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

## Resolving rate limit scope

A rate limit rule has two dimensions — resolve each independently:

**1. Target — who does the rule apply to? (`when` field)**

| User mentions | `when` field |
|---|---|
| a user / email | `subjects: [user:email]` |
| a team | `subjects: [team:name]` |
| a VA / virtual account | `subjects: [virtualaccount:name]` |
| a metadata term (tenant, app, feature, etc.) | `metadata: { key: value }` |

`subjects`, `models`, and `metadata` in a `when` block are **ANDed** — a request must match all specified conditions.

If the term does not match user, team, or VA — it is a metadata key. **Do not ask the user for the key name.** Read `ai-gateway/references/observability.md` and query `gateway_model_metrics` to discover metadata keys from live data, scoped to whatever the user specified.

**2. Bucketing — how is the limit counted? (`rate_limit_applies_per` field)**

By default, all matching requests share a **single rate limit pool**. Use `rate_limit_applies_per` to create **separate limits per entity** instead. Maximum **2 values** per rule — you can combine (e.g., `['user', 'model']`).

| Value | Effect |
|---|---|
| *(omitted)* | all matched subjects/models share one rate limit pool |
| `user` | separate limit per user |
| `model` | separate limit per model |
| `virtualaccount` | separate limit per VA |
| `metadata.<key>` | separate limit per unique metadata value |

If the bucketing term does not match user, model, or VA — it is a metadata key. **Do not ask the user for the key name.** Discover it from live data as described above.

A user query can specify both dimensions. Example: "per user rate limit on gpt-4o" → target is `when: { models: [openai/gpt-4o] }`, bucketing is `rate_limit_applies_per: ['user']`.

## Rule ordering

Rules are evaluated top to bottom. **Only the first matching rule is applied** — subsequent rules are ignored. Place higher-priority rules (overrides, exceptions) above general defaults.

## Creating/Updating Rate Limiting Rules (Write Flow)

> **CRITICAL**: The manifest **MUST** have a top-level `name` field. This field is NOT in the JSON schema, but `apply_manifest` requires it. Without it you will get: `"Manifest does not have a name field"`. Get the `name` from the existing config.

### Phase 1: Get Schema and Existing Config

1. Call `get_manifest_json_schema` with type `gateway-rate-limiting-config`.
2. Call `get_gateway_config` with `type: gateway-rate-limiting-config` to fetch the existing config. New rules must be merged with existing ones — never replace. Note the `name` field from the existing config — you will need it.

### Phase 2: Position the Rule

Call `search_docs` for "rate limiting rule ordering" to understand how rule order works (only the first matching rule applies). Review existing rules for overlapping scope before deciding where to insert the new rule.

### Phase 3: Build and Apply

Build the manifest as JSON (include `name` from existing config) → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Manifest Structure

```yaml
name: <config-name>
type: gateway-rate-limiting-config
rules:
  - id: <unique-rule-id>
    unit: <requests_per_minute|requests_per_hour|requests_per_day|tokens_per_minute|tokens_per_hour|tokens_per_day>
    when:
      subjects:
        - <user:email or team:name or virtualaccount:name>
      models:
        - <account-name/model-name>
      metadata:
        <key>: <value>
    limit_to: <numeric-limit>
    rate_limit_applies_per:
      - <user|model|virtualaccount|metadata.key>  # max 2 values
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `gateway-rate-limiting-config`?
- [ ] Did I fetch the existing config and merge rules (not replace)?
- [ ] Did I check existing rules for overlapping scope and position the new rule correctly (not just append at the end)?
- [ ] Did I include the `name` field in the manifest?
- [ ] Did I call `validate_manifest` before applying?

For more info: `search_docs` with "Gateway Rate Limit Rules", "rate limiting", "token limits".
