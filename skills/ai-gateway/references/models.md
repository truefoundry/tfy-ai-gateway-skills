---
name: models
description: Model integrations connect vendor models to the Gateway; manifests and validation for provider accounts and third-party or self-hosted models.
---

**Model integrations** are individual models from third party vendors or self hosted. Each integration has a `type` of `integration/model/<provider>` e.g. `integration/model/openai`.

A tenant can have multiple model accounts (provider accounts). Each account can have multiple model integrations. A model integration is referred as `{accountName}/{integrationName}`.

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
Modes: `chat`, `completion`, `embedding`, `image`, `video`, `text_to_speech`, `audio_transcription`, `realtime`, `rerank`, `moderation`, `responses`, `unknown`, `unsupported`.

## Creating Model Provider Accounts (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with the provider account type the user wants (e.g. `provider-account/openai`, `provider-account/aws-bedrock`, `provider-account/anthropic`, `provider-account/azure-openai`, etc.).

### Phase 2: Determine Authentication and Models

1. If the schema shows multiple authentication methods, use `ask_user_question` to ask the user which auth method to use.
2. You **MUST** call `list_providers` to get the supported models, pricing, and regions for the selected provider. Do NOT skip this step.
3. **Filter models by region** — from the `list_providers` response, only include models that have a cost entry matching the user's selected region (or `region: "*"`). Do NOT add models unavailable in the chosen region.
4. Do NOT dump the full model list to the user — it can be very large. Ask the user which models they want to add (by name or type) and look them up in the `list_providers` response.
5. **Naming rule**: For `realtime`, `audio_transcription`, `text_to_speech`, `audio_translation`, modes, integration `name` MUST equal `model_id`. For all other modes, any descriptive name works.
6. **Pricing rule — follow strictly per model type:**
   - **`chat`, `completion`, `embedding`** → add `cost:` with `metric: public_cost` to enable public pricing
   - **All other modes** (`image`, `video`, `text_to_speech`, `audio_transcription`, `realtime`, `rerank`, `moderation`, `responses`, `unknown`, `unsupported`) → do NOT add a `cost` field at all (omitting it disables cost tracking)
   - Do NOT manually copy cost values from `list_providers` output. Only add custom cost fields if the user explicitly provides their own pricing.

### Phase 3: Build and Validate

1. Build the manifest following the JSON schema strictly. Write it to a file.
2. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
3. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run to create the provider account.

### Manifest Structure

```yaml
type: <provider-account/type>
name: <unique-account-name>
collaborators:
  - role_id: provider-account-access
    subject: team:everyone              # default; replace if user specifies collaborators
region: <region>
integrations:
  - name: <integration-name>            # for realtime/audio: MUST equal model_id
    type: <integration/model/provider>
    model_id: <provider-model-id>
    model_types:
      - <chat|embedding|rerank|realtime|audio>
```

### Checklist

- [ ] For "do you support X model?" questions, did I call `list_providers` and check the metadata?
- [ ] Did I call `get_manifest_json_schema` to get the current schema for the provider account type?
- [ ] Did I ask the user which auth method to use if multiple are available?
- [ ] Did I call `list_providers` and filter models to only those available in the selected region?
- [ ] Did I avoid dumping the full model list and instead ask the user which models they want?
- [ ] For `realtime`/`audio_transcription`/`text_to_speech` modes, is the integration `name` set to exactly the `model_id`?
- [ ] Did I add `cost: metric: public_cost` ONLY for models with mode `chat`, `completion`, or `embedding`?
- [ ] Did I omit the `cost` field entirely for all other modes (`image`, `video`, `text_to_speech`, `audio_transcription`, `realtime`, `rerank`, `moderation`, `responses`, `unknown`, `unsupported`)?
- [ ] Did I validate with `scripts/validate_schema.py` before dry-running?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before applying?
- [ ] Did I call `apply_manifest` directly as a tool (not from sandbox/code mode)?

## Searching docs for additional information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_docs` to search for additional information about models.
Search terms: "supported model providers", "model integrations"
