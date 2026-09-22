---
name: tools
description: Catalog of AI Deployment / AI Engineering MCP tools — what each answers, required inputs, and when not to use it. Read when unsure which tool to call, or before inventing a parameter.
---

Every tool below requires the `deployment` feature on the tenant. Gateway-only tenants do not see them.

## Contents
- Resolve identity first
- Application and deployment
- Logs, events, metrics, alerts
- Kubernetes reads
- Cluster and workspace
- Jobs
- Write / mutate (approval required)
- Bounds and empty results

## Resolve identity first

Almost every debug call needs some combination of `applicationId`, `workspaceId`/`namespace`, `clusterId`, and sometimes `deploymentId`. Resolve once and reuse:

| Need | Tool | Notes |
|---|---|---|
| Application by name | `list_applications` | Filter by name. Same name can exist in many workspaces — ask if ambiguous |
| Application details | `get_application` | Gives `id`, `type`, `workspaceFqn`, `activeDeployment` / `lastDeployment`, manifest |
| Workspace → cluster + namespace | `list_workspaces` | Filter `fqn=<workspaceFqn>`, pass `attributes=["id","name","fqn","clusterId"]`. **Namespace = workspace `name`** |
| Deployment history | `list_application_deployments` | Past versions, status progression |
| One deployment + builds | `get_deployment` | Needs application `id` + deployment `id`. Includes `deploymentBuilds` and status history |
| FQN → id | `get_id_from_fqn` | When the user pasted an FQN |

Never construct FQNs, pod names, or image URIs. List, then take values from the response.

## Application and deployment

| Tool | Answers | Key inputs |
|---|---|---|
| `list_applications` | What exists, by name/workspace | Prefer filters; unbounded lists are huge |
| `get_application` | Type, workspace, active/last deployment, user manifest | `id` |
| `get_deployment` | Status machine, builds, whether image was produced | application `id`, deployment `id` |
| `get_application_state` | Live components, active version, pod placement snapshot | application `id` |
| `get_applied_k8s_manifest` | What was actually applied to the cluster (resolved resources, redacted secrets) | application `id` |
| `get_application_argocd_resources` | Argo CD resource tree/status — **Helm apps only** | application `id` |
| `get_pod_template_hash_map` | Maps pod-template-hash → deployment version | When correlating pods to a version |
| `generate_deployment_endpoint` | Endpoint URL shape for a service | After deploy, for "how do I call it" |

**Status reading rules for `get_deployment`:**

- Read `currentStatus.state.isTerminalState` **before** trusting `currentStatus.state.type`. While a deploy is in progress, `type` can say `success` and still not be done.
- `DEPLOY_SUCCESS` = rollout accepted, **not** pods healthy.
- `BUILD_FAILED` / missing `imageUri` → go to `builds.md`, not k8s tools.
- `DEPLOY_FAILED` / `DEPLOY_FAILED_WITH_RETRY` → events + pods; may still have partial pods.

## Logs, events, metrics, alerts

| Tool | Layer | Retention | Use for |
|---|---|---|---|
| `get_logs` | Native app logs | Persisted | Historical stdout/stderr for service/async/job/notebook. Needs `applicationId` or `applicationFqn`. Optional `podName`/`deploymentId`/`jobRunName`/`searchString`. Default limit is large — pass a smaller `limit` and a tight `startTs`/`endTs` |
| `get_build_logs` | Build pipeline | Persisted | Build failures. Path param = build `name` (`pipelineRunName`). **Always pass build `logsStartTs` as `startTs`** |
| `get_k8s_pod_logs` | Live container | Pod lifetime | Crashloops: set `previous: true`. Needs `clusterId` + one of `podName` / `deploymentName` / `jobName` / `labelSelector` |
| `list_application_events` | Native events | Persisted | Pull/schedule/mount failures over days. `applicationId` or `applicationFqn`; optional `podNames`, `jobRunName`, time range (default last 24h) |
| `list_k8s_events` | Live k8s events | ~1h | Fresh `FailedScheduling`, `FailedMount`, `Failed`. Narrow with `fieldSelector` e.g. `reason=FailedScheduling` |
| `list_app_metric_charts` | Prometheus chart catalog | — | Discover chart names/params for an app |
| `get_application_chart_data` | Prometheus series | Persisted | CPU/memory/throughput trends. Never guess chart names |
| `list_alerts` | Autopilot alerts | Persisted | Pre-classified issues (OOM, crashloop, etc.) for an application or cluster. **Only registered when autopilot is enabled** (same constraint as `list_application_events`) |
| `get_cluster_autoscaler_logs` | Cluster autoscaler / Karpenter-ish signal | Persisted | Why nodes are not coming up. Cluster-level, not app-level |

Prefer native (`get_logs`, `list_application_events`) for anything older than ~1 hour. Prefer k8s for live crash and schedule diagnosis.

## Kubernetes reads

All take `clusterId` as a path param. Namespace-scoped ones need `namespace` = workspace name.

| Tool | Returns | Typical use |
|---|---|---|
| `list_k8s_pods` | Compact: phase, restarts, `reason`, node | **First call** for any runtime question. Optional `labelSelector` |
| `list_k8s_events` | Compact events | Scheduling / pull / mount. Use `fieldSelector` |
| `list_k8s_nodes` | Capacity, taints, readiness | GPU/CPU shortage, taints. Optional `labelSelector` e.g. `nvidia.com/gpu.present=true` |
| `list_k8s_objects` | Compact CRD/builtin list | Karpenter `NodeClaim`/`NodePool`, PVC, Rollout, ScaledObject. Needs `apiVersion` + plural `resource` |
| `describe_k8s_object` | Full object (scheduling fields included) | One pod/node/NodeClaim by name — affinity, tolerations, conditions |
| `get_k8s_pod_logs` | Container logs | See above |

TrueFoundry app pods are labeled `truefoundry.com/application-id=<applicationId>`. Prefer that label selector over guessing names.

**Common `list_k8s_objects` shapes:**

| Kind | `apiVersion` | `resource` | Namespace? |
|---|---|---|---|
| Karpenter NodeClaim | `karpenter.sh/v1` (or `v1beta1`) | `nodeclaims` | cluster-scoped — omit namespace |
| Karpenter NodePool | `karpenter.sh/v1` | `nodepools` | cluster-scoped |
| PVC | `v1` | `persistentvolumeclaims` | namespaced |
| Argo Rollout | `argoproj.io/v1alpha1` | `rollouts` | namespaced |
| KEDA ScaledObject | `keda.sh/v1alpha1` | `scaledobjects` | namespaced |

If the apiVersion is wrong, the call errors — try the version from `list_cluster_addons` / docs rather than inventing.

Platform namespaces (`kube-system`, `argocd`, `istio-system`, `tfy-agent`) are generally **not** readable via these tools (namespace must map to a workspace). Cluster-scoped objects like NodeClaims still work. For Karpenter **controller logs** in `kube-system`, fall back to `get_cluster_autoscaler_logs` or tell the user you cannot read that namespace.

## Cluster and workspace

| Tool | Use |
|---|---|
| `list_clusters` / `get_cluster` | Cluster exists, config, default registry |
| `get_cluster_status` | Control-plane connectivity / agent health |
| `list_cluster_addons` | Is GPU operator / Karpenter / Prometheus installed and healthy? |
| `list_workspaces` | Resolve namespace + clusterId |
| `list_environments` / `get_environment` | Env metadata when the user mentions "prod"/"dev" |

When pods are Pending forever and nodes never appear, check `get_cluster_status` and `list_cluster_addons` before blaming the application manifest.

## Jobs

| Tool | Use |
|---|---|
| `list_job_runs` | Recent runs for a job application |
| `get_job_run` | One run's status |
| `get_logs` with `jobRunName` | Logs for that run |
| `list_application_events` with `jobRunName` | Events for that run |

Do not mix `jobRunName` and `podNames` on the same events call — the API rejects it.

## Write / mutate (approval required)

Call these as real tool calls (not from sandbox). They go through user approval.

| Tool | When |
|---|---|
| `apply_manifest` | Create/update after `validate_manifest` |
| `redeploy_application` | Redeploy current version (no manifest change) |
| `cancel_deployment` | Abort an in-flight deploy |
| `pause_application` / `resume_application` | Scale to zero / bring back |
| `sync_application` | Force Argo CD sync when resources are OutOfSync / stuck without a new deploy |

Never run `tfy apply` in the terminal for the same reason as Gateway — it bypasses approval. Exception: `build_source: local` (see `deploy-from-source.md`).

## Bounds and empty results

- Always pass time windows and `limit` on log/event/metric calls. Unbounded `list_applications` / `get_logs` can blow the context window.
- Empty ≠ healthy. See `troubleshooting.md` → Interpreting an empty result.
- `direction` on logs is `asc` or `desc` only.

For more info: `search_docs` with "monitor your service", "application logs", "Kubernetes events".
