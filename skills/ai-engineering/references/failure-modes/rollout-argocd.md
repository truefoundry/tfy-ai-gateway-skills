---
name: rollout-argocd
description: Deploy stuck, OutOfSync, Argo CD compare failed, rollout not progressing, WAITING forever, canary/traffic shift stuck, sync required, status not updating despite healthy pods. Read when deployment status is not terminal, UI shows sync errors, pods mismatch the desired version, or the control plane never reaches DEPLOY_SUCCESS.
---

TrueFoundry applies workloads through Argo CD (and often Argo Rollouts). **tfy-agent** on the compute cluster watches those objects and publishes application state (active version, deployment status, events) back to the control plane. A deploy can look fine in the cluster while the UI is stuck — or the reverse — depending on which layer failed.

## Triage

1. `get_deployment` — read `currentStatus` carefully:
   - Wait until `state.isTerminalState` before celebrating.
   - Non-terminal: `INITIALIZED`, `BUILDING`, `BUILD_SUCCESS`, `ROLLOUT_STARTED`, `WAITING`, `REDEPLOY_STARTED`, etc.
2. `list_k8s_pods` — are pods on the new version? Use `get_pod_template_hash_map` if you need to map hash → deployment version.
3. `get_applied_k8s_manifest` — what is actually applied.
4. For Helm: `get_application_argocd_resources` — resource health / sync status.
5. `list_application_events` around the deploy time.
6. If objects are OutOfSync or operation stuck: `sync_application` (writes — requires approval). Only after confirming the app is not paused.
7. If the **cluster looks healthy but the control-plane status does not move** — check **tfy-agent** (section below) before blaming the application manifest.

## When tfy-agent is the missing link

tfy-agent is what turns "Argo Synced / pods Running" into control-plane `DEPLOY_SUCCESS` and an updated `activeVersion`. Suspect it when:

| Cluster / Argo reality | Control plane / UI | Likely layer |
|---|---|---|
| Pods Running on the new version; Argo Synced/Healthy | Status stuck non-terminal (`WAITING`, `ROLLOUT_STARTED`, …) or active version stale | **tfy-agent not publishing** (or NATS path) |
| `operationState` missing/Failed but app Synced+Healthy | Status never advances | Agent may refuse to trust sync until `operationState` is rewritten — try `sync_application` first; if still stuck, agent |
| Many apps stop updating status at once | Cluster "connected" flapping or false | Agent / connectivity — `get_cluster_status`, addon health |
| One app only, pods not Ready / Rollout progressing | Status correctly non-terminal | Not the agent — stay on pods/rollout |

### What Ask AI can check (no agent log access required)

1. `get_cluster_status` — is the cluster agent connected to the control plane?
2. `list_cluster_addons` — find **tfy-agent**; note sync/health. Unhealthy or missing agent explains widespread status lag.
3. `get_application_state` — if this is empty/stale while `list_k8s_pods` shows a live version, publishing is broken even though the workload runs.
4. Compare wall-clock: deploy started long ago, pods Ready for minutes, status still non-terminal → agent/publish path, not "wait for the image to start".

### tfy-agent logs

**Yes — for this failure class you want tfy-agent logs**, especially lines about:

- `APPLICATION ACTIVE VERSION SYNC` / `APPLICATION DEPLOYMENT STATE SYNC` / `DEPLOY_SUCCESS`
- `ARGO APPLICATION STATE SYNC`
- Errors publishing status / NATS publish failures for the application name

**Limitation:** `tfy-agent` runs in a platform namespace (typically `tfy-agent`). Workspace-scoped `*_k8s_*` tools **cannot** read that namespace, so Ask AI usually **cannot** fetch those logs itself.

When the pattern above matches:

1. Say clearly that the workload may already be fine on the cluster and the gap is **status publishing via tfy-agent**.
2. Ask the user (or infra) to pull agent logs in the cluster, e.g. pods in the `tfy-agent` namespace, filtered around the application name / deploy time — or check the agent's UI/logging stack if they have one.
3. Do **not** invent kubectl against `tfy-agent` as something you already ran via tools.
4. If `get_cluster_status` is disconnected or the tfy-agent addon is unhealthy, lead with that; logs confirm the publish error but connectivity/addon health is enough to escalate.

`sync_application` rewrites Argo `operationState` so the agent can publish `DEPLOY_SUCCESS` again when status was cleared and `operationState` left empty while the app stayed Synced/Healthy. Use it when that pattern fits; it does not replace fixing a down agent.

## Common patterns

| Symptom | Likely cause | Action |
|---|---|---|
| Status non-terminal for a long time, build still `STARTED` | Build running or stuck | `builds.md` |
| `DEPLOY_SUCCESS` but old pods remain | Rollout/traffic strategy, HPA, PDB, or failed new ReplicaSet | Pods + Rollout object via `list_k8s_objects` |
| Pods Ready / Argo healthy, status never terminal or active version stale | **tfy-agent publish path** | Cluster status + addon; request agent logs; consider `sync_application` if `operationState` empty |
| UI / resources show compare or credentials scheme errors | Argo CD repo/credential misconfig | Cluster addon / Argo health — often infra; `list_cluster_addons`, `get_cluster_status` |
| Paused application | Sync/deploy blocked | `resume_application` then retry |
| Manual change in cluster drifted | OutOfSync | `sync_application` or redeploy |
| Canary / progressive rollout stuck | Analysis/metrics failing or steps waiting | Rollout CR status via `describe_k8s_object` / list objects |

## Helm-specific

`get_application_argocd_resources` only works for Helm applications. For services, use pods + applied manifest + events instead. The tfy-agent publishing rules are the same for both.

## Checklist

- [ ] Did I check `isTerminalState` before reporting deploy success?
- [ ] Did I verify pods match the intended version?
- [ ] For Helm, did I inspect Argo resources?
- [ ] If recommending sync, did I confirm the app is running (not paused)?
- [ ] If the cluster looks healthy but UI status does not move, did I check `get_cluster_status` / tfy-agent addon and call out agent logs as the next evidence?
- [ ] Did I avoid claiming I already read `tfy-agent` namespace logs when the tools cannot access that namespace?

For more info: `search_docs` with "rollout", "Argo CD", "deployment status", "tfy-agent".
