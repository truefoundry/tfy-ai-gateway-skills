---
name: canary-rollouts
description: Progressive / canary / blue-green style rollouts. Prefer rollout-strategy.md for the full picture (including rolling update and replica-change downtime). Read when the user asks specifically for canary or traffic splitting.
---

For **rolling update**, surge/unavailable, and “we only changed replicas and the old pod died”, read **`rollout-strategy.md` first**.

Canary / blue-green details:

1. Fetch live manifest (`get_application`).
2. Enable canary / blue-green fields from `get_manifest_json_schema` + `search_docs` (“canary”, “rollout”).
3. Keep probes correct — failed probes abort progression (`failure-modes/crashloop-oom-probes.md`).
4. `validate_manifest` → explain traffic steps → `apply_manifest` (approval).
5. Observe new pods; stuck OutOfSync → `failure-modes/rollout-argocd.md`. Rollback via prior manifest after approval.

Skip canary for one-replica dev apps when rolling update with sensible surge is enough.

## Checklist

- [ ] Did I open `rollout-strategy.md` when the issue was downtime / replica edits / surge?
- [ ] Did I confirm canary fields via schema/docs?
- [ ] Apply only with approval; verify new pods + smoke before calling success?

For more info: `search_docs` with "canary", "rollout strategy".
