---
name: troubleshooting
description: Diagnose a deployed workload — logs, events, metrics, crashes, pending pods, failed builds, slowness. Read this for any question about whether an application is working, why it is not, how it is performing, or what changed, before calling any read tool against a deployed application.
---

Operational questions arrive without the two facts that decide how to answer them: the application's **type**, and how far in the **past** the answer lives. Both change which tools can see anything, and a tool that cannot see returns an empty list rather than an error — which reads exactly like good news.

Read `tools.md` for parameter-level detail of any tool named below, or when the answer may sit behind "What no tool can see".

## Phase 1: Identify the application

Call `list_applications` filtered by the name. **A name is not an identifier — the same name can exist in several workspaces.** If more than one comes back, do NOT pick one: show the user the matches with their workspaces and ask which they mean. Diagnosing the wrong one produces a thorough, confident answer about an application they were not asking about, and nothing in that answer reveals the mistake.

Once you have the right application, record the fields below. If they are no longer in the conversation later, look them up again (`get_application`, `get_application_state`).

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
| `helm` | `list_application_events` (subchart pods: lifecycle only) | `get_logs` **with a pod filter** | See Helm applications; also `get_application_argocd_resources` |
| `notebook`, `rstudio`, `ssh-server` | `list_application_events` | `get_logs` | See Notebooks below; authoring/access: `notebook-ssh.md` |

If many apps fail the same way at once, jump to `failure-modes/cluster-capacity.md` before a deep single-app dive.

## Phase 2: Read the application state and route

Issue in one message: `get_application_state` (application `id`), `list_application_events` (with a `startTs` covering the problem) and `list_alerts`. Both exist only when Autopilot is enabled; if they are not listed, skip them and, when events matter, give the user `kubectl get events -n <namespace> --sort-by=.lastTimestamp`. `get_application_state` is the entry point: do not start from logs, because whether logs exist, and which container holds them, is what it establishes. It also returns `clusterId` and `namespace` (the workspace name); call `list_workspaces` only if it is `null`.

Per pod read `status`, `node`, `restarts`, `version` and the `conditions` (`type`, `status`, `reason`, `message`); per container `state`, `reason`, `exitCode` and **`lastState`** — the attempt before the last restart, where `OOMKilled` and exit 137 show while the current attempt looks fine. Trap: pod `status` is `Running` only when Ready, so a crashlooping pod also shows `Pending`.

It is the last status tfy-agent published, not a live read. If `eventGenerationTimestamp` is old, say the snapshot may be stale.

Branch on what you see, then **open the matching file** (paths under `ai-engineering/references/`) before concluding:

| State | Next file / action |
|---|---|
| Response is `null` | No status from the agent. `get_deployment` → build failed / no image: `builds.md`; otherwise `failure-modes/rollout-argocd.md` (status not publishing) |
| No pods at all | `get_deployment` → build failed / missing image: `builds.md`; deploy stuck: `failure-modes/rollout-argocd.md` |
| `node: null`, condition `reason: Unschedulable` | `failure-modes/pending-scheduling.md` (the condition `message` is the scheduler's reason) |
| `Pending`, node set, container waiting in `ContainerCreating` | Events: `FailedMount` / PVC → `failure-modes/volumes-storage.md`; image pull → `failure-modes/image-pull.md` |
| Container `reason: ImagePullBackOff` / `ErrImagePull` | `failure-modes/image-pull.md` |
| Container `reason: CreateContainerConfigError` / `CreateContainerError` | Missing Secret/ConfigMap key or bad env reference; the container never started, so no logs. Check manifest `env` and secret FQNs (`secrets.md`) and the event message |
| `lastState.reason: OOMKilled`, exit code 137, or suspected memory | `failure-modes/crashloop-oom-probes.md`. An OOM-looping container shows `reason: CrashLoopBackOff`; the OOM is in `lastState` |
| `reason: CrashLoopBackOff` / high `restarts` | `failure-modes/crashloop-oom-probes.md` |
| Init container (empty `image`, listed after the main ones) waiting or failed; pod stuck initializing | `failure-modes/crashloop-oom-probes.md` → Init container failures |
| Pod `status: Terminating` | Being deleted (rollout or scale-down), not a crash |
| Events mention `FailedMount` / PVC (any status) | `failure-modes/volumes-storage.md` |
| `Running`, but pod `version` ≠ `activeVersion` / stuck rollout / status stuck `WAITING` | `failure-modes/rollout-argocd.md` — establish blast radius (one app, one cluster, all clusters) before acting |
| `Running`, no reason, misbehaving / slow | `get_logs` + metrics (Phase 3) |
| Manifest has `artifacts_download` / model-server labels | Also read `model-debug.md` after the matching row above |

**A `Pending` pod is not a failed pod in Kubernetes terms, but it is a failed deploy for the user.** Nothing may report failure and the deployment may still say `DEPLOY_SUCCESS`.

**No pods means look before the runtime.** If no image was produced there are no pods: `get_application_state` lists none and `get_logs` returns empty.

A `list_alerts` alert is an early signal; corroborate it with state, logs or metrics.

## Phase 3: Metrics and applied spec

Logs and events say what happened at a moment. Metrics show a trend. Reach for them on OOMKilled, slowness without log errors, or when deciding whether to raise requests/limits.

1. `list_app_metric_charts`, then `get_application_chart_data` with chart names and `params` from step 1 only (inputs and millisecond time units: `tools.md`).
2. In the same message as step 1 if relevant: `list_application_deployments` ("what changed" / "worked yesterday") and `get_applied_k8s_manifest` (resources, probes, nodeSelector, tolerations, env shape actually on the cluster, secrets redacted).

## Reading logs from a crashing container

A container in `CrashLoopBackOff` has usually produced nothing in its current attempt. The stack trace is in the **previous** attempt.

Call `get_logs` with `applicationId`, `podName` (from `get_application_state`), `containerName` when the pod has several, `direction: "desc"`, `limit` ~200 and an `endTs` just after the container's `lastState.finishedAt` (nanoseconds). With VictoriaLogs or Loki on the cluster the crashed attempt's output is persisted. Without one, `get_logs` reads only the current attempt of the live container, so the crash output is out of reach: say so, and give the user `kubectl logs <pod> -c <container> --previous -n <namespace>`.

## Helm applications

Logs need a pod filter: `get_logs` on a Helm app without `podName`, `podNames` or `podNamesRegex` returns 400.

1. Get real pod names from `get_application_state`. If it lists none, use `get_application_argocd_resources`, which also shows sync/health.
2. `get_logs` with `applicationId`, that `podName` (or `podNamesRegex="^<release>-.*"`), `direction: "desc"`, `limit` ~200.

`list_application_events` keeps live events only for objects named like the release, so subchart pods get lifecycle events only. For their full events give the user `kubectl get events -n <namespace> --field-selector involvedObject.name=<pod>`.

**Never construct a pod name.** Subcharts append their own suffixes to the release name:

```
release      my-cache
StatefulSet  my-cache-master
pod          my-cache-master-0        # <set>-<ordinal>
```

`my-cache-0` does not exist, and `get_logs` for it returns an empty list rather than an error. Deployment-backed pods carry a generated ReplicaSet hash (`my-api-7d4b9c8f2a-x4kqp`) and are equally unpredictable. List, then read.

## Notebooks / SSH / RStudio

Same path as services. **OAuth / login failed** after the pod is Running is application logs and auth/IdP config, not Pending. Long startup killed by probes → `failure-modes/crashloop-oom-probes.md`; GPU notebook Pending → `failure-modes/pending-scheduling.md`.

## Interpreting an empty result

An empty list means either "nothing happened" or "I could not see it". Before reporting that a workload is healthy, rule out the second:

- Could the tool see it? Without a log backend, logs of crashed and replaced containers are gone; live events last about an hour; system namespaces and cluster objects are never visible (`tools.md` → What no tool can see).
- Did you ask the right layer? A failed build leaves no pod; an unschedulable pod leaves no logs.
- Is this a Helm release where you called `get_logs` without a pod filter, or a pod name you constructed?
- Are Prometheus/log backends missing on the cluster? (`failure-modes/cluster-capacity.md`)
- StatefulSet-backed apps (common for some model services) can show **empty** `list_application_events` while pods CrashLoop. Read container `reason` / `lastState` from `get_application_state` and the logs (`model-debug.md`).

State what you could not see rather than reporting health. "No events in the window" and "nothing is wrong" are different claims.

**`DEPLOY_SUCCESS` means the rollout was accepted, not that the workload is healthy.** Confirm with `get_application_state` before telling a user their deployment worked.

## How to answer

- Lead with one root cause, then the evidence (pod name, event reason, log line, metric); add secondary issues only if they block the fix.
- Propose a concrete fix (manifest field change, registry fix, wait for node, sync, regenerated model specs) — not a generic Kubernetes tutorial.
- When the cause sits where no tool can see (nodes, NodeClaims, PVCs, system namespaces), give the user the exact `kubectl` command to confirm it.
- For write fixes, use `validate_manifest` → `apply_manifest` (or `sync_application` / `redeploy_application` / regenerated specs from `get_model_deployment_specs`) with approval. Do not run `tfy apply` in the terminal.
- For a model server, read `model-debug.md` and research recipes/GitHub issues before inventing engine flags.
- If you still cannot tell, follow `references/support-tickets.md`.

## Checklist

- [ ] If more than one workspace had an application with that name, did I ask which one?
- [ ] Did I start from `get_application_state` and open the matching failure-mode file?
- [ ] Did I read container `reason` and `lastState`, and use `node` to tell an unscheduled `Pending` pod from an unready one?
- [ ] For a crashlooping container, did I read the previous attempt's logs (window ending at `lastState.finishedAt`), or say why I could not?
- [ ] If the type is `helm`, did I pass a real pod name or regex to `get_logs`?
- [ ] For OOM or slowness, did I look at metrics / applied limits, not only logs?
- [ ] Did I avoid calling exit 137 "OOM" without corroboration?
- [ ] If a call returned empty, did I check whether that tool could have seen the answer at all?
- [ ] If the deployment says `DEPLOY_SUCCESS`, did I confirm the pods are actually Running without a bad `reason`?
- [ ] Does my answer cite the specific pod, event, log line, or metric behind each claim — and name what I could not see?

For more info: `search_docs` with "monitor your service", "debug a deployment".
