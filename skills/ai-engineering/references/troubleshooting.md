---
name: troubleshooting
description: Diagnose a deployed workload — logs, events, metrics, crashes, pending pods, failed builds, slowness. Read this for any question about whether an application is working, why it is not, how it is performing, or what changed, before calling any read tool against a deployed application.
---

Operational questions arrive without the two facts that decide how to answer them: the application's **type**, and how far in the **past** the answer lives. Both change which tools can see anything, and a tool that cannot see returns an empty list rather than an error — which reads exactly like good news.

## Contents
- Phase 1: Identify the application
- Phase 2: Read the pod state and route
- Phase 3: Metrics, alerts, applied spec
- Failure-mode playbooks (read the matching file)
- Native tools vs k8s tools
- Reading logs from a crashing container
- Helm applications
- Notebooks / SSH / RStudio
- Interpreting an empty result
- How to answer
- Checklist

Also read `tools.md` when you need parameter-level detail for any tool named below.

## Phase 1: Identify the application

Call `list_applications` filtered by the name. **A name is not an identifier — the same name can exist in several workspaces.** If more than one comes back, do NOT pick one: show the user the matches with their workspaces and ask which they mean. Diagnosing the wrong one produces a thorough, confident answer about an application they were not asking about, and nothing in that answer reveals the mistake.

Once you have the right application, record these before doing anything else:

| Field | Why you need it |
|---|---|
| `type` | Decides whether application-level logs exist and which playbooks apply |
| `id` | Required by `get_deployment`, `get_application_state`, applied-manifest tools |
| `workspaceFqn` | Resolves the cluster and the namespace — see below |

The application does **not** carry `clusterId`, and every `*_k8s_*` tool needs it as a path parameter. Resolve it with one filtered call:

```
list_workspaces  fqn=<the application's workspaceFqn>  attributes=["id","name","fqn","clusterId"]
```

That returns `clusterId` and the workspace `name` — and the k8s `namespace` is that workspace name. Pass `attributes`: an unprojected workspace row is large enough to be worth avoiding.

What is available by type:

| `type` | Events | Logs | Notes |
|---|---|---|---|
| `service`, `async-service` | `list_application_events` | `get_logs` | Standard path |
| `job` | `list_application_events` (+ `jobRunName`) | `get_logs` (+ `jobRunName`) | Read `failure-modes/jobs.md` |
| `helm` | `list_application_events` | **none at application level** — pod-level only | Also `get_application_argocd_resources` |
| `notebook`, `rstudio`, `ssh-server` | `list_application_events` | `get_logs` | Auth/OAuth issues are often app logs + probes, not schedule |

Do NOT call `get_logs` on a Helm application and report "no logs found". There is no application-level log stream for a Helm release — the logs are pod-level and reachable.

If many apps fail the same way at once, jump to `failure-modes/cluster-capacity.md` before a deep single-app dive.

## Phase 2: Read the pod state and route

Call `list_k8s_pods` with `clusterId` and `namespace` (optional `labelSelector=truefoundry.com/application-id=<id>`). This is the entry point for every runtime question. Do NOT start from logs — whether logs exist, and which container holds them, is what this call establishes.

Each pod returns `phase`, `restarts`, and optional **`reason`** (e.g. `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`). Branch on what you see, then **open the matching failure-mode file** before concluding:

| Pod state | Next file / action |
|---|---|
| No pods at all | `get_deployment` → if build failed/missing image: `builds.md`; if deploy stuck: `failure-modes/rollout-argocd.md` |
| `Pending` | `failure-modes/pending-scheduling.md` |
| `reason: ImagePullBackOff` / `ErrImagePull` | `failure-modes/image-pull.md` |
| `reason: OOMKilled` or suspected memory | `failure-modes/crashloop-oom-probes.md` |
| `reason: CrashLoopBackOff` / high restarts | `failure-modes/crashloop-oom-probes.md` |
| Events mention `FailedMount` / PVC | `failure-modes/volumes-storage.md` |
| `Running`, no reason, but wrong version / stuck rollout | `failure-modes/rollout-argocd.md` |
| `Running`, no reason, misbehaving / slow | `get_logs` + metrics (Phase 3) |
| Manifest has `artifacts_download` / model-server labels | Also read `model-debug.md` after the matching row above |

**A `Pending` pod is not a failed pod in Kubernetes terms, but it is a failed deploy for the user.** Nothing may report failure and the deployment may still say `DEPLOY_SUCCESS`.

**No pods means look before Kubernetes.** If no image was produced there is nothing to inspect, and every `*_k8s_*` tool returns empty.

Optional early signal: `list_alerts` for the application — autopilot may already have classified OOM/crashloop. Still corroborate with pods/logs/metrics; do not stop at the alert name alone.

## Phase 3: Metrics, alerts, applied spec

Logs and events say what happened at a moment. Metrics show a trend.

Charts are a two-step call:

1. `list_app_metric_charts`
2. `get_application_chart_data` — use chart names/params from step 1 only

Reach for metrics when: OOMKilled, slowness without log errors, deciding whether to raise requests/limits.

Also useful:

- `get_application_state` — component/pod snapshot and active version
- `list_application_deployments` — "what changed" / "worked yesterday"
- `get_applied_k8s_manifest` — resolved resources/probes/env shape actually on the cluster (secrets redacted)

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
| `tools.md` | Tool inputs, retention, write tools |

## Native tools vs k8s tools

Start native. Escalate only for what native cannot provide.

| | Retention | Use for |
|---|---|---|
| `list_application_events`, `get_logs`, `list_alerts` | Persisted | Historical; pods that no longer exist |
| `list_k8s_events` | ~1h cluster TTL | Live scheduling, pull, mount |
| `get_k8s_pod_logs` | Pod lifetime only | Current or just-crashed container (`previous: true`) |
| `list_k8s_pods`, `list_k8s_nodes`, `list_k8s_objects`, `describe_k8s_object` | Live only | Phase/reason; capacity; CRDs (NodeClaim, PVC, Rollout) |
| `list_app_metric_charts`, `get_application_chart_data` | Persisted | CPU/memory/throughput trends |
| `get_application_state`, `list_application_deployments`, `get_applied_k8s_manifest` | Persisted | Health snapshot; history; applied spec |

Every `*_k8s_*` tool takes `clusterId` as a path parameter and, except for `list_k8s_nodes` and cluster-scoped objects, a `namespace` equal to the workspace name.

## Reading logs from a crashing container

A container in `CrashLoopBackOff` has usually produced nothing in its current attempt. The stack trace is in the **previous** container.

Call `get_k8s_pod_logs` with `previous: true`. Without it you read an empty log and conclude the application is silent when it is failing loudly one container back.

Useful parameters: `podName` or `deploymentName` or `jobName` or `labelSelector` (one is required), `container` when the pod has several, `tailLines`, `previous`, `timestamps`.

A pod that has never restarted has no previous container and returns an error **for that pod only** — the other pods still return logs. That is expected, not a fault.

## Helm applications

Events work normally. Logs do not.

1. `list_k8s_pods` with `clusterId` and `namespace` to get real pod names.
2. `get_k8s_pod_logs` with that `podName`.
3. Sync/health: `get_application_argocd_resources`.

**Never construct a pod name.** Subcharts and ReplicaSet hashes make names unpredictable. List, then read.

## Notebooks / SSH / RStudio

Same pod/log/event path as services. Extra failure modes seen in practice:

- **OAuth / login failed** after the pod is Running — check application logs and auth/IdP config; do not treat as Pending.
- **Long startup** killed by probes — `failure-modes/crashloop-oom-probes.md`.
- **GPU notebook Pending** — `failure-modes/pending-scheduling.md`.

## Interpreting an empty result

An empty list means either "nothing happened" or "I could not see it". Before reporting that a workload is healthy, rule out the second:

- Could the tool see it? k8s events older than ~1h are gone; logs for a replaced pod are gone.
- Did you ask the right layer? A failed build leaves no pod; an unschedulable pod leaves no logs.
- Is this a Helm release where you asked for application-level logs?
- Are Prometheus/log backends missing on the cluster? (`failure-modes/cluster-capacity.md`)

State what you could not see rather than reporting health. "No events in the last hour" and "nothing is wrong" are different claims.

**`DEPLOY_SUCCESS` means the rollout was accepted, not that the workload is healthy.** Confirm with `list_k8s_pods` before telling a user their deployment worked.

## How to answer

- Lead with the root cause, then the evidence (pod name, event reason, log line, metric).
- Prefer one primary cause. Mention secondary issues only if they block the fix.
- Prefer proposing a concrete fix (manifest field change, registry fix, wait for node, sync, regenerated model specs) — do not dump a generic Kubernetes tutorial.
- For write fixes, use `validate_manifest` → `apply_manifest` (or `sync_application` / `redeploy_application` / regenerated specs from `get_model_deployment_specs`) with approval. Do not run `tfy apply` in the terminal.
- When the workload is a model server, read `model-debug.md` and research recipes/GitHub issues before inventing engine flags.
- If you still cannot tell, follow `references/support-tickets.md`.

## Checklist

- [ ] If more than one workspace had an application with that name, did I ask which one rather than diagnosing the first?
- [ ] Did I resolve `type`, `id`, `clusterId`, and namespace (`workspace.name`)?
- [ ] If the type is `helm`, did I go pod-level for logs instead of calling `get_logs`?
- [ ] Did I read pod state with `list_k8s_pods` and open the matching failure-mode file?
- [ ] Did I use the `reason` field (not a fictional `problem` field)?
- [ ] For a crashlooping container, did I pass `previous: true`?
- [ ] Did I get pod names from `list_k8s_pods` rather than constructing them?
- [ ] For anything historical, did I use native tools rather than k8s tools?
- [ ] For OOM or slowness, did I look at metrics / applied limits, not only logs?
- [ ] Did I avoid calling exit 137 "OOM" without corroboration?
- [ ] If a call returned empty, did I check whether that tool could have seen the answer at all?
- [ ] If the deployment says `DEPLOY_SUCCESS`, did I confirm the pods are actually Running without a bad `reason`?
- [ ] Does my answer cite the specific pod, event, log line, or metric behind each claim?

For more info: `search_docs` with "monitor your service", "debug a deployment".
