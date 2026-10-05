---
name: model-deploy
description: Deploy an LLM, VLM, embedding, reranker, or classical ML model from HuggingFace / catalogue / NIM — generate specs, recover from catalogue gaps, apply, smoke-test, optionally register on Gateway and enable sticky / scale-to-0. Read before any "deploy this model / HF link / vLLM / SGLang" request.
---

Model deployments on TrueFoundry are normal **`type: service`** applications (classical sklearn/XGBoost paths may differ — see Classical ML below). The catalogue API recommends the model server (vLLM, SGLang, TRT-LLM, Infinity, TEI, …), image, args, GPU shape, artifacts download, and probes. Your job is to pick the best option for the workspace, fix gaps the API cannot see, deploy via `apply_manifest`, verify the workload actually serves, then finish the product loop (smoke test, Gateway, sticky session when useful).

## Contents
- Inputs to collect
- Generate specs (`get_model_deployment_specs`)
- Pipeline tags and modality table
- Enrich with web / recipes / Hub metadata
- When the API errors — recover intelligently
- Choose server, GPU, and availability
- Hard cases (GPU memory util, VLM, embed/rerank, image tags)
- Apply and verify
- Post-deploy product loop (smoke, Gateway, sticky, scale-to-0)
- NIM path
- Classical ML (sklearn / XGBoost / …)
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
| Post-deploy intent (optional) | Gateway registration? sticky sessions? scale-to-0? |

If the user only pasted a model name, search the Hub (web search) and confirm the exact `org/model` URL before generating specs.

## Generate specs (`get_model_deployment_specs`)

```
get_model_deployment_specs
  workspaceId=<workspace.id>
  huggingfaceHubUrl=<HF url>          # XOR modelVersionFqn
  huggingfaceHubTokenSecretFqn=<fqn>  # if gated/private
  pipelineTagOverride=<tag>           # only when Hub tag is wrong/missing — see table below
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

## Pipeline tags and modality table

Hub `pipeline_tag` drives which servers and args the catalogue returns. Wrong tag → empty options or a server that cannot load the weights.

| Modality / intent | Prefer `pipelineTagOverride` | Typical servers |
|---|---|---|
| Chat / base LLM | `text-generation` | vLLM, SGLang, TRT-LLM |
| Seq2seq / encoder-decoder | `text2text-generation` | vLLM / TGI-class as returned |
| Vision-language (VLM) | `image-text-to-text` | vLLM or SGLang with multimodal flags |
| Embeddings | `feature-extraction` or `sentence-similarity` | Infinity, TEI |
| Rerankers | `text-ranking` | Infinity / TEI as returned |
| ASR | `automatic-speech-recognition` | as returned |
| Diffusion / image gen | `text-to-image` | as returned (often not vLLM) |
| Hub says `any-to-any` / unset / toolkit | Infer from card architecture (Llama→`text-generation`, LLaVA/Qwen-VL→`image-text-to-text`, BGE→`feature-extraction`) | Retry override before giving up |

Never leave `any-to-any` as the effective tag when generating specs — always override to a concrete task.

## Enrich with web / recipes / Hub metadata

The catalogue is strong but not omniscient. **Before locking a choice**, use available web search / fetch tools:

1. **HuggingFace model card** — `pipeline_tag`, library, size, gated flag, recommended runtime.
2. **[vLLM Recipes](https://recipes.vllm.ai/)** — `https://recipes.vllm.ai/<org>/<model>`. Fold compatible flags into the chosen `spec` **without** dropping TrueFoundry-required pieces (`artifacts_download`, probes, labels, workspace_fqn).
3. **Support matrices** — vLLM supported models; SGLang; Infinity; TEI docs.
4. If the catalogue suggests a server the model does **not** support, prefer a supported server from the same response, or recover (next section).

Cite what you found (recipe URL, support-doc line) when you override catalogue defaults.

## When the API errors — recover intelligently

Do **not** stop at the first `get_model_deployment_specs` failure:

| Failure signal | Recovery |
|---|---|
| Wrong / missing `pipeline_tag` (`any-to-any`, unset, empty options) | Retry with `pipelineTagOverride` from the table above |
| Gated/private model without token | Resolve HF token secret FQN, retry with `huggingfaceHubTokenSecretFqn` |
| Unsupported quantization method | Supported quant sibling or non-quantized twin; regenerate |
| Empty `data` / no deployments | Similar-model strategy (below) |
| Framework not supported (TFY registry) | transformers + `pipeline_tag` on the version, or deploy from Hub URL |
| Workspace has no matching GPUs | Closest available GPU; warn Pending; optional workspace change |

**Similar-model strategy:** generate specs for a well-known sibling (same arch, known good on vLLM/SGLang), then surgically replace model id / HF URL / served model name / artifact fields. Re-validate. Tell the user what you borrowed.

`pipelineTagOverride: auto` is only meaningful in some registry paths — prefer an explicit Hub task string.

## Choose server, GPU, and availability

Default preference for text LLMs: **vLLM** → **SGLang** → **TRT-LLM**. For embeddings/rerankers prefer **Infinity** / **TEI** as returned. For VLMs prefer the server the catalogue marks multimodal-capable (often SGLang or recent vLLM).

GPU pick:

1. Smallest `isAvailableInWorkspace: true` option that fits memory.
2. If the user named a GPU type, match `deployments[].name` / resources.
3. Never silently pick an unavailable option.

Present a short comparison and confirm when more than one viable path exists — unless the user already specified.

## Hard cases (GPU memory util, VLM, embed/rerank, image tags)

### GPU memory utilization on small GPUs

Catalogue / vLLM defaults often set **`--gpu-memory-utilization` ≈ 0.90** on the model-server **command/args or env** (this is **not** a TrueFoundry top-level manifest field). On **small GPUs** (T4, L4, single small consumer GPU) that frequently causes **CUDA OOM at load** even when the catalogue listed that shape.

When deploying onto small GPUs, or when the user reports CUDA / GPU OOM on first start:

- Lower the flag toward **0.70–0.80** in args/env — match how the chosen image names it (commonly `--gpu-memory-utilization`). Do not add a fake `gpu_memory_utilization:` key at the service root.
- Also consider: lower max model length, AWQ/GPTQ/FP8 quant variant, or a larger GPU / higher TP.
- Do not only “add another replica” — CUDA OOM at load is per-replica GPU memory. Container `OOMKilled` is a separate memory-*limit* problem (`model-debug.md`).

### Vision-language / multimodal

- Override Hub tag to `image-text-to-text` when needed.
- Confirm the recipe enables multimodal / image input flags for that image tag.
- Smoke-test with a tiny image + text request, not only `/v1/models`.

### Embeddings and rerankers

- Prefer Infinity/TEI specs from the catalogue — do not force chat-oriented vLLM unless the catalogue offers it for that model.
- Smoke-test `/v1/embeddings` or the server’s rerank route, not chat completions.
- Gateway registration should use embedding/rerank model types (see `ai-gateway/references/models.md`).

### Image tags and recipe drift

Recipes and GitHub issues often assume a **newer** vLLM/SGLang image than the catalogue default. If flags are rejected or the architecture is “unsupported” on the pinned tag:

1. Check the image tag in the chosen `spec`.
2. Bump to a catalogue-supported newer tag **or** the recipe’s known-good tag only after confirming it exists in the workspace’s allowed images / can be pulled.
3. Re-validate; lengthen startup probes after big image/model changes.

## Apply and verify

1. Take the chosen `deployments[].spec`.
2. Ensure `name` is unique in the workspace (or confirm update per `deploy-common.md`).
3. Apply hard-case tweaks (GPU util, sticky label, auto-shutdown) **before** first apply when the user asked for them.
4. `get_manifest_json_schema` for `service` if you edited heavily; always `validate_manifest`.
5. `apply_manifest` (approval flow). Never `tfy apply` in the terminal for this path.
6. `get_deployment` → `list_k8s_pods`. Startup is long (download + load) — do not declare failure in the first few minutes if probes are still progressing.
7. Hand off deep failures to `model-debug.md`.
8. Print links per `deployment-links.md` — console `{controlPlaneUrl}/deployments/{applicationId}` **and** the HTTP endpoint from `generate_deployment_endpoint`.

## Post-deploy product loop (smoke, Gateway, sticky, scale-to-0)

`apply_manifest` success is not “users can call the model.” Finish these when relevant. Links first (`deployment-links.md`), then smoke.

### 1. Smoke test

After pods are Ready, call the service endpoint from `generate_deployment_endpoint` (see `deployment-links.md`):

| Server / task | Minimal check |
|---|---|
| vLLM / SGLang chat | `GET /v1/models` then `POST /v1/chat/completions` with a one-token user message |
| Embeddings | `POST /v1/embeddings` with a short string |
| Rerank | server’s rerank route with 1 query + 2 docs |
| VLM | chat completions with a tiny image payload per server docs |

If smoke fails with 4xx/5xx, go to `model-debug.md` — do not register on Gateway yet.

### 2. Register on AI Gateway (optional but common)

Self-hosted models are consumed through a **self-hosted model provider account** (`provider-account/self-hosted-model` / `integration/model/self-hosted-model` — confirm exact types via `get_manifest_json_schema` + `list_providers`). Follow `ai-gateway/references/models.md`:

- Point the integration at the service’s OpenAI-compatible base URL.
- Set the correct `model_types` (`chat`, `embedding`, `rerank`, …).
- Use the served model id the server exposes (`/v1/models`), not only the HF repo name.
- `validate_manifest` → `apply_manifest` for the provider account.

### 3. Sticky sessions (prefix cache)

For multi-replica chat models that benefit from KV / prefix cache, enable sticky routing:

- Add label `tfy_sticky_session_header_name: <header>` (e.g. `x-truefoundry-sticky-session-id`) — see docs “sticky routing” / schema.
- Tell the client to send that header with a stable session id (conversation id).
- Warn: stickiness is **best-effort**; pods can move. Details in `networking.md`.

### 4. Scale-to-0 / autoscaling

For idle dev models, configure auto-shutdown / Elasti scale-to-0 and HPA metrics per `autoscaling.md`. Warn about **cold start** (image + weight load) when scaling from zero.

## NIM path

For NVIDIA NIM containers use `get_nim_deployment_specs` with `nimModelId`, `nvcrDockerRegistryProviderIntegrationFqn`, and `ngcApiKeySecretFqn`. Same apply/verify/smoke loop. Do not mix NIM inputs into `get_model_deployment_specs`.

## Classical ML (sklearn / XGBoost / …)

HuggingFace LLM catalogue specs are the wrong path for pickle/joblib/MLflow sklearn-style models.

1. Prefer TrueFoundry **Model Registry** / ML Repo model version deploy flows when the model was logged there — `search_docs` for “deploy model” / framework-specific deploy; use `get_manifest_json_schema` for the application type the docs specify.
2. If the user only has an artifact URI, deploy a **service** (or job) whose image runs their inference server (FastAPI, MLflow scoring, etc.) via `deploy-from-image.md` / `deploy-from-source.md`, not `get_model_deployment_specs`.
3. Do not force vLLM onto tabular/classical models.

## Checklist

- [ ] Did I resolve `workspaceId` from `list_workspaces`?
- [ ] Did I call `get_model_deployment_specs` (or NIM) before hand-writing a vLLM service — except classical ML?
- [ ] For gated models, did I pass a secret FQN rather than a raw token?
- [ ] If Hub tags looked wrong / `any-to-any`, did I retry with an explicit `pipelineTagOverride`?
- [ ] On small GPUs, did I consider lowering `--gpu-memory-utilization` in args/env (not a top-level field)?
- [ ] Did I prefer `isAvailableInWorkspace: true` GPU options?
- [ ] For architecture / “how does vLLM work” questions, did I use `model-serving-faq.md`?
- [ ] On API failure, did I attempt override / similar-model recovery?
- [ ] Did I `validate_manifest` → `apply_manifest` → verify pods?
- [ ] Did I print console + endpoint links per `deployment-links.md`?
- [ ] Did I smoke-test the matching route and offer Gateway / sticky / scale-to-0 when relevant?

For more info: `search_docs` with "deploying an LLM", "model catalogue", "sticky routing", "scale service to 0", "self hosted model".
