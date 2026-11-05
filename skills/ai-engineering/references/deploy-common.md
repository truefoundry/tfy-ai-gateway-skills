---
name: deploy-common
description: Rules that apply to every deployment regardless of path — creating versus updating an application, resolving the workspace, what validation does and does not prove, and exposing a port. Read this alongside the reference file for your specific path.
---

These apply to every deploy path. They interleave with the path's own reference file rather than running before it:

- **Resolving the workspace** and **Creating or updating** settle first — they change what you build and what you ask the user.
- **Exposing a port** applies wherever a port has `expose: true`.
- **Validating and verifying** applies after the path's last step.

## Contents
- Resolving the workspace
- Creating or updating
- Validating and verifying
- Exposing a port
- After deploy — always print links
- Checklist

## Resolving the workspace

Call `list_workspaces(name=<workspace>)` and keep both `fqn` (for `workspace_fqn`) and `id` (for `generate_deployment_endpoint`). The same name can exist on several clusters; pick by cluster, and ask the user if it is ambiguous. Never construct an FQN.

If the workspace the user named does not exist, or the tenant has none yet, a workspace is itself a manifest (`type: workspace`) and needs a cluster — call `list_clusters`, then apply a workspace manifest before the application. Ask the user first; do not create a workspace silently to make a deploy succeed.

## Creating or updating

An application is identified by **workspace and name together** — the same name can exist in several workspaces. Call `list_applications(applicationName=<name>, workspaceFqn=<fqn>)`. One call answers create vs update. It is independent of `get_manifest_json_schema`, so batch the two.

Both `apply_manifest` and `tfy deploy` **replace the entire manifest**, so that answer decides what you are doing:

- **No row** — you are creating, even if the name exists in another workspace. Build the manifest from `get_manifest_json_schema`.
- **A row** — you are updating something that is running. Tell the user what is there and in which workspace, and confirm before changing it.

**When updating, start from the manifest that is already deployed.** Take `activeDeployment.manifest` from that `list_applications` row if the result is still in the conversation; otherwise call `get_application`. If `activeDeployment` is missing (no deployment ever succeeded), use `lastDeployment.manifest`. Change only the fields the user asked about and apply that.

Never build a fresh manifest from the schema for an update. The apply replaces everything, so every environment variable, secret reference, resource limit, replica count and probe you did not carry over is **silently dropped** — and the deploy reports success. The schema tells you what a field is called; only the deployed manifest tells you what this application had. If the fetched manifest is no longer in the conversation verbatim, fetch it again before applying; a summarized manifest drops fields.

The stored manifest of a source-built app is `image.type: image` (built locally) or `image.type: build` with `build_source.type: remote` (built by the platform). Two consequences:

- **Changing anything but the code** — replicas, resources, env vars, secrets, ports — is a plain `apply_manifest` of the fetched manifest with your edit. Either way it reuses the built image, so it needs no source and no path-specific reference file.
- **Changing the code** means producing a new image, which editing a manifest cannot do. Run the source flow in `deploy-from-source.md`.

## Validating and verifying

`validate_manifest` checks the manifest's **shape** against the JSON schema, not whether it will deploy — it returns `valid: true` for a Dockerfile path that does not exist. Never report a passing validation as "this will work".

It also does not fill in defaults. Write every field the schema lists as `required`, even ones that have a default — e.g. `replicas`, `expose`, `protocol`, job `trigger`, both rolling-update percentages, and `resources.ephemeral_storage_request` / `ephemeral_storage_limit`. Unknown fields pass validation and are then silently ignored, so a misspelled key is not caught; take names from the schema.

A deploy is not finished when the call returns. Follow it through `get_deployment` and confirm the workload is running rather than that the rollout was accepted. `troubleshooting.md` covers how.

## Exposing a port

Always write `expose` explicitly (`expose: false` for internal ports); `tfy deploy` defaults it to `true`.

A port with `expose: true` must carry a `host`. `validate_manifest` does not check this, so a missing host only fails at apply. Do not invent it: call `generate_deployment_endpoint` with `applicationType` (`service` or `async-service`), the workspace `id` as `workspaceId`, the application name as `applicationName`, and the `port`. Put the returned `host` on the port, and its `path` too when the response has one — when the host is a non-wildcard base domain, `path` is required.

The suggestion is derived from the application name, so call it again if the name changes. If it fails because the cluster has no base domain, the port cannot be exposed — say so and set `expose: false`. On an update, the deployed manifest already has its `host`; keep it. If that manifest is no longer in the conversation, fetch it again; never rebuild `host` from memory.

## After deploy — always print links

After a successful apply and a basic health check, **always** end with the links in `deployment-links.md` — the console link, and the real endpoint where there is one. Do not end on "deployed successfully" alone.

## Checklist

- [ ] Did I check `list_applications(applicationName, workspaceFqn)` before building anything?
- [ ] If updating, did I start from the verbatim `activeDeployment.manifest` (or `lastDeployment.manifest`) rather than a fresh one?
- [ ] Was the change code or configuration — and did I pick the matching path?
- [ ] Did I take `workspace_fqn` and `id` from `list_workspaces` instead of constructing them?
- [ ] Did I write every `required` field, including ones with defaults?
- [ ] Did I describe validation as a shape check rather than a guarantee?
- [ ] Did I confirm the workload is running, not just that the rollout was accepted?
- [ ] Does every port have an explicit `expose`, and every exposed port a `host` from `generate_deployment_endpoint` (or the deployed manifest, on an update)?
- [ ] Did I print the links per `deployment-links.md`?

For more info: `search_docs` with "update a deployment", "workspaces".
