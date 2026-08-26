---
name: helm-deploy
description: Deploy a Helm chart — from a chart repository or an OCI registry, with values. Read this whenever the user asks to deploy a chart, or names software that is normally installed as one such as redis, postgres, kafka or elasticsearch.
---

A Helm deployment installs a chart someone else wrote, so almost none of the usual deployment decisions apply — there is no build, no image to choose, and no application code. What matters instead is reaching the chart, picking a version, and setting values the chart expects.

Helm releases also behave differently once they are running, in ways that matter for anything asked about them afterwards. That is covered at the end and in `troubleshooting.md`.

## Contents

- Reaching the chart
- Choosing a version
- Values
- Deploying
- What a Helm release looks like afterwards

## Reaching the chart

Charts come from a chart repository, which serves an `index.yaml`, or from an OCI registry.

Two things about public chart sources are worth knowing before spending attempts on them:

**Chart repositories redirect and move.** Long-standing URLs are being retired and redirected elsewhere, and the index at the end of a redirect can be very large. If the user gives a repository URL that behaves oddly, follow where it actually resolves rather than assuming the URL is wrong.

**A public index does not mean a public chart.** Registries have moved to requiring authentication for the chart artifact while leaving the index readable. The result is that listing charts works and pulling one returns `401`. That is the registry's access decision, not a platform failure and not something a retry will fix. Report it and tell the user the chart needs credentials configured, or a different source.

If a chart cannot be pulled, say which registry refused it and why. Repeating the same call is the failure mode to avoid here — the same refusal will arrive again, and the user learns nothing.

## Choosing a version

Do not leave the version unset and do not guess one. Charts change shape between major versions, and values that were correct for one version are silently ignored by another — which produces a release that installs successfully and is configured nothing like what the user asked for.

Ask the user which version they want if they have not said. If they have no preference, take a recent stable version rather than the newest, and tell them which one you used.

## Values

Values are the entire configuration surface of a Helm deployment, and the chart's own documentation is the authority on them. Do not invent value keys — a misspelled key is not an error, it is ignored, and the release comes up with defaults.

For anything stateful, raise persistence explicitly. Charts vary in whether persistence defaults on, and a database that comes up without a volume loses everything when its pod is replaced. This is worth confirming before deploying rather than diagnosing afterwards.

Secrets belong in secret references, not in values pasted as plain text. A password written directly into a manifest is stored as part of that manifest.

## Deploying

1. Confirm the chart is reachable and pick a version, as above.
2. Call `get_manifest_json_schema` for the `helm` type — the manifest shape differs from other application types.
3. Collect values with `ask_user_question`, covering at minimum persistence and any credentials the chart requires.
4. Validate, then apply with `apply_manifest`. There is no build, so the local-source exception never applies to Helm.
5. Confirm the release actually came up. A Helm install being accepted says nothing about whether its pods started.

## What a Helm release looks like afterwards

A chart usually creates several workloads, and their names are not the release name.

Subcharts append their own suffixes: a release named `nikp-redis` produces a StatefulSet called `nikp-redis-master` and a pod called `nikp-redis-master-0`. StatefulSet pods are numbered by ordinal, so the pod name has a trailing `-0` that nothing in the release name predicts.

The consequence for anything you do later: **list the pods, never construct their names.** Constructing them produces a name that does not exist, and a query for a pod that does not exist returns empty rather than an error.

Events work normally — `list_application_events` covers a Helm release like any other application. Logs do not: there is no application-level log stream, so reading logs means going through `list_k8s_pods` to find the real pod and then `get_k8s_pod_logs`. `troubleshooting.md` covers this.
