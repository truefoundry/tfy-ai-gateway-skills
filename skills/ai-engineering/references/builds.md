---
name: builds
description: Read build logs and diagnose a build that failed or produced an unexpected image. Read this when a deployment from source did not come up, or when the user asks what happened during a build.
---

A build runs before any workload exists. That single fact decides how to investigate one: there is no pod, no container and no runtime log, so every Kubernetes tool returns empty — and empty is easy to misread as a healthy, quiet service.

## Contents

- Finding the build
- Reading the logs
- Common failures
- When the logs do not match the code

## Finding the build

`get_deployment` returns the deployment along with its builds. Start there rather than looking for a workload, and read the build status before anything else — if no image was produced, nothing downstream is worth investigating.

The deployment's own status is not a reliable signal here. A deployment can report that it was accepted while its build has failed, so read the build outcome directly rather than inferring it.

## Reading the logs

Build logs are fetched per build, using identifiers from the build record rather than constructed. Take them from the build row returned above.

Build logs are also time-windowed, and the build row carries the timestamp the logs start at. Use it. A log query with no start time can land on a window in which nothing happened and return nothing at all — which, again, looks like a build that produced no output rather than a query that looked in the wrong place.

Read the end of the log first. Build failures report their cause on the last lines; the rest is dependency resolution and layer caching that rarely explains anything.

## Common failures

**A dependency could not be resolved.** The most common cause, and usually an exact version that no longer exists or a private package the builder has no credentials for. The log names the package.

**The Dockerfile refers to files that are not there.** A `COPY` of something in the author's working directory but not committed, or a build context path that does not contain what the Dockerfile expects. This is one that a local build catches in seconds — see `deploy-from-source.md`.

**The base image could not be pulled.** Same class of problem as pulling any other image, and increasingly a registry authentication decision rather than a missing tag.

**The build ran out of resources.** Large images, or a compile step that needs more memory than the builder has. The failure often appears as a process being killed rather than as an explicit error.

## When the logs do not match the code

If the build log describes something other than what you expect — an older commit, a change that is not reflected, a build that finished implausibly fast — consider that no build ran at all.

Builds are deduplicated. When the same repository and ref have already been built, the existing image is reused rather than rebuilt, and the deployment then points at that earlier build. The logs are real, but they belong to the previous build rather than to this deployment.

This matters when someone pushes a change without moving the ref, or redeploys expecting a rebuild. If the log looks stale, check what the build record actually refers to before drawing conclusions from its contents.

## After a successful build

A build succeeding means an image exists. It does not mean the workload is running — the image still has to be pulled, scheduled and started, and each of those can fail separately.

Once there is an image, the investigation moves to runtime and `troubleshooting.md` applies.
