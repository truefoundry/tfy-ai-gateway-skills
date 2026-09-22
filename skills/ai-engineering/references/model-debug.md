---
name: model-debug
description: Debug a deployed model service (vLLM, SGLang, TRT-LLM, Infinity, TEI, NIM, …) — distinguish model download failures from server startup failures, pull logs/events/metrics, research GitHub issues and recipes, then propose a fixed service manifest and apply with approval. Read when a model deployment is Pending, CrashLooping, OOM, slow to become Ready, or returning inference errors.
---

Model services fail in layers. Diagnose the layer first, then research the specific model server, then patch the **service** manifest (these are ordinary services) and ask for approval to apply.

## Contents
- Identify it is a model deployment
- Layered triage
- Model download vs model server
- Research (GitHub, recipes, Reddit, docs)
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
| Ready but 4xx/5xx on `/v1/chat/completions` | Runtime config / template / max length | Server logs + research |
| Many model apps stuck together | Cluster / agent | `failure-modes/cluster-capacity.md`, `rollout-argocd.md` |

Always inspect **all** containers: init (`tfy-model-downloader` or similar) **and** the main server. Use `get_k8s_pod_logs` with `container=<name>` and `previous: true` on crashloops.

## Model download vs model server

### Download failed / stuck

Signals: long time in init; logs mentioning HuggingFace, `HF_TOKEN`, 401/403, gated repo, disk quota, `No space left`, PVC mount errors; pod never passes startup probe.

Check:

1. `list_application_events` / `list_k8s_events` for FailedMount / mount / disk.
2. Init container logs — auth vs network vs size.
3. Manifest `artifacts_download` and whether `huggingfaceHubTokenSecretFqn` / env `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` is present for gated models.
4. Cache volume size vs model weight size (large LLMs need tens–hundreds of GB).

Fixes to propose: attach/correct HF token secret, enlarge cache volume, fix storage class / mount (`failure-modes/volumes-storage.md`), confirm Hub URL/revision.

### Download succeeded, server failed

Signals: weights on disk / download logs completed; main container `CrashLoopBackOff` or `OOMKilled`; logs from vLLM/SGLang/Infinity engine.

Classify:

| Log / reason pattern | Likely fix direction |
|---|---|
| `OOMKilled` / CUDA OOM / `torch.OutOfMemoryError` | More / bigger GPUs, lower `gpu_memory_utilization`, smaller max model length, quant variant, TP size — regenerate via `get_model_deployment_specs` or edit resources/args |
| `ValueError` / unsupported architecture / missing multimodal | Wrong server or `pipeline_tag` — override tag and regenerate; or switch vLLM ↔ SGLang |
| Engine args rejected / unknown flag | Align args with the **image tag’s** docs; remove flags from an older recipe |
| NCCL / TP size errors | GPU count not matching `--tensor-parallel-size`; fix resources + args together |
| Startup probe killed (exit 137, events Unhealthy) | Lengthen probes — large models need long `initialDelaySeconds` / failure thresholds (`failure-modes/crashloop-oom-probes.md`) |
| Tokenizer / chat template errors | Mount or set chat template; check Hub tokenizer files |

Re-read applied resources with `get_applied_k8s_manifest` — catalogue recommendations and what actually runs can diverge after manual edits.

## Research (GitHub, recipes, Reddit, docs)

When the stack trace names a model server library, **search before guessing**:

1. **Official recipes** — https://recipes.vllm.ai/`<org>/<model>` for known-good flags/hardware.
2. **Support matrices** — vLLM supported models docs; SGLang backend docs; Infinity/TEI READMEs.
3. **GitHub issues** (web search) on the server repo, scoped to the model id / error string:
   - vLLM: `https://github.com/vllm-project/vllm/issues`
   - SGLang: `https://github.com/sgl-project/sglang/issues`
   - Infinity: `https://github.com/michaelfeil/infinity/issues`
   - TEI / TGI: HuggingFace inference repos
   - TensorRT-LLM / NIM: NVIDIA repos
4. **Reddit / HF discussions / release notes** for the exact error string + model id when GitHub is quiet.

Summarize the best matching issue/recipe (title + URL + what they changed). Translate that into a concrete TrueFoundry manifest edit (args, env, image tag, GPU, pipeline tag) — do not dump unrelated workarounds.

## Propose and apply a fix

Fixes are **service manifest** updates (same as any deployment):

1. Start from `get_application` → `activeDeployment.manifest` (full replace — `deploy-common.md`).
2. Prefer regenerating with `get_model_deployment_specs` (correct `pipelineTagOverride`, token, workspace) and merging user-specific bits (name, mounts, autoscaling) when the catalogue can produce a better baseline.
3. Otherwise surgically patch: resources, `image`, command/args, env, probes, `artifacts_download`.
4. `validate_manifest` → explain the diff to the user → `apply_manifest` (approval). For trivial “redeploy same spec” use `redeploy_application`.
5. Verify with pods + logs; for inference errors, suggest a minimal curl/OpenAI chat completion against the endpoint after Ready.

This same **diagnose → research → patch manifest → ask approval → apply → verify** loop applies to **any** service/job deployment when the user wants a fix, not only models — for non-models skip catalogue regeneration and edit the existing manifest.

## Checklist

- [ ] Did I confirm model-server labels / `artifacts_download` before using this playbook?
- [ ] Did I separate download failures from server runtime failures (init vs main container logs)?
- [ ] For CrashLoop, did I use `previous: true` and the correct `container`?
- [ ] Did I check GPU Pending / OOM / probe playbooks when those signals appeared?
- [ ] Did I search recipes + GitHub issues for the exact model/error before inventing flags?
- [ ] Did I propose a concrete manifest diff and apply only after approval?
- [ ] Did I verify pods/logs after the fix instead of stopping at apply?

For more info: `search_docs` with "deploying an LLM", "monitor your service", "model catalogue".
