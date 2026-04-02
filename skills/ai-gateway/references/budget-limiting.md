---
name: budget-limiting
description: Budget policies enforce spending and token budgets with optional alerts and audit mode for Gateway usage.
---

**Budget Config** defines **Budget Rules** that set limits using `when` matchers (subjects, models, metadata), `limit_to`, `unit`, optional `budget_applies_per`, optional `alerts`, and optional `audit_mode` (track overages without blocking).

## Fetching existing budget configuration

Use the `gateway_get_config` tool to get the budget config manifest. The response would look like this:

```yaml
result:
  id: ...
  manifest:
    name: budget
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
      - # more rules
```

## Generating Valid Manifests for Budget Limiting

### Phase 1: Fetch existing budget config.

1. Gateway has a single budget config manifest. The final manifest will be union of existing + your changes.

### Phase 2: Research Budget Config Schema

1. Use grep on `scripts/manifest_schemas.py` to understand schema of class `BudgetConfig` and related classes.

    ```shell
    grep -A 20 -h -E 'class Budget.+' scripts/manifest_schemas.py
    ```

### Phase 3: You must validate your budget config rule understanding from `search_true_foundry_docs`.

### Phase 4: Generate Valid Budget Config Manifest

1. Using the discovered schema write yaml manifest to a file.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat the process until the manifest is valid.

## Searching Docs for Additional Information

Use `search_true_foundry_docs` to search for additional information about Budget Limiting feature.
Search terms: "gateway budget rules", "gateway budget alerts", "budget limits", "spend limits"

## Checklist

- [ ] Did I ensure that the final manifest is a union of existing manifest and my recommendation?
- [ ] Did I check docs to get updated understanding of budget?
- [ ] Did I use the correct order of rules in the manifest?