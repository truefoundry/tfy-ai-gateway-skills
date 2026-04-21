---
name: virtual-models
description: Virtual models compose multiple model integrations with weight, latency, or priority routing, fallbacks, and optional slugs.
---

**Virtual models** are pseudo models that are composed of multiple model integrations. They define `routing_config` for weight, latency, or priority based routing and fallbacks. A virtual model can also be assigned a slug to uniquely identify it.

A tenant can have multiple virtual model accounts. Each account can have multiple virtual models. A virtual model is referred as `{accountName}/{modelName}`.

## Fetching existing virtual model configurations

Use the `gateway_list_models` tool to get the list of virtual models. The response shape is similar to:

```yaml
result:
  manifest:
    type: provider-account/virtual-model
    name: my-virtual-group
    integrations:
      - name: balanced-chat
        type: integration/model/virtual
        slug: balanced-chat
        routing_config:
          type: weight-based-routing
          load_balance_targets:
            - target: openai-account/gpt-4o
              weight: 50
            # more targets
```

The identifier `openai-account/gpt-4o` refers to the `gpt-4o` integration under model account `openai-account`.

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

Use `search_true_foundry_docs` to search for additional information about virtual models.
Search terms: "virtual models", "weight based routing", "latency based routing", "priority based routing", "model load balancing", "model fallback"
