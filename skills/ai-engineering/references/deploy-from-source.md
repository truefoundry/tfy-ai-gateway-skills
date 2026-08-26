---
name: deploy-from-source
description: Deploy a service, async-service or job by building an image from source — a git repository or local code. Read this whenever the user points at a repository or a directory rather than an existing image, including "deploy this repo" and "deploy my project".
---

Deploying from source means the platform builds a container image before anything runs. Most of what goes wrong here goes wrong at build time, before there is any workload to inspect — so the useful work is in choosing the right build type and checking it before you deploy.

Applies to `service`, `async-service` and `job`. The build mechanics are identical across the three; only the manifest differs, and `get_manifest_json_schema` is the authority on that.

## Contents

- Choosing the build type
- Where the source comes from
- Checking the build before deploying
- Deploying
- When the build fails

## Choosing the build type

Look at what is actually in the repository before deciding — clone it or read its contents rather than assuming from the language.

**A Dockerfile is present** → use the `dockerfile` build type. Give it the path to the Dockerfile and the build context path. This is the preferred path when it is available, because the repository's own Dockerfile encodes decisions the author made that a generated one will not reproduce.

**A Python project with no Dockerfile** → use the `tfy-python-buildpack` build type. It builds a Python image without a Dockerfile existing in the repository, so there is no need to author one or to ask the user to add one to their repo. It needs the Python version and the command to run.

**Anything else with no Dockerfile** → a Dockerfile has to exist before this can be built. Say so plainly rather than guessing at one. If you are running locally with access to the code, writing a Dockerfile and building from local source is a real option. If you cannot change the code — which is the case when you have no working copy — then the honest answer is that the repository needs a Dockerfile, and the user has to add it.

## Where the source comes from

`GitSource` points at a repository the platform clones and builds remotely. Its `ref` field is described in the schema as a tag or commit SHA; branch names such as `main` also work, and are usually what a user means when they hand over a repository URL. Prefer the branch the user names, and use a SHA only when they want a specific commit pinned.

`LocalSource` builds from the machine running the command. This is the one case that cannot go through `apply_manifest`, because the image is built locally and pushed — no API call can reach the files on your disk. It requires `tfy deploy` from the sandbox, and it is the only reason to use the CLI instead of the approval-gated tool.

Use local source when the code is not in a repository the platform can reach, or when it contains changes that are not committed yet.

## Checking the build before deploying

If Docker and Python are both available, build the image locally first and see whether it succeeds. A local build failure arrives in seconds with a full error; the same failure discovered through the platform arrives minutes later and has to be read out of build logs.

This is worth doing even when you intend to deploy from a git source, because the failure modes are the same — a missing dependency, a bad base image, a Dockerfile that assumes files that are not committed.

If Docker is not available, skip this and read the build logs afterwards instead. Do not tell the user you verified the build when you did not.

Note what `validate_manifest` does not do here. It checks the shape of the manifest, so it will return `valid: true` for a Dockerfile path that does not exist in the repository. A successful validation says the manifest is well formed, not that it will build.

## Deploying

1. Read the repository and choose the build type, as above.
2. Call `get_manifest_json_schema` for the entity type — `service`, `async-service` or `job`.
3. Ask the user for anything you would otherwise be guessing at: which workspace, the port the application listens on, resource limits, environment variables, and for a job its trigger and retry behaviour.
4. Validate, understanding what that does and does not establish.
5. Apply with `apply_manifest` — or `tfy deploy` if and only if you are building from local source.
6. Follow the build through to a running workload. `apply_manifest` returning successfully means the deployment was accepted, not that an image was built or that anything is running. Read `builds.md` and check the outcome.

## When the build fails

Build failures happen before any pod exists, which makes every Kubernetes tool the wrong tool — they will return nothing, and nothing looks like health. Go to `builds.md`.

The distinction worth holding on to: if the build never produced an image, there is nothing to inspect at runtime. Reaching for pod logs at that point wastes a step and produces an empty result that is easy to misread as a quiet, healthy service.
