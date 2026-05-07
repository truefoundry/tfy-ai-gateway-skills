---
name: guardrails
description: Guardrails are used to filter and sanitize model and mcp tool calls inputs and outputs.
---

**Guardrail Config** defines when to apply **Guardrail Integrations** (either truefoundry managed or third party managed).

A tenant can have multiple guardrail groups (provider accounts). Each guardrail group can have multiple guardrail integrations. A guardrail integration is referred as `{groupName}/{integrationName}`.

## Fetching existing guardrails configurations

Use the `get_gateway_config` tool (from `truefoundry-mcp`) with `type: gateway-guardrails-config` to get the guardrail config manifest. The response is shaped like:

```yaml
id: ...
tenantName: ...
type: gateway-guardrails-config
manifest:
  name: guardrails-control
  type: gateway-guardrails-config
  rules:
    - id: pii-guardrail-rule
      when:
        target:
          operator: or
          conditions:
            model:
              values:
                - openai-main/o3
              condition: in
        subjects:
          operator: and
          conditions:
            in:
              - user:alice@example.com
            not_in:
              - user:bob@example.com
      llm_input_guardrails:
        - pii-guardrail-group/pii-redaction
      llm_output_guardrails: []
      mcp_tool_pre_invoke_guardrails: []
      mcp_tool_post_invoke_guardrails: []
    - # more rules
createdBySubject: { ... }
createdAt: ...
updatedAt: ...
```

The `pii-guardrail-group/pii-redaction` refers to `pii-redaction` guardrail integration under `pii-guardrail-group` guardrail config group.

Use the `list_provider_accounts` tool (from `truefoundry-mcp`) with `includeGuardrailConfigs: true` (and other `include*` flags set to `false` to filter out other account types) to list guardrail config groups along with their integrations. The response shape is:

```yaml
data:
  - id: ...
    name: pii-guardrail-group
    fqn: truefoundry:guardrail-config-group:pii-guardrail-group
    provider: guardrail-config-group
    manifest:
      name: pii-guardrail-group
      type: provider-account/guardrail-config-group
      collaborators:
        - role_id: provider-account-manager
          subject: user:alice@example.com
        - role_id: provider-account-access
          subject: team:everyone
      integrations:
        - name: pii-redaction
          type: integration/guardrail-config/tfy-pii
          operation: validate
          enforcing_strategy: enforce
          # Fields specific to integration/guardrail-config/tfy-pii
    integrations:
      - id: ...
        name: pii-redaction
        fqn: truefoundry:guardrail-config-group:pii-guardrail-group:guardrail-config:pii-redaction
        type: guardrail-config
        providerAccountFqn: truefoundry:guardrail-config-group:pii-guardrail-group
        manifest:
          name: pii-redaction
          type: integration/guardrail-config/tfy-pii
          operation: validate
          enforcing_strategy: enforce
          # Fields specific to integration/guardrail-config/tfy-pii
        # ...other top-level integration fields (createdBy, timestamps, etc.)
pagination:
  total: ...
  offset: 0
  limit: 100
```

To inspect a single guardrail config group by id, use `get_provider_account` (from `truefoundry-mcp`).

## Generating Valid Manifests for Guardrail Usage

### Phase 1: Research Guardrail Integrations

1. Use grep in `scripts/manifest_schemas.py` to find guardrail integration type of the provider or interest. If you want to find all guardrail integration types, use the following command:

    ```shell
    grep -h -E 'integration/guardrail-config/' scripts/manifest_schemas.py
    ```

2. Use grep further on `scripts/manifest_schemas.py` to read the schema for a specific type

    ```shell
    grep -B 20 -A 20 -h -E 'integration/guardrail-config/azure-prompt-shield' scripts/manifest_schemas.py
    ```

### Phase 2: Generate Valid Guardrail Integration Manifest

1. Using the discovered schemas write yaml manifest to a file.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat the process until the manifest is valid.

### Phase 3: Research Guardrail Config Schema

1. Use grep on `scripts/manifest_schemas.py` to understand schema of class `GuardrailsConfig` and related classes.

    ```shell
    grep -A 20 -h -E 'class Guardrails.+' scripts/manifest_schemas.py
    ```

### Phase 4: Generate Valid Guardrail Config Manifest

1. Using the discovered schemas write yaml manifest to a file. This should reference the guardrail integrations written in Phase 2.
2. Use `python ./scripts/validate_schema.py --file-path <path-to-manifest>` to validate the guardrail config manifest.
3. Repeat the process until the guardrail config manifest is valid.

## Searching Docs for Additional Information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_docs` to search for additional information about guardrails.

Search terms: "configure guardrails", "guardrail integrations", "guardrail rules", "truefoundry guardrails", "azure pii guardrails", "content safety guardrails"
