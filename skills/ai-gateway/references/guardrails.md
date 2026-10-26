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

Each guardrails policy (type `gateway-guardrails-config`) is its own named manifest. The available tools cannot list existing policies: `get_gateway_config` returns nothing for `gateway-guardrails-config`, so never use it to decide which policies exist. To see or change an existing policy, ask the user for its exact `name` and current YAML (UI: `{controlPlaneUrl}/llm-gateway/policies/guardrails` → Edit as YAML).

A policy references guardrail integrations as `{groupName}/{integrationName}`: `pii-guardrail-group/pii-redaction` is the `pii-redaction` integration in the `pii-guardrail-group` guardrail config group.

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

### Phase 1: Get Schema and Existing Groups

1. Call `get_manifest_json_schema` with type `provider-account/guardrail-config-group`.
2. Call `list_provider_accounts` with `includeGuardrailConfigs: true` (other `include*` flags `false`). If the group name already exists, start from that group's current `manifest` and append the new integration.

> **CRITICAL**: Applying a group replaces its whole `integrations` list. Any integration you leave out is permanently deleted, including its stored credentials, and policies that reference it silently lose it.

### Phase 2: Determine Guardrail Type and Auth

1. Use `ask_user_question` to ask the user which guardrail type they want to add (options come from the schema — e.g. `integration/guardrail-config/aws-bedrock`, `integration/guardrail-config/tfy-pii`, `integration/guardrail-config/azure-content-safety`, etc.).
2. If the selected type has multiple auth methods, ask the user which to use. Collect required credentials.

### Phase 3: Validate and Apply

Build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Manifest Structure

> **CRITICAL**: The field for guardrail entries is `integrations` — NOT `guardrail_configs`. The agent frequently gets this wrong.

```yaml
name: <unique-group-name>
type: provider-account/guardrail-config-group
collaborators:
  - role_id: provider-account-manager
    subject: user:<current-user-email>  # from the session context
  - role_id: provider-account-access
    subject: team:everyone
integrations:                             # NOT guardrail_configs
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
- [ ] If the group already exists, did I keep every existing integration in `integrations`?
- [ ] Did I ask the user which guardrail type and auth method to use?

## Creating/Updating Guardrails Config (Write Flow)

A guardrails policy (type `gateway-guardrails-config`) defines **when** guardrail integrations are applied. Each policy is one manifest with a required top-level `name`.

> **CRITICAL**: NEVER put a `rules:` array in a `gateway-guardrails-config` manifest. The platform treats it as the legacy combined format and does a full replace: every guardrails policy whose name is not in the array is deleted.

### Phase 1: Get Schema and Decide Create or Update

1. Call `get_manifest_json_schema` with type `gateway-guardrails-config`.
2. **Create:** pick a new unique `name`. Applying it adds one policy and leaves every other policy untouched, so there is nothing to merge.
3. **Update:** ask the user for the policy's exact `name` and its current YAML (see "Fetching existing guardrails configurations"). Applying under an existing `name` replaces that whole policy, so start from its current YAML and change only what was asked.

### Phase 2: Build and Apply

Build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Manifest Structure

> **CRITICAL**: Every policy needs `when.target` — the platform rejects a policy without one. Use `model` with `values: ["*"]` to apply to all models. All four hook arrays are required; use `[]` for hooks you don't use. Subject types are: `user:<email>`, `team:<name>`, `virtualaccount:<name>`.

```yaml
type: gateway-guardrails-config
name: <policy-name>
when:
  target:                                  # REQUIRED
    operator: or
    conditions:
      model:
        values:
          - "*"                            # all models, or specific: account-name/model-name
        condition: in
      mcpServers:                          # optional — omit if not targeting MCP
        values:
          - <mcp-server-name or serverName:toolName>
        condition: in
  subjects:
    operator: and
    conditions:
      in:
        - <user:email or team:name or virtualaccount:name>
      not_in:
        - <user:email or team:name>
llm_input_guardrails:
  - <groupName/integrationName>
llm_output_guardrails: []
mcp_tool_pre_invoke_guardrails: []
mcp_tool_post_invoke_guardrails: []
custom_error_message: <optional>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `gateway-guardrails-config`?
- [ ] Is the manifest one policy with a top-level `name`, and no `rules:` or `id:` fields?
- [ ] For an update, did I start from the policy's current YAML from the user?
- [ ] Does the policy have a `when.target` with at least one condition (`model` or `mcpServers`)?
- [ ] Are all four hook arrays present (`[]` when unused)?
- [ ] Are guardrail integrations referenced correctly in `groupName/integrationName` format?
- [ ] Did I use `virtualaccount` (no hyphen) for VA subjects?
- [ ] Did I call `validate_manifest` before applying?

For more info: `search_docs` with "configure guardrails", "guardrail integrations", "guardrail rules", "truefoundry guardrails".
