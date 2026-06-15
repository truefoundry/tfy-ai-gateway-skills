---
name: guardrails
description: Guardrails are used to filter and sanitize model and mcp tool calls inputs and outputs.
---

**Guardrail Config** defines when to apply **Guardrail Integrations** (either truefoundry managed or third party managed).

A tenant can have multiple guardrail groups (provider accounts). Each guardrail group can have multiple guardrail integrations. A guardrail integration is referred as `{groupName}/{integrationName}`.

## Fetching existing guardrails configurations

Use the `get_gateway_config` tool with `type: gateway-guardrails-config` to get the guardrail config manifest. The response is shaped like:

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

Use the `list_provider_accounts` tool with `includeGuardrailConfigs: true` (and other `include*` flags set to `false` to filter out other account types) to list guardrail config groups along with their integrations. The response shape is:

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
        # ...other top-level integration fields (createdBySubject, timestamps, etc.)
pagination:
  total: ...
  offset: 0
  limit: 100
```

To inspect a single guardrail config group by id, use `get_provider_account`.

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

## Creating Guardrail Config Groups (Write Flow)

A guardrail config group is a provider account that holds one or more guardrail integrations.

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `provider-account/guardrail-config-group`.

### Phase 2: Determine Guardrail Type and Auth

1. Use `ask_user_question` to ask the user which guardrail type they want to add (options come from the schema — e.g. `integration/guardrail-config/aws-bedrock`, `integration/guardrail-config/tfy-pii`, `integration/guardrail-config/azure-content-safety`, etc.).
2. If the selected type has multiple auth methods, ask the user which to use. Collect required credentials.

### Phase 3: Build and Validate

1. Build the manifest following the JSON schema strictly. Write it to a file.
2. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
3. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run to create the guardrail group.

### Manifest Structure

```yaml
name: <unique-group-name>
type: provider-account/guardrail-config-group
collaborators:
  - role_id: provider-account-manager
    subject: user:<current-user-email>  # from get_me; ask user before adding others
integrations:
  - name: <integration-name>
    type: <integration/guardrail-config/type>
    config:
      region: <region>
      guardrail_id: <guardrail-id>
      guardrail_version: <version>
    auth_data:
      type: <auth-type>
      access_key_id: <secret-fqn-or-value>
      secret_access_key: <secret-fqn-or-value>
    operation: <validate|mutate>
    description: <description>
    enforcing_strategy: <enforce|enforce_but_ignore_on_error>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I ask the user which guardrail type and auth method to use?
- [ ] Did I validate with `scripts/validate_schema.py` before dry-running?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before creating?

## Creating/Updating Guardrails Config Policy (Write Flow)

The guardrails config (type `gateway-guardrails-config`) defines **when** guardrail integrations are applied.

> **CRITICAL**: The manifest **MUST** have a top-level `name` field. This field is NOT in the JSON schema, but `apply_manifest` requires it. Without it you will get: `"Manifest does not have a name field"`. Get the `name` from the existing config.

### Phase 1: Get Schema and Existing Config

1. Call `get_manifest_json_schema` with type `gateway-guardrails-config`.
2. Call `get_gateway_config` with `type: gateway-guardrails-config` to fetch the existing config. New rules must be merged with existing ones — never replace. Note the `name` field from the existing config — you will need it.

### Phase 2: Build and Validate

1. Build the complete manifest. **You MUST include the `name` field** from the existing config at the top level. Write it to a file.
2. **Do NOT run `validate_schema.py`** — the guardrails config schema uses `extra = forbid` and rejects the `name` field, so local validation will fail. Use dry-run as the sole validation step.
3. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run to update the config.

### Manifest Structure

```yaml
name: <config-name>
type: gateway-guardrails-config
rules:
  - id: <unique-rule-id>
    when:
      target:
        operator: or
        conditions:
          model:
            values:
              - <account-name/model-name or * for all>
            condition: in
          mcpServers:
            values:
              - <mcp-server-name or serverName:toolName>
            condition: in
      subjects:
        operator: and
        conditions:
          in:
            - <user:email or team:name>
          not_in:
            - <user:email or team:name>
    llm_input_guardrails:
      - <groupName/integrationName>
    llm_output_guardrails:
      - <groupName/integrationName>
    mcp_tool_pre_invoke_guardrails:
      - <groupName/integrationName>
    mcp_tool_post_invoke_guardrails:
      - <groupName/integrationName>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I fetch the existing guardrails config and merge rules?
- [ ] Did I include the `name` field in the manifest?
- [ ] Did I ask the user for guardrail type and auth method when creating a guardrail group?
- [ ] Are guardrail integrations referenced correctly in the format `groupName/integrationName`?
- [ ] Did I skip `validate_schema.py` (it rejects the required `name` field)?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before applying?

## Searching Docs for Additional Information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_docs` to search for additional information about guardrails.

Search terms: "configure guardrails", "guardrail integrations", "guardrail rules", "truefoundry guardrails", "azure pii guardrails", "content safety guardrails"
