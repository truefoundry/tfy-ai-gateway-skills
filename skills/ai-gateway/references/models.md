---
name: models
description: Model integrations connect vendor models to the Gateway; manifests and validation for provider accounts and third-party or self-hosted models.
---

**Model integrations** are individual models from third party vendors or self hosted. Each integration has a `type` of `integration/model/<provider>` e.g. `integration/model/openai`.

A tenant can have multiple model accounts (provider accounts). Each account can have multiple model integrations. A model integration is referred as `{accountName}/{integrationName}`.

## Fetching existing model configurations

Use the `gateway_list_models` tool to get the list of all models and virtual models. The response shape for **model accounts** is similar to:

```yaml
result:
  manifest:
    type: provider-account/openai
    name: my-openai-account
    integrations:
      - name: gpt-4o
        type: integration/model/openai
        model_id: gpt-4o
        # Fields specific to integration/model/openai
```

The identifier `my-openai-account/gpt-4o` refers to the `gpt-4o` integration under provider account `my-openai-account`.

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

## Searching docs for additional information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_true_foundry_docs` to search for additional information about models.
Search terms: "supported model providers", "model integrations"

