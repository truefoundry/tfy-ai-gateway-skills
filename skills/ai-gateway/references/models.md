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

The response is an array of supported providers, each containing supported integrations with a `metadata` object keyed by `model_id`. The shape is:

```yaml
- type: provider-account/openai          # provider account type
  label: OpenAI                           # display name
  integrations:
    - type: integration/model/openai      # integration type
      label: OpenAI Model
      metadata:                           # keyed by model_id
        gpt-4o:
          model: gpt-4o                   # the model_id to use in manifests
          mode: chat                      # chat | embedding | rerank | completion
          costs:
            - input_cost_per_token: 0.0000025
              output_cost_per_token: 0.00001
              region: "*"                 # "*" means all regions
          limits:
            context_window: 128000
            max_output_tokens: 16384
          features:                       # supported capabilities
            - function_calling
            - structured_output
            - prompt_caching
          status: active                  # active | deprecated
          isDeprecated: false
        # ...more models
- type: provider-account/aws-bedrock
  label: AWS Bedrock
  integrations:
    - type: integration/model/bedrock
      metadata:
        anthropic.claude-sonnet-4-20250514-v1:0:
          model: anthropic.claude-sonnet-4-20250514-v1:0
          mode: chat
          costs:
            - input_cost_per_token: 0.000003
              output_cost_per_token: 0.000015
              region: us-east-1           # region-specific pricing
            - input_cost_per_token: 0.000003
              output_cost_per_token: 0.000015
              region: us-west-2
          # ...
# ...more providers
```

Key fields in each model entry under `metadata.<model_id>`:
- `model` — the model ID to use in manifests
- `mode` — `chat`, `embedding`, `rerank`, or `completion`
- `costs[]` — pricing per region (`region: "*"` = all regions)
- `limits` — context window, max output tokens
- `features[]` — capabilities like `function_calling`, `structured_output`, `prompt_caching`
- `status` / `isDeprecated` — whether the model is still active

## Generating Valid Manifests for Model Integrations and Model Provider Accounts

### Phase 1: Research Model Integration Schema

1. Use grep in `scripts/manifest_schemas.py` to find model integration type of the provider or interest. If you want to find all model integration types, use the following command:

    ```shell
    grep -h -E 'integration/model/' scripts/manifest_schemas.py
    ```

2. Use grep further on `scripts/manifest_schemas.py` to read the schema for a specific type

    ```shell
    grep -B 20 -A 20 -h -E 'integration/model/bedrock' scripts/manifest_schemas.py
    ```

### Phase 2: Research Model Provider Account Schema

1. Once you know the class name of the model integration, use grep on `scripts/manifest_schemas.py` to find the provider account class.

    ```shell
    grep -B 20 -A 20 -h -E 'integrations: list\[BedrockModel\]' scripts/manifest_schemas.py
    ```

### Phase 3: Generate Model Provider Account Manifest

1. Using the discovered schemas, write a YAML manifest to a file. This should reference the model integrations written in Phase 2.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat until the manifest is valid.

## Creating Model Provider Accounts (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with the provider account type the user wants (e.g. `provider-account/openai`, `provider-account/aws-bedrock`, `provider-account/anthropic`, `provider-account/azure-openai`, etc.).

### Phase 2: Determine Authentication and Models

1. If the schema shows multiple authentication methods, use `ask_user_question` to ask the user which auth method to use.
2. You **MUST** call `list_providers` to get the supported models, pricing, and regions for the selected provider. Do NOT skip this step — present the supported models to the user so they can pick which ones to add to the provider account.
3. For pricing:
   - For **chat, completions, and embedding** models: enable public pricing by default (do NOT disable cost tracking).
   - For **all other model types** (rerank, etc.): disable cost by default.
   - Do NOT manually add cost fields from `list_providers` output. Only add custom cost fields if the user explicitly provides their own pricing.
4. For **realtime and audio** models: the integration `name` and `model_id` MUST be exactly the same value (e.g. `name: gpt-4o-realtime-preview`, `model_id: gpt-4o-realtime-preview`).

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
  - role_id: provider-account-manager
    subject: user:<current-user-email>  # from get_me; ask user before adding others
region: <region>
integrations:
  - name: <integration-name>
    type: <integration/model/provider>
    model_id: <provider-model-id>
    model_types:
      - <chat|embedding|rerank>
```

### Checklist

- [ ] For "do you support X model?" questions, did I call `list_providers` and check the metadata?
- [ ] Did I call `get_manifest_json_schema` to get the current schema for the provider account type?
- [ ] Did I ask the user which auth method to use if multiple are available?
- [ ] Did I call `list_providers` to show supported models and regions?
- [ ] For realtime/audio models, is the integration `name` identical to `model_id`?
- [ ] Did I validate with `scripts/validate_schema.py` before dry-running?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before creating?
- [ ] Did I apply without dry-run only after dry-run passed?

## Searching docs for additional information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_docs` to search for additional information about models.
Search terms: "supported model providers", "model integrations"
