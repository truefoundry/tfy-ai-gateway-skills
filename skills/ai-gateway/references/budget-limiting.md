---
name: budget-limiting
description: Legacy Budget Limiting V1 (`gateway-budget-config`) — reading V1 rules, changing or disabling them, and migrating to V2. New budgets go to `budget-limiting-v2.md`.
---

> **V1 is deprecated.** Use **Budget Limiting V2** (`budget-limiting-v2.md`) for all new budget work. This file covers V1 only for reading, disabling, and migrating existing `gateway-budget-config` rules.

**Budget Config** is one document per tenant holding an ordered `rules[]`. Each rule sets a limit using `when` matchers (subjects, models, metadata), `limit_to`, `unit`, optional `budget_applies_per`, optional `alerts`, and optional `audit_mode` (track overages without blocking).

## Fetching existing budget configuration

Call `get_gateway_config` with `type: gateway-budget-config`. The response is shaped like:

```yaml
id: ...
type: gateway-budget-config
manifest:
  name: budget                    # optional, reference only
  type: gateway-budget-config
  rules:
    - id: ...
      unit: cost_per_day
      when:
        models: [openai/gpt-4o-mini]
        subjects: [user:john@example.com]
      limit_to: 0.000001
      audit_mode: false
      budget_applies_per: [model]
      alerts:
        thresholds: [50, 75, 90, 100]
        notification_target:
          - type: slack-bot
            channels: ["#notification-test"]
            notification_channel: truefoundry:slack:test-bot:notification-channel:tfy-slack-bot
createdBySubject: { ... }
updatedAt: ...
```

**Usage:** no tool reads V1 usage; say so and never estimate it. `get_budget_usage` reads V2 budgets only (`budget-limiting-v2.md`).

## Resolving budget scope

**1. Target (`when`)**

| User mentions | `when` field |
|---|---|
| a user / email | `subjects: [user:email]` |
| a team | `subjects: [team:name]` |
| a VA / virtual account | `subjects: [virtualaccount:name]` |
| a metadata term (tenant, app, feature…) | `metadata: { key: value }` |

A term that isn't a user, team or VA is a metadata key. Don't ask the user for the key name: discover it from live data (see `observability.md`, `gateway_model_metrics`).

**2. Bucketing (`budget_applies_per`)** — omitted means all matching requests share one budget pool (two users in `subjects` share one combined budget). Only one value per rule: `user`, `model`, `virtualaccount`, or `metadata.<key>`.

Example: "per tenant budget for tfy-ai-features VA" → `subjects: [virtualaccount:tfy-ai-features]`, `budget_applies_per: [metadata.<tenant-key>]`.

## Rule ordering

Rules are evaluated top to bottom. The **first matching rule** controls allow/block, but cost is tracked against **all matching rules**. Place higher-priority rules (overrides, exceptions) above general defaults.

## Changing V1 rules (write flow)

Read `write-rules.md` in the same batch. This is a legacy singleton: the whole `rules[]` is replaced on every apply.

1. In one batch: `get_manifest_json_schema` with type `gateway-budget-config`, and `get_gateway_config` with `type: gateway-budget-config`.
2. **Always merge into the full `rules[]` from a `get_gateway_config` result that is still in the conversation. If it isn't, call `get_gateway_config` again right before building. Never rebuild `rules[]` from memory or a summary** — a missing rule is deleted.
3. Position the rule: review existing rules for overlapping scope and insert the new rule above any broader rule it should override (see Rule ordering).
4. Build the manifest as JSON. Top-level `name` is optional for this type and used only for reference. Keep the existing config's `name` if it has one; if there is no existing config, use `budget`.
5. `validate_manifest`, wait for `valid: true`, then `apply_manifest` (separate batches). `validate_manifest` checks the schema only; the one-value `budget_applies_per` and one-`notification_target` limits are enforced by `apply_manifest`, so check them yourself first.

### Manifest structure

```yaml
name: <existing-name-if-any>
type: gateway-budget-config
rules:
  - id: <unique-rule-id>
    unit: <cost_per_day|cost_per_week|cost_per_month|cost_per_quarter|tokens_per_day|tokens_per_month>
    when:                       # required in V1; when: {} matches all traffic
      subjects: [<user:email | team:name | virtualaccount:name>]
      models: [<account-name/model-name>]
      metadata: { <key>: <value> }
    limit_to: <budget-limit-in-usd-or-tokens>
    audit_mode: <true|false>
    budget_applies_per: [<user|model|virtualaccount|metadata.key>]   # max 1
    alerts:
      thresholds: [<percentage>]          # 0-100, default [75, 90, 95, 100]
      notification_target:                # at most ONE entry in V1
        - type: slack-bot                 # email | slack-webhook | slack-bot | pagerduty | ms-teams-webhook
          channels: [<channel-name>]
          notification_channel: <notification-channel-fqn>
```

Token units are enforced but have no V2 equivalent.

## Disabling V1 rules

V1 rules have no disable flag. To stop one rule: fetch with `get_gateway_config` → remove that rule from `rules[]` (here removal is intended; keep every other rule unchanged) → `validate_manifest` → `apply_manifest`. To keep tracking without blocking, set `audit_mode: true` instead. Only when every rule has been migrated, delete the whole config with `delete_manifest` and manifest `{type: gateway-budget-config}`. This removes all V1 rules, so confirm with the user first.

## Checklist

- [ ] Is this V1 work (reading, changing, disabling or migrating existing rules)? Otherwise use `budget-limiting-v2.md`.
- [ ] Merged into the full `rules[]` from a current `get_gateway_config` result?
- [ ] Positioned the rule against overlapping rules, not just appended?
- [ ] Kept the existing `name`, if any?
- [ ] At most one `budget_applies_per` value and one `notification_target`?
- [ ] `validate_manifest` returned `valid: true` before `apply_manifest`?
