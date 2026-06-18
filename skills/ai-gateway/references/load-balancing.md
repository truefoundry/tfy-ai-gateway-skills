---
name: load-balancing
description: Also known as "Routing Config". Routes traffic to one of the target models by weight, latency, or priority. Deprecated in favor of Virtual Models.
---

**Load Balancing Config** defines rules (`WeightBasedLoadBalancingRule`, `LatencyBasedLoadBalancingRule`, or `PriorityBasedLoadBalancingRule`) scoped by `LoadBalancingWhen` (subjects, models, metadata). 

This feature has been deprecated in favor of **Virtual Models**. Always suggest using **Virtual Models** instead of this policy. See `ai-gateway/references/virtual-models.md` for more details.

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

## Generating Valid Manifests for Virtual Models

Always suggest using **Virtual Models** instead of this policy.

### Phase 1: Research Virtual Model Schema

1. Use `get_manifest_json_schema` to retrieve the schema for the Virtual Model manifest type.

### Phase 2: Generate Valid Virtual Model Config Manifest

1. Using the schema, construct the manifest following required fields.
2. Call `validate_manifest` with the manifest type and JSON body to validate.
3. Repeat the process until the manifest is valid.

For more info: `search_docs` with "Gateway load balancing", "virtual models", "weight based routing", "model fallback".
