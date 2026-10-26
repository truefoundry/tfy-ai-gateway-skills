---
name: model-deploy
description: Deploy an LLM, VLM, embedding or reranker from a HuggingFace URL or a registry transformers version — catalogue specs, recovery, apply, smoke test, Gateway, sticky, scale-to-0. Read before any "deploy this model / HF link / vLLM / SGLang" request. NIM and sklearn/XGBoost are in `model-deploy-nim-classical.md`.
---

Model deployments are ordinary **`type: service`** applications. `get_model_deployment_specs` is the starting point: it returns complete service manifests (server, image, env, GPU shape, `artifacts_download`, probes). Your job is to pick the right option, fix what the catalogue cannot see, apply, verify it serves, then finish the product loop.

## Inputs to collect

| Input | How |
|---|---|
| Target **workspace** | `list_workspaces` → `id` is `workspaceId` |
| **Already deployed?** | `list_applications` filtered by the user's name or the model name (catalogue specs name the service after the model id), target workspace only. If it exists you are updating — read **Creating or updating** in `deploy-common.md` before generating specs or asking about GPUs |
| Model source | HuggingFace URL `https://huggingface.co/<org>/<model>` **or** a registry `modelVersionFqn`. If the user gave only a name, confirm the exact `org/model` with a web search |
| HF token (gated/private Hub models) | `list_secrets` → take the secret's `fqn`. Never ask the user to paste the raw token into chat |
| Optional | Preferred server, GPU type, post-deploy intent (Gateway, sticky, scale-to-0) |

`list_workspaces`, `list_applications` and (for gated models) `list_secrets` are independent — call them in one parallel batch.

## Steps

### 1. Generate specs

```
get_model_deployment_specs
  workspaceId=<workspace.id>
  huggingfaceHubUrl=<HF url>                       # XOR modelVersionFqn
  huggingfaceHubTokenSecretFqn=tfy-secret://<fqn>  # gated/private Hub models only
  pipelineTagOverride=<tag>                        # only when the Hub tag is wrong/missing
```

Prefix the secret `fqn` with `tfy-secret://`. A bare FQN is treated as the raw token, so the Hub call fails with 401.

Never pass `pipelineTagOverride=auto`: on Hub URLs it equals omitting the param, and on registry versions it is taken literally and yields the wrong server. Pass a concrete task string from the table below.

The response is large and is saved to a sandbox file — extract only `name`, `deployments[].name`, `isAvailableInWorkspace`, `isTRTLLMEngineAvailable` and the chosen `spec` with one `jq`/program. Shape:

```yaml
data:
  - name: vLLM                       # model server
    deployments:
      - name: "1 x A10G (24 GB) GPU" # or "CPU"; MIG: "<n> x <gpu> (MIG <profile>)"
        isAvailableInWorkspace: true|false
        isTRTLLMEngineAvailable: true|false   # TRT-LLM only
        cost: ...
        spec:                        # complete type: service manifest
          type: service
          image: ...
          resources: ...
          artifacts_download: ...    # artifacts + cache_volume
          env: {GPU_MEMORY_UTILIZATION: '0.90', MAX_MODEL_LENGTH: ..., ...}
          ports: ...
          labels:
            tfy_model_server: vLLM
            huggingface_model_task: text-generation
            tfy_sticky_session_header_name: x-truefoundry-sticky-session-id
          workspace_fqn: ...
  - name: SGLang
    deployments: [...]
```

What the catalogue already did: `workspace_fqn` is always set. If the cluster has no base domain, ports come back `expose: false` with no public URL and no sticky label; on Ingress-based clusters the `huggingface_model_task`, `tfy_openapi_path` and sticky labels are removed. Do not re-add them.

### 2. Pipeline tags — which servers come back

The tag drives which servers are returned. A wrong tag gives empty options or a server that cannot load the weights.

| Modality | `pipelineTagOverride` | Servers returned |
|---|---|---|
| Chat / base LLM | `text-generation` | vLLM, SGLang, TRT-LLM (public, non-quantized, supported architectures only) |
| Seq2seq / encoder-decoder | `text2text-generation` | TGI only |
| Vision-language | `image-text-to-text` | vLLM, SGLang |
| Embeddings | `feature-extraction` or `sentence-similarity` | Infinity, TEI (vLLM if the architecture is supported) |
| Rerankers | `text-ranking` | Infinity, vLLM (vLLM only for CausalLM rerankers) |
| ASR / image generation | `automatic-speech-recognition` / `text-to-image` | as returned |
| Hub says `any-to-any`, unset or toolkit | Infer from the card architecture (Llama → `text-generation`, LLaVA/Qwen-VL → `image-text-to-text`, BGE → `feature-extraction`) | retry with the override |

Embedding tags reach Infinity/TEI only when the model is tagged `sentence-transformers`. If the response offers only MMS for an embedding model, do not deploy MMS — pick a sentence-transformers variant, or hand-write an Infinity/TEI service from a working embedding spec.

### 3. When the call fails — recover, do not stop

| Failure | Recovery |
|---|---|
| Wrong/missing tag (`any-to-any`, unset, empty options) | Retry with `pipelineTagOverride` from the table |
| Gated/private model, 401 | Retry with `huggingfaceHubTokenSecretFqn=tfy-secret://<fqn>` |
| Unsupported quantization method | Supported quant sibling or the non-quantized twin; regenerate |
| `does not have .safetensors or .bin weight files` / `does not contain a config.json` (GGUF-only or adapter-only repo) | Use the original safetensors repo, or an AWQ/GPTQ/FP8 safetensors sibling; regenerate |
| `Framework is not supported` / `Missing pipeline_tag and base_model` (registry) | The version needs `framework.type: transformers` with both `pipeline_tag` and `library_name`, or `framework.base_model` / `metadata.huggingface_model_url` pointing at a public, non-gated HF model. Have the user update the version ([docs](https://www.truefoundry.com/docs/deploying-an-llm-model-from-the-model-catalogue#making-llm-in-truefoundry-model-registry-deployable)) or deploy from the Hub URL. sklearn/XGBoost → `model-deploy-nim-classical.md` |
| Empty `data` / no deployments | Similar-model strategy: generate specs for a well-known sibling (same architecture), then replace model id / HF URL / served model name / artifact fields. Re-validate and tell the user what you borrowed |

### 4. Choose server and GPU

- Text LLMs: vLLM, then SGLang. Only pick a TRT-LLM option whose `isTRTLLMEngineAvailable` is `true`; options with `false` have no prebuilt engine and will not serve.
- VLMs: vLLM or SGLang — pick using the model's vLLM recipe / SGLang support list.
- Embeddings / rerankers: Infinity or TEI as returned; do not force a chat server.
- GPU: the smallest `isAvailableInWorkspace: true` option that fits. If the user named a GPU, match it by substring of `deployments[].name` or by `spec.resources.devices`. Never silently pick an unavailable option.
- `isAvailableInWorkspace` is only checked against node pools on AKS, generic clusters and GKE MIG shapes; on EKS and GKE it is always `true` and means the autoscaler may provision it, not that a node exists. If nothing is available, say which GPUs the catalogue wanted, check `list_cluster_addons` (`TFY_GPU_OPERATOR`, `KARPENTER`) for the GPU stack, and ask before using an unavailable shape (it may stay Pending — `failure-modes/pending-scheduling.md`). No tool lists nodes; give the user `kubectl get nodes -l nvidia.com/gpu.present=true` if inventory matters.
- When more than one viable path exists and the user did not specify, show a short comparison and confirm.

### 5. Check against recipes before locking

The catalogue cannot see everything. Check the HuggingFace card (tag, library, size, gated), [vLLM Recipes](https://recipes.vllm.ai/) at `https://recipes.vllm.ai/<org>/<model>`, and the server's support matrix. Fold compatible flags into the chosen `spec` without dropping `artifacts_download`, probes, labels or `workspace_fqn`. Cite the recipe or support-doc line when you override a catalogue default.

Recipes often assume a newer image than the catalogue's; if flags are rejected or the architecture is unsupported on the pinned tag, bump to a known-good tag that exists.

### 6. Tweak before the first apply

**GPU memory utilization on small GPUs** (the one place this lives; other files link here). Catalogue specs expose these as env vars — edit the env, not the command:

- vLLM `GPU_MEMORY_UTILIZATION` (default `0.90`; try `0.80`–`0.85` on small GPUs such as T4/L4).
- SGLang `MEM_FRACTION_STATIC` (catalogue sets 0.75–0.85 by GPU memory; lower by 0.05).
- Both: `MAX_MODEL_LENGTH` (catalogue caps it at 8192).

Never add `--gpu-memory-utilization` to an SGLang command, and never add a `gpu_memory_utilization:` key at the service root. Also consider a quantized variant or a bigger GPU / more GPUs. CUDA OOM at load is per replica, so more replicas do not help; container `OOMKilled` is a memory-limit problem (`model-debug.md`).

**Name:** `ports[].host` was generated from the spec's `name`. If you change the name, regenerate the host — **Exposing a port** in `deploy-common.md`.

**VLM:** confirm the recipe's multimodal flags work on that image tag.

### 7. Apply and verify

1. Check the chosen spec's `name` with `list_applications` in the target workspace (reuse that result if it is still in the conversation; otherwise call it again) — it must not already exist unless you are updating. Updating replaces the whole manifest (`deploy-common.md`).
2. `validate_manifest` (use `get_manifest_json_schema` for `service` first if you edited heavily) → `apply_manifest` (approval). Never `tfy apply` in the terminal.
3. `get_deployment` → `get_application_state`. Startup is long (download + load); do not declare failure while probes are still progressing. Deep failures → `model-debug.md`.
4. Print the links per `deployment-links.md`: the console link and the endpoint from the deployed manifest's `ports`.

### 8. Post-deploy loop

`apply_manifest` success is not "users can call the model". Finish what applies.

**Smoke test** once pods are Ready, against the endpoint from `deployment-links.md`. No exposed port means no public URL — say so.

| Server / task | Minimal check |
|---|---|
| vLLM / SGLang chat | `GET /v1/models`, then `POST /v1/chat/completions` with a one-token message |
| Embeddings | `POST /v1/embeddings` with a short string |
| Rerank | the server's rerank route with 1 query + 2 docs |
| VLM | chat completions with a tiny image |

If smoke fails, go to `model-debug.md` — do not register on Gateway yet.

**Gateway registration:** add the service as a self-hosted model per `ai-gateway/references/models.md` — OpenAI-compatible base URL, the right model type (chat / embedding / rerank), and the served model id from `/v1/models`.

**Sticky sessions** (prefix-cache affinity for multi-replica chat): catalogue vLLM/SGLang/TRT-LLM/NIM specs already carry `tfy_sticky_session_header_name: x-truefoundry-sticky-session-id` when the cluster has a base domain — check it is present; add it only to hand-written specs. Tell the client to send `x-truefoundry-sticky-session-id: <conversation id>`. Stickiness is best-effort (`networking.md`).

**Scale-to-0 / autoscaling** for idle dev models per `autoscaling.md`; warn about cold start (image pull + weight load).

## Checklist

- [ ] Checked whether the model is already deployed, then called `get_model_deployment_specs` before hand-writing anything?
- [ ] Token passed as `tfy-secret://<fqn>`; tag override concrete, never `auto`?
- [ ] Picked `isAvailableInWorkspace: true`, and TRT-LLM only with `isTRTLLMEngineAvailable: true`?
- [ ] On small GPUs, lowered the GPU memory env var?
- [ ] Applied, checked `get_application_state`, printed links, smoke-tested, offered Gateway / sticky / scale-to-0?

For more info: `search_docs` with "deploying an LLM", "model catalogue", "sticky routing", "scale service to 0", "self hosted model".
