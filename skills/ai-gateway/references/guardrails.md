---
name: guardrails
description: Guardrails are used to filter and sanitize model and mcp tool calls inputs and outputs.
---

**Guardrail Config** defines when to apply **Guardrail Integrations** (either truefoundry managed or third party managed).

A tenant can have multiple guardrail groups (provider accounts). Each guardrail group can have multiple guardrail integrations. A guardrail integration is referred as `{groupName}/{integrationName}`.

## Fetching existing guardrails configurations

Use the `gateway_get_config` tool to get guardrail config manifest. The response would look like this

```yaml
result:
  manifest:
    type: gateway-guardrails-config
    rules:
      - id: pii-guardrail-rule
        when:
          ...
        llm_input_guardrails:
          - pii-guardrail-group/pii-redaction
        llm_output_guardrails: []
        mcp_tool_pre_invoke_guardrails: []
        mcp_tool_post_invoke_guardrails: []
      - # more rules
```

The `pii-guardrail-group/pii-redaction` refers to `pii-redaction` guardrail integration under `pii-guardrail-group` guardrail config group.

Use the `gateway_list_guardrails` tool to get the list of guardrail groups and their integrations. The response would look like this:

```yaml
data:
  - id: ...
    provider: guardrail-config-group
    manifest:
      name:  pii-guardrail-group
      type: provider-account/guardrail-config-group
      integrations:
        - name:  pii-redaction
          type: integration/guardrail-config/tfy-pii
          # Fields specific to integration/guardrail-config/tfy-pii
```

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

Use `search_true_foundry_docs` to search for additional information about guardrails.

Search terms: "configure guardrails", "guardrail integrations", "guardrail rules", "truefoundry guardrails", "azure pii guardrails", "content safety guardrails"
