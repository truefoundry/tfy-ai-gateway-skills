---
name: crashloop-oom-probes
description: CrashLoopBackOff, OOMKilled, exit 137, liveness/readiness probe kills, restarts climbing, container starts then dies. Read when list_k8s_pods shows CrashLoopBackOff, OOMKilled, Error, or high restarts on a Running/unknown phase.
---

Restarts look alike in the UI. The cause is not. Exit code 137 is **not** automatically OOM — it is SIGKILL, which also comes from the kubelet killing a container that failed its liveness probe. Corroborate with `reason`, events, metrics, and previous-container logs before naming the root cause.

## Contents
- Classify the failure
- CrashLoopBackOff (application or config)
- OOMKilled (memory limit)
- Probe-driven restarts (fake OOM)
- Init container failures
- Checklist

## Classify the failure

From `list_k8s_pods`, read `phase`, `restarts`, and `reason` (not a field named `problem` — the projection field is `reason`).

| `reason` / signal | Likely class | First evidence call |
|---|---|---|
| `OOMKilled` | Memory limit hit | Metrics memory chart + `get_applied_k8s_manifest` for actual limit |
| `CrashLoopBackOff` | Process exited non-zero repeatedly | `get_k8s_pod_logs` with `previous: true` |
| `Error` / `Completed` with restarts on a service | Main container exiting | Previous logs |
| High restarts, `reason` empty, currently Running | Recovered after kills — history still matters | Previous logs + events + metrics around restart timestamps |
| Events: `Unhealthy` / `Killing` mentioning Liveness/Readiness | Probe kill | Events + probe config in applied manifest; **not** memory |

Always take **all** pods of the application into account. One healthy replica does not mean the rollout is healthy.

## CrashLoopBackOff (application or config)

1. `get_k8s_pod_logs` with `previous: true` (and `timestamps: true` if useful). The current container attempt is often empty.
2. If previous logs are empty, try `get_logs` (native, persisted) for the same pod/deployment window — the previous container may already be gone from kubelet retention.
3. Read the **last** meaningful lines: import errors, missing env, bad bind address, migration failure, permission denied, segfault.
4. Cross-check config with `get_application` → active manifest env/secrets/command, and `get_applied_k8s_manifest` if you need the resolved pod template.

Common application-side causes: missing required env, wrong `PORT` vs container port, failed DB connection at startup, incompatible wheel/binary, code exception on import.

Do not invent fixes for application code you cannot see — cite the log line and ask the user to change the image/config accordingly. If the fix is a TrueFoundry manifest field (resources, probes, env), propose a concrete manifest edit via `apply_manifest` after `validate_manifest`.

## OOMKilled (memory limit)

1. Confirm `reason: OOMKilled` (or terminated reason in describe) — do not infer from exit 137 alone.
2. `list_app_metric_charts` → `get_application_chart_data` for memory usage vs time. Look for a climb to the limit, or a spike.
3. `get_applied_k8s_manifest` (or active deployment manifest) for `memory_limit` / `resources.limits.memory`. Compare usage to limit.
4. Distinguish:
   - **Limit too low** — usage saturates the limit; raise limit (and usually request).
   - **Leak / unbounded growth** — usage climbs across hours/days; raising limit only delays the kill.
   - **Burst** — rare spikes (compaction, model load); raise limit or change workload pattern.

For jobs/workflows that OOM once per run, check that run's logs and whether the job's resource block differs from the service's.

## Probe-driven restarts (fake OOM)

Field pattern: exit 137, CrashLoopBackOff, memory usage well under limit, events show Liveness probe failed / Killing.

1. `list_application_events` / `list_k8s_events` — look for `Unhealthy`, `Killing`, messages mentioning Liveness or Readiness.
2. Read probe settings from the applied manifest: `initialDelaySeconds`, `timeoutSeconds`, `periodSeconds`, `failureThreshold`.
3. Effective time-to-kill ≈ `initialDelaySeconds + (failureThreshold - 1) * periodSeconds + timeoutSeconds` (order-of-magnitude). Slow-starting apps (large models, many watchers, cold JVM) often need a longer delay or a startupProbe.
4. Compare to wall-clock time-to-listen in previous logs — if the app becomes ready after the kill window, it is probes, not OOM.

**Never** recommend a memory increase when metrics show headroom and events show probe failures.

## Init container failures

If `reason` is prefixed with `Init:` (projection does this), the main container never started. Logs must target the **init container name** (`container` param on `get_k8s_pod_logs`). Describe the pod to list init container names and their states.

## Checklist

- [ ] Did I use the `reason` field (and events) instead of guessing from exit code 137?
- [ ] For CrashLoopBackOff, did I fetch **previous** container logs?
- [ ] For OOMKilled, did I pull memory metrics and the actual memory limit?
- [ ] Did I check for Liveness/Readiness kill events before calling it OOM?
- [ ] Did I look at every replica, not one lucky pod?
- [ ] Does my answer quote the log line, event, or metric that supports the diagnosis?

For more info: `search_docs` with "health probes", "OOM", "troubleshoot crashloop".
