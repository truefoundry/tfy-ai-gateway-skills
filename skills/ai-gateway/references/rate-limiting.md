---
name: rate-limiting
description: Legacy Rate Limiting V1 (`gateway-rate-limiting-config`) — reading, changing or removing existing V1 rules and migrating them to V2. New rate limits go to `rate-limiting-v2.md`.
---

> **V1 is deprecated.** New rate limits belong in Rate Limiting V2 (`tenant-rate-limit-config/model` for LLM traffic, `tenant-rate-limit-config/mcp` for MCP tool calls): read `rate-limiting-v2.md`. Use this file to read V1 rules, change or remove them, and migrate them. Add a new V1 rule only if the user explicitly asks for V1.

**Rate Limiting Config** is one document per tenant holding an ordered `rules[]`. Each rule caps usage with `when` matchers (subjects, models, metadata), `limit_to`, `unit`, and optional `rate_limit_applies_per` for per-entity buckets.

## Reading V1 rules

Call `get_gateway_config` with `type: gateway-rate-limiting-config`. The response is shaped like:

```yaml
id: ...
type: gateway-rate-limiting-config
manifest:
  name: platform-rate-limits      # optional, reference only
  type: gateway-rate-limiting-config
  rules:
    - id: per-user-rpm
      when:
        subjects: []
        models: [my-openai/gpt-4o]
        metadata: {}
      limit_to: 100
      unit: requests_per_minute
      rate_limit_applies_per: [user]
createdBySubject: { ... }
updatedAt: ...
```

A null or empty result means there are no V1 rules, not that there are no rate limits: V2 limits come from `list_gateway_config_instances` (see `rate-limiting-v2.md`). Report both.

## Rule semantics

**Target (`when`)** — `subjects`, `models` and `metadata` are ANDed.

| User mentions | `when` field |
|---|---|
| a user / email | `subjects: [user:email]` |
| a team | `subjects: [team:name]` |
| a VA / virtual account | `subjects: [virtualaccount:name]` |
| a metadata term (tenant, app, feature…) | `metadata: { key: value }` |

A term that isn't a user, team or VA is a metadata key. Don't ask the user for the key name: discover it from live data (the metadata keys query in `observability.md`).

**Bucketing (`rate_limit_applies_per`)** — omitted means all matching requests share one pool. At most 2 values per rule (e.g. `['user', 'model']`): `user`, `model`, `virtualaccount`, or `metadata.<key>`.

**Ordering** — Rules are evaluated top to bottom. The first matching rule decides block or allow, but **every** matching rule counts the request. So a broad shared rule lower down can fill up from traffic that an earlier rule allowed, and then 429 everyone else whose first match it is. Put overrides above defaults, and give generic rules `rate_limit_applies_per` (e.g. `['user','virtualaccount']`) so callers don't share one bucket.

V1 is checked before V2: if a V1 rule blocks, V2 is not consulted.

## Changing V1 rules (write flow)

Read `write-rules.md` in the same batch. This is a legacy singleton: the whole `rules[]` is replaced on every apply.

1. In one batch: `get_manifest_json_schema` with type `gateway-rate-limiting-config`, and `get_gateway_config` with `type: gateway-rate-limiting-config`.
2. **Always merge into the full `rules[]` from a `get_gateway_config` result that is still in the conversation. If it isn't, call `get_gateway_config` again right before building. Never rebuild `rules[]` from memory or a summary** — a missing rule is deleted.
3. Position the rule: review existing rules for overlapping scope and insert the new rule above any broader rule it should override (see Ordering).
4. Build the manifest as JSON. Top-level `name` is optional for this type and used only for reference. Keep the existing config's `name` if it has one; if there is no existing config, use `rate-limits`.
5. `validate_manifest`, wait for `valid: true`, then `apply_manifest` (separate batches). `validate_manifest` checks the schema only; the 2-value cap and allowed `rate_limit_applies_per` values are enforced by `apply_manifest`, so check them yourself first.
6. Link `{controlPlaneUrl}/llm-gateway/policies/rate-limiting`.

### Manifest structure

```yaml
name: <existing-name-if-any>
type: gateway-rate-limiting-config
rules:
  - id: <unique-rule-id>
    unit: <requests_per_minute|requests_per_hour|requests_per_day|tokens_per_minute|tokens_per_hour|tokens_per_day>
    when:                      # required; when: {} matches all traffic
      subjects: [<user:email | team:name | virtualaccount:name>]
      models: [<account-name/model-name>]
      metadata: { <key>: <value> }
    limit_to: <positive-integer>
    rate_limit_applies_per: [<user|model|virtualaccount|metadata.key>]   # max 2
```

## Disabling V1 rules

V1 rules have no disable flag and no audit mode. To stop one rule: fetch with `get_gateway_config` → remove that rule from `rules[]` (here removal is intended; keep every other rule unchanged) → `validate_manifest` → `apply_manifest`. Only when every rule has been migrated, delete the whole config with `delete_manifest` and manifest `{type: gateway-rate-limiting-config}`. This removes all V1 rules, so confirm with the user first.

## Migrating V1 rules to V2

Migration is: build and apply one V2 manifest per V1 rule (`rate-limiting-v2.md`), then remove the V1 rules.

1. Fetch V1 with `get_gateway_config` and map each rule to a `tenant-rate-limit-config/model` manifest:
   - `id` → `name`. V2 names allow only letters, digits and hyphens (start with a letter, 2–62 chars); rename ids containing `.`, `_` or `{}`.
   - `subjects: [user:a, team:t, virtualaccount:v]` → `when.subjects.users.in: [a]`, `teams.in: [t]`, `virtual_accounts.in: [v]`
   - `models: [m]` → `when.models: { in: [m] }`; `metadata: { k: v }` → `when.metadata: { k: { in: [v] } }`
   - `limit_to` + `unit` → `limits: { <unit>: <limit_to> }` (same unit names)
   - `rate_limit_applies_per`: omitted → `applies_to: { type: aggregate }`; `user` / `model` / `virtualaccount` → `per-user` / `per-model` / `per-virtual-account`; `metadata.<key>` → `{ type: metadata, metadata: <key> }`. V2 has exactly one partition: a two-value V1 rule has no direct equivalent, so tell the user and agree on one.
2. V2 has no ordering. If a V1 rule was an override above a default, exclude that group from the default with `not_in`, or use per-entity `overrides` inside `applies_to`.
3. Suggest `mode: audit` first, then `enforce` once usage looks right.
4. Once the V2 limits are applied (and, if in audit, the user is happy with usage), remove the migrated V1 rules (see Disabling V1 rules). Until then both run: V1 is checked first and both count the traffic they match.

## Checklist

- [ ] Is this really V1 work (reading, changing, removing or migrating existing rules)? Otherwise use `rate-limiting-v2.md`.
- [ ] Merged into the full `rules[]` from a current `get_gateway_config` result?
- [ ] Positioned the rule against overlapping rules, not just appended?
- [ ] Kept the existing `name`, if any?
- [ ] `validate_manifest` returned `valid: true` before `apply_manifest`?
