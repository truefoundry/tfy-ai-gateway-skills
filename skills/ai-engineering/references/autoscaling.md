---
name: autoscaling
description: Configure metric-based autoscaling (replicas min/max on CPU, RPS, cron or queue) on services and async-services, and Elasti scale-to-0 (auto_shutdown) on services. Read when the user asks to scale replicas, scale to zero, idle shutdown, or right-size cost.
---

Autoscaling on TrueFoundry has two layers that are easy to confuse:

1. **1 → N** — `replicas` as an autoscaling object, driven by one metric.
2. **1 ↔ 0** — Elasti scale-to-0 (`auto_shutdown`) when idle; cold-starts on the next request.

Pause/resume (`pause_application` / `resume_application`) is a **manual** third path — do not substitute it when the user asked for automatic idle shutdown.

## Contents
- Collect intent
- Scale 1→N
- Scale-to-0
- Model-specific warnings
- Cost / right-sizing
- Apply pattern
- Checklist

## Collect intent

| User wants | Configure |
|---|---|
| More replicas under load | `replicas: {min_replicas, max_replicas, metrics}` |
| Idle → zero, wake on traffic | `auto_shutdown: {wait_time: <seconds>}` (service only) |
| Stop billing until I come back | `pause_application` (manual) — only if they want manual control |
| Async workers on queue depth | `replicas.metrics` of the queue type matching `worker_config.input_config.type` |

Always edit the **live** manifest (see **Apply pattern**). Take field names from `get_manifest_json_schema` for `service` / `async-service`; the UI labels these "Autoscaling" and "Auto Shutdown".

## Scale 1→N

Autoscaling lives in `replicas`: a fixed integer, or `{min_replicas, max_replicas, polling_interval?, metrics}` where `metrics` is one object. There is no `autoscaling` field — an `autoscaling:` block passes validation and is silently ignored.

```yaml
replicas:
  min_replicas: 1
  max_replicas: 3
  metrics:
    type: cpu_utilization
    value: 70
```

Metric types (`replicas.metrics.type`):

- **service:** `cpu_utilization` (`value` 1–100), `rps` (`value` > 0), `cron` (`start`, `end`, `timezone`, `desired_replicas?`).
- **async-service:** `sqs` / `nats` / `kafka` / `amqp`, which must match `worker_config.input_config.type`, or `cron`.

There is no memory, concurrency or cooldown setting; the only timing knob is `polling_interval` (seconds, default 30). Write `min_replicas` and `max_replicas` explicitly — `validate_manifest` lists both as required.

Rules:

- `min_replicas` must be ≥ 1 for `cpu_utilization` and `rps`; apply rejects 0.
- `max_replicas` must fit workspace/cluster GPU or CPU quota — otherwise Pending (`failure-modes/pending-scheduling.md`).
- For GPU model servers, scaling out multiplies **GPU count × replicas**; confirm capacity first.

## Scale-to-0

- Scale-to-0 is `auto_shutdown: {wait_time: <seconds>}`. The unit is **seconds**, not minutes (900 = 15 min, the default; max 604800). The docs and UI say minutes, so convert before writing — `wait_time: 15` scales to zero after 15 seconds.
- `auto_shutdown` exists only on `service`; on an async-service it is silently ignored. It needs the Elasti addon on the cluster and is rejected with `canary` / `blue_green` rollout strategies.
- When `replicas` is an autoscaling object, its `metrics.type` must be `rps`; apply rejects any other metric with `auto_shutdown`. If the user asked for another metric plus scale-to-0, say they conflict and ask for an RPS target or which to drop; never pick the value yourself.
- Elasti handles **0 ↔ 1**; the autoscaler handles **1 → N**. Both can coexist.
- **Cold start**: the next request waits for schedule + image pull + (for models) weight load. Say this explicitly for LLM services — cold start can be minutes.
- Best suited for dev / low-traffic workloads. Prefer `min_replicas: 1` without `auto_shutdown` for latency-critical prod.

## Model-specific warnings

- Scale-to-0 + large models = painful cold starts; suggest scale-to-0 in prod only when idle cost matters more than latency.
- Sticky sessions (`networking.md`) reshuffle on scale-up/down — prefix-cache benefits are best-effort.
- Do not scale `max_replicas` above available GPUs in the workspace.
- A replica-count or autoscaling-bounds edit creates a new deployment version but usually leaves the pod template unchanged, so pods are scaled, not replaced. Pods are replaced when the pod template changes (image, env, resources, probes, labels). Some replica edits do change it: moving to or from `replicas: 1` on a CPU-only on-demand service in a production environment toggles a do-not-disrupt annotation. When a user reports pods replaced after a replica edit, read `rollout-strategy.md` before calling it safe or a bug.

## Cost / right-sizing

When the user asks to reduce cost:

1. Read current replicas, GPU type, and utilization (`get_application_state`, metrics tools per `tools.md`).
2. Prefer: smaller GPU shape via `get_model_deployment_specs`, lower `max_replicas`, scale-to-0 for idle dev services, or pause for unused apps.
3. Do not silently destroy prod capacity — confirm the environment.

## Apply pattern

1. Take the live manifest per **Creating or updating** in `deploy-common.md` (from the `list_applications` row if still in the conversation, otherwise `get_application`). If it is no longer in the conversation verbatim, fetch it again; a summarized manifest drops fields.
2. Patch `replicas` / `auto_shutdown` only.
3. `validate_manifest` → explain the change → `apply_manifest` (approval).
4. Verify: replica count moves under load/idle as expected; for scale-to-0, confirm idle behavior without declaring failure during cold start.

## Checklist

- [ ] Did I distinguish autoscaling (1→N), Elasti (0↔1), and pause/resume?
- [ ] Is autoscaling written under `replicas` with `min_replicas` / `max_replicas` and a single `metrics` object?
- [ ] Is `wait_time` in seconds, and `auto_shutdown` only on a `service` (with `rps` if autoscaling)?
- [ ] For models, did I warn about GPU × replicas and cold start?
- [ ] Did I edit the live manifest and apply only with approval?

For more info: `search_docs` with "scale service to 0", "autoscaling", "pause resume service".
