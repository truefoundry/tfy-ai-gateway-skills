---
name: workflow-spark
description: Author and debug workflow, spark-job, and application-set workloads using schema + docs. Read when the user asks for pipelines, Spark, or multi-app sets — not covered by service/job deploy-from-* alone.
---

These application types are supported on the platform but are **not** the same as `service` / `job` image deploys. Always start from schema + docs; do not reuse vLLM or service templates.

## Contents
- Workflows
- Spark jobs
- Application sets
- Debugging
- Checklist

## Workflows

1. `search_docs` for TrueFoundry workflows / pipeline semantics.
2. `get_manifest_json_schema` for `workflow` (exact type string from schema list).
3. Build the manifest from schema — task DAGs, retries, and input/output refs are product-specific.
4. `validate_manifest` → `apply_manifest` (approval).
5. Run/trigger per docs; debug failed tasks with job/pod tools when the workflow spawns underlying jobs (`failure-modes/jobs.md`).

## Spark jobs

1. `get_manifest_json_schema` for `spark-job`.
2. Confirm cluster has Spark operator / required addons (`list_cluster_addons`, `cluster-onboard.md`).
3. Set driver/executor resources carefully — Pending looks like service GPU Pending (`failure-modes/pending-scheduling.md`).
4. Validate → apply → follow driver/executor pods with `list_k8s_pods` + logs.

## Application sets

Multi-application templates / generators:

1. Schema for `application-set` (confirm name).
2. Explain that applying an application-set may create **many** child apps — confirm naming and workspace with the user.
3. Validate → apply → list child applications to verify.

## Debugging

| Layer | Playbook |
|---|---|
| Child service/job pods | `troubleshooting.md` + matching failure-mode |
| Workflow task failed | Task logs + underlying job failure-mode |
| Spark driver/executor | Pod logs; scheduling; shuffle/storage |
| Nothing schedules cluster-wide | `cluster-capacity.md` |

## Checklist

- [ ] Did I use the correct type schema (workflow / spark-job / application-set)?
- [ ] Did I confirm addons/operators before declaring the manifest wrong?
- [ ] Did I avoid forcing these into `deploy-from-image.md` service shapes?

For more info: `search_docs` with "workflow", "spark", "application set".
