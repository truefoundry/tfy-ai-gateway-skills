---
name: model-debug
description: Debug a deployed model service (vLLM, SGLang, TRT-LLM, Infinity, TEI, NIM, …) — distinguish download vs server failures, handle empty events on StatefulSets, research recipes/GitHub, then propose and apply a fixed service manifest. Read when a model deployment is Pending, CrashLooping, OOM, slow to become Ready, or returning inference errors.
---

Model services fail in layers. Diagnose the layer first, then research the specific model server, then patch the **service** manifest (these are ordinary services) and ask for approval to apply.

## Contents
- Identify it is a model deployment
- Layered triage
- Empty events / StatefulSet caveat
- Model download vs model server
- Hard cases (GPU util, probes, wrong tag, image drift)
- Research (GitHub, recipes, docs)
- Propose and apply a fix
- Checklist

## Identify it is a model deployment

From `get_application` / active deployment manifest, look for:

- `artifacts_download` with `huggingface-hub` or `truefoundry-artifact`
- Labels such as `truefoundry.com/model-server` (vLLM, SGLang, …) and `truefoundry.com/huggingface-model-task`
- Image names containing `vllm`, `sglang`, `text-embeddings-inference`, `infinity`, `tensorrt_llm`, `nim`

If those are absent, use generic `troubleshooting.md` playbooks. If present, continue here **and** still use the shared failure-mode files for Pending / OOM / ImagePull.

## Layered triage

Follow `troubleshooting.md` Phase 1–2 first (`clusterId`, namespace, `list_k8s_pods`).

Then split on evidence:

| Observation | Layer | Next |
|---|---|---|
| `Pending` / FailedScheduling / GPU | Schedule | `failure-modes/pending-scheduling.md` |
| `ImagePullBackOff` | Image | `failure-modes/image-pull.md` |
| Init / early logs: download, HF Hub, 401, disk, PVC | **Model download** | Section below |
| Download finished; main container restarting; vLLM/SGLang stack traces | **Model server** | Section below |
| Ready but 4xx/5xx on `/v1/chat/completions` or embeddings | Runtime config / template / max length | Server logs + research |
| Many model apps stuck together | Cluster / agent | `failure-modes/cluster-capacity.md`, `rollout-argocd.md` |

Always inspect **all** containers: init (`tfy-model-downloader` or similar) **and** the main server. Use `get_k8s_pod_logs` with `container=<name>` and `previous: true` on crashloops.

## Empty events / StatefulSet caveat

**Do not treat empty `list_application_events` as healthy.**

Some model (and other) workloads are backed by **StatefulSets**. Application-scoped event APIs can return **no events** even while pods are CrashLooping. When events are empty or suspiciously quiet:

1. Call `list_k8s_events` for the pod/namespace (and `get_k8s_pod_logs` with `previous: true`).
2. Read `list_k8s_pods` `reason` / container state — that remains authoritative.
3. Say that application events may be incomplete for this workload shape; continue diagnosis from pod logs and cluster events.

Never conclude “no problems” from an empty event list alone.

## Model download vs model server

### Download failed / stuck

Signals: long time in init; logs mentioning HuggingFace, `HF_TOKEN`, 401/403, gated repo, disk quota, `No space left`, PVC mount errors; pod never passes startup probe.

Check:

1. `list_k8s_events` / `list_application_events` for FailedMount / mount / disk (prefer k8s events if application events are empty).
2. Init container logs — auth vs network vs size.
3. Manifest `artifacts_download` and whether HF token secret / env is present for gated models.
4. Cache volume size vs model weight size (large LLMs need tens–hundreds of GB).

Fixes: attach/correct HF token secret FQN, enlarge cache volume, fix storage class / mount (`failure-modes/volumes-storage.md`), confirm Hub URL/revision.

### Download succeeded, server failed

Signals: weights on disk / download logs completed; main container `CrashLoopBackOff` or `OOMKilled`; logs from vLLM/SGLang/Infinity engine.

Classify:

| Log / reason pattern | Likely fix direction |
|---|---|
| Container `reason: OOMKilled` (cgroup / memory limit) | Raise **memory** `resources` limits/requests — not GPU util. See `failure-modes/crashloop-oom-probes.md` |
| CUDA OOM / `torch.OutOfMemoryError` / GPU OOM in logs (pod may still show CrashLoop, not always `OOMKilled`) | Lower `--gpu-memory-utilization` (or equivalent) in **command/args or env** (especially from ~0.90 on small GPUs), smaller max length, quant variant, more/bigger GPUs, TP size — regenerate via `get_model_deployment_specs` or edit args/env/resources |
| `ValueError` / unsupported architecture / missing multimodal | Wrong server or `pipeline_tag` — override tag and regenerate; or switch vLLM ↔ SGLang |
| Engine args rejected / unknown flag | Align args with the **image tag’s** docs; bump image tag or remove flags from a newer recipe |
| NCCL / TP size errors | GPU count not matching `--tensor-parallel-size`; fix resources + args together |
| Startup probe killed (exit 137, events Unhealthy) | Lengthen probes — large models need long `initialDelaySeconds` / failure thresholds (`failure-modes/crashloop-oom-probes.md`). Corroborate exit 137 before calling it OOM |
| Tokenizer / chat template errors | Mount or set chat template; check Hub tokenizer files |

Re-read applied resources with `get_applied_k8s_manifest` — catalogue recommendations and what actually runs can diverge after manual edits.

## Hard cases (GPU util, probes, wrong tag, image drift)

1. **Small-GPU CUDA OOM at load** — treat default `--gpu-memory-utilization ≈ 0.90` (in args/env, not a top-level manifest field) as a first suspect; try 0.70–0.80 before only scaling GPUs. See `model-deploy.md`. Do not confuse with container `OOMKilled`.
2. **Wrong Hub task** — regenerate with `pipelineTagOverride` from the modality table in `model-deploy.md`.
3. **Probe vs OOM** — exit 137 + Unhealthy probe events often means slow startup, not memory; lengthen probes first when download/load logs look healthy.
4. **Recipe newer than image** — bump vLLM/SGLang image tag carefully; re-validate; expect longer pull + startup.
5. **Inference-only failures** (Ready but bad responses) — check served model id, max tokens, chat template, sticky header mismatch, Gateway base URL pointing at wrong path.

## Research (GitHub, recipes, docs)

When the stack trace names a model server library, **search before guessing**:

1. **Recipes** — https://recipes.vllm.ai/`<org>/<model>`
2. **Support matrices** — vLLM / SGLang / Infinity / TEI docs
3. **GitHub issues** scoped to model id + error string:
   - vLLM: `https://github.com/vllm-project/vllm/issues`
   - SGLang: `https://github.com/sgl-project/sglang/issues`
   - Infinity: `https://github.com/michaelfeil/infinity/issues`
   - TEI / TGI / TensorRT-LLM / NIM as applicable
4. HF discussions / release notes when GitHub is quiet

Summarize the best matching issue/recipe (title + URL + what they changed). Translate into a concrete TrueFoundry manifest edit — do not dump unrelated workarounds.

## Propose and apply a fix

Fixes are **service manifest** updates:

1. Start from `get_application` → `activeDeployment.manifest` (full replace — `deploy-common.md`).
2. Prefer regenerating with `get_model_deployment_specs` (correct `pipelineTagOverride`, token, workspace) and merging user-specific bits (name, mounts, autoscaling, sticky labels) when the catalogue can produce a better baseline.
3. Otherwise surgically patch only real service fields: `resources`, `image`, command/args, env, probes, `artifacts_download`. To change GPU memory fraction, edit the **server flag in args/env** (e.g. `--gpu-memory-utilization`) — never invent a top-level `gpu_memory_utilization` manifest key.
4. `validate_manifest` → explain the diff → `apply_manifest` (approval). For trivial “redeploy same spec” use `redeploy_application`.
5. Verify with pods + logs (+ `list_k8s_events` if application events stay empty). For inference errors, re-run the smoke curl from `model-deploy.md`.

This same **diagnose → research → patch manifest → ask approval → apply → verify** loop applies to **any** service/job deployment when the user wants a fix — for non-models skip catalogue regeneration.

## Checklist

- [ ] Did I confirm model-server labels / `artifacts_download` before using this playbook?
- [ ] Did I separate download failures from server runtime failures (init vs main)?
- [ ] For CrashLoop, did I use `previous: true` and the correct `container`?
- [ ] If `list_application_events` was empty, did I fall back to `list_k8s_events` / pod logs?
- [ ] Did I separate container `OOMKilled` (memory limits) from CUDA OOM (args/env GPU util)?
- [ ] Did I patch `--gpu-memory-utilization` via args/env (not a fake top-level field), and consider probes / pipeline tag / image tag before inventing flags?
- [ ] Did I search recipes + GitHub for the exact model/error?
- [ ] Did I propose a concrete manifest diff and apply only after approval?
- [ ] Did I verify pods/logs (and smoke test) after the fix?

For more info: `search_docs` with "deploying an LLM", "monitor your service", "model catalogue".
