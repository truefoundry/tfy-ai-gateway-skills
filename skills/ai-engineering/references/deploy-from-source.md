---
name: deploy-from-source
description: Deploy a service, async-service or job by building a container image from source. Read this whenever the user points at a git repository or a directory rather than an existing image, including "deploy this repo" and "deploy my project".
---

The flow is the same every time: clone the repository, make sure it can produce an image, deploy with `tfy deploy`, read the build logs. Only one thing varies — whether Docker is available to build locally.

Applies to `service`, `async-service` and `job`. Build mechanics are identical; only the manifest differs, and `get_manifest_json_schema` is the authority on that.

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

The buildpack accepts only `python_version`, `requirements_path`, `pip_packages`, `apt_packages`, `cuda_version` and `command`. If a Python repository needs anything beyond those — a Node asset build, a non-Python base image, a multi-stage build — write a Dockerfile instead.

Note the **command** that starts the application. The buildpack requires it, and a Dockerfile without a `CMD` needs one.

## Phase 2: Collect inputs

1. **Check whether the name is taken** — call `list_applications` filtered by it. If something is already deployed under that name you are updating, and the values below come from the deployed manifest rather than from the user. Read **Creating or updating** in `SKILL.md` before going further.
2. `get_manifest_json_schema` for the entity type — `service`, `async-service` or `job`. Do not recall fields from memory.
3. `list_workspaces` — take `workspace_fqn` from the response. Do NOT construct an FQN. If it returns nothing for the workspace the user named, see **Resolving the workspace** in `SKILL.md`.
4. `ask_user_question` for anything you would otherwise guess: the port and whether to expose it, CPU and memory, environment variables, and for a `job` its `trigger` and `retries`.

## Phase 3: Deploy and read the build logs

The source is always `local`, because the build runs against your clone — which may contain a Dockerfile you wrote, and the platform cannot clone a file that was never pushed.

One check decides `local_build`:

```
docker info
```

- **Docker works** → `local_build: true`. Run `docker build` first to catch failures in seconds rather than minutes, then deploy.
- **No Docker** → `local_build: false`. The source is uploaded and the platform builds it. Do NOT claim you verified a build you could not run.

When the check is inconclusive, use `false` — it always works, whereas `true` without a daemon fails at deploy time.

Build the manifest — see **Manifest structure** below — then `validate_manifest` → fix and re-validate until it passes → `tfy deploy`.

`validate_manifest` checks the manifest's **shape**, not whether it will deploy — it returns `valid: true` for a `dockerfile_path` that does not exist. Never report a passing validation as "this will work".

Finally read the build logs. A deploy call returning successfully means the deployment was accepted, not that an image was built, and when the platform does the building that log is the only place a failure appears. See `builds.md`.

## Manifest structure

```yaml
type: service                          # or async-service, job
name: <application-name>
workspace_fqn: <fqn from list_workspaces>
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
resources:
  cpu_request: 0.2
  cpu_limit: 0.5
  memory_request: 500
  memory_limit: 1000
env:
  KEY: value
```

For a Python repository with no Dockerfile, replace `build_spec`:

```yaml
  build_spec:
    type: tfy-python-buildpack
    build_context_path: ./
    python_version: "3.11"
    requirements_path: ./requirements.txt
    command: python main.py
```

## Checklist

- [ ] Did I clone and read the repository rather than inferring its contents?
- [ ] If it has a Dockerfile, did I use it instead of the buildpack? If Python without one, the buildpack instead of writing a Dockerfile?
- [ ] Did I set `local_build` from an actual `docker info` check rather than assuming?
- [ ] If Docker was available, did I build locally first — and if not, did I avoid claiming I verified it?
- [ ] Did I call `get_manifest_json_schema` and take `workspace_fqn` from `list_workspaces`?
- [ ] Did I ask the user for ports, resources and environment rather than choosing them?
- [ ] Did I read the build logs instead of reporting success when the deploy call returned?

For more info: `search_docs` with "deploy from a git repository", "build configuration", "tfy deploy".
