---
name: helm-deploy
description: Deploy a Helm chart from a chart repository, an OCI registry or a git repository, with values. Read this when the user asks to deploy a chart, or has confirmed they want a chart rather than a plain image for software that ships as both — redis, postgres, kafka, elasticsearch, prometheus.
---

A Helm deployment installs a chart someone else wrote, so the usual deployment decisions do not apply — there is no build, no image to choose, no application code. What matters is reaching the chart, pinning a version, and setting the values the chart expects.

A Helm release also behaves differently once running, which matters for every question asked about it afterwards. See the last section.

## Contents
- Phase 1: Reach the chart
- Phase 2: Pin a version
- Phase 3: Collect values
- Phase 4: Validate and apply
- Manifest structure
- What a Helm release looks like afterwards
- Checklist

## Phase 1: Reach the chart

| `source.type` | Fields |
|---|---|
| `helm-repo` | `repo_url`, `chart`, `version`; `integration_fqn` (helm-repo integration) for a private repository |
| `oci-repo` | `oci_chart_url` (`oci://...`), `version`; `integration_fqn` (docker-registry integration) for a private registry |
| `git-helm-repo` | `repo_url`, `revision`, `path`, `value_files?` |

For `oci://` sources, call `validate_oci_chart(chartUrl, integrationFQN?)` before putting the chart in a manifest. It returns `{accessible, message}`. `accessible: false` means the chart cannot be pulled without credentials; report it and do not retry.

Two things about public chart sources, both worth knowing before spending attempts:

**Repository URLs redirect and move.** Long-standing chart repository URLs are being retired and redirected elsewhere, and the index at the end of a redirect can be very large. Follow where a URL actually resolves rather than assuming it is wrong.

**A public index does not mean a public chart.** Registries have moved to requiring authentication for the chart artifact while leaving the index readable, so listing charts succeeds and pulling one fails. This is the registry's access decision — not a platform failure, and not something a retry will fix. Report which registry refused it and tell the user the chart needs credentials (`integration_fqn`) or a different source.

Ask the user for the chart name and version, or read the repository's index directly.

## Phase 2: Pin a version

Do not leave `version` unset and do not guess one. Charts change shape between major versions, and values correct for one version are **silently ignored** by another — producing a release that installs successfully and is configured nothing like what was asked for.

Ask the user which version they want. If they have no preference, use a recent stable version and tell them which one you used.

## Phase 3: Collect values

Values are the entire configuration surface, and the chart's own documentation is the authority. Do not invent value keys — a misspelled key is not an error, it is ignored, and the release comes up on defaults.

1. `list_workspaces(name=<workspace>)` — keep `fqn` (see **Resolving the workspace** in `deploy-common.md`).
2. In one parallel batch: `list_applications(applicationName=<release name>, workspaceFqn=<fqn>)` and `get_manifest_json_schema` with type `helm` (the shape differs from other application types). A row back means you are upgrading — read **Creating or updating** in `deploy-common.md`; its values come from the deployed manifest, and a fresh `values` block silently drops everything the release had set.
3. Otherwise use `ask_user_question` for at least:
   - **Persistence** — charts differ on whether it defaults on. A database without a volume loses everything when its pod is replaced. Confirm before deploying.
   - **Credentials** — passwords and keys the chart requires. Reference secrets as `tfy-secret://<tenant>:<group>:<key>` (see `secrets.md`); never write a password into the manifest as plain text.
   - **Architecture** — many charts offer standalone vs replicated, and the choice changes how many workloads appear.
   - **Resources** — requests no node can satisfy leave pods `Pending` with no error.

## Phase 4: Validate and apply

Build the manifest as JSON → `validate_manifest` → fix and re-validate → `apply_manifest`. There is no build, so Helm always goes through `apply_manifest`.

After applying, confirm the release's pods actually came up. A Helm install being accepted says nothing about whether its workloads started. Then print the console link per `deployment-links.md`.

## Manifest structure

```yaml
type: helm
name: <release-name>
workspace_fqn: <fqn from list_workspaces>
source:
  type: helm-repo
  repo_url: https://<chart-repository>
  chart: redis
  version: "20.1.0"                    # always pin
values:                                # chart-specific — read the chart's docs
  architecture: standalone
  auth:
    enabled: true
    password: tfy-secret://<tenant>:<secret-group>:<key>
  master:
    persistence:
      enabled: true
      size: 8Gi
```

For an OCI source, replace `source` with:

```yaml
source:
  type: oci-repo
  oci_chart_url: oci://<registry>/<path>/<chart>
  version: "20.1.0"
```

## What a Helm release looks like afterwards

A chart usually creates several workloads, and **their names are not the release name** — subcharts append their own suffixes and StatefulSet pods carry an ordinal. A query for a pod that does not exist returns empty rather than an error, so a constructed name produces a confident wrong answer. **Never construct a pod name: take them from `get_application_state` (or `get_application_argocd_resources`), then use the real ones.**

Events work normally — `list_application_events` covers a Helm release like any other application.

Logs need a pod filter: `get_logs` on a Helm app without `podName` / `podNames` / `podNamesRegex` is rejected. Get the pod names first, then call `get_logs` with `applicationId` and `podName`.

`troubleshooting.md` has the naming example and the rest of the operational path.

## Checklist

- [ ] Did I confirm the chart is reachable — and for `oci://`, did I call `validate_oci_chart`?
- [ ] If the chart was not accessible, did I report which registry refused it rather than retrying?
- [ ] Did I pin an explicit `version` rather than leaving it unset or guessing?
- [ ] Did I take value keys from the chart's documentation rather than inventing them?
- [ ] Did I raise persistence explicitly for a stateful chart?
- [ ] Are credentials referenced as `tfy-secret://...` rather than written as plain text?
- [ ] Did I call `get_manifest_json_schema` with type `helm` and take `workspace_fqn` from `list_workspaces`?
- [ ] After applying, did I confirm the pods are running via `get_application_state`?
- [ ] Did I print the console link per `deployment-links.md`?

For more info: `search_docs` with "deploy a helm chart", "helm values".
