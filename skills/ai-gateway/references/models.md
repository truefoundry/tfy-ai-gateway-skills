---
name: models
description: Model integrations connect vendor models to the Gateway; manifests and validation for provider accounts and third-party or self-hosted models.
---

**Model integrations** are individual models from third party vendors or self hosted. Each integration has a `type` of `integration/model/<provider>` e.g. `integration/model/openai`.

A tenant can have multiple model accounts (provider accounts). Each account can have multiple model integrations. A model integration is referred as `{accountName}/{integrationName}`.

## Contents
- Fetching existing model configurations
- Querying supported models with `list_providers`
- Creating Model Provider Accounts (Write Flow)

## Fetching existing model configurations

Use the `list_provider_accounts` tool with `includeModelProviders: true` (and other `include*` flags set to `false` to filter out non-model accounts) to list model provider accounts along with their model integrations. The response shape is:

```yaml
data:
  - id: ...
    name: my-openai-account
    fqn: truefoundry:openai:my-openai-account
    provider: openai
    manifest:
      name: my-openai-account
      type: provider-account/openai
      collaborators:
        - role_id: provider-account-manager
          subject: user:alice@example.com
        - role_id: provider-account-access
          subject: team:everyone
      integrations:
        - name: gpt-4o
          type: integration/model/openai
          model_id: gpt-4o
          # Fields specific to integration/model/openai
    integrations:
      - id: ...
        name: gpt-4o
        fqn: truefoundry:openai:my-openai-account:model:gpt-4o
        type: model
        providerAccountFqn: truefoundry:openai:my-openai-account
        manifest:
          name: gpt-4o
          type: integration/model/openai
          model_id: gpt-4o
          # Fields specific to integration/model/openai
        # ...other top-level integration fields (createdBySubject, timestamps, etc.)
pagination:
  total: ...
  offset: 0
  limit: 100
```

The integration manifest under `data[].manifest.integrations` and `data[].integrations[].manifest` are equivalent for the integration spec; the latter additionally exposes `id`, `fqn`, `providerAccountFqn`, and audit fields.

The identifier `my-openai-account/gpt-4o` refers to the `gpt-4o` integration under provider account `my-openai-account`.

To inspect a single provider account by id, use `get_provider_account`.

## Querying supported models with `list_providers`

`list_providers` returns the **platform catalog** — every provider, model, and pricing tier the platform *supports*. It does NOT return the user's existing/configured provider accounts (use `list_provider_accounts` for that).

Use `list_providers` for:
- **Checking model support** — when the user asks "do you support X model?", "is X available?", always call `list_providers` and search the response. Do NOT answer from memory.
- **Checking provider support** — when asked "which providers do you support?", "which providers are available?", list the top-level `type` / `label` entries from the response.
- **Building provider account manifests** — when creating a provider account (write flow), use this data to present available models, get the correct `model_id` values, and determine available regions.

The response is an array of providers. Each provider has integrations with a `metadata` object keyed by `model_id`:

```yaml
- type: provider-account/openai
  label: OpenAI
  integrations:
    - type: integration/model/openai
      metadata:
        gpt-4o:
          model: gpt-4o              # model_id to use in manifests
          mode: chat                 # see modes below
          costs:
            - input_cost_per_token: 0.0000025
              output_cost_per_token: 0.00001
              region: "*"            # "*" = all regions; otherwise region-specific
          status: active
        # ...more models
# ...more providers
```

Key fields: `model` (model_id for manifests), `mode`, `costs[]` (per region), `status`.
ModelType enum: `chat`, `completion`, `embedding`, `realtime`, `rerank`, `audio_transcription`, `audio_translation`, `text_to_speech`, `moderation`, `image`, `responses`.

## Creating Model Provider Accounts (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with the provider account type the user wants (e.g. `provider-account/openai`, `provider-account/aws-bedrock`, `provider-account/anthropic`, `provider-account/azure-openai`, etc.).

### Phase 2: Determine Authentication and Models

1. If the schema shows multiple authentication methods, use `ask_user_question` to ask the user which auth method to use.
2. You **MUST** call `list_providers` to get the supported models, pricing, and regions for the selected provider. NEVER use your own knowledge for model names, IDs, or modes — only use what `list_providers` returns. Your training data is outdated; `list_providers` is the source of truth.
3. The `list_providers` response is very large (200K+ lines). After calling it, filter by the provider `type` (e.g. `provider-account/openai`) to find the relevant entry, then extract models from its `integrations[0].metadata`. Every provider has models — if you think you found none, you are parsing the response wrong. Re-examine it.
4. **Filter models by region** — from the `list_providers` response, only include models that have a cost entry matching the user's selected region (or `region: "*"`). Do NOT add models unavailable in the chosen region.
5. Do NOT dump the full model list to the user — it can be very large. Ask the user which models they want to add (by name or type) and look them up in the `list_providers` response.
6. **Naming rule**: For `realtime`, `audio_transcription`, `audio_translation`, `text_to_speech` modes, integration `name` MUST equal `model_id`. For all other modes, any descriptive name works.
7. **Pricing rule — follow strictly per model type:**
   - **`chat`, `completion`, `embedding`, `responses`** → add `cost:` with `metric: public_cost` to enable public pricing
   - **All other modes** (`realtime`, `rerank`, `audio_transcription`, `audio_translation`, `text_to_speech`, `moderation`, `image`) → the `cost` field MUST NOT be present. Do not add it, do not set it to null, do not set it to empty — omit it entirely.
   - Do NOT manually copy cost values from `list_providers` output. Only add custom cost fields if the user explicitly provides their own pricing.

### Phase 3: Validate and Apply

Build the manifest → write to file → `python scripts/validate_schema.py --file-path <manifest.yaml>` → `apply_manifest` with `dryRun: true` → fix if needed → `apply_manifest` without dry-run.

### Manifest Structure

```yaml
type: <provider-account/type>
name: <unique-account-name>
collaborators:
  - role_id: provider-account-manager
    subject: user:<current-user-email>  # from get_me
  - role_id: provider-account-access
    subject: team:everyone
region: <region>
integrations:
  - name: <integration-name>            # for realtime/audio_transcription/text_to_speech: MUST equal model_id
    type: <integration/model/provider>
    model_id: <provider-model-id>
    model_types:
      - <chat|completion|embedding|realtime|rerank|audio_transcription|audio_translation|text_to_speech|moderation|image|responses>
```

### Checklist

- [ ] For "do you support X model?" questions, did I call `list_providers` and check the metadata?
- [ ] Did I call `get_manifest_json_schema` to get the current schema for the provider account type?
- [ ] Did I ask the user which auth method to use if multiple are available?
- [ ] Did I call `list_providers` and filter models to only those available in the selected region?
- [ ] Did I avoid dumping the full model list and instead ask the user which models they want?
- [ ] For `realtime`/`audio_transcription`/`audio_translation`/`text_to_speech` modes, is the integration `name` set to exactly the `model_id`?
- [ ] Did I add `cost: metric: public_cost` ONLY for `chat`, `completion`, `embedding`, `responses` modes?
- [ ] Did I completely omit the `cost` field (not present at all) for every other mode?
- [ ] Did every model I added come from the `list_providers` response (not from my own knowledge)?

For more info: `search_docs` with "supported model providers", "model integrations".
