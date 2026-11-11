---
name: cluster-onboard
description: Diagnose and guide cluster onboarding / agent / addon health when apps cannot schedule or status does not publish. Read when a new cluster is disconnected, addons missing, or widespread Pending across workspaces.
---

Cluster problems present as “my deploy is broken” but the fix is on the **cluster / agent / addon** plane, not the application manifest.

## Signals this is a cluster issue

- Many apps in different workspaces Pending simultaneously.
- `get_application_state` / cluster tools fail or return empty for a cluster that should be connected.
- UI status stale for everyone; Argo/apps not syncing (`failure-modes/rollout-argocd.md`).
- GPU / Karpenter / autoscaler addons missing while users request GPUs (`failure-modes/pending-scheduling.md`, `failure-modes/cluster-capacity.md`).

If only one app fails with a clear CrashLoop log, stay on application playbooks.

## What to check

Get the `clusterId` from `list_workspaces` (or `list_clusters`). Steps 1–3 are independent — call them in one parallel batch.

1. `get_cluster_status id=<clusterId>` — `isConnected: false` means the agent tunnel is down.
2. `list_cluster_addons` — check each addon's `installed`, `healthStatus` and `syncStatus`. Names: agent → `TFY_AGENT`; sync → `ARGOCD`, `ARGO_ROLLOUT`, `ARGO_WORKFLOW`; GPU → `TFY_GPU_OPERATOR`; autoscaling → `KARPENTER`, `KEDA`, `ELASTI`; storage → `AWS_EFS_CSI_DRIVER`, `AWS_EBS_CSI_DRIVER`; ingress → `TFY_ISTIO_INGRESS`, `ISTIO_BASE`, `ISTIO_DISCOVERY`. Addons not applicable to the cluster type are not listed.
3. `get_cluster` — `firingAlertsCount`; then `list_alerts` for the cluster if it is non-zero (Autopilot only; if not listed, skip it).
4. Capacity — widespread FailedScheduling (`failure-modes/cluster-capacity.md`).

**tfy-agent has two parts.** **tfy-agent-proxy** carries control plane → cluster API calls; when it is down, `get_cluster_status` shows `isConnected: false` and runtime reads and deploys fail. **tfy-agent** streams cluster state; when it is down the cluster shows connected but statuses go stale (`failure-modes/rollout-argocd.md`). With read access to the tfy-agent workspace, `get_application_state` on the agent's `applicationId` (from `list_cluster_addons`) shows its pods; otherwise give the user `kubectl get deployment -n tfy-agent` to check both.

Do not claim you can finish cloud account linking or IAM yourself when those require console or cloud-admin steps — give the user the exact checklist.

## Onboarding guidance

When the user is **adding** a cluster:

1. `search_docs` for the matching cloud (EKS/GKE/AKS/existing K8s) onboarding guide.
2. Order of operations matters: register cluster → install agent → enable addons → create workspace → deploy.
3. On AKS and generic clusters, a GPU node pool must exist before a model option's `isAvailableInWorkspace` is `true`; on EKS/GKE it is always `true`, so check `TFY_GPU_OPERATOR` / `KARPENTER` in `list_cluster_addons` instead.
4. Storage classes must exist before PVC-backed model caches (`failure-modes/volumes-storage.md`).

## Handoff

- Single-app fix → application failure-mode files.
- Agent/Argo sync → `failure-modes/rollout-argocd.md`.
- Need platform engineering beyond documented addon toggles → follow `references/support-tickets.md`.

## Checklist

- [ ] Did I verify the blast radius (one app vs whole cluster)?
- [ ] Did I check `get_cluster_status`, addons and capacity before rewriting app manifests?
- [ ] Did I use cloud-specific docs for onboarding steps I cannot execute via MCP?

For more info: `search_docs` with "add cluster", "tfy-agent", "cluster addons".
