---
name: model-debug
description: Debug a deployed model service (vLLM, SGLang, TRT-LLM, TGI, Infinity, TEI, NIM, …) — tell download failures from server failures, find the downloader's logs, handle empty application events, research recipes/GitHub, then propose and apply a fixed service manifest. Read when a model deployment is Pending, CrashLooping, OOM, slow to become Ready, or returning inference errors.
---

Model services fail in layers. Diagnose the layer first, then research the specific model server, then patch the **service** manifest (these are ordinary services) and ask for approval to apply.

## Identify it is a model deployment

From `get_application` (active deployment manifest), treat it as a model deployment if any of these is present: `artifacts_download` (`huggingface-hub` or `truefoundry-artifact`), label `tfy_model_server` (vLLM, SGLang, TRT-LLM, TGI, Infinity, TEI, NIM, …) or `nvidia_nim_task`, or a model-server image (`vllm`, `sglang`, `text-embeddings-inference`, `infinity`, `tensorrt_llm`, `nim`). `huggingface_model_task` may be missing on Ingress-based clusters.

If none is present, use the generic `troubleshooting.md` playbooks. If present, continue here **and** still use the shared failure-mode files for Pending / OOM / ImagePull.

## Layered triage

Follow `troubleshooting.md` Phase 1–2 first (`get_application_state`). Then split on evidence:

| Observation | Layer | Next |
|---|---|---|
| `Pending` / FailedScheduling / GPU | Schedule | `failure-modes/pending-scheduling.md` |
| `ImagePullBackOff` | Image | `failure-modes/image-pull.md` |
| Download logs: HF Hub, 401, disk, PVC; or no new pods yet | **Model download** | Section below |
| Download finished; main container restarting; engine stack traces | **Model server** | Section below |
| Ready but 4xx/5xx on `/v1/chat/completions` or embeddings | Runtime config / template / max length | Server logs + research |
| Many model apps stuck together | Cluster / agent | `failure-modes/cluster-capacity.md`, `failure-modes/rollout-argocd.md` |

Read logs with `get_logs` (`applicationId`, plus `podName` and `containerName`); on crashloops, use a window ending just after the container's `lastState.finishedAt`.

## Model download vs model server

### Where the download runs

Check `artifacts_download.cache_volume` in the manifest — there are two download paths:

- **No `cache_volume`:** an init container `download-models` in the service pod. Read it with `get_logs podName=<pod> containerName=download-models`.
- **`cache_volume` set:** no init container. A PreSync Argo Workflow `downloader-<deploymentId>` downloads into the PVC `<app>-artifacts-volume` before any new service pod is created, so no new pods during the download is expected, not a stall. Its pods carry the application label: `get_logs applicationId=<id> podNamesRegex=downloader-<deploymentId>.* containerName=main` (`deploymentId` from `get_application` → `lastDeployment`). Pods are deleted on success and kept on failure; the Workflow itself is deleted 300 s after it finishes.

### Empty events caveat

`list_application_events` only returns events for objects named after the application. Events for the downloader workflow (`downloader-<deploymentId>`) and the cache PVC (`<app>-artifacts-volume`) never appear there. **Do not treat empty events as healthy.** Diagnose from `get_application_state` (container `state` / `reason` / `lastState`) and logs; if PVC or workflow events matter, give the user `kubectl get events -n <workspace> --field-selector involvedObject.name=<app>-artifacts-volume`.

### Download failed / stuck

Signals: logs mentioning HuggingFace, `HF_TOKEN`, 401/403, gated repo, `No space left`, mount errors; pod never passes its startup probe.

Check, in one parallel batch where you can: downloader logs (above), `list_application_events` for FailedMount on the service pod, and the manifest's `artifacts_download` and HF token env.

Fixes:

- Gated model: the token secret must be referenced (`secrets.md`); regenerating specs needs `huggingfaceHubTokenSecretFqn=tfy-secret://<fqn>` (`model-deploy.md`).
- Disk full: raise `artifacts_download.cache_volume.cache_size` (GB) to more than 2× the model size. It can only grow; `storage_class` cannot be changed on an existing application.
- Mount / storage class problems: `failure-modes/volumes-storage.md`.
- Wrong repo or revision: confirm the Hub URL / revision.

### Download succeeded, server failed

Signals: download logs completed; main container `CrashLoopBackOff` or `OOMKilled`; engine logs from vLLM/SGLang/Infinity.

| Log / reason pattern | Fix direction |
|---|---|
| Container `reason: OOMKilled` (memory limit) | Raise **memory** `resources` — not GPU memory. `failure-modes/crashloop-oom-probes.md` |
| CUDA OOM / `torch.OutOfMemoryError` (pod may show CrashLoop, not `OOMKilled`) | See **GPU memory utilization on small GPUs** in `model-deploy.md` |
| `ValueError` / unsupported architecture / missing multimodal | Wrong server or tag — regenerate with `pipelineTagOverride` (table in `model-deploy.md`), or switch vLLM ↔ SGLang |
| Engine args rejected / unknown flag | Align args with the **image tag's** docs; bump the tag or drop flags from a newer recipe |
| NCCL / tensor-parallel errors | GPU count does not match `--tensor-parallel-size`; fix resources and args together |
| Startup probe killed (exit 137, Unhealthy events) | Lengthen probes (`failure-modes/crashloop-oom-probes.md`). Exit 137 with healthy load logs usually means slow startup, not memory — corroborate before calling it OOM |
| Tokenizer / chat template errors | Mount or set a chat template; check Hub tokenizer files |
| Ready but bad responses | Served model id, max tokens, chat template, sticky header, Gateway base URL path |

Compare with `get_applied_k8s_manifest` — what runs can diverge from the catalogue spec after manual edits.

## Research (GitHub, recipes, docs)

When the stack trace names a model server library, search before guessing:

1. Recipes — `https://recipes.vllm.ai/<org>/<model>`
2. Support matrices — vLLM / SGLang / Infinity / TEI docs
3. GitHub issues scoped to model id + error string: `https://github.com/vllm-project/vllm/issues`, `https://github.com/sgl-project/sglang/issues`, `https://github.com/michaelfeil/infinity/issues`, and TEI / TGI / TensorRT-LLM / NIM as applicable
4. HF discussions / release notes when GitHub is quiet

Summarize the best match (title + URL + what they changed) and translate it into a concrete manifest edit.

## Propose and apply a fix

1. Start from `get_application` → `activeDeployment.manifest` (a full replace — `deploy-common.md`).
2. Where the catalogue can give a better baseline, regenerate with `get_model_deployment_specs` and merge the user's bits (name, mounts, autoscaling, sticky labels). **Keep the live `artifacts_download.cache_volume.storage_class` and never lower `cache_size`** — the apply is rejected otherwise. Moving to a different storage class means deleting and recreating the app; ask the user first.
3. Otherwise patch only real service fields: `resources`, `image`, command/args, env, probes, `artifacts_download`. GPU memory fraction is an env var, not a manifest field.
4. `validate_manifest` → explain the diff → `apply_manifest` (approval). For "redeploy the same spec" use `redeploy_application`.
5. Verify with `get_application_state` + logs; for inference errors re-run the smoke test from `model-deploy.md`.

The same diagnose → research → patch → approve → apply → verify loop works for any service or job; for non-models skip regeneration.

## Checklist

- [ ] Confirmed it is a model deployment (labels / `artifacts_download` / image)?
- [ ] Checked `cache_volume` to know whether the download runs in `download-models` or the `downloader-<deploymentId>` workflow, and read the right logs?
- [ ] Did not read empty `list_application_events` as healthy?
- [ ] Separated container `OOMKilled` (memory limit) from CUDA OOM (GPU memory env)?
- [ ] Considered probes, pipeline tag and image tag before inventing engine flags; searched recipes + GitHub?
- [ ] When merging a regenerated spec, kept `storage_class` and did not shrink `cache_size`?
- [ ] Proposed a concrete diff, applied only after approval, and verified?

For more info: `search_docs` with "deploying an LLM", "monitor your service", "model catalogue".
