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

## Generating Valid Manifests for Budget Limiting

### Phase 1: Fetch existing budget config.

1. Gateway has a single budget config manifest. The final manifest will be union of existing + your changes.

### Phase 2: Research Budget Config Schema

1. Use grep on `scripts/manifest_schemas.py` to understand schema of class `BudgetConfig` and related classes.

    ```shell
    grep -A 20 -h -E 'class Budget.+' scripts/manifest_schemas.py
    ```

### Phase 3: Validate your understanding of budget config rules

1. Use `search_docs` for "gateway budget rules" to find the canonical doc page.
2. Fetch the doc page to understand the semantic rules (e.g. how `budget_applies_per` interacts with `when` matchers, alert thresholds, audit mode behavior). The schema gives you structure; the docs give you correctness.

### Phase 4: Generate Valid Budget Config Manifest

1. Using the discovered schema write yaml manifest to a file.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat the process until the manifest is valid.

## Creating/Updating Budget Rules (Write Flow)

> **CRITICAL**: The manifest **MUST** have a top-level `name` field. This field is NOT in the JSON schema, but `apply_manifest` requires it. Without it you will get: `"Manifest does not have a name field"`. Get the `name` from the existing config.

### Phase 1: Get Schema and Existing Config

1. Call `get_manifest_json_schema` with type `gateway-budget-config`.
2. Call `get_gateway_config` with `type: gateway-budget-config` to fetch the existing config. New rules must be merged with existing ones — never replace. Note the `name` field from the existing config — you will need it.

### Phase 2: Build and Validate

1. Build the complete manifest. **You MUST include the `name` field** from the existing config at the top level. Write it to a file.
2. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
3. Call `apply_manifest` with `dryRun: true` to validate against the live platform.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` without dry-run to update the config.

### Manifest Structure

```yaml
name: <config-name>
type: gateway-budget-config
rules:
  - id: <unique-rule-id>
    unit: <cost_per_day|cost_per_month|cost_per_hour>
    when:
      subjects:
        - <user:email or team:name>
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

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I fetch the existing budget config before making changes?
- [ ] Did I merge new rules with existing rules (not replace)?
- [ ] Did I include the `name` field in the manifest?
- [ ] Did I verify that subjects in the new rule are not already matched by earlier rules?
- [ ] Did I validate with `scripts/validate_schema.py` before dry-running?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before applying?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about budget config.
Search terms: "gateway budget rules", "gateway budget alerts", "budget limits", "spend limits"
