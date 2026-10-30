---
name: cluster-capacity
description: Cluster disconnected, addons unhealthy, Prometheus missing, autoscaler failures, everything Pending across many apps, agent not reporting. Read when many applications fail together or cluster-level tools are needed.
---

When **multiple unrelated applications** misbehave the same way, stop debugging one manifest and check the cluster.

## Triage

1. `get_cluster` and `get_cluster_status`. `isConnected` shows only that the control plane reaches the cluster through tfy-agent-proxy. From `get_cluster` read `manifest.cluster_type` and `manifest.monitoring` (`prometheus_url`, `loki_url`, `victoria_logs_url`); reuse them if still in the conversation, otherwise call again. No `prometheus_url` → metrics tools return 405. No logs URL → `get_logs` returns 405 unless you pass `podName` and `containerName`, and then reads the live container only.
2. `list_cluster_addons` — Karpenter, GPU operator, metrics/Prometheus, CSI, ingress. It shows what is installed, not health; check a suspect addon with `get_application_state` on its `applicationId`.
3. Is tfy-agent publishing? `get_application_state` on two or three affected apps: `null` or an old `eventGenerationTimestamp` across them → `failure-modes/rollout-argocd.md`. The same call shows the node each pod landed on with its Ready / pressure conditions; for the full node picture ask the user for `kubectl get nodes`.
4. Provisioning, by `manifest.cluster_type`: Azure/GCP → `get_cluster_autoscaler_logs` with `direction: "desc"`; AWS → Karpenter events and NodeClaim status from the user (`failure-modes/pending-scheduling.md`).
5. Only then return to a single application's playbook.

Steps 1–4 are independent once you know a few affected apps: issue them in one message.

## Patterns

| Pattern | Interpretation |
|---|---|
| All new pods Pending; no NodeClaims | Provisioner/autoscaler broken or cloud quota |
| Nodes Ready but GPU allocatable 0 | GPU operator / device plugin |
| Metrics tools 405 / "no Prometheus" | Monitoring URL missing on cluster — cannot do OOM trend analysis; say so |
| `get_logs` returns 405 for every app | No Loki/VictoriaLogs URL on the cluster — only live container logs per pod are readable |
| Single workspace only | Quota, NetworkPolicy, or registry secret scoped to that workspace |

## What you cannot see

System namespaces are not visible to any tool (`tools.md` → What no tool can see). You may diagnose "addon unhealthy" from `list_cluster_addons` without being able to read the addon's logs. State that limit, give the user the `kubectl` command, and escalate with the evidence you do have.

## Checklist

- [ ] Did I check cluster status/addons before deep-diving one app, when failures are widespread?
- [ ] Did I notice missing Prometheus/logs backends and avoid fake metric conclusions?
- [ ] Did I separate cluster outage from application bugs in the answer?

For more info: `search_docs` with "cluster status", "addons", "compute plane".
