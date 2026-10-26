---
name: troubleshooting
description: Diagnose a deployed workload — logs, events, metrics, crashes, pending pods, failed builds, slowness. Read this for any question about whether an application is working, why it is not, how it is performing, or what changed, before calling any read tool against a deployed application.
---

Operational questions arrive without the two facts that decide how to answer them: the application's **type**, and how far in the **past** the answer lives. Both change which tools can see anything, and a tool that cannot see returns an empty list rather than an error — which reads exactly like good news.

## Contents
- Phase 1: Identify the application
- Phase 2: Read the application state and route
- Phase 3: Metrics, alerts, applied spec
- Failure-mode playbooks (read the matching file)
- Reading logs from a crashing container
- Helm applications
- Notebooks / SSH / RStudio
- Interpreting an empty result
- How to answer
- Checklist

Also read `tools.md` when you need parameter-level detail for any tool named below, or when the answer may sit behind "What no tool can see".

## Phase 1: Identify the application

Call `list_applications` filtered by the name. **A name is not an identifier — the same name can exist in several workspaces.** If more than one comes back, do NOT pick one: show the user the matches with their workspaces and ask which they mean. Diagnosing the wrong one produces a thorough, confident answer about an application they were not asking about, and nothing in that answer reveals the mistake.

Once you have the right application, record:

| Field | Why you need it |
|---|---|
| `type` | Decides how logs are read and which playbooks apply |
| `id` | Required by `get_application_state`, `get_logs`, `get_deployment`, events and applied-manifest tools |
| `workspaceFqn` | Resolves the cluster if `get_application_state` returns `null` |

What is available by type:

| `type` | Events | Logs | Notes |
|---|---|---|---|
| `service`, `async-service` | `list_application_events` | `get_logs` | Standard path |
| `job` | `list_application_events` (+ `jobRunName`) | `get_logs` (+ `jobRunName`) | Read `failure-modes/jobs.md` |
| `helm` | `list_application_events` | `get_logs` **with a pod filter** — see Helm applications | Also `get_application_argocd_resources` |
| `notebook`, `rstudio`, `ssh-server` | `list_application_events` | `get_logs` | Author/access: `notebook-ssh.md`. Auth/OAuth issues are often app logs + probes, not schedule |

If many apps fail the same way at once, jump to `failure-modes/cluster-capacity.md` before a deep single-app dive.

## Phase 2: Read the application state and route

Call `get_application_state` with the application `id`. This is the entry point for every runtime question. Do NOT start from logs — whether logs exist, and which container holds them, is what this call establishes. It also returns `clusterId` and `namespace` (the workspace name) for the cluster tools.

The response has `activeVersion` and `components[].pods[]`. Per pod: `status`, `message`, `conditions` (`type`, `status`, `reason`, `message`), `restarts`, `version`, `node`. Per container: `state`, `reason`, `exitCode`, and **`lastState`** — the attempt before the last restart, which is where `OOMKilled` and exit 137 show while the current attempt looks fine.

It is the last status the cluster agent published, not a live read. If `eventGenerationTimestamp` is old, say the snapshot may be stale.

Branch on what you see, then **open the matching failure-mode file** before concluding:

| State | Next file / action |
|---|---|
| Response is `null` | The agent has not published a status. `get_deployment` → if build failed / no image: `builds.md`; otherwise `get_cluster_status` and `failure-modes/rollout-argocd.md` (status not publishing) |
| No pods at all | `get_deployment` → if build failed/missing image: `builds.md`; if deploy stuck: `failure-modes/rollout-argocd.md` |
| Pod `status: Pending` | Events first (`list_application_events`): `FailedMount` / PVC → `failure-modes/volumes-storage.md`; otherwise `failure-modes/pending-scheduling.md` (the pod `message` / `PodScheduled` condition carries the scheduler's reason) |
| Container `reason: ImagePullBackOff` / `ErrImagePull` | `failure-modes/image-pull.md` |
| `lastState.reason: OOMKilled`, exit code 137, or suspected memory | `failure-modes/crashloop-oom-probes.md` |
| `reason: CrashLoopBackOff` / high `restarts` | `failure-modes/crashloop-oom-probes.md` |
| Events mention `FailedMount` / PVC (any status) | `failure-modes/volumes-storage.md` |
| `Running`, but pod `version` ≠ `activeVersion` / stuck rollout | `failure-modes/rollout-argocd.md` |
| Status stuck `WAITING` / stale active version / "no new pods" while the cluster may be fine | `failure-modes/rollout-argocd.md` — establish blast radius (one app, one cluster, all clusters) before acting |
| `Running`, no reason, misbehaving / slow | `get_logs` + metrics (Phase 3) |
| Manifest has `artifacts_download` / model-server labels | Also read `model-debug.md` after the matching row above |

**A `Pending` pod is not a failed pod in Kubernetes terms, but it is a failed deploy for the user.** Nothing may report failure and the deployment may still say `DEPLOY_SUCCESS`.

**No pods means look before the runtime.** If no image was produced there is nothing to inspect, and every runtime tool returns empty.

Optional early signal: `list_alerts` for the application — autopilot may already have classified OOM/crashloop. Still corroborate with state/logs/metrics; do not stop at the alert name alone.

## Phase 3: Metrics, alerts, applied spec

Logs and events say what happened at a moment. Metrics show a trend.

Charts are a two-step call:

1. `list_app_metric_charts`
2. `get_application_chart_data` — use chart names/params from step 1 only

Reach for metrics when: OOMKilled, slowness without log errors, deciding whether to raise requests/limits.

Also useful:

- `list_application_deployments` — "what changed" / "worked yesterday"
- `get_applied_k8s_manifest` — resources, probes, nodeSelector, tolerations and env shape actually on the cluster (secrets redacted)
- `get_pod_template_hash_map` — maps a pod's `podTemplateHash` to a deployment version

## Failure-mode playbooks (read the matching file)

Paths are under `ai-engineering/references/`:

| File | When |
|---|---|
| `model-deploy.md` | User wants to deploy a HuggingFace / catalogue / NIM model |
| `model-debug.md` | Deployed model service unhealthy or inference broken |
| `failure-modes/pending-scheduling.md` | Pending, FailedScheduling, GPU, Karpenter |
| `failure-modes/crashloop-oom-probes.md` | CrashLoop, OOM, exit 137, probe kills |
| `failure-modes/image-pull.md` | ImagePullBackOff / ErrImagePull |
| `failure-modes/volumes-storage.md` | FailedMount, PVC, EFS/NFS |
| `failure-modes/jobs.md` | Job runs, cron, retries |
| `failure-modes/rollout-argocd.md` | Stuck deploy, OutOfSync, rollout |
| `failure-modes/cluster-capacity.md` | Cluster-wide / addon / agent issues |
| `builds.md` | Build never produced a runnable image |
| `tools.md` | Tool inputs, retention, write tools, what no tool can see |

## Reading logs from a crashing container

A container in `CrashLoopBackOff` has usually produced nothing in its current attempt. The stack trace is in the **previous** attempt.

Call `get_logs` with `applicationId`, `podName` (from `get_application_state`), `containerName` when the pod has several, and a time window that ends just after the container's `lastState.finishedAt`. Logs are persisted when the cluster has a log backend (Loki or VictoriaLogs), so the crashed attempt's output is there. On a cluster without one, `get_logs` reads live pods only and the crashed attempt may be missing — say so rather than calling the app silent.

## Helm applications

Events work normally. Logs need a pod filter: `get_logs` on a Helm app without `podName`, `podNames` or `podNamesRegex` is rejected.

1. Get real pod names from `get_application_state`. If it lists none, use `get_application_argocd_resources` (Helm only), which also shows sync/health.
2. `get_logs` with `applicationId` and that `podName` (or `podNames`).

**Never construct a pod name.** Subcharts append their own suffixes to the release name:

```
release      my-cache
StatefulSet  my-cache-master
pod          my-cache-master-0        # <set>-<ordinal>
```

`my-cache-0` does not exist, and a query for a pod that does not exist returns empty rather than an error. Deployment-backed pods carry a generated ReplicaSet hash (`my-api-7d4b9c8f2a-x4kqp`) and are equally unpredictable. List, then read.

## Notebooks / SSH / RStudio

Same state/log/event path as services. Extra failure modes seen in practice:

- **OAuth / login failed** after the pod is Running — check application logs and auth/IdP config; do not treat as Pending.
- **Long startup** killed by probes — `failure-modes/crashloop-oom-probes.md`.
- **GPU notebook Pending** — `failure-modes/pending-scheduling.md`.

## Interpreting an empty result

An empty list means either "nothing happened" or "I could not see it". Before reporting that a workload is healthy, rule out the second:

- Could the tool see it? Logs of replaced pods are gone on clusters without a log backend; system namespaces and cluster objects are never visible (`tools.md` → What no tool can see).
- Did you ask the right layer? A failed build leaves no pod; an unschedulable pod leaves no logs.
- Is this a Helm release where you called `get_logs` without a pod filter?
- Are Prometheus/log backends missing on the cluster? (`failure-modes/cluster-capacity.md`)
- **StatefulSet-backed apps (common for some model services):** `list_application_events` can return **empty even while pods CrashLoop**. Read container `reason` / `lastState` from `get_application_state` and the pod logs (`model-debug.md`). Never treat empty application events as proof of health.

State what you could not see rather than reporting health. "No events in the window" and "nothing is wrong" are different claims.

**`DEPLOY_SUCCESS` means the rollout was accepted, not that the workload is healthy.** Confirm with `get_application_state` before telling a user their deployment worked.

## How to answer

- Lead with the root cause, then the evidence (pod name, event reason, log line, metric).
- Prefer one primary cause. Mention secondary issues only if they block the fix.
- Prefer proposing a concrete fix (manifest field change, registry fix, wait for node, sync, regenerated model specs) — do not dump a generic Kubernetes tutorial.
- When the cause sits where no tool can see (nodes, NodeClaims, PVCs, system namespaces), give the user the exact `kubectl` command to confirm it.
- For write fixes, use `validate_manifest` → `apply_manifest` (or `sync_application` / `redeploy_application` / regenerated specs from `get_model_deployment_specs`) with approval. Do not run `tfy apply` in the terminal.
- When the workload is a model server, read `model-debug.md` and research recipes/GitHub issues before inventing engine flags.
- If you still cannot tell, follow `references/support-tickets.md`.

## Checklist

- [ ] If more than one workspace had an application with that name, did I ask which one rather than diagnosing the first?
- [ ] Did I start from `get_application_state` and open the matching failure-mode file?
- [ ] Did I read container `reason` and `lastState` (not a fictional `problem` field)?
- [ ] For a crashlooping container, did I read the logs of the previous attempt (time window around `lastState.finishedAt`)?
- [ ] If the type is `helm`, did I pass a real pod name to `get_logs`?
- [ ] Did I take pod names from `get_application_state` rather than constructing them?
- [ ] For OOM or slowness, did I look at metrics / applied limits, not only logs?
- [ ] Did I avoid calling exit 137 "OOM" without corroboration?
- [ ] If a call returned empty, did I check whether that tool could have seen the answer at all?
- [ ] If the deployment says `DEPLOY_SUCCESS`, did I confirm the pods are actually Running without a bad `reason`?
- [ ] Does my answer cite the specific pod, event, log line, or metric behind each claim — and name what I could not see?

For more info: `search_docs` with "monitor your service", "debug a deployment".
