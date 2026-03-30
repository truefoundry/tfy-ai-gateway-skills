---
name: load-balancing
description: Legacy Gateway load balancing policy routes traffic by weight, latency, or priority; prefer Virtual Models for new setups.
---

**Load Balancing Config** defines rules (`WeightBasedLoadBalancingRule`, `LatencyBasedLoadBalancingRule`, or `PriorityBasedLoadBalancingRule`) scoped by `LoadBalancingWhen` (subjects, models, metadata). 

This feature has been deprecated in favor of **Virtual Models** (`integration/model/virtual` under `provider-account/virtual-model`). See `references/virtual-models.md` for more details.

## Fetching existing load balancing configuration

Use the `gateway_get_config` tool to get the load balancing config manifest. The response would look like this:

```yaml
result:
  id: ...
  manifest:
    rules:
      - id: ...
        type: priority-based-routing
        when:
          models:
            - ...
        load_balance_targets:
          - target: openai-account/gpt-4o
            priority: 2
            sla_cutoff:
              time_per_output_token_ms: 30000
            timeout_ms: 30000
            retry_config:
              delay: 100
              attempts: 2
              on_status_codes:
                - "429"
                - "500"
                - "504"
            fallback_candidate: true
            fallback_status_codes:
              - "429"
              - "500"
              - "502"
              # ...
          - # more targets
      # more rules
```

## Generating Valid Manifests for Virtual Models

Always suggest using **Virtual Models** instead of this policy.

### Phase 1: Research Virtual Model Schema

1. Use grep on `scripts/manifest_schemas.py` to understand schema of class `VirtualModel` and related classes.

    ```shell
    grep -A 10 -h -E 'class (VirtualModel.*|.+LoadBalancing|.*LoadBalanceTarget)' scripts/manifest_schemas.py
    ```

### Phase 2: Generate Valid Virtual Model Config Manifest

1. Using the discovered schema, write a YAML manifest to a file.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat the process until the manifest is valid.

## Searching Docs for Additional Information

**Important**: This should be only used when other sources provide insufficient information.

Use `search_true_foundry_docs` to search for additional information about Gateway load balancing and virtual models.

Search terms: "Gateway load balancing", "virtual models", "weight based routing", "latency based routing", "priority based routing", "model fallback"
