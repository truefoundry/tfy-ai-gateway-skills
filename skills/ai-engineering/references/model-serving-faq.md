---
name: model-serving-faq
description: Common questions about how TrueFoundry deploys and runs model servers (especially vLLM) — architecture, GPUs, download/storage, autoscaling, networking, image upgrades, and platform defaults. Read when users ask how model serving works, not only how to deploy one model.
---

Use this for **architecture / how-it-works** questions about model serving on TrueFoundry. For “deploy this HF URL” use `model-deploy.md`. For crashes use `model-debug.md`. Ground answers in the live tenant when possible (`get_application`, catalogue specs) — these are platform defaults, not a promise that every custom manifest matches.

## Contents
- How is vLLM / a model deployed?
- How are GPUs allocated?
- How do model download, storage, and mounting work?
- How does autoscaling work for models?
- What is the networking / inference path?
- How do vLLM (image) upgrades work?
- What platform defaults sit on top of stock vLLM?
- Checklist

## How is vLLM / a model deployed?

- Each model is its own TrueFoundry **`type: service`** Application.
- That maps to a dedicated Kubernetes workload with a **single** model-server container (vLLM: `vllm.entrypoints.openai.api_server`, typically port **8000**).
- TrueFoundry does **not** run a shared multi-model vLLM fleet on this path.
- Multi-GPU uses **tensor parallelism inside the same pod** (`--tensor-parallel-size`), not one pod per GPU shard.
- Recommended specs come from `get_model_deployment_specs` / `get_nim_deployment_specs` (catalogue fills a server template such as `vllm.yaml`) and are applied as a normal service via `apply_manifest`.

## How are GPUs allocated?

- Default recommended path requests **dedicated NVIDIA GPUs** (`nvidia_gpu`).
- GPU count is typically a **power of 2** sized for tensor parallelism from model size and GPU memory.
- **MIG / fractional GPUs** are supported when enabled on the workspace / node pools.
- **GPU timeslicing** exists as a platform capability but is **not** part of the default catalogue vLLM recommendations.
- This path does **not** co-locate multiple models on one full GPU in a single pod.

## How do model download, storage, and mounting work?

- Weights are downloaded **into the cluster** — no intermediate object-storage staging on the default catalogue path.
- **HuggingFace** → `huggingface-hub` artifact type (Hub pull).
- **TrueFoundry model versions** → `truefoundry-artifact` from the artifact store.
- Artifacts land under `/opt/truefoundry`; the server is pointed at the local path (commonly via `MODEL_ID` / equivalent).
- If the cluster has a suitable **RWX** storage class, a **cache PVC** is attached so downloads survive restarts; otherwise **emptyDir** + init container (`tfy-model-downloader`).
- vLLM’s own cache is typically under `/opt/truefoundry/.cache/vllm`.
- Without a working cache volume, every rollout re-downloads — large models can take **1–2+ hours** per attempt (`model-debug.md`, `failure-modes/volumes-storage.md`).

## How does autoscaling work for models?

- Same path as other services: **KEDA** / platform autoscaling (`autoscaling.md`).
- Catalogue recommendations often default to a **fixed replica count of 1**.
- Users can enable CPU, RPS (Istio/Envoy), cron, queue-based triggers, and **scale-to-0** / auto-shutdown.
- TrueFoundry does **not** currently scale from vLLM-native signals such as KV-cache utilization or waiting-queue depth.
- Changing min/max replicas is a **new deployment revision** and follows **`rollout_strategy`** — see `rollout-strategy.md` (GPU models with maxSurge 0% can briefly take the only pod down).

## What is the networking / inference path?

Typical path:

**Client → Istio VirtualService / Ingress (cluster base domain) → ClusterIP Service (e.g. port 8000) → Pod → OpenAI-compatible model server**

- Sticky sessions (label `tfy_sticky_session_header_name`) improve prefix-cache affinity (`networking.md`).
- Registered on the AI Gateway as a **self-hosted** OpenAI-compatible model (vLLM base often needs `/v1`). See `model-deploy.md` post-deploy loop and `ai-gateway/references/models.md`.
- Always resolve the real URL with `deployment-links.md` / `generate_deployment_endpoint`.

## How do vLLM (image) upgrades work?

- **New** catalogue deploys pick up the **current** recommended vLLM (or other server) image from the template.
- **Existing** apps keep their pinned image until someone edits the image tag (or regenerates specs and merges carefully) and applies — they do **not** auto-bump.
- Prefer a concrete tag over `latest`. After bumping, expect longer startup; lengthen probes if needed (`model-debug.md`).
- If a model needs a newer server than the catalogue default (e.g. NVFP4 only on a newer/nightly tag), say so, point at recipes/GitHub, and patch **image tag + args** from the live manifest — do not invent unsupported claims.

## What platform defaults sit on top of stock vLLM?

Catalogue / recommended deployments commonly add (when compatible):

- Prefix caching
- Expert parallelism for MoE on multi-GPU
- Dtype selection from GPU architecture (float16 vs bfloat16)
- Lower GPU memory utilization for very large (≥70B) models (via **args/env**, not a top-level manifest field)
- Chat-template mounting when needed
- Startup probes sized for download + load time
- **Conservative rolling updates** — often **max surge 0% / max unavailable 25%** (important for GPU; see `rollout-strategy.md`)
- Sticky sessions for prefix-cache affinity
- Parallel image prefetch alongside model download

Confirm on the live `activeDeployment.manifest` before asserting a specific default for a tenant’s app.

## Checklist

- [ ] Did I answer architecture from this FAQ + the live manifest, not from memory of one customer cluster?
- [ ] For deploy/fix actions, did I still use `model-deploy.md` / `model-debug.md`?
- [ ] When replicas or rollout came up, did I open `rollout-strategy.md` / `autoscaling.md`?
- [ ] Did I avoid claiming vLLM-native autoscaling metrics or a shared multi-model fleet?

For more info: `search_docs` with "deploying an LLM", "model catalogue", "rollout strategy", "autoscaling", "sticky routing".
