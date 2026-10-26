---
name: virtual-models
description: Read to list, create or change virtual models — one model name that routes across several model integrations by weight, latency, priority or request complexity, with fallbacks, retries and optional slugs.
---

A **virtual model** routes each request to one of several real model integrations. Virtual models live in a **virtual model group** (`provider-account/virtual-model`); each virtual model is an integration of type `integration/model/virtual`, addressed as `{groupName}/{modelName}` or by its `slug`.

## List existing virtual models

Call `list_provider_accounts` with `includeModelProviders: true` and `includeCustomEndpoints: true`, and `includeInfraProviders`, `includeMCPProviders`, `includeGuardrailConfigs` set to `false`. Omit `limit` to get every account. Virtual model groups are the items with `provider: virtual-model`; their `manifest.integrations[]` hold `name`, `model_types`, `slug` and `routing_config`. The other items are the real models you can route to: `data[].integrations[].manifest` has their `name` and `model_types`. For one group by id, use `get_provider_account`.

## Create or update a virtual model

Read this file and `write-rules.md` together, and follow the write steps there.

### Inputs to collect

- Group name, and create a new group or update an existing one.
- Per virtual model: name, `model_types`, routing strategy, targets.
- Per target: `weight` (weight-based), `priority` plus optional `sla_cutoff` (priority-based), nothing extra (latency-based), or `tier` (complexity-based). Whether each target is a fallback candidate.

### Step 1 — one parallel batch

- `list_provider_accounts` (flags as above): existing groups and the real models you can target.
- `get_manifest_json_schema` with type `provider-account/virtual-model`, in its own batch because it is large. Reuse it if it is still in the conversation; otherwise call it again.

If a matching group or virtual model exists, ask whether to update it or create a new one with a different name. If that answer is no longer in the conversation, ask again before applying.

### Step 2 — check the targets

Reuse the Step 1 `list_provider_accounts` response if it is still in the conversation; otherwise call it again. For each target:

- It exists as `accountName/modelName` and is a real model integration, not another virtual model; apply rejects virtual-model targets.
- Its `manifest.model_types` contains every `model_type` set on the virtual model. `apply_manifest` rejects the virtual model otherwise, and `validate_manifest` does not check this.
- If the virtual model's `model_types` includes `text_to_speech`, `audio_transcription` or `audio_translation`, all targets come from accounts of the same provider (for example all `openai`); apply rejects mixed providers.

### Step 3 — build, validate, apply

Build the manifest from the template. Validate with `validate_manifest`; once it returns `valid: true`, apply with `apply_manifest` in a separate call. Updating a group sends its whole `integrations` list: keep every existing virtual model, and delete `collaborators` from the fetched manifest (`write-rules.md` → Collaborators).

### Field rules

- Group `name`: 3–64 characters; lowercase letters, digits, `-` or `_`; starts with a letter, ends with a letter or digit.
- Virtual model `name`: 2–64 characters; letters, digits, `-`, `.` or `_`; starts with a letter.
- `slug` and each `alias`: 2–62 characters, same character set, unique across every virtual model in the tenant. Either can be used instead of `groupName/modelName`.
- `model_types`: one or more of `chat`, `completion`, `embedding`, `rerank`, `moderation`, `audio_transcription`, `audio_translation`, `text_to_speech`, `image`, `responses`, `video`, `decision` (default `[chat]`, and it must not be empty). `realtime` and `ocr` are not allowed on virtual models.
- Use exactly one routing type per `routing_config`; each has its own target fields.
- Weights are integers from 0 to 100; make them sum to 100 (traffic is split in proportion to weight).
- Priority: a lower number means higher priority; 0 (the default) is the highest.

### Manifest template

```yaml
type: provider-account/virtual-model
name: <group-name>
collaborators:
  - role_id: provider-account-manager
    subject: user:<current-user-email>   # from the session context; call get_session_context only if it is missing
  - role_id: provider-account-access
    subject: team:everyone
integrations:
  - name: <virtual-model-name>
    type: integration/model/virtual
    model_types: [chat]
    routing_config:
      type: weight-based-routing
      load_balance_targets:
        - target: <account-name/model-name>
          weight: 70
        - target: <account-name/model-name>
          weight: 30
          fallback_candidate: true
```

Other `routing_config` blocks:

```yaml
# Priority-based: lowest priority number first, falls back down the list
routing_config:
  type: priority-based-routing
  load_balance_targets:
    - target: <account-name/model-name>
      priority: 0
      sla_cutoff: {time_per_output_token_ms: <ms>, time_to_first_token_ms: <ms>}   # optional
    - target: <account-name/model-name>
      priority: 1

# Latency-based: targets only
routing_config:
  type: latency-based-routing
  load_balance_targets:
    - target: <account-name/model-name>
    - target: <account-name/model-name>

# Complexity-based: each request is classified into a tier
routing_config:
  type: complexity-based-routing
  classification_strategy: {type: heuristic}   # default
  load_balance_targets:
    - {target: <account-name/model-name>, tier: simple}
    - {target: <account-name/model-name>, tier: medium}
    - {target: <account-name/model-name>, tier: complex}
```

Complexity-based rules: give each of `simple`, `medium` and `complex` at least one target; a model may appear only once. The virtual model's `model_types` may contain only `chat`, `completion` or `responses`. `classification_strategy.type` is `heuristic` (default), `llm-classifier`, `decision-classifier` or `custom`. An `llm-classifier` `model` must be a non-virtual chat model; a `decision-classifier` `model` must be a `decision` model on a `typesafe` account; `custom` needs an https `url`.

Optional fields: on the virtual model, `slug` and `alias[]`. On `routing_config`, `sticky_routing` (weight-based only: `ttl_seconds` 1800–86400, `session_identifiers: [{source: headers or metadata, key}]`). Per target: `retry_config` (`attempts` required; `delay` default 100 ms; `on_status_codes` default `["429","500","502","503"]`), `fallback_status_codes` (default `["401","403","404","408","429","500","502","503"]`), `fallback_candidate` (default `true`), `override_params`, `headers_override: {set, remove}`, `metadata_match`, and `sla_cutoff` (priority-based only).

### Checklist

- [ ] Did I get the schema for `provider-account/virtual-model`?
- [ ] Did the user choose the routing strategy and targets?
- [ ] Does every target exist as `accountName/modelName`, and is none of them a virtual model?
- [ ] Does every target support every `model_type` set on the virtual model?
- [ ] For audio `model_types`, are all targets from the same provider?
- [ ] Complexity-based: does every tier have a target, with no model in two tiers?
- [ ] When updating, did I keep every existing virtual model and omit `collaborators`?

For more info: `search_docs` with "virtual models", "weight based routing", "latency based routing", "model fallback".
