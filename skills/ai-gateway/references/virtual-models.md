---
name: virtual-models
description: Virtual models compose multiple model integrations with weight, latency, or priority routing, fallbacks, and optional slugs.
---

**Virtual models** are pseudo models that are composed of multiple model integrations. They define `routing_config` for weight, latency, or priority based routing and fallbacks. A virtual model can also be assigned a slug to uniquely identify it.

A tenant can have multiple virtual model accounts. Each account can have multiple virtual models. A virtual model is referred as `{accountName}/{modelName}`.

## Fetching existing virtual model configurations

Use the `list_provider_accounts` tool (from `truefoundry-mcp`) with `includeModelProviders: true` (and other `include*` flags set to `false` to filter out non-model accounts) — virtual model accounts come back alongside model accounts and are identified by `provider: virtual-model` / `manifest.type: provider-account/virtual-model`. The response shape is:

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
        # ...other top-level integration fields (createdBy, timestamps, etc.)
pagination:
  total: ...
  offset: 0
  limit: 100
```

The integration manifest under `data[].manifest.integrations` and `data[].integrations[].manifest` are equivalent for the integration spec; the latter additionally exposes `id`, `fqn`, `providerAccountFqn`, and audit fields.

The identifier `openai-account/gpt-4o` refers to the `gpt-4o` integration under model account `openai-account`.

To inspect a single virtual-model account by id, use `get_provider_account` (from `truefoundry-mcp`).

## Generating Valid Manifests for Virtual Models and Virtual Model Accounts

### Phase 1: Research Virtual Model Schema

1. Use grep on `scripts/manifest_schemas.py` to understand schema of class `VirtualModel` and related classes.

    ```shell
    grep -A 10 -h -E 'class (VirtualModel.*|.+LoadBalancing|.*LoadBalanceTarget)' scripts/manifest_schemas.py
    ```

### Phase 2: Generate Valid Virtual Model Account Manifest

1. Using the discovered schemas, write a YAML manifest to a file. This should reference the virtual model integrations written in Phase 2.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat the process until the manifest is valid.

## Searching Docs for Additional Information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_docs` to search for additional information about virtual models.
Search terms: "virtual models", "weight based routing", "latency based routing", "priority based routing", "model load balancing", "model fallback"
