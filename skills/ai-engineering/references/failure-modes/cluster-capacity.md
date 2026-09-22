---
name: cluster-capacity
description: Cluster disconnected, addons unhealthy, Prometheus missing, autoscaler failures, everything Pending across many apps, agent not reporting. Read when many applications fail together or cluster-level tools are needed.
---

When **multiple unrelated applications** misbehave the same way, stop debugging one manifest and check the cluster.

## Triage

1. `get_cluster` / `get_cluster_status` — is the cluster connected? Is tfy-agent reporting?
2. `list_cluster_addons` — Karpenter, GPU operator, metrics/Prometheus, CSI, ingress.
3. `list_k8s_nodes` — Ready vs NotReady, pressure conditions, absent GPU labels.
4. `get_cluster_autoscaler_logs` — provisioning failures.
5. Only then return to a single application's playbook.

## Patterns

| Pattern | Interpretation |
|---|---|
| All new pods Pending; no NodeClaims | Provisioner/autoscaler broken or cloud quota |
| Nodes Ready but GPU allocatable 0 | GPU operator / device plugin |
| Metrics tools 405 / "no Prometheus" | Monitoring URL missing on cluster — cannot do OOM trend analysis; say so |
| `get_logs` fails for every app | Logging stack (Loki/Victoria) URL misconfigured on cluster |
| Single workspace only | Quota, NetworkPolicy, or registry secret scoped to that workspace |

## What you cannot see

System namespaces are usually outside workspace RBAC. You may diagnose "addon unhealthy" from `list_cluster_addons` without being able to `get_k8s_pod_logs` for the addon itself. State that limit and escalate with evidence you do have.

## Checklist

- [ ] Did I check cluster status/addons before deep-diving one app, when failures are widespread?
- [ ] Did I notice missing Prometheus/logs backends and avoid fake metric conclusions?
- [ ] Did I separate cluster outage from application bugs in the answer?

For more info: `search_docs` with "cluster status", "addons", "compute plane".
