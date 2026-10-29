---
name: builds
description: Read build logs and work out why a build failed or produced an unexpected image. Read this when a deploy from source did not come up, when the user asks what happened during a build, or when a running workload is not the code the user expects.
---

A build runs before any workload exists, so there is no pod, no container and no runtime log. Every runtime tool (`get_application_state`, `get_logs`, events) returns empty for a build problem, and empty reads as a healthy quiet service. Start here instead.

## Contents
- Getting from an application to its build
- What the build record tells you
- Reading the log
- The image is not what the user expects
- After a successful build
- Checklist

## Getting from an application to its build

Three calls, in order:

1. `get_application` — gives you the application `id` and its `activeDeployment` / `lastDeployment`. If you only have a name, `list_applications` first: the same name can exist in several workspaces, so ask which one the user means rather than taking the first match.
2. `get_deployment` with that application `id` and the deployment `id` — the response carries `deploymentBuilds`.
3. `get_build_logs` with the build's `name` as `pipelineRunName`.

`deploymentBuilds` is an array because an application can have several components, each built separately. `componentName` says which one, so on a multi-component application check you are reading the build you meant.

## What the build record tells you

Read these fields before fetching any log — most build questions are answered here:

| Field | Use |
|---|---|
| `status` | `STARTED`, `SUCCEEDED` or `FAILED`. Only the last two are terminal — `STARTED` means it is still running, not that it stalled |
| `imageUri` | Present means an image exists. Absent on a `FAILED` build, which is the fastest way to know nothing was produced |
| `name` | The pipeline run name — this is the `pipelineRunName` that `get_build_logs` takes |
| `logsStartTs` | The timestamp the log window opens at. Required, see below |
| `componentName` | Which component of the application this build belongs to |

Deployment status `BUILDING` / `BUILD_FAILED` is the quick signal; the build record's `status` is the authority. `DEPLOY_SUCCESS` only means the rollout was accepted — it says nothing about runtime health.

## Reading the log

`get_build_logs` takes `pipelineRunName` in the path and these query params: `startTs` (= `logsStartTs`), `endTs` (defaults to startTs + 2 h — pass a later value for longer builds), `limit` (default 10000), `direction` (`asc`/`desc`), `numLogsToIgnore`, `filterQuery` (JSON, e.g. `{"matchString":"error","type":"substring","operator":"equal"}`). Timestamps are nanoseconds since the epoch.

**Pass `logsStartTs` from the build record as `startTs`.** The log query is time-windowed, and without a start timestamp the window does not cover the build — you get an empty result, which looks like a build that printed nothing rather than a query that looked in the wrong place. This is the single most common way a build investigation dead-ends.

Read the end of the log first. A build reports its cause on the last lines; everything before is dependency resolution and layer caching. Read the tail with `direction=desc limit=200` rather than paging through the whole thing.

The log is the build tool's own output — a Dockerfile step that failed, a dependency that would not resolve, a base image that could not be pulled. Read it as you would any build log; nothing about it is TrueFoundry-specific.

## The image is not what the user expects

Two different situations, and they need different answers.

**The build ran and succeeded, but the code is old.** Builds are deduplicated: when the platform judges the same source has already been built, it reuses the existing image and points the deployment at that earlier build. The logs are real but describe the previous build. Compare the build's `createdAt` against when the user made their change — if the build predates it, their change was never built. Say so plainly: a reused image is the one case where a deployment succeeds and still runs the old code.

Look for transition `REUSING_EXISTING_BUILD` (message "Reusing previously built image for …") in the deployment's status history from `get_deployment` — that confirms reuse directly. For git sources, reuse means `ref` did not change: have the user push and deploy the new commit SHA.

**The build is still going.** `status: STARTED` with no `imageUri` means it has not finished. Do not report a failure — the workload will not exist yet, and pod tools returning empty is expected. Check again rather than diagnosing.

## After a successful build

`SUCCEEDED` with an `imageUri` means an image exists. It does not mean the workload runs — the image still has to be pulled, scheduled and started, and each can fail on its own. Continue to `troubleshooting.md`.

## Checklist

- [ ] Did I read the build's `status` rather than inferring the outcome from the deployment status?
- [ ] Did I check `imageUri` to establish whether an image was produced at all?
- [ ] Did I pass `logsStartTs` as `startTs` when fetching the log?
- [ ] On a multi-component application, did I check `componentName` to confirm I read the right build?
- [ ] If `status` was `STARTED`, did I treat it as unfinished instead of reporting a failure?
- [ ] If the code looked stale, did I compare the build's `createdAt` against the user's change and tell them if it was never built?
- [ ] After a successful build, did I continue to runtime instead of reporting the deploy complete?

For more info: `search_docs` with "image and build", "customize build workflow", "docker build secrets".
