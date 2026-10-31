---
name: load-balancing
description: Read only for the deprecated load-balancing policy ("Routing Config", `gateway-load-balancing-config`) — to show existing rules or migrate them. New routing goes in virtual models.
---

**Load Balancing Config** defines rules (`WeightBasedLoadBalancingRule`, `LatencyBasedLoadBalancingRule`, or `PriorityBasedLoadBalancingRule`) scoped by `LoadBalancingWhen` (subjects, models, metadata).

This feature has been deprecated in favor of **Virtual Models**. Always suggest a virtual model instead of this policy (`ai-gateway/references/virtual-models.md`).

## Fetching existing load balancing configuration

Use the `get_gateway_config` tool with `type: gateway-load-balancing-config` to get the load balancing config manifest. The response is shaped like:

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

## Migrating a rule to a virtual model

Follow the write flow in `ai-gateway/references/virtual-models.md`. Create one virtual model per rule. Copy the rule's `type` and `load_balance_targets` into the virtual model's `routing_config` (same field names), then have callers use the virtual model name instead of the original model. `when.subjects` and `when.metadata` have no virtual-model equivalent; use per-target `metadata_match` for metadata-based selection.

For more info: `search_docs` with "virtual models", "weight based routing", "model fallback".
