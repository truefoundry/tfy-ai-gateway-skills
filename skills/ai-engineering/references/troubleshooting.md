---
name: troubleshooting
description: Diagnose a deployed workload — logs, events, metrics, crashes, pending pods, failed builds, slowness. Read this for any question about whether an application is working, why it is not, how it is performing, or what changed, before calling any read tool against a deployed application.
---

Operational questions arrive without the two facts that decide how to answer them: the application's **type**, and how far in the **past** the answer lives. Both change which tools can see anything, and a tool that cannot see returns an empty list rather than an error — which reads exactly like good news.

## Contents
- Phase 1: Identify the application
- Phase 2: Read the pod state
- Phase 3: Metrics and application state
- Native tools vs k8s tools
- Reading logs from a crashing container
- Helm applications
- Interpreting an empty result
- Checklist

## Phase 1: Identify the application

Call `list_applications` filtered by the name. **A name is not an identifier — the same name can exist in several workspaces.** If more than one comes back, do NOT pick one: show the user the matches with their workspaces and ask which they mean. Diagnosing the wrong one produces a thorough, confident answer about an application they were not asking about, and nothing in that answer reveals the mistake.

Once you have the right application, record these before doing anything else:

| Field | Why you need it |
|---|---|
| `type` | Decides whether application-level logs exist. See the table below. |
| `id` | Required by `get_deployment`. |
| `workspaceFqn` | Resolves the cluster and the namespace — see below. |

The application does **not** carry `clusterId`, and every `*_k8s_*` tool needs it as a path parameter. Resolve it with one filtered call:

```
list_workspaces  fqn=<the application's workspaceFqn>  attributes=["id","name","fqn","clusterId"]
```

That returns `clusterId` and the workspace `name` — and the k8s `namespace` is that workspace name. Pass `attributes`: an unprojected workspace row is large enough to be worth avoiding.

What is available by type:

| `type` | Events | Logs |
|---|---|---|
| `service`, `async-service`, `job` | `list_application_events` | `get_logs` |
| `helm` | `list_application_events` | **none at application level** — go pod-level |
| `notebook`, `rstudio`, `ssh-server` | `list_application_events` | `get_logs` |

Do NOT call `get_logs` on a Helm application and report "no logs found". There is no application-level log stream for a Helm release — the logs are pod-level and reachable.

## Phase 2: Read the pod state

Call `list_k8s_pods` with `clusterId` and `namespace`. This is the entry point for every runtime question because it is the one thing observable in a single call, and it tells you which branch to take. Do NOT start from logs — whether logs exist, and which container holds them, is what this call establishes.

Each pod returns its `phase`, `restarts` and a `problem` field. Branch on what you see:

| Pod state | What it means | Next call |
|---|---|---|
| No pods at all | Nothing was ever created — usually the build never produced an image | `get_deployment` → `builds.md` |
| `Pending` | Nothing can schedule it | `list_k8s_events` for the reason, `list_k8s_nodes` for capacity and taints |
| `problem: OOMKilled` | Killed for exceeding its memory limit | `list_app_metric_charts` → `get_application_chart_data` for the memory trend |
| `problem: ImagePullBackOff` / `ErrImagePull` | The image could not be pulled — the container never ran, so there are no logs | `list_application_events` or `list_k8s_events` for the registry's reason |
| `problem: CrashLoopBackOff`, `restarts` climbing | Started and exited repeatedly | `get_k8s_pod_logs` with `previous: true` |
| `Running`, no problem, but misbehaving | Started fine; the issue is inside the application or its capacity | `get_logs`, then metrics |

**A `Pending` pod is not a failed pod.** Kubernetes leaves an unschedulable workload `Pending` indefinitely. Nothing reports failure and the deployment may still say `DEPLOY_SUCCESS`.

**No pods means look before Kubernetes.** If no image was produced there is nothing to inspect, and every `*_k8s_*` tool returns empty.

## Phase 3: Metrics and application state

Logs and events say what happened at a moment. Metrics show a trend, which is the only way to see a problem building rather than one that already fired.

Charts are a two-step call:

1. `list_app_metric_charts` — the charts available for the application
2. `get_application_chart_data` — the data for a chart from that list

Do NOT guess chart names; take them from step 1. These are per-application; for node-level capacity use `list_k8s_nodes`.

Reach for metrics when:

- the pod was `OOMKilled` — memory over time shows whether the limit is too low or the application leaks
- the user reports slowness rather than failure, where nothing is in the logs
- you are deciding whether resource requests need raising, instead of guessing

Two more tools worth knowing:

- `get_application_state` — the application's current state, for "is this healthy" without reading pods directly
- `list_application_deployments` — deployment history, for "it worked yesterday" and "what changed"

## Native tools vs k8s tools

Start native. Escalate only for what native cannot provide.

| | Retention | Use for |
|---|---|---|
| `list_application_events`, `get_logs` | Persisted | Anything historical; any pod that no longer exists |
| `list_k8s_events` | ~1h cluster TTL | Live scheduling and pull failures |
| `get_k8s_pod_logs` | Pod lifetime only | Current or just-crashed container output |
| `list_k8s_pods`, `list_k8s_nodes` | Live only | Pod phase, restarts, `problem`; node capacity and taints |
| `list_app_metric_charts`, `get_application_chart_data` | Persisted | An application's CPU, memory and throughput over time |
| `get_application_state`, `list_application_deployments` | Persisted | Current health; deployment history |

Escalate to `*_k8s_*` when you need live pod state, a previous container's logs, scheduling detail, or node capacity. Every `*_k8s_*` tool takes `clusterId` as a path parameter and, except for `list_k8s_nodes`, a `namespace` equal to the workspace name.

Kubernetes discards events after roughly an hour and keeps pod logs only for the life of the pod. Asking a k8s tool a historical question returns nothing — not because nothing happened, but because it is gone.

## Reading logs from a crashing container

A container in `CrashLoopBackOff` has usually produced nothing in its current attempt. The stack trace is in the **previous** container.

Call `get_k8s_pod_logs` with `previous: true`. Without it you read an empty log and conclude the application is silent when it is failing loudly one container back.

Useful parameters: `podName` or `deploymentName` or `jobName` or `labelSelector` (one is required), `container` when the pod has several, `tailLines`, `previous`, `timestamps`.

A pod that has never restarted has no previous container and returns an error **for that pod only** — the other pods still return logs. That is expected, not a fault.

## Helm applications

Events work normally. Logs do not.

1. `list_k8s_pods` with `clusterId` and `namespace` (the workspace name) to get the real pod names.
2. `get_k8s_pod_logs` with the `podName` from step 1.

**Never construct a pod name.** Subcharts append their own suffixes to the release name:

```
release      my-cache
StatefulSet  my-cache-master
pod          my-cache-master-0        # <set>-<ordinal>
```

`my-cache-0` does not exist, and a query for a pod that does not exist returns empty rather than an error. Deployment-backed pods carry a generated ReplicaSet hash (`my-api-7d4b9c8f2a-x4kqp`) and are equally unpredictable. List, then read.

## Interpreting an empty result

An empty list means either "nothing happened" or "I could not see it". Before reporting that a workload is healthy, rule out the second:

- Could the tool see it? k8s events older than ~1h are gone; logs for a replaced pod are gone.
- Did you ask the right layer? A failed build leaves no pod; an unschedulable pod leaves no logs.
- Is this a Helm release where you asked for application-level logs?

State what you could not see rather than reporting health. "No events in the last hour" and "nothing is wrong" are different claims, and an empty result supports only the first.

**`DEPLOY_SUCCESS` means the rollout was accepted, not that the workload is healthy.** A pod that is crashlooping, out of memory, or unable to pull its image still reports it. Confirm with `list_k8s_pods` before telling a user their deployment worked.

## Checklist

- [ ] If more than one workspace had an application with that name, did I ask which one rather than diagnosing the first?
- [ ] Did I call `get_application` for `type` and `id`, then `list_workspaces` for `clusterId` and the namespace?
- [ ] If the type is `helm`, did I go pod-level for logs instead of calling `get_logs`?
- [ ] Did I read pod state with `list_k8s_pods` before deciding where to look?
- [ ] For a crashlooping container, did I pass `previous: true`?
- [ ] Did I get pod names from `list_k8s_pods` rather than constructing them?
- [ ] For anything historical, did I use the native tools rather than k8s tools?
- [ ] For an OOM kill or a slowness report, did I look at the memory trend rather than only the logs?
- [ ] Did I take chart names from `list_app_metric_charts` rather than guessing them?
- [ ] If a call returned empty, did I check whether that tool could have seen the answer at all?
- [ ] If the deployment says `DEPLOY_SUCCESS`, did I confirm the pods are actually running?
- [ ] Does my answer cite the specific pod, event or log line behind each claim?

For more info: `search_docs` with "monitor your service", "debug a deployment".
