---
name: rollout-argocd
description: Deploy stuck, OutOfSync, Argo CD compare failed, rollout not progressing, WAITING forever, canary/traffic shift stuck, sync required. Read when deployment status is not terminal, UI shows sync errors, or pods mismatch the desired version.
---

TrueFoundry applies workloads through Argo CD (and often Argo Rollouts). A deploy can be "accepted" while the cluster objects are not what the user expects.

## Triage

1. `get_deployment` — read `currentStatus` carefully:
   - Wait until `state.isTerminalState` before celebrating.
   - Non-terminal: `INITIALIZED`, `BUILDING`, `BUILD_SUCCESS`, `ROLLOUT_STARTED`, `WAITING`, `REDEPLOY_STARTED`, etc.
2. `list_k8s_pods` — are pods on the new version? Use `get_pod_template_hash_map` if you need to map hash → deployment version.
3. `get_applied_k8s_manifest` — what is actually applied.
4. For Helm: `get_application_argocd_resources` — resource health / sync status.
5. `list_application_events` around the deploy time.
6. If objects are OutOfSync or operation stuck: `sync_application` (writes — requires approval). Only after confirming the app is not paused.

## Common patterns

| Symptom | Likely cause | Action |
|---|---|---|
| Status non-terminal for a long time, build still `STARTED` | Build running or stuck | `builds.md` |
| `DEPLOY_SUCCESS` but old pods remain | Rollout/traffic strategy, HPA, PDB, or failed new ReplicaSet | Pods + Rollout object via `list_k8s_objects` |
| UI / resources show compare or credentials scheme errors | Argo CD repo/credential misconfig | Cluster addon / Argo health — often infra; `list_cluster_addons`, `get_cluster_status` |
| Paused application | Sync/deploy blocked | `resume_application` then retry |
| Manual change in cluster drifted | OutOfSync | `sync_application` or redeploy |
| Canary / progressive rollout stuck | Analysis/metrics failing or steps waiting | Rollout CR status via `describe_k8s_object` / list objects |

## Helm-specific

`get_application_argocd_resources` only works for Helm applications. For services, use pods + applied manifest + events instead.

## Checklist

- [ ] Did I check `isTerminalState` before reporting deploy success?
- [ ] Did I verify pods match the intended version?
- [ ] For Helm, did I inspect Argo resources?
- [ ] If recommending sync, did I confirm the app is running (not paused)?

For more info: `search_docs` with "rollout", "Argo CD", "deployment status".
