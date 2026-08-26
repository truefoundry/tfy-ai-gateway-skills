---
name: deploy-common
description: Rules that apply to every deployment regardless of path — creating versus updating an application, resolving the workspace, and what validation does and does not prove. Read this alongside the reference file for your specific path.
---

These apply to every deploy path. They interleave with the path's own reference file rather than running before it:

- **Creating or updating** settles first — it changes what you build and what you ask the user.
- **Resolving the workspace** applies wherever the path asks for `workspace_fqn`.
- **Validating and verifying** applies after the path's last step.

## Contents
- Creating or updating
- Resolving the workspace
- Validating and verifying
- Checklist

## Creating or updating

An application is identified by **workspace and name together**, not by name alone — the same name can exist in several workspaces. Settle the target workspace first, then call `list_applications` filtered by the name and look only at what is in that workspace.

Both `apply_manifest` and `tfy deploy` **replace the entire manifest**, so that pair decides what you are doing:

- **Nothing of that name in the target workspace** — you are creating, even if the name exists in another workspace. Build the manifest from `get_manifest_json_schema`.
- **That workspace already has one** — you are updating something that is running. Tell the user what is there and in which workspace, and confirm before changing it.

Do not treat a match in a different workspace as a collision, and do not treat a match in the target workspace as a different application because the user did not name the workspace.

**When updating, start from the manifest that is already deployed.** `get_application` returns `activeDeployment`, which carries that deployment's `manifest`. Change the fields the user asked about and apply that.

Never build a fresh manifest from the schema for an update. The apply replaces everything, so every environment variable, secret reference, resource limit, replica count and probe the user had configured and you did not carry over is silently dropped — and the deploy reports success. The schema tells you what a field is called; only the deployed manifest tells you what this application had.

**The stored manifest is resolved, not the one that was submitted.** An application built from source stores `image: {type: image, image_uri: ...}` pointing at the image that was built, not the build spec that produced it. Two consequences:

- **Changing anything but the code** — replicas, resources, env vars, secrets, ports — is a plain `apply_manifest` of the fetched manifest with your edit. It reuses the existing image and does not rebuild, so it needs no source and no path-specific reference file.
- **Changing the code** means producing a new image, which editing a manifest cannot do. Run the source flow in `deploy-from-source.md`.

## Resolving the workspace

`workspace_fqn` comes from `list_workspaces`. Never construct one.

If the workspace the user named does not exist, or the tenant has none yet, a workspace is itself a manifest (`type: workspace`) and needs a cluster — call `list_clusters`, then apply a workspace manifest before the application. Ask the user first; do not create a workspace silently to make a deploy succeed.

## Validating and verifying

`validate_manifest` checks the manifest's **shape**, not whether it will deploy — it returns `valid: true` for a Dockerfile path that does not exist. Never report a passing validation as "this will work".

A deploy is not finished when the call returns. Follow it through `get_deployment` and confirm the workload is running rather than that the rollout was accepted. `troubleshooting.md` covers how.

## Checklist

- [ ] Did I check whether the name was already taken before building anything?
- [ ] If updating, did I start from `activeDeployment.manifest` rather than a fresh one?
- [ ] Was the change code or configuration — and did I pick the matching path?
- [ ] Did I take `workspace_fqn` from `list_workspaces` instead of constructing it?
- [ ] Did I describe validation as a shape check rather than a guarantee?
- [ ] Did I confirm the workload is running, not just that the rollout was accepted?

For more info: `search_docs` with "update a deployment", "workspaces".
