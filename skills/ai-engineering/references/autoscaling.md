---
name: autoscaling
description: Configure HPA / KEDA-style metrics autoscaling and Elasti scale-to-0 (auto-shutdown) on services and async-services. Read when the user asks to scale replicas, scale to zero, idle shutdown, or right-size cost.
---

Autoscaling on TrueFoundry services has two layers that are easy to confuse:

1. **1 → N** — HPA/KEDA-style autoscaling on CPU, memory, RPS, or queue depth (async).
2. **1 ↔ 0** — Elasti **scale-to-0 / auto-shutdown** when idle; cold-starts on the next request.

Pause/resume is a **manual** third path — do not substitute it when the user asked for automatic idle shutdown.

## Contents
- Collect intent
- Scale 1→N (autoscaling metrics)
- Scale-to-0 (Elasti / auto-shutdown)
- Model-specific warnings
- Cost / right-sizing
- Apply pattern
- Checklist

## Collect intent

| User wants | Configure |
|---|---|
| More replicas under load | `autoscaling` min/max + metrics (CPU%, memory%, RPS, …) |
| Idle → zero, wake on traffic | Auto-shutdown / scale-to-0 idle timeout (minutes) |
| Stop billing until I come back | Pause application (manual) — only if they want manual control |
| Async workers on queue depth | Async-service autoscaling metrics (NATS/queue — per schema) |

Always edit the **live** `activeDeployment.manifest` (`deploy-common.md`). Field names vary by schema version — call `get_manifest_json_schema` for `service` / `async-service` and use the documented property names (UI often labels this “Auto Shutdown” + “Autoscaling”).

## Scale 1→N (autoscaling metrics)

Typical knobs (confirm in schema):

- `minReplicas` / `maxReplicas` (or equivalent)
- Target metric: CPU utilization %, memory %, requests/sec, concurrent requests, or async queue metrics
- Stabilization / cooldown if present

Rules:

- Set `minReplicas ≥ 1` unless scale-to-0 is also enabled and intended.
- Max replicas must fit workspace/cluster GPU or CPU quota — otherwise Pending (`failure-modes/pending-scheduling.md`).
- For GPU model servers, scaling out multiplies **GPU count × replicas**; confirm capacity first.

## Scale-to-0 (Elasti / auto-shutdown)

Docs: scale service to 0 / Elasti.

- Configure **idle timeout** (e.g. 10–15 minutes with no requests).
- Elasti handles **0 ↔ 1**; HPA handles **1 → N**. Both can coexist.
- **Cold start**: next request waits for schedule + image pull + (for models) weight load. Say this explicitly for LLM services — cold start can be minutes.
- Best suited for **dev / low-traffic** workloads. Prefer minReplicas=1 for latency-critical prod.

## Model-specific warnings

- Scale-to-0 + large models = painful cold starts; suggest keeping minReplicas=1 in prod only when idle cost matters more than latency.
- Sticky sessions (`networking.md`) reshuffle on scale-up/down — prefix-cache benefits are best-effort.
- Do not scale maxReplicas above available GPUs in the workspace.
- **Changing min/max replicas applies a new deployment revision.** Behavior of the old pod (including brief downtime) depends on `rollout_strategy` — especially catalogue defaults with **max surge 0%**. Read `rollout-strategy.md` before telling the user a replica-only edit is “safe” or a “bug”.

## Cost / right-sizing

When the user asks to reduce cost:

1. Read current replicas, GPU type, and utilization (`list_k8s_pods`, metrics tools per `tools.md`).
2. Prefer: smaller GPU shape via `get_model_deployment_specs`, lower maxReplicas, scale-to-0 for idle digests, or pause for unused apps.
3. Do not silently destroy prod capacity — confirm environment.

## Apply pattern

1. `get_application` → copy full manifest.
2. Patch autoscaling / auto-shutdown fields only.
3. `validate_manifest` → explain → `apply_manifest` (approval).
4. Verify: replica count moves under load/idle as expected; for scale-to-0, confirm idle behavior without declaring failure during cold start.

## Checklist

- [ ] Did I distinguish HPA (1→N), Elasti (0↔1), and pause/resume?
- [ ] Did I use schema field names from `get_manifest_json_schema`?
- [ ] For models, did I warn about GPU × replicas and cold start?
- [ ] Did I edit the live manifest and apply only with approval?

For more info: `search_docs` with "scale service to 0", "autoscaling", "pause resume service".
