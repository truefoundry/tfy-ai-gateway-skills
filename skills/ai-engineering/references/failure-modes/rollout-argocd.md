---
name: rollout-argocd
description: Read when a deploy is stuck — status not terminal or WAITING forever, Argo CD OutOfSync or compare failed, active version not updating, pods on the wrong version, canary not advancing. Covers blast radius (one app, one cluster, all clusters), sync, and restarting only the main tfy-agent Deployment.
---

TrueFoundry applies workloads through Argo CD (and often Argo Rollouts). **tfy-agent** on the compute cluster watches those objects and publishes application state (active version, deployment status, pods) to the TrueFoundry control plane (agent → controller over secure WebSocket; the control plane stores it in NATS). A deploy can look fine in the cluster while the UI is stuck in `WAITING` — or the reverse — depending on which layer failed.

A common unblock (seen in the field): **restart only the main `tfy-agent` Deployment pods** on the affected cluster. Do **not** restart sibling components whose names also start with `tfy-agent-`.

## Triage

1. Issue in one message: `get_deployment`, `get_application_state`, `get_applied_k8s_manifest`, `list_application_events` (with a `startTs` around the deploy), `get_cluster_status`, plus `get_application_argocd_resources` for Helm apps. Then decide.
2. Read `get_deployment` → `currentStatus`:
   - Wait for `state.isTerminalState` before celebrating.
   - Non-terminal statuses: `INITIALIZED`, `BUILDING`, `BUILD_SUCCESS`, `ROLLOUT_STARTED`, `SET_TRAFFIC`, `PAUSED`, `REDEPLOY_STARTED`, `DEPLOY_FAILED_WITH_RETRY`.
   - `WAITING` is not a status: it is `currentStatus.transition` (on `ROLLOUT_STARTED` / `SET_TRAFFIC` / `PAUSED`) and means manifests were applied and the platform is waiting for the rollout to finish.
3. Read `get_application_state`: are pods on the new version (pod `version` vs `activeVersion`)?
   - Pods **Pending** with an `Unschedulable` condition → `failure-modes/pending-scheduling.md` (not agent restart first).
   - Pods **missing / never appear** but `transition: WAITING` for a long time → continue here; agent/publish/sync issues often present as "stuck waiting / no progress".
4. If objects are OutOfSync or the operation is stuck: `sync_application` (write — requires approval). If it returns 400 "Application is paused", call `resume_application` first.
5. **Blast radius** (next section) — one app vs one cluster vs all clusters.
6. If the **cluster looks healthy but control-plane status does not move** (or many apps stuck on `transition: WAITING`) — **tfy-agent restart** section below before rewriting the application manifest.

Argo sync / health / `operationState` of a non-Helm app is not readable by any tool; when you need it, give the user `kubectl get application <app name> -n <workspace name> -o yaml` (look at `status.sync`, `status.health`, `status.operationState`).

## Blast radius (one app / one cluster / all clusters)

Before restarting anything, establish scope:

| Scope | How to tell | Likely layer |
|---|---|---|
| **One application** | Sibling apps on the same cluster still update status / finish deploys | App-specific: pods, rollout strategy, Argo OutOfSync, build — stay on app playbooks first; agent restart is last resort |
| **One cluster** (many apps stuck on `transition: WAITING` / stale status) | Other clusters in the tenant look fine (`list_clusters`, then `get_application_state` on a healthy app there) | **tfy-agent on that cluster** (restart main agent pods) |
| **All / most clusters** | Status lag or stuck `WAITING` across unrelated clusters | **Control plane** (controller/NATS) first. Restarting one cluster's agent may not fix others. Say so; you can still restart agents per cluster after calling that out |

Call `list_clusters` and check the affected cluster plus at least one other when the user has more than one. Several TrueFoundry clusters can be logical clusters on one physical cluster sharing one tfy-agent: if the affected "clusters" share a physical cluster, treat them as one (one agent, one restart). Do not jump to "restart tfy-agent" for a single CrashLooping app pod.

## When tfy-agent is the missing link

tfy-agent is what turns "Argo Synced / pods Running" into control-plane `DEPLOY_SUCCESS` and an updated `activeVersion`. Suspect it when:

| Cluster / Argo reality | Control plane / UI | Likely layer |
|---|---|---|
| Pods Running on the new version; Argo Synced/Healthy | Status non-terminal (`transition: WAITING`, `ROLLOUT_STARTED`, …) or active version stale | **tfy-agent not publishing** (or control plane) |
| UI stuck `WAITING` / "no new pods coming up" for a long time; other apps on cluster also stalled | Agent / sync path on **this** cluster | Restart **main** `tfy-agent` (below) |
| `operationState` missing/Failed but app Synced+Healthy | Status never advances | Try `sync_application` first; if still stuck, agent restart |
| Many apps stop updating status at once on one cluster | Stale `eventGenerationTimestamp` across apps | Agent — check its pods (below), then restart |
| Same symptom on **every** cluster | Control plane | Escalate as a control-plane issue (`references/support-tickets.md`); do not treat as one bad app manifest |

### What you can check

1. `get_cluster_status` → `isConnected` shows only whether the control plane reaches the cluster through tfy-agent-proxy. It does not show whether the main `tfy-agent` is publishing.
2. To test publishing, read `get_application_state` on an affected app: `null`, or an `eventGenerationTimestamp` older than pod changes the user can see (UI or `kubectl get pods -n <workspace>`), means the agent is not publishing — even when `isConnected` is true.
3. `list_cluster_addons` → find **tfy-agent**; note `installed` and `applicationId`. It has no health field: call `get_application_state` with that `applicationId` to see the agent's pods (needs read access to the tfy-agent workspace).
4. Wall-clock: deploy started long ago, pods Ready (or nothing progressing) for minutes, still `transition: WAITING` → agent/publish path, not "wait a bit more for the image".

## Restart tfy-agent (exact Deployment only)

**Goal:** bounce the main agent so it reconnects and resumes publishing / syncing.

| Restart | Do not restart |
|---|---|
| Kubernetes **Deployment** named exactly `tfy-agent` (namespace usually `tfy-agent`) | `tfy-agent-proxy` |
| Pods owned by that Deployment only (name often `tfy-agent-<hash>-<id>`) | Anything like `tfy-agent-sds-server-…`, `sds-server`, `tfy-agent-external-secret-…`, `external-secrets`, ESO, SDS |
| | Other addons that merely share the `tfy-agent` **prefix** or Helm release |

If unsure which Deployment is the main agent: prefer the one whose name is **exactly** `tfy-agent`. Never bulk-delete `tfy-agent-*`.

### How to restart (the user runs it)

No tool restarts or deletes pods, so this is a command the **user** runs — it does not go through the approval flow, and you should not present it as something you did. Do **not** substitute a tool call that would delete or restart application pods instead.

1. Confirm blast radius = this cluster (or proceed per-cluster after the control-plane callout).
2. Confirm via `list_cluster_addons` that tfy-agent is installed on that cluster.
3. Tell the user what the restart does and why you think it applies, then give them the exact commands:

```bash
kubectl -n tfy-agent rollout restart deployment/tfy-agent
kubectl -n tfy-agent rollout status deployment/tfy-agent
```

`rollout restart` replaces only the pods of that one Deployment. Do not offer deleting pods by label as an alternative: a selector can match sibling components you cannot rule out.

If they manage the addon through Argo CD: open the **tfy-agent** Application and restart **only** the `tfy-agent` Deployment (not sibling Deployments in the same app). If their install uses a different namespace, the Deployment name is still `tfy-agent`.

### If Deployment `tfy-agent` is not found

Say so — do not guess other Deployments to restart. Tell the user to restart the main tfy-agent workload from **Argo CD** (tfy-agent Application) or with kubectl once they locate it:

```bash
kubectl get deploy -A --field-selector metadata.name=tfy-agent
# then: kubectl -n <namespace from the output> rollout restart deployment/tfy-agent
```

Agent addon missing from `list_cluster_addons` → `cluster-onboard.md` / support ticket.

### After restart

1. Re-check the stuck application's `get_deployment` / `get_application_state` — `eventGenerationTimestamp` should be fresh, the transition should leave `WAITING` or the active version catch up within a few minutes.
2. If still stuck on **all** clusters → escalate as a control-plane issue (`references/support-tickets.md`) rather than restarting agents again.
3. If still stuck on **one** app only with bad pods → return to app failure-mode files.

`sync_application` rewrites Argo `operationState` so the agent can publish `DEPLOY_SUCCESS` again when status was cleared and `operationState` left empty while the app stayed Synced/Healthy. Use it when that pattern fits; it does not replace fixing a stuck agent.

## tfy-agent logs

Try once to read the main agent yourself: `get_logs(applicationId=<tfy-agent applicationId from list_cluster_addons>, podNamesRegex="^tfy-agent-[a-z0-9]+-[a-z0-9]{5}$", direction="desc", limit=200)` — the regex excludes `tfy-agent-proxy`. Ask the user for logs only if that returns 403/404 or nothing, and never claim you read them when you did not. Useful lines:

- `APPLICATION ACTIVE VERSION SYNC` / `APPLICATION DEPLOYMENT STATE SYNC` / `DEPLOY_SUCCESS`
- `ARGO APPLICATION STATE SYNC`
- Errors publishing status for the application name

## Common patterns

| Symptom | Likely cause | Action |
|---|---|---|
| Status non-terminal for a long time, build still `STARTED` | Build running or stuck | `builds.md` |
| `DEPLOY_SUCCESS` but old pods remain | Rollout/traffic strategy, HPA, PDB, or failed new ReplicaSet | Pod versions + `rollout-strategy.md` |
| Pods Ready / Argo healthy, status never terminal or active version stale | **tfy-agent publish path** | Agent checks above; **restart main tfy-agent**; agent logs; `sync_application` if `operationState` empty |
| Many apps `WAITING` on one cluster; other clusters OK | Agent on that cluster | Restart **only** `deployment/tfy-agent` |
| Same stuck status on all clusters | **Control plane** (controller/NATS) | Escalate as a control-plane issue (`references/support-tickets.md`); per-cluster agent restart only if still needed |
| Compare or repo-credential errors in Argo | Argo CD repo/credential misconfig | `get_application_argocd_resources` (Helm) or the user's `kubectl get application` output |
| Manual change in cluster drifted | OutOfSync | `sync_application` or redeploy |
| Canary / progressive rollout stuck | Analysis/metrics failing or steps waiting | Helm: `get_application_argocd_resources`; otherwise pod versions in `get_application_state` + events, or ask the user for `kubectl describe rollout <name> -n <workspace>` |

## Checklist

- [ ] Did I check `isTerminalState` before reporting deploy success, and read `WAITING` as a transition?
- [ ] Did I verify pods (Pending vs Running vs missing) before blaming the agent?
- [ ] Did I establish blast radius (one app / one cluster / all clusters), and call out the control plane when all clusters are affected?
- [ ] Did I test publishing with `eventGenerationTimestamp`, not only `isConnected`?
- [ ] For Helm apps, did I inspect Argo resources when relevant?
- [ ] If recommending agent restart, did I target **only** Deployment `tfy-agent` (not proxy/SDS/ESO/external-secret siblings)?
- [ ] If `tfy-agent` Deployment was not found, did I tell the user to restart from Argo CD / kubectl instead of guessing another workload?
- [ ] Did I avoid claiming I read agent logs or restarted pods when I did not?

For more info: `search_docs` with "rollout", "Argo CD", "deployment status", "tfy-agent".
