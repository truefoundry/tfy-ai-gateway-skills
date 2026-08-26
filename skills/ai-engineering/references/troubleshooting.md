---
name: troubleshooting
description: Diagnose a deployed workload — logs, events, crashes, pending pods, failed builds. Read this before calling get_logs, list_application_events, or any k8s tool, for any question about whether something is working or why it is not.
---

Operational questions arrive without the two facts that decide how to answer them: what type the application is, and how far in the past the answer lives. Both change which tools can see anything, and a tool that cannot see returns an empty result rather than an error — which reads exactly like good news.

## Contents

- Step 1: resolve the application type
- Step 2: work out which layer failed
- Choosing between native and Kubernetes tools
- Reading logs from a crashing container
- Helm applications
- When a result is empty

## Step 1: resolve the application type

Call `get_application` first. The `type` field changes what is available:

| type | events | logs |
| ---- | ------ | ---- |
| `service`, `async-service`, `job` | `list_application_events` | `get_logs` |
| `helm` | `list_application_events` | **no application-level logs** — go pod-level, see below |
| others | `list_application_events` | try `get_logs`, fall back to pod-level |

One call, and it prevents the most common wrong turn: reaching for `get_logs` on a Helm release and reporting "no logs" when the logs were simply somewhere else.

## Step 2: work out which layer failed

Failures happen at different layers, and each layer is visible to a different tool. Establish the layer before choosing a tool — an agent that always checks pods, then logs, then events gets most of these wrong.

| What went wrong | Layer | What actually answers it |
| --------------- | ----- | ------------------------ |
| Out of memory | runtime | `list_k8s_pods` — the `problem` field says `OOMKilled` |
| Application error, crashlooping | runtime | `get_k8s_pod_logs` with `previous: true` |
| Image cannot be pulled, bad tag, missing credentials | pull | `list_application_events` or `list_k8s_events` — no logs exist, the container never started |
| Nothing will schedule it — no capacity, no GPU, a taint | schedule | `list_k8s_events` plus `list_k8s_nodes` |
| The build never produced an image | before Kubernetes | `get_deployment` and `builds.md` — no pod exists, so every Kubernetes tool is the wrong tool |

Two of these are easy to misread:

**A pending pod is not a failed pod.** When nothing can schedule a workload, Kubernetes leaves it `Pending` indefinitely. Nothing reports failure, health checks say nothing is wrong, and the deployment may still say it succeeded. Look at the pod phase directly.

**A failed build has no pod at all.** If the image was never produced, there is nothing running to inspect. Reaching for pod logs here returns nothing and looks like a healthy quiet service.

## Choosing between native and Kubernetes tools

Start with the native tools — `get_logs`, `list_application_events`. They persist history, they are scoped to the application, and they keep working after a pod is gone.

Escalate to the `*_k8s_*` tools when you need something native cannot give you:

- live pod state — phase, restart count, the reason a container is failing
- the previous container's logs after a crash
- scheduling detail: why nothing will place this pod
- node capacity or taints

The two see different windows. Kubernetes discards events after roughly an hour and keeps pod logs only for the life of the pod, while the native tools persist. So for anything historical, or any pod that no longer exists, the Kubernetes tools return nothing — not because nothing happened, but because it is no longer there to see.

## Reading logs from a crashing container

A container in `CrashLoopBackOff` has usually produced nothing in its current attempt — it died before it could. The stack trace explaining the crash is in the **previous** container.

Pass `previous: true` to `get_k8s_pod_logs`. Without it you will read an empty log and conclude the application is silent, when in fact it is failing loudly one container back.

If a pod has never restarted there is no previous container, and the request returns an error for that pod rather than for the whole call. That is expected, not a fault.

## Helm applications

Events behave normally: use `list_application_events`.

Logs do not. There is no application-level log stream for a Helm release, so go pod-level:

1. `list_k8s_pods` for the workspace namespace
2. `get_k8s_pod_logs` for the pod you want

**Do not construct pod names.** A Helm chart's subcharts append their own suffixes to the release name, so a release called `nikp-redis` produces a StatefulSet called `nikp-redis-master` and a pod called `nikp-redis-master-0`. Guessing `nikp-redis-0` finds nothing. List the pods and read the real names.

The same applies to anything that owns pods indirectly. StatefulSet pods are named `<set>-<ordinal>`; Deployment pods carry a generated ReplicaSet hash. Neither is predictable from the application name.

## When a result is empty

An empty list is the least informative answer a tool can give, because it means either "nothing happened" or "I could not see it". Before reporting that a workload is fine:

- Could the tool have seen it? Kubernetes events older than an hour are gone. Pod logs for a replaced pod are gone.
- Did you ask the right layer? A failed build leaves no pod; an unschedulable pod leaves no logs.
- Is this a Helm release where you asked for application-level logs?

If the check that returned empty was one of these, say what you could not see rather than reporting health. "No events in the last hour" and "nothing is wrong" are different statements, and only one of them is supported by an empty result.
