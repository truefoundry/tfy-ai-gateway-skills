---
name: budget-limiting
description: Budget policies enforce spending and token budgets with optional alerts and audit mode for Gateway usage.
---

**Budget Config** defines **Budget Rules** that set limits using `when` matchers (subjects, models, metadata), `limit_to`, `unit`, optional `budget_applies_per`, optional `alerts`, and optional `audit_mode` (track overages without blocking).

## Fetching existing budget configuration

Use the `get_gateway_config` tool with `type: gateway-budget-config` to get the budget config manifest. The response is shaped like:

```yaml
id: ...
tenantName: ...
type: gateway-budget-config
manifest:
  name: budget
  type: gateway-budget-config
  rules:
    - id: ...
      unit: cost_per_day
      when:
        models:
          - openai/gpt-4o-mini
        subjects:
          - user:john@example.com
      limit_to: 0.000001
      audit_mode: false
      budget_applies_per:
        - model
      alerts:
        thresholds: [50, 75, 90, 100]
        notification_target:
          - type: slack-bot
            channels: ["#notification-test"]
            notification_channel: truefoundry:slack:test-bot:notification-channel:tfy-slack-bot
    - # more rules
createdBySubject: { ... }
createdAt: ...
updatedAt: ...
```

## Creating/Updating Budget Rules (Write Flow)

> **Note**: For complex rules, use `search_docs` for "gateway budget rules" to understand how `budget_applies_per` interacts with `when` matchers, alert thresholds, and audit mode behavior.

> **CRITICAL**: The manifest **MUST** have a top-level `name` field. This field is NOT in the JSON schema, but `apply_manifest` requires it. Without it you will get: `"Manifest does not have a name field"`. Get the `name` from the existing config.

### Phase 1: Get Schema and Existing Config

1. Call `get_manifest_json_schema` with type `gateway-budget-config`.
2. Call `get_gateway_config` with `type: gateway-budget-config` to fetch the existing config. New rules must be merged with existing ones — never replace. Note the `name` field from the existing config — you will need it.

### Phase 2: Build and Apply

Build the manifest as a **JSON object** (not YAML, include `name` from existing config) → call `validate_manifest` with type and JSON body → fix if needed → call `apply_manifest` with JSON body.

### Manifest Structure

```yaml
name: <config-name>
type: gateway-budget-config
rules:
  - id: <unique-rule-id>
    unit: <cost_per_day|cost_per_month|cost_per_hour>
    when:
      subjects:
        - <user:email or team:name or virtualaccount:name>
      models:
        - <account-name/model-name>
      metadata:
        <key>: <value>
    limit_to: <budget-limit-in-usd>
    audit_mode: <true|false>
    budget_applies_per:
      - <user|model>
    alerts:
      thresholds:
        - <percentage-value>
      notification_target:
        - type: slack-bot
          channels:
            - <channel-name>
          notification_channel: <notification-channel-fqn>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `gateway-budget-config`?
- [ ] Did I fetch the existing config and merge rules (not replace)?
- [ ] Did I include the `name` field in the manifest?
- [ ] Did I call `validate_manifest` before applying?

For more info: `search_docs` with "gateway budget rules", "budget limits", "spend limits".
