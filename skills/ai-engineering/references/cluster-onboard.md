---
name: cluster-onboard
description: Diagnose and guide cluster onboarding / agent / addon health when apps cannot schedule or status does not publish. Read when a new cluster is disconnected, addons missing, or widespread Pending across workspaces.
---

Cluster problems present as “my deploy is broken” but the fix is on the **cluster / agent / addon** plane, not the application manifest.

## Contents
- Signals this is a cluster issue
- What to check
- Onboarding guidance
- Handoff
- Checklist

## Signals this is a cluster issue

- Many apps in different workspaces Pending simultaneously.
- `list_k8s_pods` / cluster tools fail or return empty for a cluster that should be connected.
- UI status stale for everyone; Argo/apps not syncing (`failure-modes/rollout-argocd.md`).
- GPU / Karpenter / autoscaler addons missing while users request GPUs (`failure-modes/pending-scheduling.md`, `failure-modes/cluster-capacity.md`).

If only one app fails with a clear CrashLoop log, stay on application playbooks.

## What to check

1. Cluster connection / agent health — `list_clusters` or equivalent; tfy-agent deployment Ready; agent logs if cluster is connected but status is stale (`failure-modes/rollout-argocd.md`).
2. `list_cluster_addons` — required addons for GPU, storage, ingress, Argo.
3. Node / capacity — widespread FailedScheduling (`failure-modes/cluster-capacity.md`).
4. Alerts — `list_alerts` when available.

Do not claim you can finish cloud account linking or IAM from Ask AI if those require Console/cloud admin steps — give the exact checklist.

## Onboarding guidance

When the user is **adding** a cluster:

1. `search_docs` for the matching cloud (EKS/GKE/AKS/existing K8s) onboarding guide.
2. Order of operations matters: register cluster → install agent → enable addons → create workspace → deploy.
3. GPU node pools / device plugins must exist before model `isAvailableInWorkspace` becomes true.
4. Storage classes must exist before PVC-backed model caches (`failure-modes/volumes-storage.md`).

## Handoff

- Single-app fix → application failure-mode files.
- Agent/Argo sync → `rollout-argocd.md`.
- Need platform engineering beyond documented addon toggles → follow `support-tickets.md`.

## Checklist

- [ ] Did I verify the blast radius (one app vs whole cluster)?
- [ ] Did I check agent, addons, and capacity before rewriting app manifests?
- [ ] Did I use cloud-specific docs for onboarding steps I cannot execute via MCP?

For more info: `search_docs` with "add cluster", "tfy-agent", "cluster addons".
