---
name: model-deploy
description: Deploy an LLM, VLM, embedding, or reranker from a HuggingFace URL or TrueFoundry model version — generate recommended model-server + GPU specs, validate support, fall back when the catalogue errors, then apply a service manifest. Read before any "deploy this model / HF link / vLLM / SGLang" request.
---

Model deployments on TrueFoundry are normal **`type: service`** applications. The catalogue API recommends the model server (vLLM, SGLang, TRT-LLM, Infinity, TEI, …), image, args, GPU shape, artifacts download, and probes. Your job is to pick the best option for the workspace, fix gaps the API cannot see, deploy via `apply_manifest`, and verify the workload actually serves.

## Contents
- Inputs to collect
- Generate specs (`get_model_deployment_specs`)
- Enrich with web / recipes / Hub metadata
- When the API errors — recover intelligently
- Choose server, GPU, and availability
- Apply and verify
- NIM path
- Checklist

## Inputs to collect

Before calling tools, resolve:

| Input | How |
|---|---|
| Target **workspace** | `list_workspaces` → use `id` as `workspaceId` and `fqn` on the manifest |
| Model source | HuggingFace URL (`https://huggingface.co/<org>/<model>`) **or** TrueFoundry `modelVersionFqn` |
| HF token (gated/private) | Secret FQN via `list_secrets` / `list_secret_groups` — never ask the user to paste the raw token into chat |
| Preferred server (optional) | vLLM / SGLang / TRT-LLM / Infinity / TEI / NIM — otherwise pick from recommendations |
| GPU preference (optional) | Otherwise pick an `isAvailableInWorkspace: true` option |

If the user only pasted a model name, search the Hub (web search) and confirm the exact `org/model` URL before generating specs.

## Generate specs (`get_model_deployment_specs`)

```
get_model_deployment_specs
  workspaceId=<workspace.id>
  huggingfaceHubUrl=<HF url>          # XOR modelVersionFqn
  huggingfaceHubTokenSecretFqn=<fqn>  # if gated/private
  pipelineTagOverride=<tag>           # only when Hub tag is wrong/missing — see below
```

Response shape (simplified):

```yaml
data:
  - name: vLLM          # ModelServer enum value
    displayName: vLLM
    description: ...
    deployments:
      - name: "A10G · 1 GPU"   # human label
        isAvailableInWorkspace: true|false
        cost: ...
        spec:                    # full type: service manifest
          type: service
          name: ...
          image: ...
          resources: ...
          artifacts_download: ...
          env: ...
          ports: ...
          probes: ...
          labels:
            truefoundry.com/huggingface-model-task: text-generation
            truefoundry.com/model-server: vLLM
  - name: SGLang
    deployments: [...]
```

**Rules:**

- Prefer options with `isAvailableInWorkspace: true`. If none are available, say which GPUs the catalogue wanted and what the workspace actually has (`list_cluster_addons` / nodepools via workspace), then ask whether to proceed with an unavailable shape (may stay Pending — see `failure-modes/pending-scheduling.md`).
- Each `deployments[].spec` is already a service manifest — merge workspace_fqn (API usually sets it), validate, apply. Do **not** rebuild from scratch unless recovery requires it.
- Read `deploy-common.md` before apply: updating an existing name replaces the whole manifest.

## Enrich with web / recipes / Hub metadata

The catalogue is strong but not omniscient. **Before locking a choice**, use available web search / fetch tools (Ask AI web search MCP, etc.):

1. **HuggingFace model card** for the exact URL — `pipeline_tag`, library, size, gated flag, recommended runtime, open issues on the card.
2. **[vLLM Recipes](https://recipes.vllm.ai/)** — open `https://recipes.vllm.ai/<org>/<model>` (and hardware/variant query params when relevant). Pull recommended flags, TP size, quantization, and image hints; fold compatible flags into the chosen `spec` (args/env) **without** dropping TrueFoundry-required pieces (`artifacts_download`, probes, labels, workspace_fqn).
3. **Model-server support matrices**:
   - vLLM: https://docs.vllm.ai/en/latest/models/supported_models.html
   - SGLang: https://sgl-project.github.io/
   - Infinity: https://github.com/michaelfeil/infinity
   - TEI: HuggingFace Text Embeddings Inference docs
4. If the catalogue suggests a server the model does **not** support (or Hub tags say so), prefer a supported server from the same response, or recover (next section).

Cite what you found (recipe URL, support-doc line) when you override catalogue defaults.

## When the API errors — recover intelligently

Do **not** stop at the first `get_model_deployment_specs` failure. Common recoveries:

| Failure signal | Recovery |
|---|---|
| Wrong / missing `pipeline_tag` (generic toolkit, empty options, or Hub says `any-to-any` / unset) | Retry with `pipelineTagOverride`. Common values: `text-generation`, `text2text-generation`, `image-text-to-text`, `feature-extraction`, `sentence-similarity`, `text-ranking`, `text-to-image`, `automatic-speech-recognition`. Infer from Hub card + similar models (same architecture family). |
| Gated/private model without token | Resolve HF token secret FQN, retry with `huggingfaceHubTokenSecretFqn` |
| Unsupported quantization method | Search for an officially supported quant variant of the same model, or a non-quantized sibling; regenerate specs |
| Empty `data` / no deployments | Web-research a close public twin that *is* supported; generate specs for the twin to learn server/GPU shape; adapt `artifacts_download` / model id back to the user's model; validate |
| Framework not supported (TFY registry model) | Ensure transformers framework + `pipeline_tag` on the model version, or deploy from the Hub URL instead |
| Workspace has no matching GPUs | Offer the closest available GPU option; warn about Pending; optionally suggest changing workspace/cluster |

**Similar-model strategy:** when the exact model fails, find a well-known sibling (same arch, known good on vLLM/SGLang — e.g. another Llama/Qwen/Mistral size), generate specs for that sibling, then surgically replace model id / HF URL / served model name / artifact fields. Re-validate. Tell the user what you borrowed and what you changed.

`pipelineTagOverride: auto` is only meaningful in some registry paths — prefer an explicit Hub task string when overriding.

## Choose server, GPU, and availability

Default preference for text LLMs when multiple servers return options: **vLLM** (broadest ops knowledge) → **SGLang** (strong for structured/constrained decode) → **TRT-LLM** (when catalogue offers it and engines exist). For embeddings/rerankers prefer **Infinity** / **TEI** as returned.

GPU pick:

1. Smallest `isAvailableInWorkspace: true` option that fits memory (catalogue already sizes TP / GPU count).
2. If the user named a GPU type, match `deployments[].name` / resources accordingly.
3. Never silently pick an unavailable option.

Present a short comparison (server, GPU, rough cost if present) and confirm when more than one viable path exists — unless the user already specified.

## Apply and verify

1. Take the chosen `deployments[].spec`.
2. Ensure `name` is unique in the workspace (or confirm update per `deploy-common.md`).
3. `get_manifest_json_schema` for `service` if you edited fields heavily; always `validate_manifest`.
4. `apply_manifest` (approval flow). Never `tfy apply` in the terminal for this path.
5. Follow with `get_deployment` → `list_k8s_pods`. Startup is long (model download + load) — do not declare failure in the first few minutes if probes are still progressing.
6. Hand off deep failures to `model-debug.md`.

After success, show the service endpoint (`generate_deployment_endpoint` if useful) and note OpenAI-compatible paths for vLLM/SGLang (`/v1/chat/completions`, etc.).

## NIM path

For NVIDIA NIM containers use `get_nim_deployment_specs` with `nimModelId`, `nvcrDockerRegistryProviderIntegrationFqn`, and `ngcApiKeySecretFqn`. Same apply/verify loop. Do not mix NIM inputs into `get_model_deployment_specs`.

## Checklist

- [ ] Did I resolve `workspaceId` from `list_workspaces` (not a guessed id)?
- [ ] Did I call `get_model_deployment_specs` (or NIM) before hand-writing a vLLM service?
- [ ] For gated models, did I pass a secret FQN rather than a raw token?
- [ ] If Hub tags looked wrong, did I retry with `pipelineTagOverride` informed by the model card?
- [ ] Did I check vLLM recipes / support docs when recommending flags or choosing a server?
- [ ] Did I prefer `isAvailableInWorkspace: true` GPU options?
- [ ] On API failure, did I attempt override / similar-model recovery instead of giving up?
- [ ] Did I `validate_manifest` then `apply_manifest`, then verify pods rather than stopping at apply?

For more info: `search_docs` with "deploying an LLM", "model catalogue", "deploy model from huggingface".
