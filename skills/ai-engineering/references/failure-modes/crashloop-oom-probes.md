---
name: crashloop-oom-probes
description: CrashLoopBackOff, OOMKilled, exit 137, liveness/readiness probe kills, restarts climbing, container starts then dies. Read when get_application_state shows CrashLoopBackOff, OOMKilled, Error, or high restarts on a Running/unknown pod.
---

Restarts look alike in the UI. The cause is not. Exit code 137 is **not** automatically OOM — it is SIGKILL, which also comes from the kubelet killing a container that failed its liveness probe. Corroborate with `reason`, events, metrics, and the previous attempt's logs before naming the root cause.

## Contents
- Classify the failure
- CrashLoopBackOff (application or config)
- OOMKilled (memory limit)
- Probe-driven restarts (fake OOM)
- Init container failures
- Checklist

## Classify the failure

From `get_application_state`, read each pod's `status` and `restarts`, and each container's `state`, `reason`, `exitCode` and `lastState` (not a field named `problem`). A container that is Running now may show `lastState.reason: OOMKilled` — that is the last crash. A crashlooping pod's `status` reads `Pending` (it is not Ready); its container `reason` says `CrashLoopBackOff`.

| `reason` / signal | Likely class | First evidence call |
|---|---|---|
| `OOMKilled` (in `reason` or `lastState.reason`) | Memory limit hit | Metrics memory chart + `get_applied_k8s_manifest` for actual limit |
| `CrashLoopBackOff` | Process exited non-zero repeatedly | `get_logs` for the pod, window ending just after `lastState.finishedAt` |
| `Error` with restarts on a service | Main container exiting | Logs of the previous attempt |
| High restarts, `reason` empty, currently Running | Recovered after kills — history still matters | Logs + events + metrics around `lastState.finishedAt` |
| Events: `Unhealthy` / `Killing` mentioning Liveness/Readiness | Probe kill | Events + probe config in applied manifest; **not** memory |

Always take **all** pods of the application into account. One healthy replica does not mean the rollout is healthy.

## CrashLoopBackOff (application or config)

1. `get_logs` with `applicationId`, `podName`, `containerName` if the pod has several, `direction: "desc"`, `limit` ~200 and an `endTs` just after the container's `lastState.finishedAt`. The current attempt is often empty; the crash output is in the previous one.
2. If that is empty, check whether the cluster has a log backend (`get_cluster` → `manifest.monitoring`). Without VictoriaLogs/Loki, `get_logs` reads only the current attempt of the live container, so the crash output is out of reach: say so and give the user `kubectl logs <pod> -c <container> --previous -n <namespace>`.
3. Read the **last** meaningful lines: import errors, missing env, bad bind address, migration failure, permission denied, segfault.
4. Cross-check config with `get_application` → active manifest env/secrets/command, and `get_applied_k8s_manifest` if you need the resolved pod template.

Common application-side causes: missing required env, wrong `PORT` vs container port, failed DB connection at startup, incompatible wheel/binary, code exception on import.

Do not invent fixes for application code you cannot see — cite the log line and ask the user to change the image/config accordingly. If the fix is a TrueFoundry manifest field (resources, probes, env), propose a concrete manifest edit via `apply_manifest` after `validate_manifest`.

## OOMKilled (memory limit)

1. Confirm `OOMKilled` in the container's `reason` or `lastState.reason` — do not infer from exit 137 alone.
2. `list_app_metric_charts` → `get_application_chart_data` for memory usage vs time. Look for a climb to the limit, or a spike.
3. `get_applied_k8s_manifest` for the applied `resources.limits.memory`. Compare usage to limit. Issue it in the same message as step 2's `list_app_metric_charts`.
4. Distinguish:
   - **Limit too low** — usage saturates the limit; raise limit (and usually request).
   - **Leak / unbounded growth** — usage climbs across hours/days; raising limit only delays the kill.
   - **Burst** — rare spikes (compaction, model load); raise limit or change workload pattern.

For jobs/workflows that OOM once per run, check that run's logs and whether the job's resource block differs from the service's.

## Probe-driven restarts (fake OOM)

Field pattern: exit 137, CrashLoopBackOff, memory usage well under limit, events show Liveness probe failed / Killing.

1. `list_application_events` — look for `Unhealthy`, `Killing`, messages mentioning Liveness or Readiness.
2. Read probe settings from the applied manifest: `initialDelaySeconds`, `timeoutSeconds`, `periodSeconds`, `failureThreshold`.
3. Effective time-to-kill ≈ `initialDelaySeconds + (failureThreshold - 1) * periodSeconds + timeoutSeconds` (order-of-magnitude). Slow-starting apps (large models, many watchers, cold JVM) often need a longer delay or a startupProbe.
4. Compare to wall-clock time-to-listen in the logs — if the app becomes ready after the kill window, it is probes, not OOM.

When proposing the fix, edit the TrueFoundry manifest fields: `liveness_probe` / `readiness_probe` / `startup_probe` with `initial_delay_seconds` (default 0), `period_seconds` (10), `timeout_seconds` (1), `failure_threshold` (3); memory is `resources.memory_limit` and `resources.memory_request` in MB. The camelCase names are only what you read in the applied Kubernetes manifest.

**Never** recommend a memory increase when metrics show headroom and events show probe failures.

## Init container failures

Init containers appear in `get_application_state` after the main containers, with an empty `image`. If one is waiting or terminated with an error, the main container never started and the pod stays `Pending`. Logs must target the **init container name** — take it from that entry (or `initContainers` in `get_applied_k8s_manifest`) and pass it as `containerName` to `get_logs`. Containers named `init` or `wait` are always excluded from `get_logs`; for those give the user `kubectl logs <pod> -c <name> -n <namespace>`.

## Checklist

- [ ] Did I use the `reason` field (and events) instead of guessing from exit code 137?
- [ ] For CrashLoopBackOff, did I fetch the logs of the **previous** attempt (window around `lastState.finishedAt`)?
- [ ] For OOMKilled, did I pull memory metrics and the actual memory limit?
- [ ] Did I check for Liveness/Readiness kill events before calling it OOM?
- [ ] Did I look at every replica, not one lucky pod?
- [ ] Does my answer quote the log line, event, or metric that supports the diagnosis?

For more info: `search_docs` with "health probes", "OOM", "troubleshoot crashloop".
