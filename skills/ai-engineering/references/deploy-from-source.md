---
name: deploy-from-source
description: Deploy a service, async-service or job by building a container image from source — a git repository or local code. Read this whenever the user points at a repository or a directory rather than an existing image, including "deploy this repo" and "deploy my project".
---

Deploying from source builds an image before anything runs, so most failures happen at build time, before there is a workload to inspect. The decisions that matter are the build type and the source type.

Applies to `service`, `async-service` and `job`. Build mechanics are identical across all three; only the manifest differs, and `get_manifest_json_schema` is the authority on that.

## Contents
- Choosing the build spec
- Choosing the source
- Phase 1: Inspect the repository
- Phase 2: Get the schema and collect inputs
- Phase 3: Verify the build locally
- Phase 4: Validate and apply
- Manifest structure
- Checklist

## Choosing the build spec

`build_spec.type` has two values. Inspect the repository before choosing — do NOT infer from the language alone.

| Repository contains | `build_spec.type` | Required fields |
|---|---|---|
| A Dockerfile | `dockerfile` | `dockerfile_path`, `build_context_path` |
| Python, no Dockerfile | `tfy-python-buildpack` | `build_context_path`, `command`; optionally `python_version`, `requirements_path`, `pip_packages` |
| Neither | — | A Dockerfile must be written first. Say so. |

`tfy-python-buildpack` builds a Python image **without a Dockerfile existing in the repository**, so a Python project never needs one authored. Prefer `dockerfile` when one is present — the repository's own Dockerfile encodes decisions a buildpack will not reproduce.

For a non-Python repository with no Dockerfile: if you have a working copy you can write one and use `LocalSource`. If you cannot change the code, the honest answer is that the repository needs a Dockerfile before it can be built.

## Choosing the source

`build_source.type` decides where the code comes from and, critically, which apply path is allowed.

| | `type` | Fields | Apply with |
|---|---|---|---|
| Remote git | `git` | `repo_url`, `ref`, `branch_name?` | `apply_manifest` |
| Local files | `local` | `project_root_path`, `local_build` | **`tfy deploy` only** |

**`ref` and `branch_name` are different fields.** `ref` is the commit SHA. `branch_name` selects the latest commit on that branch. When the user names a branch, set `branch_name`; use `ref` only to pin a specific commit. Do NOT put a branch name in `ref` and assume it is correct.

`LocalSource` builds the image on the machine running the command and pushes it, which no API call can do — the files are on your disk. This is the **only** case that uses `tfy deploy` from the sandbox instead of the approval-gated `apply_manifest`. Use it when the code is not in a repository the platform can reach, or has uncommitted changes.

## Phase 1: Inspect the repository

1. Read the repository contents. Look for a Dockerfile and note its path relative to the repo root.
2. Note whether the project is Python (`requirements.txt`, `pyproject.toml`, `setup.py`).
3. Choose `build_spec.type` from the table above.
4. Establish the command that starts the application — the buildpack requires `command`, and a Dockerfile may need one if it has no `CMD`.

## Phase 2: Get the schema and collect inputs

1. Call `get_manifest_json_schema` with the entity type — `service`, `async-service` or `job`. Do not recall fields from memory; the schema is the source of truth.
2. Call `list_workspaces` to resolve the target workspace, and use its `fqn` for `workspace_fqn`. Do NOT construct an FQN.
3. Use `ask_user_question` for anything you would otherwise guess:
   - the port the application listens on, and whether it should be exposed
   - CPU and memory requests and limits
   - environment variables and secrets
   - for a `job`: `trigger`, `retries`, `concurrency_limit`

Secrets are referenced by FQN (`tfy-secret://...`), never pasted as literal values.

## Phase 3: Verify the build locally

If Docker **and** Python are both available, build the image locally before deploying:

```
docker build -f <dockerfile_path> <build_context_path>
```

A local failure arrives in seconds with the full error. The same failure found through the platform arrives minutes later and has to be read out of build logs. This is worth doing even when deploying from a git source, because the failure modes are identical — a missing dependency, a bad base image, a Dockerfile that copies files that were never committed.

If Docker is not available, skip this and read build logs afterwards. Do NOT tell the user you verified the build when you did not.

## Phase 4: Validate and apply

Build the manifest as JSON → `validate_manifest` → fix and re-validate until it passes → `apply_manifest` (or `tfy deploy` for `local` source only).

**`validate_manifest` checks the shape of the manifest, not whether it will deploy.** It returns `valid: true` for a `dockerfile_path` that does not exist in the repository. Never report a passing validation as "this will work".

After applying, follow the build to completion — `apply_manifest` returning successfully means the deployment was accepted, not that an image was built. See `builds.md`.

## Manifest structure

```yaml
type: service                          # or async-service, job
name: <application-name>
workspace_fqn: <fqn from list_workspaces>
image:
  type: build
  build_source:
    type: git
    repo_url: https://github.com/<org>/<repo>
    branch_name: main                  # branch; use `ref` for a pinned commit SHA
  build_spec:
    type: dockerfile                   # or tfy-python-buildpack
    dockerfile_path: ./Dockerfile
    build_context_path: ./
ports:
  - port: 8000
    protocol: TCP
    expose: true
resources:
  cpu_request: 0.2
  cpu_limit: 0.5
  memory_request: 500
  memory_limit: 1000
env:
  KEY: value
```

For `tfy-python-buildpack`, replace `build_spec` with:

```yaml
  build_spec:
    type: tfy-python-buildpack
    build_context_path: ./
    python_version: "3.11"
    requirements_path: ./requirements.txt
    command: python main.py
```

## Checklist

- [ ] Did I read the repository to decide the build spec, rather than inferring from the language?
- [ ] If the repo has a Dockerfile, did I use `dockerfile` rather than the buildpack?
- [ ] If the user named a branch, did I set `branch_name` rather than putting it in `ref`?
- [ ] Did I call `get_manifest_json_schema` before writing the manifest?
- [ ] Did I take `workspace_fqn` from `list_workspaces` instead of constructing it?
- [ ] Did I ask the user for ports, resources and environment rather than choosing them?
- [ ] If Docker was available, did I build locally first — and if not, did I avoid claiming I verified it?
- [ ] Did I describe the validation result as a shape check, not a guarantee it will deploy?
- [ ] For `local` source, did I use `tfy deploy`? For everything else, `apply_manifest`?
- [ ] Did I follow the build to completion instead of reporting success when apply returned?

For more info: `search_docs` with "deploy from a git repository", "build configuration".
