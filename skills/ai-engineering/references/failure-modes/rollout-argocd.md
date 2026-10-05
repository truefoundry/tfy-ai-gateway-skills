---
name: rollout-argocd
description: Read when a deploy is stuck — status not terminal or WAITING forever, Argo CD OutOfSync or compare failed, active version not updating, pods on the wrong version, canary not advancing. Covers blast radius (one app, one cluster, all clusters), sync, and restarting only the main tfy-agent Deployment.
---

TrueFoundry applies workloads through Argo CD (and often Argo Rollouts). **tfy-agent** on the compute cluster watches those objects and publishes application state (active version, deployment status, events) back to the control plane over **NATS**. A deploy can look fine in the cluster while the UI is stuck in `WAITING` — or the reverse — depending on which layer failed.

A common unblock (seen in the field): **restart only the main `tfy-agent` Deployment pods** on the affected cluster. Do **not** restart sibling components whose names also start with `tfy-agent-`.

## Contents
- Triage
- Blast radius (one app / one cluster / all clusters)
- When tfy-agent is the missing link
- Restart tfy-agent (exact Deployment only)
- tfy-agent logs
- Common patterns
- Helm-specific
- Checklist

## Triage

1. `get_deployment` — read `currentStatus` carefully:
   - Wait until `state.isTerminalState` before celebrating.
   - Non-terminal: `INITIALIZED`, `BUILDING`, `BUILD_SUCCESS`, `ROLLOUT_STARTED`, `WAITING`, `REDEPLOY_STARTED`, etc.
2. `list_k8s_pods` — are pods on the new version? Use `get_pod_template_hash_map` if you need to map hash → deployment version.
   - If pods are **Pending** with FailedScheduling → `failure-modes/pending-scheduling.md` (not agent restart first).
   - If pods are **missing / never appear** but status is `WAITING` for a long time, still continue here — agent/publish/sync issues often present as “stuck waiting / no progress” in the UI.
3. `get_applied_k8s_manifest` — what is actually applied.
4. For Helm: `get_application_argocd_resources` — resource health / sync status.
5. `list_application_events` around the deploy time.
6. If objects are OutOfSync or operation stuck: `sync_application` (writes — requires approval). Only after confirming the app is not paused.
7. **Blast radius** (next section) — one app vs one cluster vs all clusters.
8. If the **cluster looks healthy but control-plane status does not move** (or many apps stuck `WAITING`) — **tfy-agent restart** section below before rewriting the application manifest.

## Blast radius (one app / one cluster / all clusters)

Before restarting anything, establish scope:

| Scope | How to tell | Likely layer |
|---|---|---|
| **One application** | Sibling apps on the same cluster still update status / finish deploys | App-specific: pods, rollout strategy, Argo OutOfSync, build — stay on app playbooks first; agent restart is last resort |
| **One cluster** (many apps stuck `WAITING` / stale status / “no progress”) | Other clusters in the tenant look fine (`list_clusters` + spot-check another cluster’s `get_cluster_status` / a healthy app) | **tfy-agent on that cluster** (restart main agent pods) |
| **All / most clusters** | Status lag or stuck `WAITING` across unrelated clusters | Prefer **NATS / control-plane** connectivity first (agent publish path). Restarting one cluster’s agent may not fix others. Say NATS/control plane is in play; still can restart agents **per cluster** after calling that out |

Always call `list_clusters` + `get_cluster_status` on the affected cluster and at least one other cluster when the user has more than one. Do not jump to “delete tfy-agent” for a single CrashLooping app pod.

## When tfy-agent is the missing link

tfy-agent is what turns "Argo Synced / pods Running" into control-plane `DEPLOY_SUCCESS` and an updated `activeVersion`. Suspect it when:

| Cluster / Argo reality | Control plane / UI | Likely layer |
|---|---|---|
| Pods Running on the new version; Argo Synced/Healthy | Status stuck non-terminal (`WAITING`, `ROLLOUT_STARTED`, …) or active version stale | **tfy-agent not publishing** (or NATS) |
| UI stuck `WAITING` / “no new pods coming up” for a long time; other apps on cluster also stalled | Agent / sync path on **this** cluster | Restart **main** `tfy-agent` (below) |
| `operationState` missing/Failed but app Synced+Healthy | Status never advances | Try `sync_application` first; if still stuck, agent restart |
| Many apps stop updating status at once on one cluster | Cluster "connected" flapping or false | Agent — `get_cluster_status`, addon health, then restart |
| Same symptom on **every** cluster | NATS / control plane | Flag NATS; do not treat as one bad app manifest |

### What you can check

1. `get_cluster_status` — is the cluster agent connected?
2. `list_cluster_addons` — find **tfy-agent**; note sync/health. Missing/unhealthy agent explains widespread status lag.
3. `get_application_state` — empty/stale while `list_k8s_pods` shows a live version → publishing broken even if workload runs.
4. Wall-clock: deploy started long ago, pods Ready (or nothing progressing) for minutes, status still `WAITING` → agent/publish path, not “wait a bit more for the image”.

Workspace-scoped `*_k8s_*` tools usually **cannot** read the `tfy-agent` namespace. Do not pretend you listed those pods via tools if the call failed or is disallowed.

## Restart tfy-agent (exact Deployment only)

**Goal:** bounce the main agent so it reconnects and resumes publishing / syncing. Field fix that often unblocks stuck `WAITING`: restart Deployment **`tfy-agent`** only.

### What to restart

| Restart | Do not restart |
|---|---|
| Kubernetes **Deployment** named exactly `tfy-agent` (namespace usually `tfy-agent`) | `tfy-agent-proxy` |
| Pods owned by that Deployment only (name often `tfy-agent-<hash>-<id>`) | Anything like `tfy-agent-sds-server-…`, `sds-server`, `tfy-agent-external-secret-…`, `external-secrets`, ESO, SDS |
| | Other addons that merely share the `tfy-agent` **prefix** or Helm release |

If unsure which Deployment is the main agent: prefer the one whose name is **exactly** `tfy-agent`. Never bulk-delete `tfy-agent-*`.

### How to restart (the user runs it)

No tool you have restarts or deletes pods in the `tfy-agent` namespace, so this is a command the **user** runs — it does not go through the approval flow, and you should not present it as something you did. Do **not** substitute a tool call that would delete or restart application pods instead.

1. Confirm blast radius = this cluster (or proceed per-cluster after the NATS callout).
2. Confirm via `list_cluster_addons` that tfy-agent is installed on that cluster.
3. Tell the user what the restart does and why you think it applies, then give them the exact commands:

```bash
kubectl -n tfy-agent rollout restart deployment/tfy-agent
kubectl -n tfy-agent rollout status deployment/tfy-agent
```

`rollout restart` replaces only the pods of that one Deployment. Do not offer deleting pods by label as an alternative: you cannot see that namespace, so you cannot check what else a selector would match.

If they manage the addon through Argo CD: open the **tfy-agent** Application and restart **only** the `tfy-agent` Deployment (not sibling Deployments in the same app).

If their install uses a different namespace, the Deployment name is still `tfy-agent`.

### If Deployment `tfy-agent` is not found

1. Say so — do not guess other Deployments to restart.
2. Tell the user to restart the main tfy-agent workload from **Argo CD** (tfy-agent Helm/Application) or with kubectl once they locate the Deployment named `tfy-agent`.
3. Example guidance:

```bash
kubectl get deploy -A --field-selector metadata.name=tfy-agent
# then: kubectl -n <namespace from the output> rollout restart deployment/tfy-agent
```

4. Optionally `list_cluster_addons` / `get_cluster_status` evidence that the agent addon is missing or unhealthy → `cluster-onboard.md` / support ticket if the addon itself is gone.

### After restart

1. Re-check `get_cluster_status`.
2. Re-check the stuck application’s `get_deployment` / `get_application_state` — status should leave `WAITING` or active version should catch up within a few minutes.
3. If still stuck on **all** clusters → escalate NATS / control plane (`references/support-tickets.md`) rather than restarting agents again.
4. If still stuck on **one** app only with bad pods → return to app failure-mode files.

`sync_application` rewrites Argo `operationState` so the agent can publish `DEPLOY_SUCCESS` again when status was cleared and `operationState` left empty while the app stayed Synced/Healthy. Use it when that pattern fits; it does not replace fixing a stuck agent.

## tfy-agent logs

Useful lines (when the user can pull them):

- `APPLICATION ACTIVE VERSION SYNC` / `APPLICATION DEPLOYMENT STATE SYNC` / `DEPLOY_SUCCESS`
- `ARGO APPLICATION STATE SYNC`
- Errors publishing status / NATS publish failures for the application name

Ask the user for logs from the **main** `tfy-agent` pods only. Do not claim you already read `tfy-agent` namespace logs via MCP if you could not.

## Common patterns

| Symptom | Likely cause | Action |
|---|---|---|
| Status non-terminal for a long time, build still `STARTED` | Build running or stuck | `builds.md` |
| `DEPLOY_SUCCESS` but old pods remain | Rollout/traffic strategy, HPA, PDB, or failed new ReplicaSet | Pods + Rollout object; `rollout-strategy.md` |
| Pods Ready / Argo healthy, status never terminal or active version stale | **tfy-agent publish path** | Cluster status + addon; **restart main tfy-agent**; request agent logs; `sync_application` if `operationState` empty |
| Many apps `WAITING` on one cluster; other clusters OK | Agent on that cluster | Restart **only** `deployment/tfy-agent` |
| Same stuck status on all clusters | **NATS / control plane** | Call out NATS; then per-cluster agent restart if still needed; escalate if persists |
| UI / resources show compare or credentials scheme errors | Argo CD repo/credential misconfig | `list_cluster_addons`, `get_cluster_status` |
| Paused application | Sync/deploy blocked | `resume_application` then retry |
| Manual change in cluster drifted | OutOfSync | `sync_application` or redeploy |
| Canary / progressive rollout stuck | Analysis/metrics failing or steps waiting | Rollout CR status via `describe_k8s_object` / list objects |

## Helm-specific

`get_application_argocd_resources` only works for Helm applications. For services, use pods + applied manifest + events instead. The tfy-agent publishing rules are the same for both.

## Checklist

- [ ] Did I check `isTerminalState` before reporting deploy success?
- [ ] Did I verify pods (Pending vs Running vs missing) before blaming the agent?
- [ ] Did I establish blast radius (one app / one cluster / all clusters) and mention NATS when all clusters are affected?
- [ ] For Helm apps, did I inspect Argo resources when relevant?
- [ ] If recommending sync, did I confirm the app is not paused?
- [ ] If recommending agent restart, did I target **only** Deployment `tfy-agent` (not proxy/SDS/ESO/external-secret siblings)?
- [ ] If `tfy-agent` Deployment was not found, did I tell the user to restart from Argo CD / kubectl instead of guessing another workload?
- [ ] Did I avoid claiming I already read or deleted pods in the `tfy-agent` namespace when tools cannot?

For more info: `search_docs` with "rollout", "Argo CD", "deployment status", "tfy-agent".
