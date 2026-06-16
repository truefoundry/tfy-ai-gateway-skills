---
name: virtual-models
description: Virtual models compose multiple model integrations with weight, latency, or priority routing, fallbacks, and optional slugs.
---

**Virtual models** are pseudo models that are composed of multiple model integrations. They define `routing_config` for weight, latency, or priority based routing and fallbacks. A virtual model can also be assigned a slug to uniquely identify it.

A tenant can have multiple virtual model accounts. Each account can have multiple virtual models. A virtual model is referred as `{accountName}/{modelName}`.

## Fetching existing virtual model configurations

Use the `list_provider_accounts` tool with `includeModelProviders: true` (and other `include*` flags set to `false` to filter out non-model accounts) — virtual model accounts come back alongside model accounts and are identified by `provider: virtual-model` / `manifest.type: provider-account/virtual-model`. The response shape is:

```yaml
data:
  - id: ...
    name: my-virtual-group
    fqn: truefoundry:virtual-model:my-virtual-group
    provider: virtual-model
    manifest:
      name: my-virtual-group
      type: provider-account/virtual-model
      collaborators:
        - role_id: provider-account-manager
          subject: user:alice@example.com
        - role_id: provider-account-access
          subject: team:everyone
      integrations:
        - name: balanced-chat
          type: integration/model/virtual
          model_types: [chat]
          routing_config:
            type: weight-based-routing
            load_balance_targets:
              - target: openai-account/gpt-4o
                weight: 50
              # more targets
    integrations:
      - id: ...
        name: balanced-chat
        fqn: truefoundry:virtual-model:my-virtual-group:model:balanced-chat
        type: model
        providerAccountFqn: truefoundry:virtual-model:my-virtual-group
        manifest:
          name: balanced-chat
          type: integration/model/virtual
          model_types: [chat]
          routing_config:
            type: weight-based-routing
            load_balance_targets:
              - target: openai-account/gpt-4o
                weight: 50
              # more targets
        # ...other top-level integration fields (createdBySubject, timestamps, etc.)
pagination:
  total: ...
  offset: 0
  limit: 100
```

The integration manifest under `data[].manifest.integrations` and `data[].integrations[].manifest` are equivalent for the integration spec; the latter additionally exposes `id`, `fqn`, `providerAccountFqn`, and audit fields.

The identifier `openai-account/gpt-4o` refers to the `gpt-4o` integration under model account `openai-account`.

To inspect a single virtual-model account by id, use `get_provider_account`.

## Creating Virtual Model Accounts (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `provider-account/virtual-model`.

### Phase 2: Gather Requirements

1. Collect from the user:
   - Which routing strategy to use per virtual model (`weight-based-routing`, `priority-based-routing`, or `latency-based-routing`)
   - Which target models to route to (format: `accountName/modelName`)
   - Weights, priorities, or latency SLA cutoffs depending on routing type
   - Whether targets should be fallback candidates
2. Verify target models exist by calling `list_provider_accounts` with `includeModelProviders: true` and confirming each `accountName/modelName` is present.

### Phase 3: Validate and Apply

Build the manifest → write to file → `python scripts/validate_schema.py --file-path <manifest.yaml>` → `apply_manifest` with `dryRun: true` → fix if needed → `apply_manifest` without dry-run.

### Manifest Structure

```yaml
type: provider-account/virtual-model
name: <unique-account-name>
collaborators:
  - role_id: provider-account-manager
    subject: user:<current-user-email>  # from get_me
  - role_id: provider-account-access
    subject: team:everyone
integrations:
  - name: <virtual-model-name>
    type: integration/model/virtual
    model_types:
      - <chat|completion|embedding>
    routing_config:
      type: <weight-based-routing|priority-based-routing|latency-based-routing>
      load_balance_targets:
        - target: <account-name/model-name>
          weight: <weight>
          priority: <priority>
          fallback_candidate: <true|false>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `provider-account/virtual-model`?
- [ ] Did I ask the user which routing strategy to use?
- [ ] Did I verify target models exist via `list_provider_accounts`?
- [ ] Are all target models referenced correctly in `accountName/modelName` format?

For more info: `search_docs` with "virtual models", "weight based routing", "latency based routing", "model fallback".
