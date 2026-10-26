---
name: models
description: Read to list a tenant's models, answer "do you support model X / provider Y?", or create or update a model provider account (OpenAI, Bedrock, Azure, Vertex, …) and its model integrations, including "add all models".
---

A **model provider account** (`provider-account/<provider>`) holds credentials and a list of **model integrations**. An integration is addressed as `{accountName}/{integrationName}`; its `model_id` is the provider's own name for the model. The integration type follows the host account, not the model maker: Claude on Vertex is `integration/model/vertex`.

## List the tenant's models

Call `list_provider_accounts` with `includeModelProviders: true` and `includeCustomEndpoints: true` (custom-endpoint accounts are model accounts too), and `includeInfraProviders`, `includeMCPProviders`, `includeGuardrailConfigs` set to `false`. Omit `limit` to get every account. Each `data[]` item has `name`, `provider`, `fqn` and `manifest` (with `integrations`); `data[].integrations[]` adds `id`, `fqn` and the integration `manifest` (`name`, `type`, `model_id`, `model_types`). Virtual-model groups come back too (`provider: virtual-model`). For one account by id, use `get_provider_account`.

## "Do you support model X / provider Y?"

Answer from `list_providers`, the platform catalogue, never from memory. For one provider, pass `providerType` (its `type`, below). To list all providers, pass `includeModelProviders: true` and the other `include*` flags `false` (very large). If saved to a file, extract only what you need with one `jq`.

- Shape: `data[]` is one entry per provider, with `type` (e.g. `provider-account/openai`) and `label`. Providers have no `name` field; filter on `type`.
- Models: `data[i].integrations[0].metadata` is an object keyed by `model_id`. Each value has `model`, `mode`, optional `supportedModes`, `status` (`active`, `deprecated`, `preview`, `retired`) and `costs[]`.
- Providers: list `type` and `label`. `provider-account/virtual-model` has no catalogue.
- If `metadata` is empty or missing, recheck the type; if still empty, say the catalogue has no models for that provider. Never invent models.

## Create or update a provider account

Read this file and `write-rules.md` together. Follow the write steps there; the steps below say what is specific to models.

### Inputs to collect

- Provider (the `provider-account/<provider>` type) and account name.
- Create a new account or update an existing one.
- Auth method, if the schema offers more than one, and a `tfy-secret://<owner>:<secret-group>:<secret-key>` reference for each key or secret (never a raw value).
- Region, if the schema has one (Azure OpenAI and Microsoft Foundry: `deployment_type` instead).
- Which models: "all", a list of names, or modes (for example "all chat and embedding models"). Never dump the catalogue to the user; ask by name or mode.

### Step 1 — one parallel batch

These are independent; issue them together:

- `list_provider_accounts` (flags as in "List the tenant's models"; no name filter) to find accounts of this provider or name.
- `get_manifest_json_schema` for the account type, e.g. `provider-account/openai`. Reuse it if it is still in the conversation; otherwise call it again.
- `list_providers` from the sandbox with `providerType` (the account type), saved to a file. If a saved `list_providers` file from this conversation is still referenced and still exists, reuse it; otherwise call it again.

If matching accounts exist, ask whether to update one or create a new one with a different name. If that answer is no longer in the conversation, ask again before applying.

### Step 2 — read the schema

From the schema, extract with one `jq`:

- The integration `type` constant under `integrations` items. Take it from the schema, not from `list_providers` (it reports some wrongly, e.g. `aws-sagemaker` for `sagemaker`). It differs from the account suffix for `aws-bedrock` → `integration/model/bedrock`, `aws-bedrock-mantle` → `integration/model/bedrock-mantle`, `google-vertex` → `integration/model/vertex`, `google-gemini` → `integration/model/gemini`, `aws-sagemaker` → `integration/model/sagemaker`.
- The account `name` pattern (it varies by provider; OpenAI allows 3–32 lowercase letters, digits and `-`).
- The `auth_data` variants. Some providers require `auth_data` (for example `azure-openai`, `google-gemini`); some offer several shapes (Bedrock has three). If there is more than one, ask which.
- The `region` enum, if the account has `region`.

**Region.** If the schema has `region`, collect the distinct `costs[].region` values of this provider's models, keep only values that are also in the schema's `region` enum, and ask the user to choose. `*` means "default price for any region"; never offer it as a region. Skip this if the schema has no `region`.

### Step 3 — resolve the model selection

Before writing the program, turn the user's answer into an exact selection, with one `jq` over the saved `list_providers` file:

- **"All"** or **modes** ("all chat and embedding models"): nothing to resolve; the program selects them.
- **Named models:** match each name to a catalogue key (`model_id`): an exact key first, else keys containing the name, ignoring case. One match: use it. Several: ask the user to pick (show at most 10). None: the model is not in the catalogue. Ask for its exact `model_id` and model types, and add it without `cost` (public cost exists only for catalogue models; any other gets a 400).

### Step 4 — build the manifest in the sandbox with one program

Write one program that reads the saved `list_providers` file and writes the complete manifest as JSON to a file.

**Inputs:** the provider `type`; the integration `type` from Step 2; the account `name`; the region or `deployment_type`; the selection from Step 3; `auth_data`; collaborators (from `write-rules.md`); when updating, the current manifest from `list_provider_accounts`.

**Program**, in this order:

1. **Catalogue:** the `data[]` entry whose `type` is the provider type; models are `integrations[0].metadata`, keyed by `model_id`.
2. **Select:** for "all", every model whose `status` is not `retired`; for modes, the same, kept only if `model_types` (next step) include a chosen mode; for names, the keys from Step 3, plus any non-catalogue model with the user's `model_id` and types.
3. **`model_types`:** `mode` plus every value in `supportedModes`, de-duplicated, keeping only `chat`, `completion`, `embedding`, `realtime`, `rerank`, `audio_transcription`, `audio_translation`, `text_to_speech`, `moderation`, `image`, `responses`, `ocr`, `video`, `decision`. Drop `unknown` and `unsupported`; if nothing is left, skip the model. Never default to `[chat]`: the gateway rejects calls whose type is not in `model_types` (for example `/embeddings` on a `[chat]` model).
4. **Region filter** (accounts with `region`): for "all" and modes, keep only models with a `costs` entry whose `region` is the chosen region or `*`. A named model without one is not priced there: tell the user, and add it without `cost` only if they confirm.
5. **Name:** `model_id` with every `/` and `:` replaced by `-` (`openai/tts-1:v2` → `openai-tts-1-v2`). For `realtime`, `text_to_speech`, `audio_transcription` and `audio_translation` models this exact name is required and `apply_manifest` rejects any other (the audio check is skipped on `aws-bedrock` and `aws-bedrock-mantle`; the realtime check applies everywhere). The name must match `^[a-zA-Z](?:[a-zA-Z0-9\-._]{0,62}[a-zA-Z0-9])$`; for other models you may replace remaining invalid characters with `-`. Skip names that still fail, and duplicates.
6. **Cost** — decide for each integration. A wrong `public_cost` makes `apply_manifest` return a 400 listing every bad model.
   - No `cost` if the integration type is `custom-endpoint` or `virtual` (no `cost` field), or the model is not in the catalogue.
   - Otherwise pick the cost entry: the one whose `region` is the target (Bedrock, Bedrock Mantle, Vertex: the chosen `region`; Azure OpenAI and Microsoft Foundry: `deployment_type` `global`, `datazone_us` or `datazone_eu`, with `standard` meaning `*`), else the `region: "*"` entry. Providers without a region: the `*` entry.
   - Add `cost: {metric: public_cost}` only if that entry exists and has a key besides `region` (`input_cost_per_token`, `input_cost_per_character`, `input_cost_per_second`, `tiered_pricing`, …). Otherwise omit `cost`.
   - Never copy price values. If the user gives their own pricing, use the matching private metric from the schema instead of `public_cost`.
7. **Integration:** `{name, type, model_id, model_types}`, plus `cost` from step 6, plus any field the schema requires (Azure OpenAI: `api_version`). For Azure OpenAI and Microsoft Foundry, `model_id` is the user's deployment name, so ask for the deployments rather than taking "all"; set `deployment_type`, and `foundation_model` to the catalogue key (pricing is looked up by `foundation_model`, else `model_id`).
8. **Update:** start from the current manifest; delete `collaborators` and each integration's `authorized_subjects` (`write-rules.md` → Collaborators); append only names not already there. **`integrations` replaces the whole list: a dropped integration is deleted.**
9. **Write** the manifest (template below) to a file. Print only a summary: count by model type, how many have `cost`, and each skipped model with why.

Show the user the summary, not the full list.

### Step 5 — validate in the sandbox, apply once

Call `validate_manifest` from the sandbox with the file's JSON as `{"manifest": …}`; on errors, fix the program's rule, rebuild the file and validate again. Once it returns `valid: true`, call `apply_manifest` once, directly (it needs approval), with the same JSON. `validate_manifest` checks only the schema; the pricing, naming and credential checks run at apply, which is why program steps 5 and 6 must be right before you apply. If apply fails, fix the program's rule (not single entries) and rebuild.

Then show the UI link from `write-rules.md`.

### Manifest template

```yaml
type: provider-account/<provider>
name: <account-name>                     # schema's name pattern
auth_data:                               # shape from the schema, e.g.
  type: api-key
  api_key: tfy-secret://<owner>:<secret-group>:<secret-key>
region: <region>                         # only if the schema has region
collaborators:                           # create only; omit on update
  - role_id: provider-account-manager
    subject: user:<current-user-email>   # from the session context; call get_session_context only if it is missing
  - role_id: provider-account-access
    subject: team:everyone
integrations:
  - name: <model_id with / and : replaced by ->
    type: <integration type const from the schema>
    model_id: <metadata key>
    model_types: [<mode>, <supportedModes>…]
    cost:                                # only per the pricing rule
      metric: public_cost
```

### Checklist

- [ ] Did every model come from `list_providers`, not memory?
- [ ] Is each integration `type` taken from the schema?
- [ ] Is `model_types` from `mode` plus `supportedModes`, never defaulted to `[chat]`, with no `unknown`/`unsupported`?
- [ ] For realtime/TTS/STT/audio-translation models, is `name` the `model_id` with `/` and `:` replaced by `-`?
- [ ] Is `cost: {metric: public_cost}` only on models whose picked cost entry has a price field?
- [ ] If the schema has `region`, did the user choose one from the schema enum (never `*`), and are the models filtered by it?
- [ ] Are credentials `tfy-secret://` references in the schema's `auth_data` shape?
- [ ] When updating, did I keep every integration and omit `collaborators`?
- [ ] Was the manifest built by one program into a file, validated once and applied once?

For more info: `search_docs` with "supported model providers", "model integrations".
