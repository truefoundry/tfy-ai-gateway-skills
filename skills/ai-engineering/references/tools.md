---
name: tools
description: Catalog of AI Deployment / AI Engineering MCP tools — what each answers, required inputs, and when not to use it. Read when unsure which tool to call, or before inventing a parameter.
---

Every tool below except `list_secret_groups`, `validate_manifest` and `apply_manifest` requires the `deployment` feature on the tenant; Gateway-only tenants do not see them.

## Resolve identity first

Debug calls need `applicationId`, `workspaceId`/`namespace`, `clusterId`, sometimes `deploymentId`. Reuse these while they are still in the conversation; otherwise resolve them again:

| Need | Tool | Notes |
|---|---|---|
| Application by name | `list_applications` | Always filter. Same name can exist in many workspaces — ask if ambiguous |
| Application details | `get_application` | Gives `id`, `type`, `workspaceId`, `workspaceFqn`, `lastDeployment` (with its `id` and manifest), `activeVersion` / `lastVersion`, `metadata.paused`. For the active deployment's id, match `activeVersion` in `list_application_deployments` |
| Workspace → cluster + namespace | `list_workspaces` | Only if `get_application_state` is `null`. Filter `fqn=<workspaceFqn>`, pass `attributes=["id","name","fqn","clusterId"]`. **Namespace = workspace `name`** |
| Deployment history | `list_application_deployments` | Past versions, status progression |
| One deployment + builds | `get_deployment` | Application `id` + deployment `id`. Status machine, `deploymentBuilds` (was an image produced?) |
| FQN → id | `get_id_from_fqn` | User pasted an FQN |
| Secret FQN | `list_secret_groups` | Groups with their secrets, never values (`secrets.md`) |

Never construct FQNs, pod names, or image URIs. List, then take values from the response.

## Model catalogue

| Tool | Answers | Key inputs |
|---|---|---|
| `get_model_deployment_specs` | Recommended model servers + GPU-sized `type: service` manifests for a Hub URL or deployable model version | `workspaceId` (required), `huggingfaceHubUrl` **or** `modelVersionFqn`, optional `huggingfaceHubTokenSecretFqn` (`tfy-secret://<fqn>`; a bare FQN is used as the raw token), optional `pipelineTagOverride` |
| `get_nim_deployment_specs` | NIM container deployment options | `workspaceId`, `nimModelId`, `nvcrDockerRegistryProviderIntegrationFqn`, `ngcApiKeySecretFqn` (`tfy-secret://<fqn>`) |

Use these instead of hand-writing vLLM/SGLang services (`model-deploy.md`; NIM and sklearn/XGBoost: `model-deploy-nim-classical.md`; broken model service: `model-debug.md`).

## Application and deployment

| Tool | Answers | Key inputs |
|---|---|---|
| `get_application_state` | **First call for any runtime question.** The last pod snapshot tfy-agent published (not a live read; check `eventGenerationTimestamp`), plus `clusterId`, `namespace`, `activeVersion`. Fields below the table | application `id` |
| `get_applied_k8s_manifest` | What was actually applied to the cluster: resources/requests, probes, nodeSelector, tolerations, env shape (secrets redacted) | application `id`. Helm apps return 400 unless they use `kustomize` |
| `get_application_argocd_resources` | Per-resource Argo CD sync status and health; **Helm apps only** (400 otherwise) | application `id` |
| `get_pod_template_hash_map` | pod-template-hash → deployment version. `get_application_state` already gives each pod's `version`; use this only for pods it doesn't list | application `id`, `podTemplateHashes` (the middle segment of `<app>-<hash>-<id>`) |
| `generate_deployment_endpoint` | **Suggests** a `host` / `path` for a port you are about to expose (service / async-service only) while building a manifest (`deploy-common.md`). A deployed app's URL is in its manifest's `ports` (`deployment-links.md`) | `applicationType`, `workspaceId`, `applicationName`, optional `port` / `preferWildcard` / `baseDomain` |

**`get_application_state` fields.** `null` = no status from tfy-agent for this app. Pods are under `components[].pods[]`, newest first; Helm pods are included when they belong to a Deployment, StatefulSet, DaemonSet or Job in the release.
- Pod: `name`, `status`, `node`, `message`, `conditions`, `restarts`, `version`, `podTemplateHash`. `status` is `Running` only when the pod is Ready; a started but unready pod (crashlooping, failing readiness) also shows `Pending`, so tell them apart by `node` (`null` = never scheduled) and container reasons. `node` has `name`, `type` (instance type), `capacityType` and `status` (`ready`, `memoryPressure`, `diskPressure`, `pidPressure`); taints are not included.
- `conditions` are Kubernetes pod conditions (`type`, `status`, `reason`, `message`). `PodScheduled` with `reason: Unschedulable` carries the scheduler's "0/N nodes are available…" in `message`.
- Container: `name`, `state`, `reason`, `exitCode`, `image`, `lastState` (`state`, `reason`, `exitCode`, `finishedAt` of the attempt before the last restart — where `OOMKilled` shows while the container backs off as `CrashLoopBackOff`). `exitCode` is the previous attempt's when there is one. Init containers are listed after the main containers with an empty `image`; `restarts` counts main containers only.

**Reading `get_deployment`:** check `currentStatus.state.isTerminalState` before trusting `currentStatus.state.type` (it can say `success` mid-deploy). `DEPLOY_SUCCESS` = rollout accepted, not pods healthy. `BUILD_FAILED` / no `imageUri` → `builds.md`. `DEPLOY_FAILED` / `DEPLOY_FAILED_WITH_RETRY` → `get_application_state` + events; partial pods may exist.

## Logs, events, metrics, alerts

Time units differ: logs (incl. autoscaler) take nanosecond-epoch strings, metrics milliseconds, events ISO-8601 UTC.

| Tool | Layer | Retention | Use for |
|---|---|---|---|
| `get_logs` | App logs (stdout/stderr) | Persisted when the cluster has VictoriaLogs or Loki; otherwise live pods only | Details below |
| `get_build_logs` | Build pipeline | Persisted | Build failures. Path param = build `name` (`pipelineRunName`). **Always pass build `logsStartTs` as `startTs`** |
| `list_application_events` | Live Kubernetes events + persisted lifecycle events. Autopilot only; if not listed, give the user `kubectl get events -n <workspace>` | Live: the cluster's event TTL (~1h by default). Lifecycle (pending, OOM-killed, unhealthy, error, evicted): persisted | Full pull / schedule / mount / probe messages exist only while the Kubernetes event does; older windows show only the lifecycle category. `applicationId`; optional `podNames` or `jobRunName` (not both), `startTs`/`endTs` (default last 24h). Live events are kept only for objects named `<app>`, `<app>-<hash>` or `<app>-<hash>-<id>`, so Helm subchart pods (e.g. `my-cache-master-0`) get lifecycle events only |
| `list_app_metric_charts` | Prometheus chart catalog | — | Path `workspaceId` (from `get_application`), query `applicationId`, `filterEntity` (`application`; or `pod` with `filterQuery={"pod":"<pod name>"}` — the only option for Helm apps), optional `startTs`/`endTs` (default: since the last deploy) |
| `get_application_chart_data` | Prometheus series | Persisted | Path `workspaceId` + `chart`, query `startTs`, `endTs`, `utcOffsetSeconds` (`0`), `params` = that chart's `graphs[*].params`, unchanged. Never guess chart names. 405 on either = no Prometheus on the cluster |
| `list_alerts` | Autopilot alerts | Persisted | Pre-classified issues (OOM, crashloop…) for an app or cluster. Autopilot only; if not listed, skip it |
| `get_cluster_autoscaler_logs` | Provisioning logs: **Azure** cluster-autoscaler or **GCP** NAP | Persisted | Path param = cluster `id`. Default is the oldest 100 lines of the last hour: pass `direction: "desc"` and widen with `startTs`. Optional `filterQuery` is a JSON string. **AWS returns 501**; no cloud integration returns 400 "does not have a cloud integration" — both expected, move on |

**`get_logs`.** Pass `applicationId` (from `list_applications` / `get_application`); never pass only `applicationFqn` — the query is then not filtered by application and returns logs from every app in the workspace.
- Default `limit` is 5000 and default order is oldest first, so a capped read returns the earliest lines. For recent errors pass `direction: "desc"` (`asc`/`desc` only), `limit` 100–300 and a `startTs`.
- Narrow with one of `podName` / `podNames` / `podNamesRegex` (two → 400), plus `containerName`, `deploymentId`, `jobRunName`, `searchString` or `searchFilters`. **Helm apps require one of the three pod filters** (400 "only supports pod level logs" otherwise).
- Containers named `init` or `wait` are always excluded.
- Without VictoriaLogs/Loki on the cluster (`get_cluster` → `manifest.monitoring`), `get_logs` reads the live pod: it needs `podName` and `containerName` (405 / 400 otherwise), returns the last `limit` lines of the **current** container only, and cannot read a crashed attempt.

## What no tool can see

There are no raw Kubernetes read tools. Out of reach: node lists and taints, Karpenter NodeClaims / NodePools, PVC objects, Argo Rollout and KEDA objects of non-Helm apps, live events of pods outside the app's naming pattern, and anything in system namespaces (`kube-system`, `argocd`, `istio-system`), including controller logs. TrueFoundry addons such as tfy-agent are Helm applications: with read access to their workspace, `get_application_state` and `get_logs` work on their `applicationId` from `list_cluster_addons`.

When the answer is behind that line, say what you checked, say what you could not see, and give the user the exact `kubectl` command to run (e.g. `kubectl get nodeclaims`, `kubectl describe pvc <name> -n <workspace>`). Never present a guess as something you read.

## Cluster and workspace

| Tool | Use |
|---|---|
| `list_clusters` / `get_cluster` | `manifest.cluster_type` (`aws-eks`, `azure-aks`, `gcp-gke-standard`, `generic`, `civo-talos`; `list_clusters attributes=["id","name","manifest.cluster_type"]`), `manifest.default_registry_fqn`, `manifest.monitoring` (`prometheus_url`, `loki_url`, `victoria_logs_url`) |
| `get_cluster_status` | Returns `isConnected`: whether the control plane reaches the cluster through tfy-agent-proxy. It does not show whether the main `tfy-agent` is publishing state |
| `list_cluster_addons` | Which addons are installed (`installed`, `version` = chart version, `applicationId`, `namespace`). No health field: for health, call `get_application_state` (or `get_application_argocd_resources`) with the addon's `applicationId` |
| `list_environments` / `get_environment` | When the user says "prod"/"dev" |

## Jobs

`list_job_runs` (path `jobId` = application `id`; filter `status: ["FAILED"]`) returns runs newest first with `name`, `status`, `error`, `exitCode`, `totalRetries`, so `get_job_run` is rarely needed. Then `get_logs` and `list_application_events` with `jobRunName` (never with `podNames` too — rejected). Full recipe: `failure-modes/jobs.md`.

## Write / mutate (approval required)

Real tool calls (not from sandbox); each goes through user approval.

| Tool | When |
|---|---|
| `apply_manifest` | Create/update after `validate_manifest` |
| `redeploy_application` | Redeploy current version (no manifest change) |
| `cancel_deployment` | Abort an in-flight deploy. Needs application `id` + `deploymentId`; 409 if the deployment is terminal or its `transition` is `DEPLOYING` |
| `pause_application` / `resume_application` | Scale to zero / back |
| `sync_application` | Force Argo CD sync when resources are OutOfSync / stuck without a new deploy. 400 "Application is paused" → `resume_application` first |

## Bounds and empty results

- Always pass time windows and `limit` on log calls, and a time window on event/metric calls. A result over ~24,000 characters is saved to a sandbox file: extract only the fields you need with one `jq`/program.
- Issue independent reads in one message (they run in parallel).
- Empty ≠ healthy. See `troubleshooting.md` → Interpreting an empty result.
