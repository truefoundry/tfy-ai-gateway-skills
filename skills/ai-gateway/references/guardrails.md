---
name: guardrails
description: Read when the user wants to see, add or change guardrails — guardrail groups and their integrations (PII, moderation, prompt injection, Bedrock, custom, etc.) or guardrail policies that decide which models, MCP servers and users they apply to.
---

**Guardrail integrations** (TrueFoundry-managed or third-party) check or rewrite model and MCP tool inputs and outputs. They live in **guardrail groups** (provider accounts of type `provider-account/guardrail-config-group`). **Guardrail policies** (type `gateway-guardrails-config`) decide when integrations run. A policy refers to an integration as `{groupName}/{integrationName}`: `pii-guardrail-group/pii-redaction` is the `pii-redaction` integration in the `pii-guardrail-group` group.

Every write also follows `write-rules.md` (steps, granting access, UI link); read it in the same batch.

## Contents
- Reading existing guardrails
- Create or update a guardrail group
- Create or update a guardrail policy

## Reading existing guardrails

**Groups and integrations:** call `list_provider_accounts` with `includeGuardrailConfigs: true` and every other `include*` flag `false`. Use `get_provider_account` for one group by `id`. If the result is saved to a file, extract only `name`, `manifest.integrations[].name`, `.type` and `.operation` with one `jq`. Response shape:

```yaml
data:
  - id: ...
    name: pii-guardrail-group
    fqn: truefoundry:guardrail-config-group:pii-guardrail-group
    provider: guardrail-config-group
    manifest:
      name: pii-guardrail-group
      type: provider-account/guardrail-config-group
      collaborators: [...]
      integrations:
        - name: pii-redaction
          type: integration/guardrail-config/tfy-pii
          operation: validate
          enforcing_strategy: enforce
          # type-specific fields
    integrations:
      - id: ...
        name: pii-redaction
        fqn: truefoundry:guardrail-config-group:pii-guardrail-group:guardrail-config:pii-redaction
        manifest: { ... }
```

**Policies:** each policy is its own named manifest. List them with `list_gateway_config_instances` and `type: gateway-guardrails-config`; each `data[]` row's `manifest` is the full policy. `get_gateway_config` returns nothing for this type, so never use it to decide which policies exist. If `list_gateway_config_instances` is not in your tool list, ask the user for the policy's exact `name` and current YAML (UI: `{controlPlaneUrl}/llm-gateway/policies/guardrails` → Edit as YAML).

## Create or update a guardrail group

### Steps

1. In one batch: `get_manifest_json_schema` with type `provider-account/guardrail-config-group` (large; see `write-rules.md` → Steps on batching), and `list_provider_accounts` as above.
2. If the group name already exists, start from that group's current `manifest`, delete `collaborators`, and append the new integration. **Applying a group replaces its whole `integrations` list: any integration you leave out is permanently deleted with its stored credentials, and policies that reference it silently lose it.**
3. Ask the user which guardrail type to add (options from the schema), and which auth method if the type has several. Collect the credentials.
4. Read that type's `config`, `auth_data` and allowed `operation` values from the schema. Fields differ per type and some types have no `auth_data`.
5. Validate, then apply (`write-rules.md` → Steps).

### Rules for integrations

- Group and integration names: 3–36 chars, lowercase letters, digits and hyphens, starting with a letter.
- `operation`: many types allow only `validate`, so read the allowed values from the schema. `mutate` guardrails run in `priority` order (lower first; default 1).
- `enforcing_strategy`: `enforce` (block on violation and on guardrail error), `enforce_but_ignore_on_error` (default: block on violation, allow on guardrail error) or `audit` (log only, never block).
- A `custom` guardrail with `target: request` can only be used in `llm_input_guardrails`, and one with `target: response` only in `llm_output_guardrails`.
- Types (`integration/guardrail-config/<type>`): openai-moderations, aws-bedrock, custom, azure-pii, azure-content-safety, azure-prompt-shield, enkrypt-ai, palo-alto-prisma-airs, fiddler, cisco-ai-defense, crowdstrike-aidr, patronus, secret-detection, code-safety-linter, sql-sanitizer, regex, tfy-pii, tfy-content-moderation, tfy-prompt-injection, tfy-metadata, cedar, opa, google-model-armor, grayswan-cygnal, cato-networks, noma-security, calypsoai, akto, trojai, hiddenlayer, fireworks, zscaler-ai-guard.

### Manifest template (aws-bedrock example)

The list field is `integrations`, not `guardrail_configs`.

```yaml
name: <unique-group-name>
type: provider-account/guardrail-config-group
integrations:
  - <every existing integration, unchanged>
  - name: <integration-name>
    type: integration/guardrail-config/aws-bedrock
    description: <description>
    operation: validate
    enforcing_strategy: enforce_but_ignore_on_error
    config:
      region: <region>
      guardrail_id: <guardrail-id>
      guardrail_version: <version or DRAFT>
    auth_data:
      type: access-key-based
      access_key_id: <secret-fqn-or-value>
      secret_access_key: <secret-fqn-or-value>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` and `list_provider_accounts`?
- [ ] If the group already exists, did I keep every existing integration?
- [ ] Did I ask the user which guardrail type and auth method to use?
- [ ] Did I take `config`, `auth_data` and `operation` for this type from the schema?

## Create or update a guardrail policy

**NEVER put a `rules:` array in a `gateway-guardrails-config` manifest.** The platform treats it as the legacy combined format and does a full replace: every guardrail policy whose name is not in the array is deleted.

### Steps

1. In one batch: `get_manifest_json_schema` with type `gateway-guardrails-config`, `list_provider_accounts` (as above) to get valid `{groupName}/{integrationName}` selectors, and `list_gateway_config_instances` with `type: gateway-guardrails-config`.
2. **Create:** `name` is the policy's unique ID — it starts with a letter and uses letters, digits and hyphens (2–62 chars). Propose a descriptive name not already listed and confirm it with the user. Applying a new name adds one policy and leaves every other policy untouched, so there is nothing to merge.
3. **Update:** start from that policy's listed `manifest`. Applying an existing `name` replaces that whole policy, so change only what was asked.
4. Build the manifest (rules below), then validate and apply (`write-rules.md` → Steps).

### Rules for policies

- `when.target` must have at least one non-empty condition (`model`, `mcpServers` or `mcpTools`); otherwise apply is rejected. Use `model: {condition: in, values: ["*"]}` for all models, or `<account-name>/<model-name>` for specific ones.
- If you target `model`, set at least one of `llm_input_guardrails` / `llm_output_guardrails`. If you target `mcpServers` or `mcpTools`, set at least one of `mcp_tool_pre_invoke_guardrails` / `mcp_tool_post_invoke_guardrails`.
- All four hook arrays are required; use `[]` for hooks you don't use.
- `mcpServers.values` accepts `<server-name>` (all tools) or `<server-name>:<tool-name>` (one tool). To target several tools of one server, use `mcpTools: {condition: in, values: [{name: <server-name>, enable_all_tools: false, enabled_tools: [<tool-1>, <tool-2>]}]}`.
- Check every selector in `mcp_tool_pre_invoke_guardrails` / `mcp_tool_post_invoke_guardrails` against `list_provider_accounts`: the backend does not validate MCP hook selectors, so a typo silently disables the guardrail.
- Subjects are `user:<email>`, `team:<name>` or `virtualaccount:<name>` (no hyphen).
- Optional `when.metadata: {<key>: <value>}` (directly under `when`, not under `target`) matches requests whose `X-TFY-METADATA` header contains those pairs.
- Optional `custom_error_message` overrides the block message and supports `{{guardrail_message}}` and `{{failed_guardrails}}`.

### Manifest template

```yaml
type: gateway-guardrails-config
name: <policy-name>
when:
  target:
    operator: or
    conditions:
      model:
        condition: in
        values: ["*"]
      mcpServers:                 # optional — omit if not targeting MCP
        condition: in
        values: [<server-name or server-name:tool-name>]
  subjects:
    operator: and
    conditions:
      in: [team:everyone]
      not_in: [<user:email or team:name>]   # optional
llm_input_guardrails: [<groupName/integrationName>]
llm_output_guardrails: []
mcp_tool_pre_invoke_guardrails: []
mcp_tool_post_invoke_guardrails: []
```

### Checklist

- [ ] Is the manifest one policy with a top-level `name`, and no `rules:` or `id:` fields?
- [ ] For a create, is the `name` new and confirmed? For an update, did I start from the policy's current manifest?
- [ ] Does `when.target` have a non-empty condition, with a matching non-empty hook for each target kind?
- [ ] Are all four hook arrays present (`[]` when unused), and does every selector exist in `list_provider_accounts`?
- [ ] Did I call `validate_manifest` before `apply_manifest`?

For more info: `search_docs` with "configure guardrails", "guardrail integrations", "guardrail rules", "truefoundry guardrails".
