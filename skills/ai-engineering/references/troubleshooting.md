---
name: troubleshooting
description: Diagnose a deployed workload — logs, events, crashes, pending pods, failed builds. Read this before calling get_logs, list_application_events, or any k8s tool, for any question about whether an application is working or why it is not.
---

Operational questions arrive without the two facts that decide how to answer them: the application's **type**, and how far in the **past** the answer lives. Both change which tools can see anything, and a tool that cannot see returns an empty list rather than an error — which reads exactly like good news.

## Contents
- Phase 1: Identify the application
- Phase 2: Identify the failing layer
- Native tools vs k8s tools
- Reading logs from a crashing container
- Helm applications
- Interpreting an empty result
- Checklist

## Phase 1: Identify the application

Call `list_applications` (filter by name) or `get_application` to get the application. Record four fields before doing anything else:

| Field | Why you need it |
|---|---|
| `type` | Decides whether application-level logs exist. See the table below. |
| `id` | Required by `get_deployment`. |
| `workspaceId` / workspace name | The k8s namespace equals the workspace name. |
| `clusterId` | Required by every `*_k8s_*` tool as a path parameter. |

What is available by type:

| `type` | Events | Logs |
|---|---|---|
| `service`, `async-service`, `job` | `list_application_events` | `get_logs` |
| `helm` | `list_application_events` | **none at application level** — go pod-level |
| `notebook`, `rstudio`, `ssh-server` | `list_application_events` | `get_logs` |

Do NOT call `get_logs` on a Helm application and report "no logs found". There is no application-level log stream for a Helm release — the logs are pod-level and reachable.

## Phase 2: Identify the failing layer

Establish where the failure is before choosing a tool. An agent that always runs pods → logs → events gets most of these wrong.

| Symptom | Layer | Tool that answers it |
|---|---|---|
| Container killed, restart count climbing | runtime | `list_k8s_pods` — read the `problem` field, e.g. `OOMKilled` |
| Application throws and restarts | runtime | `get_k8s_pod_logs` with `previous: true` |
| Image cannot be pulled, bad tag, no credentials | pull | `list_application_events`, or `list_k8s_events` for the live view |
| Nothing schedules it — no capacity, no GPU, a taint | schedule | `list_k8s_events` + `list_k8s_nodes` |
| Never produced an image | pre-Kubernetes | `get_deployment` → `builds.md` |

**A `Pending` pod is not a failed pod.** When nothing can schedule a workload, Kubernetes leaves it `Pending` indefinitely. Nothing reports failure and the deployment may still say `DEPLOY_SUCCESS`. Read the pod phase directly from `list_k8s_pods`.

**A failed build has no pod.** If no image was produced there is nothing running to inspect, and every k8s tool returns empty. Check `get_deployment` before reaching for pod tools.

## Native tools vs k8s tools

Start native. Escalate only for what native cannot provide.

| | Retention | Use for |
|---|---|---|
| `list_application_events`, `get_logs` | Persisted | Anything historical; any pod that no longer exists |
| `list_k8s_events` | ~1h cluster TTL | Live scheduling and pull failures |
| `get_k8s_pod_logs` | Pod lifetime only | Current or just-crashed container output |
| `list_k8s_pods`, `list_k8s_nodes` | Live only | Pod phase, restarts, `problem`; node capacity and taints |

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
release      nikp-redis
StatefulSet  nikp-redis-master
pod          nikp-redis-master-0        # <set>-<ordinal>
```

`nikp-redis-0` does not exist, and a query for a pod that does not exist returns empty rather than an error. Deployment-backed pods carry a generated ReplicaSet hash (`tsx-gpu-86d675bf87-hcgbd`) and are equally unpredictable. List, then read.

## Interpreting an empty result

An empty list means either "nothing happened" or "I could not see it". Before reporting that a workload is healthy, rule out the second:

- Could the tool see it? k8s events older than ~1h are gone; logs for a replaced pod are gone.
- Did you ask the right layer? A failed build leaves no pod; an unschedulable pod leaves no logs.
- Is this a Helm release where you asked for application-level logs?

State what you could not see rather than reporting health. "No events in the last hour" and "nothing is wrong" are different claims, and an empty result supports only the first.

**`DEPLOY_SUCCESS` means the rollout was accepted, not that the workload is healthy.** A pod that is crashlooping, out of memory, or unable to pull its image still reports it. Confirm with `list_k8s_pods` before telling a user their deployment worked.

## Checklist

- [ ] Did I call `get_application` first and record `type`, `id`, workspace name and `clusterId`?
- [ ] If the type is `helm`, did I go pod-level for logs instead of calling `get_logs`?
- [ ] Did I identify which layer failed before choosing a tool?
- [ ] For a crashlooping container, did I pass `previous: true`?
- [ ] Did I get pod names from `list_k8s_pods` rather than constructing them?
- [ ] For anything historical, did I use the native tools rather than k8s tools?
- [ ] If a call returned empty, did I check whether that tool could have seen the answer at all?
- [ ] If the deployment says `DEPLOY_SUCCESS`, did I confirm the pods are actually running?
- [ ] Does my answer cite the specific pod, event or log line behind each claim?

For more info: `search_docs` with "monitor your service", "debug a deployment".
