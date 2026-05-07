---
name: load-balancing
description: Also known as "Routing Config". Routes traffic to one of the target models by weight, latency, or priority. Deprecated in favor of Virtual Models.
---

**Load Balancing Config** defines rules (`WeightBasedLoadBalancingRule`, `LatencyBasedLoadBalancingRule`, or `PriorityBasedLoadBalancingRule`) scoped by `LoadBalancingWhen` (subjects, models, metadata). 

This feature has been deprecated in favor of **Virtual Models**. Always suggest using **Virtual Models** instead of this policy. See `references/virtual-models.md` for more details.

## Fetching existing load balancing configuration

Use the `get_gateway_config` tool (from `truefoundry-mcp`) with `type: gateway-load-balancing-config` to get the load balancing config manifest. The response is shaped like:

```yaml
id: ...
tenantName: ...
type: gateway-load-balancing-config
manifest:
  name: routing-config
  type: gateway-load-balancing-config
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
createdBySubject: { ... }
createdAt: ...
updatedAt: ...
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

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_docs` to search for additional information about Gateway load balancing and virtual models.

Search terms: "Gateway load balancing", "virtual models", "weight based routing", "latency based routing", "priority based routing", "model fallback"
