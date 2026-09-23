---
name: secrets
description: Create and reference TrueFoundry secrets / secret groups in application manifests — HF tokens, registry creds, API keys. Read when deploying gated models, private images, or injecting credentials.
---

Never put raw secret values in chat, manifests committed to git, or `env` plain strings when a Secret FQN exists. Prefer Secret Groups + FQNs.

## Contents
- Find existing secrets
- Create secrets (when allowed)
- Reference in manifests
- Common use cases
- Checklist

## Find existing secrets

1. `list_secret_groups` / `list_secrets` (exact tool names per `tools.md` / MCP catalogue).
2. Match by name/FQN for HF tokens, NGC keys, Docker registry, DB passwords.
3. Use the **FQN** in the application manifest — not the decrypted value.

If the user pastes a raw token, ask them to store it as a TrueFoundry secret (or create via API if your tools support write) and then reference the FQN. Do not echo the token back.

## Create secrets (when allowed)

When MCP/tools support creating secrets or the user will create in UI:

- Put secrets in the correct **secret group** / workspace scope the app can read.
- Name clearly (`hf-token-prod`, `ngc-api-key`).
- For model deploy: pass `huggingfaceHubTokenSecretFqn` into `get_model_deployment_specs` and/or set the env the downloader expects (`HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` via secret ref).

If write tools are unavailable, give precise UI steps: Secret Group → add secret → copy FQN → paste into deploy form / tell you the FQN only.

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
