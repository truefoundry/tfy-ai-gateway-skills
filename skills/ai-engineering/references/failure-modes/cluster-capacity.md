---
name: cluster-capacity
description: Cluster disconnected, addons unhealthy, Prometheus missing, autoscaler failures, everything Pending across many apps, agent not reporting. Read when many applications fail together or cluster-level tools are needed.
---

When **multiple unrelated applications** misbehave the same way, stop debugging one manifest and check the cluster.

## Triage

1. `get_cluster` / `get_cluster_status` — is the cluster connected? Is tfy-agent reporting?
2. `list_cluster_addons` — Karpenter, GPU operator, metrics/Prometheus, CSI, ingress.
3. Nodes — no tool lists them. `get_application_state` shows the node each pod landed on with its Ready / pressure conditions; for the full picture ask the user for `kubectl get nodes`.
4. `get_cluster_autoscaler_logs` — provisioning failures (Azure/GCP). On AWS expect 501; ask for NodeClaim status instead (`failure-modes/pending-scheduling.md`).
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

System namespaces are not visible to any tool (`tools.md` → What no tool can see). You may diagnose "addon unhealthy" from `list_cluster_addons` without being able to read the addon's logs. State that limit, give the user the `kubectl` command, and escalate with the evidence you do have.

## Checklist

- [ ] Did I check cluster status/addons before deep-diving one app, when failures are widespread?
- [ ] Did I notice missing Prometheus/logs backends and avoid fake metric conclusions?
- [ ] Did I separate cluster outage from application bugs in the answer?

For more info: `search_docs` with "cluster status", "addons", "compute plane".
