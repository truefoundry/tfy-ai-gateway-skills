---
name: secrets
description: Create and reference TrueFoundry secrets / secret groups in application manifests — HF tokens, registry creds, API keys. Read when deploying gated models, private images, or injecting credentials.
---

Never put raw secret values in chat, manifests committed to git, or `env` plain strings when a Secret FQN exists. Prefer Secret Groups + FQNs.

## Contents
- Find existing secrets
- Create secrets
- Reference in manifests
- Common use cases
- Checklist

## Find existing secrets

1. `list_secret_groups` — the groups the user can access, each with its secrets. Values are never returned. `list_secrets` lists secrets directly.
2. Match by name/FQN for HF tokens, NGC keys, Docker registry, DB passwords.
3. Use the **FQN** in the application manifest — not the decrypted value.

If the user pastes a raw token, do not echo it back and do not put it in a manifest. Ask them to store it as a TrueFoundry secret (below) and give you the FQN.

## Create secrets

No tool you have stores a secret **value**. `apply_manifest` can create a secret **group** (`type: secret-group` — it needs the secret store's `integration_fqn`; take the schema from `get_manifest_json_schema`), but the group starts empty and values are added in the console.

So when the secret does not exist yet, give the user the steps — Secret Groups → the group → add secret → copy its FQN — and ask them for the **FQN only**.

- Put secrets in a **secret group** the application's workspace can read.
- Name clearly (`hf-token-prod`, `ngc-api-key`).
- For model deploy: pass `huggingfaceHubTokenSecretFqn` into `get_model_deployment_specs` and/or set the env the downloader expects (`HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` via secret ref).

## Reference in manifests

Patterns (confirm in `get_manifest_json_schema`):

- Env value as secret reference / `value_from` secret FQN (platform-specific shape).
- Image pull secrets / private registry integrations for `ImagePullBackOff` (`failure-modes/image-pull.md`).
- NIM: `ngcApiKeySecretFqn` + NVCR registry integration FQN on `get_nim_deployment_specs`.

Editing secrets on an existing app = full manifest replace (`deploy-common.md`) — keep every other field.

## Common use cases

| Need | Secret |
|---|---|
| Gated HuggingFace model | HF token secret FQN |
| Private container image | Registry creds / integration |
| NVIDIA NIM | NGC API key secret FQN |
| App talks to OpenAI/etc directly | Provider API key secret (or prefer AI Gateway) |
| DB / Redis password | Secret FQN in env |

## Checklist

- [ ] Did I use FQNs instead of raw values?
- [ ] Did I avoid printing secret values in the reply?
- [ ] For gated models, did I pass the FQN into catalogue specs / artifacts download?
- [ ] Did I validate the manifest after wiring secret refs?

For more info: `search_docs` with "secrets", "secret groups", "huggingface token".
