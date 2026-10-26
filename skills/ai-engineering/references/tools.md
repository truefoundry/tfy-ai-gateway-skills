---
name: tools
description: Catalog of AI Deployment / AI Engineering MCP tools — what each answers, required inputs, and when not to use it. Read when unsure which tool to call, or before inventing a parameter.
---

Every tool below requires the `deployment` feature on the tenant. Gateway-only tenants do not see them.

## Contents
- Resolve identity first
- Model catalogue
- Application and deployment
- Logs, events, metrics, alerts
- What no tool can see
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
| Secret FQN | `list_secret_groups` | Groups with their secrets; values are never returned. See `secrets.md` |

Never construct FQNs, pod names, or image URIs. List, then take values from the response.

## Model catalogue

| Tool | Answers | Key inputs |
|---|---|---|
| `get_model_deployment_specs` | Recommended model servers + GPU-sized `type: service` manifests for a Hub URL or deployable model version | `workspaceId` (required), `huggingfaceHubUrl` **or** `modelVersionFqn`, optional `huggingfaceHubTokenSecretFqn`, optional `pipelineTagOverride` |
| `get_nim_deployment_specs` | NIM container deployment options | `workspaceId`, `nimModelId`, `nvcrDockerRegistryProviderIntegrationFqn`, `ngcApiKeySecretFqn` |

Use these instead of hand-writing vLLM/SGLang services. Full workflow: `model-deploy.md`. Debugging a broken model service: `model-debug.md`.

## Application and deployment

| Tool | Answers | Key inputs |
|---|---|---|
| `list_applications` | What exists, by name/workspace | Prefer filters; unbounded lists are huge |
| `get_application` | Type, workspace, active/last deployment, user manifest | `id` |
| `get_deployment` | Status machine, builds, whether image was produced | application `id`, deployment `id` |
| `get_application_state` | **First call for any runtime question.** Per pod: `status`, `message` (e.g. the scheduling failure), `conditions`, `restarts`, `version`, `node` (instance type, capacity type, pressure). Per container: `state`, `reason`, `exitCode`, and `lastState` (the attempt before the last restart — where `OOMKilled` / exit 137 shows). Returns `null` if the cluster agent has not published a status | application `id` |
| `get_applied_k8s_manifest` | What was actually applied to the cluster: resources/requests, probes, nodeSelector, tolerations, env shape (secrets redacted) | application `id` |
| `get_application_argocd_resources` | Argo CD resource tree/status — **Helm apps only** | application `id` |
| `get_pod_template_hash_map` | Maps pod-template-hash → deployment version | When correlating pods to a version |
| `generate_deployment_endpoint` | **Suggests** a `host` / `path` for a port you are about to expose — **service** or **async-service** only; other types are rejected | `applicationType`, `workspaceId`, `applicationName`, optional `port` / `preferWildcard` / `baseDomain`. Use while building a manifest (`deploy-common.md`). A deployed application's URL is in its manifest's `ports` — `deployment-links.md` |

**Status reading rules for `get_deployment`:**

- Read `currentStatus.state.isTerminalState` **before** trusting `currentStatus.state.type`. While a deploy is in progress, `type` can say `success` and still not be done.
- `DEPLOY_SUCCESS` = rollout accepted, **not** pods healthy.
- `BUILD_FAILED` / missing `imageUri` → go to `builds.md`, not runtime tools.
- `DEPLOY_FAILED` / `DEPLOY_FAILED_WITH_RETRY` → `get_application_state` + events; may still have partial pods.

## Logs, events, metrics, alerts

| Tool | Layer | Retention | Use for |
|---|---|---|---|
| `get_logs` | App logs (stdout/stderr) | Persisted when the cluster has Loki or VictoriaLogs; otherwise live pods only | Any app, including crashed and replaced containers. Pass `applicationId` (from `list_applications` / `get_application`); never pass only `applicationFqn` — the query is then not filtered by application and returns logs from every app in the workspace. Narrow with one of `podName` / `podNames` / `podNamesRegex`, plus `containerName`, `deploymentId`, `jobRunName`, `searchString`. **Helm apps require a pod filter.** Default limit is 5000 — pass a smaller `limit` and a tight `startTs`/`endTs` |
| `get_build_logs` | Build pipeline | Persisted | Build failures. Path param = build `name` (`pipelineRunName`). **Always pass build `logsStartTs` as `startTs`** |
| `list_application_events` | Kubernetes events for the app | Persisted | Pull / schedule / mount / probe failures over days. `applicationId` or `applicationFqn`; optional `podNames`, `jobRunName`, time range (default last 24h) |
| `list_app_metric_charts` | Prometheus chart catalog | — | Discover chart names/params for an app |
| `get_application_chart_data` | Prometheus series | Persisted | CPU/memory/throughput trends. Never guess chart names |
| `list_alerts` | Autopilot alerts | Persisted | Pre-classified issues (OOM, crashloop, etc.) for an application or cluster |
| `get_cluster_autoscaler_logs` | Provisioning logs: **Azure** cluster-autoscaler or **GCP** NAP | Persisted | **Required** on GPU / capacity Pending when nodes are not appearing (`failure-modes/pending-scheduling.md`). Path param = cluster `id`. **AWS returns 501** — expected. Not app-level |

## What no tool can see

There are no raw Kubernetes read tools. These are out of reach: node lists and taints, Karpenter NodeClaims / NodePools, PVC objects, Argo Rollout and KEDA objects of non-Helm apps, and anything in system namespaces (`kube-system`, `argocd`, `istio-system`, `tfy-agent`), including controller and agent logs.

What you can still get: the node a pod landed on and its conditions (`get_application_state`), the scheduler's reason in the pod `message` / `conditions` and in `list_application_events`, the applied spec (`get_applied_k8s_manifest`), addon health (`list_cluster_addons`), agent connectivity (`get_cluster_status`) and, on Azure/GCP, autoscaler logs.

When the answer is behind that line, say what you checked, say what you could not see, and give the user the exact `kubectl` command to run (e.g. `kubectl get nodeclaims`, `kubectl describe pvc <name> -n <workspace>`). Never present a guess as something you read. For **stuck `WAITING` / status not publishing**, follow `failure-modes/rollout-argocd.md`.

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

Never run `tfy apply` in the terminal — it is `apply_manifest` without the approval step. Deploying from source is different: it uses `tfy deploy` (`deploy-from-source.md`).

## Bounds and empty results

- Always pass time windows and `limit` on log/event/metric calls. Unbounded `list_applications` / `get_logs` can blow the context window.
- Empty ≠ healthy. See `troubleshooting.md` → Interpreting an empty result.
- `direction` on logs is `asc` or `desc` only.

For more info: `search_docs` with "monitor your service", "application logs".
