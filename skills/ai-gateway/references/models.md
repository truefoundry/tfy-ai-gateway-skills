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

The response is `{ "data": [...] }` — an object with a `data` array. Each element in `data` is a provider:

```yaml
{
  "data": [
    {
      "type": "provider-account/openai",    # use this to filter — NOT "name"
      "label": "OpenAI",
      "integrations": [
        {
          "type": "integration/model/openai",
          "metadata": {                      # keys are model_id strings
            "gpt-4o": {
              "model": "gpt-4o",            # model_id to use in manifests
              "mode": "chat",
              "costs": [
                { "input_cost_per_token": 0.0000025, "output_cost_per_token": 0.00001, "region": "*" }
              ]
            }
          }
        }
      ]
    }
  ]
}
```

**How to find a provider:** access `result["data"]`, then filter by `type` field (e.g. `type == "provider-account/openai"`). Providers do NOT have a `name` field — do not filter by `name`.
**How to get models:** `provider["integrations"][0]["metadata"]` — this is a dict keyed by `model_id`.
**Key fields per model:** `model` (model_id for manifests), `mode`, `costs[]` (per-region availability + pricing).
**`costs[]`:** Each entry has `region`. If the entry also has `input_cost_per_token` → public pricing exists for that region. If only `region` is present → model is available but has no public pricing.
ModelType enum: `chat`, `completion`, `embedding`, `realtime`, `rerank`, `audio_transcription`, `audio_translation`, `text_to_speech`, `moderation`, `image`, `responses`.

## Creating Model Provider Accounts (Write Flow)

### Phase 1: Check for Existing Accounts

Call `list_provider_accounts` with `includeModelProviders: true` and check if a provider account matching what the user asked for already exists (by name if they gave one, or by provider type if the request is general).

- **Matches found:** Present the matching accounts to the user and ask whether they want to create a new account (with a different name) or update an existing one. Carry their choice forward into Phase 2.
- **No matches:** Proceed to Phase 2.

### Phase 2: Get Schema and Provider Data

1. Call `get_manifest_json_schema` with the provider account type the user wants (e.g. `provider-account/openai`, `provider-account/aws-bedrock`, `provider-account/anthropic`, `provider-account/azure-openai`, etc.).
2. Call `list_providers` — always call this for every model provider account creation. It returns the supported models, their types, pricing, and regions. Never use your own knowledge for model names, IDs, or modes — only use what `list_providers` returns. Your training data is outdated; `list_providers` is the source of truth.

### Phase 3: Determine Authentication, Region, and Models

1. If the schema shows multiple authentication methods, use `ask_user_question` to ask the user which auth method to use.
2. The `list_providers` response is very large (200K+ lines). Call it from sandbox, save to a file, then parse. Access `result["data"]` to get the providers array, then **filter by `type` field first** (e.g. `type == "provider-account/openai"`) — NOT `name` (providers don't have a `name` field). Extract models from `provider["integrations"][0]["metadata"]`. Every provider has models — if you find none, your filter is wrong.
3. **Region** — check the JSON schema from Phase 1. If the schema includes a `region` field, collect the distinct `region` values from the **filtered provider's** models' `costs[]` entries and ask the user which region to use (via `ask_user_question`). If the schema does not have a `region` field, skip this step.
4. **Filter models by region** — if a region was selected, only include models that have a `costs` entry whose `region` matches the user's selected region (or `region: "*"`). Do NOT add models unavailable in the chosen region.
5. Do NOT dump the full model list to the user — it can be very large. Ask the user which models they want to add (by name or type) and look them up in the `list_providers` response.
6. **Naming rule**: For `realtime`, `audio_transcription`, `audio_translation`, `text_to_speech` modes, integration `name` MUST equal `model_id`. For all other modes, any descriptive name works.
7. **Pricing rule:** Add `cost: metric: public_cost` to a model **only if** its `costs` entry for the target region has `input_cost_per_token`. Otherwise omit `cost` entirely. Never manually copy cost values — only add custom cost if the user provides their own pricing.

### Phase 4: Validate and Apply

Build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Manifest Structure

```yaml
type: <provider-account/type>
name: <unique-account-name>
collaborators:
  - role_id: provider-account-manager
    subject: user:<current-user-email>  # from get_me
  - role_id: provider-account-access
    subject: team:everyone
region: <region>                          # only if schema has region field
integrations:
  # Model with public pricing available (costs entry has input_cost_per_token)
  - name: <integration-name>
    type: <integration/model/provider>
    model_id: <provider-model-id>
    model_types: [chat]
    cost:
      metric: public_cost
  # Model without public pricing (costs entry has only region) — omit cost
  - name: <integration-name>
    type: <integration/model/provider>
    model_id: <provider-model-id>
    model_types: [chat]
```

### Checklist

- [ ] For "do you support X model?" questions, did I call `list_providers` and check the metadata?
- [ ] Did I call `get_manifest_json_schema` to get the current schema for the provider account type?
- [ ] Did I ask the user which auth method to use if multiple are available?
- [ ] If the schema has a `region` field, did I ask the user which region to use?
- [ ] If a region was selected, did I filter models to only those available in that region?
- [ ] Did I avoid dumping the full model list and instead ask the user which models they want?
- [ ] For `realtime`/`audio_transcription`/`audio_translation`/`text_to_speech` modes, is the integration `name` set to exactly the `model_id`?
- [ ] Did I check each model's `costs` entry for `input_cost_per_token` before adding `cost: metric: public_cost`? Omitted `cost` when absent?
- [ ] Did every model I added come from the `list_providers` response (not from my own knowledge)?

For more info: `search_docs` with "supported model providers", "model integrations".
