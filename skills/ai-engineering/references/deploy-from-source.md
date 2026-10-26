---
name: deploy-from-source
description: Deploy a service, async-service or job by building a container image from source. Read this whenever the user points at a git repository or a directory rather than an existing image, including "deploy this repo" and "deploy my project".
---

The flow is the same every time: clone the repository, make sure it can produce an image, deploy with `tfy deploy`, read the build logs. Only one thing varies — whether Docker is available to build locally.

Applies to `service`, `async-service` and `job`. Build mechanics are identical; only the manifest differs, and `get_manifest_json_schema` is the authority on that. Read `deploy-common.md` alongside this.

## Contents
- Phase 1: Clone and choose the build spec
- Phase 2: Collect inputs
- Phase 3: Deploy and read the build logs
- Manifest structure
- Checklist

## Phase 1: Clone and choose the build spec

```
git clone <repo_url> && cd <repo>
```

Read the repository and pick `build_spec.type` from what is there:

| Repository has | `build_spec.type` |
|---|---|
| A Dockerfile | `dockerfile` |
| Python, no Dockerfile (`requirements.txt`, `pyproject.toml`, `setup.py`) | `tfy-python-buildpack` |
| Neither | Write a Dockerfile in the clone, then `dockerfile` |

The buildpack takes `python_version`, `build_context_path`, `python_dependencies`, `apt_packages`, `cuda_version` and `command` (required). Set dependencies with `python_dependencies`:

- `{type: pip, requirements_path: ./requirements.txt}`
- `{type: uv}` — needs `pyproject.toml` and `uv.lock` in the build context root
- `{type: poetry}` — needs `pyproject.toml` and `poetry.lock` in the build context root

Write a Dockerfile only when the repo needs more than these — a Node asset build, a non-Python base image, a multi-stage build.

Note the **command** that starts the application. The buildpack requires it, and a Dockerfile without a `CMD` needs one. `dockerfile_path` and `build_context_path` are relative to `project_root_path`.

## Phase 2: Collect inputs

1. `list_workspaces(name=<workspace>)` — keep `fqn` and `id`. See **Resolving the workspace** in `deploy-common.md`.
2. In one parallel batch: `list_applications(applicationName=<name>, workspaceFqn=<fqn>)` and `get_manifest_json_schema` for the entity type (`service`, `async-service` or `job`). A row back means you are updating — read **Creating or updating** in `deploy-common.md` before going further, and take values from the deployed manifest rather than the user. Take fields from the schema, not memory.
3. `ask_user_question` for anything you would otherwise guess: the port and whether to expose it, CPU and memory, environment variables, and for a `job` its `trigger` and `retries`. An exposed port needs a `host` — see **Exposing a port** in `deploy-common.md`.

## Phase 3: Deploy and read the build logs

Use `build_source.type: local` when you changed or added files in the clone — the platform cannot clone a file that was never pushed. Escape hatch: for an unmodified repo that is already pushed, `build_source: {type: git, repo_url, ref: <commit SHA>, branch_name?}` through `validate_manifest` → `apply_manifest` also works and needs no CLI.

One check decides `local_build`:

```
docker info
```

- **Docker works** → `local_build: true`. Run `docker build` first to catch failures in seconds rather than minutes, then deploy.
- **No Docker** → `local_build: false`. The source is uploaded and the platform builds it. Do not claim you verified a build you could not run.

When the check is inconclusive, use `false`. Setting `true` without a reachable Docker daemon only makes the CLI warn and build remotely, so it costs speed, not correctness.

Then:

1. Build the manifest — see **Manifest structure** below — and run `validate_manifest`; fix and re-validate until it passes. A pass is a shape check only (see `deploy-common.md`).
2. Write the manifest to `truefoundry.yaml` at the clone root and run, from there:

   ```
   tfy deploy -f truefoundry.yaml --no-wait
   ```

   Without `--no-wait` it blocks while tailing logs. Never use `tfy apply` for this.
3. Follow with `get_deployment` and `get_build_logs`. A deploy call returning means the deployment was accepted, not that an image was built, and when the platform does the building that log is the only place a failure appears. See `builds.md`.

## Manifest structure

```yaml
type: service                          # job / async-service: see below
name: <application-name>
workspace_fqn: <fqn from list_workspaces>
replicas: 1
image:
  type: build
  build_source:
    type: local
    project_root_path: ./
    local_build: false                 # true only if `docker info` works
  build_spec:
    type: dockerfile
    dockerfile_path: ./Dockerfile
    build_context_path: ./
ports:
  - port: 8000
    protocol: TCP
    expose: true
    host: <host from generate_deployment_endpoint>
resources:
  cpu_request: 0.2
  cpu_limit: 0.5
  memory_request: 500
  memory_limit: 1000
  ephemeral_storage_request: 1000
  ephemeral_storage_limit: 2000
env:
  KEY: value
```

- `job`: drop `ports` and `replicas`; add `trigger: {type: manual}` (or `{type: scheduled, schedule: "<cron>"}`) and optionally `retries` (0–10).
- `async-service`: `worker_config` is required; take its shape from `get_manifest_json_schema`.

For a Python repository with no Dockerfile, replace `build_spec`:

```yaml
  build_spec:
    type: tfy-python-buildpack
    build_context_path: ./
    python_version: "3.11"
    python_dependencies:
      type: pip
      requirements_path: ./requirements.txt
    command: python main.py
```

## Checklist

- [ ] Did I clone and read the repository rather than inferring its contents?
- [ ] If it has a Dockerfile, did I use it? If Python without one, the buildpack with the right `python_dependencies` type?
- [ ] Did I set `local_build` from an actual `docker info` check rather than assuming?
- [ ] If Docker was available, did I build locally first — and if not, did I avoid claiming I verified it?
- [ ] Did I take fields from `get_manifest_json_schema` and `workspace_fqn` from `list_workspaces`, and write every required field?
- [ ] Did I ask the user for ports, resources and environment rather than choosing them?
- [ ] Did I run `tfy deploy -f truefoundry.yaml --no-wait`, then read the build logs instead of reporting success when the deploy call returned?
- [ ] Did I print the links per `deployment-links.md`?

For more info: `search_docs` with "deploy from a git repository", "build configuration", "tfy deploy".
