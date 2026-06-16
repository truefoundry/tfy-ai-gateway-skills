---
name: guardrails
description: Guardrails are used to filter and sanitize model and mcp tool calls inputs and outputs.
---

**Guardrail Config** defines when to apply **Guardrail Integrations** (either truefoundry managed or third party managed).

A tenant can have multiple guardrail groups (provider accounts). Each guardrail group can have multiple guardrail integrations. A guardrail integration is referred as `{groupName}/{integrationName}`.

## Contents
- Fetching existing guardrails configurations
- Creating Guardrail Config Groups (Write Flow)
- Creating/Updating Guardrails Config (Write Flow)

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

## Creating Guardrail Config Groups (Write Flow)

A guardrail config group is a provider account that holds one or more guardrail integrations.

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `provider-account/guardrail-config-group`.

### Phase 2: Determine Guardrail Type and Auth

1. Use `ask_user_question` to ask the user which guardrail type they want to add (options come from the schema — e.g. `integration/guardrail-config/aws-bedrock`, `integration/guardrail-config/tfy-pii`, `integration/guardrail-config/azure-content-safety`, etc.).
2. If the selected type has multiple auth methods, ask the user which to use. Collect required credentials.

### Phase 3: Validate and Apply

Build the manifest → write to file → `python scripts/validate_schema.py --file-path <manifest.yaml>` → `apply_manifest` with `dryRun: true` → fix if needed → `apply_manifest` without dry-run.

### Manifest Structure

```yaml
name: <unique-group-name>
type: provider-account/guardrail-config-group
collaborators:
  - role_id: provider-account-manager
    subject: user:<current-user-email>  # from get_me
  - role_id: provider-account-access
    subject: team:everyone
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

- [ ] Did I call `get_manifest_json_schema` with type `provider-account/guardrail-config-group`?
- [ ] Did I ask the user which guardrail type and auth method to use?

## Creating/Updating Guardrails Config (Write Flow)

The guardrails config (type `gateway-guardrails-config`) defines **when** guardrail integrations are applied.

> **CRITICAL**: The manifest **MUST** have a top-level `name` field. This field is NOT in the JSON schema, but `apply_manifest` requires it. Without it you will get: `"Manifest does not have a name field"`. Get the `name` from the existing config.

### Phase 1: Get Schema and Existing Config

1. Call `get_manifest_json_schema` with type `gateway-guardrails-config`.
2. Call `get_gateway_config` with `type: gateway-guardrails-config` to fetch the existing config. New rules must be merged with existing ones — never replace. Note the `name` field from the existing config — you will need it.

### Phase 2: Build and Apply

Build the manifest (include `name` from existing config) → write to file → skip `validate_schema.py` (schema uses `extra = forbid`, rejects `name`) → `apply_manifest` with `dryRun: true` → fix if needed → `apply_manifest` without dry-run.

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

- [ ] Did I call `get_manifest_json_schema` with type `gateway-guardrails-config`?
- [ ] Did I fetch the existing guardrails config and merge rules (not replace)?
- [ ] Did I include the `name` field in the manifest?
- [ ] Are guardrail integrations referenced correctly in `groupName/integrationName` format?
- [ ] Did I skip `validate_schema.py` (it rejects the required `name` field)?

For more info: `search_docs` with "configure guardrails", "guardrail integrations", "guardrail rules", "truefoundry guardrails".
