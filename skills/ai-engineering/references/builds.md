---
name: builds
description: Read build logs and diagnose a build that failed or produced an unexpected image. Read this when a deployment from source did not come up, or when the user asks what happened during a build.
---

A build runs before any workload exists. That decides how to investigate one: there is no pod, no container and no runtime log, so every `*_k8s_*` tool returns empty — and empty is easy to misread as a healthy, quiet service.

## Contents
- Phase 1: Find the build
- Phase 2: Read the logs
- Common build failures
- When the logs do not match the code
- After a successful build
- Checklist

## Phase 1: Find the build

1. Call `get_application` (or `list_applications`) to get the application `id`.
2. Call `get_deployment` with that `id` and the `deploymentId`. The response includes the deployment's builds.
3. Read the **build** status before anything else. If no image was produced, nothing downstream is worth investigating.

Do NOT infer the build outcome from the deployment status. A deployment can report `DEPLOY_SUCCESS` — meaning the rollout was accepted — while its build failed. Read the build record directly.

From the build row, keep:

| Field | Used for |
|---|---|
| build / pipeline run name | Fetching the logs |
| `logsStartTs` | The log query's start timestamp |
| status | Whether an image exists at all |

## Phase 2: Read the logs

Fetch build logs using the identifiers from the build row. Do NOT construct them.

**Pass the start timestamp.** Build logs are time-windowed, and the build row carries the timestamp the logs begin at. Without it the query can land on a window where nothing happened and return empty — which looks like a build that produced no output rather than a query that looked in the wrong place.

**Read the end of the log first.** Build failures report their cause on the last lines. Everything before it is dependency resolution and layer caching, which rarely explains anything.

## Common build failures

| Log shows | Cause | Fix |
|---|---|---|
| Package or version not found | A pinned version no longer exists, or a private package with no credentials | Correct the version, or configure registry credentials |
| `COPY` / `ADD` failed, file not found | The Dockerfile references files that were not committed, or `build_context_path` is wrong | Fix the path, or commit the missing files |
| Base image pull failed | Bad tag, or the base registry now requires authentication | Correct the tag, or configure credentials |
| Process killed during a compile or install step | The builder ran out of memory | Reduce the build, or raise build resources |

The first two are the ones a local `docker build` catches in seconds — see `deploy-from-source.md`.

## When the logs do not match the code

If the log describes something other than what you expect — an older commit, a change that is not reflected, a build that finished implausibly fast — consider that **no build ran at all**.

Builds are deduplicated. When the same repository and ref have already been built, the existing image is reused rather than rebuilt, and the deployment points at that earlier build. The logs are real, but they belong to the previous build rather than to this deployment.

This matters when someone pushes a change without moving the ref, or redeploys expecting a rebuild. Check what the build record actually refers to before drawing conclusions from its contents, and tell the user their change was not built if that is what happened.

## After a successful build

A successful build means an image exists. It does not mean the workload is running — the image still has to be pulled, scheduled and started, and each can fail separately.

Once an image exists, the investigation moves to runtime: `troubleshooting.md`.

## Checklist

- [ ] Did I read the build status from `get_deployment` rather than inferring it from the deployment status?
- [ ] Did I pass the start timestamp from the build row when fetching logs?
- [ ] Did I read the end of the log first?
- [ ] If the log looked stale or unexpectedly short, did I check whether the build was deduplicated?
- [ ] If a build was reused, did I tell the user their change was not rebuilt?
- [ ] Did I avoid reaching for pod or k8s tools for a build that never produced an image?
- [ ] After a successful build, did I continue to runtime instead of reporting the deployment complete?

For more info: `search_docs` with "build logs", "troubleshoot a build failure".
