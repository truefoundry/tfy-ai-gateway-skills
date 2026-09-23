---
name: canary-rollouts
description: Progressive / canary / blue-green style rollouts for TrueFoundry services. Read when the user asks for canary, gradual rollout, traffic splitting, or safer production deploys.
---

TrueFoundry services can roll out gradually instead of replacing all replicas at once. Exact fields live in the service JSON schema and product docs — always confirm with `get_manifest_json_schema` and `search_docs` (“canary”, “rollout”, “traffic split”).

## Contents
- When to use
- Configure
- Observe and promote / rollback
- Checklist

## When to use

- Production services where a bad image should not take 100% traffic immediately.
- Model server upgrades (new vLLM tag / weights) where smoke tests should pass on a slice first.

Skip for one-replica dev apps — canary adds little and complicates debugging.

## Configure

1. Fetch live manifest (`get_application`).
2. Enable the rollout / canary strategy fields from schema (steps, weights, analysis windows — names vary).
3. Keep probes correct — failed probes abort progression (`failure-modes/crashloop-oom-probes.md`).
4. `validate_manifest` → explain traffic steps → `apply_manifest` (approval).

If the schema has no canary fields for this application type, say so and offer: deploy under a new name + shift traffic at the Gateway/ingress layer, or standard rolling update with careful probe/readiness.

## Observe and promote / rollback

During rollout:

- `list_k8s_pods` — old and new ReplicaSets/Revisions present.
- Logs/metrics on the **new** pods only when diagnosing canary failures.
- `failure-modes/rollout-argocd.md` if the rollout sticks OutOfSync / never progresses.
- Rollback: redeploy previous deployment / apply prior manifest (full replace) after approval — do not “kubectl undo” in the cluster.

## Checklist

- [ ] Did I confirm canary fields via schema/docs for this app type?
- [ ] Did I warn that single-replica canary is low value?
- [ ] Did I verify new pods + smoke before calling the rollout successful?
- [ ] Apply only with approval; rollback via prior manifest if needed?

For more info: `search_docs` with "canary", "rollout strategy", "deployment strategy".
