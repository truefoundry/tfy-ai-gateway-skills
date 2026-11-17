---
name: releases
description: Read for release notes, breaking changes, upgrades, known issues, supported versions and the public product roadmap, for both products — "what's new", "what changes if I upgrade", "which version should I run", "is X fixed in my version", "is X planned / when does X ship", and before any feature-request ticket.
---

A release is `0.183`; a patch (what is installed) is `0.183.20`.

- **Control plane version:** `controlPlaneVersion` in the session context, unless the user names another; say which one you used.
- **Gateway version** (hybrid customers run their own gateway, e.g. `0.183.5`): no tool shows it; ask.
- Ask only for a version you need and don't have.

## Changelog tools

Every answer is JSON under `data`.

| The user asks | Call |
|---|---|
| What changes if I upgrade, any breaking changes | `get_diff` with `fromControlPlaneVersion` and `toControlPlaneVersion`, or `fromGatewayVersion` and `toGatewayVersion` |
| Which version to run, is my version supported, known issues in my version, should I upgrade now | `get_recommendation` with `controlPlaneVersion` or `gatewayVersion`; with neither, both recommended versions |
| What's new, what's in a release | `list_releases` (`monthlyStable: false` for every release, not only monthly Stable), then `get_release` with a release like `0.184` |
| Is X in my version, which version added X | `get_diff` from their version to the newest patch (`latestControlPlaneVersion` of the first release from `list_releases` with `monthlyStable: false`): if X is there, they get it by upgrading (its `controlPlaneVersion` names a patch that has it; a backport can bring it to an older release too); if not, they have it |

- No upgrade target named: use `recommendedControlPlaneVersion` (or `recommendedGatewayVersion`) from `get_recommendation`, unless they ask for the newest.
- `VERSION_NOT_FOUND` or `RELEASE_NOT_FOUND`: say the release notes don't cover that version. Never guess its contents.

## Is my version OK

`get_recommendation` with their version returns `current`: its `status`, `knownIssues` (each with `title`, `severity`, `workaround` and where it is fixed) and, when they should move, `upgrade`. No `upgrade` means no need to upgrade. By `upgrade.reason`:

- `CRITICAL_ISSUE`, `WITHDRAWN`, `UNSUPPORTED`: upgrade now, to `upgrade.toControlPlaneVersion`, through each of `requiredStopControlPlaneVersions` in order. `isAheadOfMonthlyStable` means the target is past the monthly Stable; say so.
- `ENDING_SOON`: upgrade before the next monthly Stable.
- `NEWER_RECOMMENDED`: upgrade at a regular upgrade.

Give each known issue's workaround.

## Upgrade answers

Lead with, in this order:

1. Every `breakingChange`, and every `upgradeStep` (quote the step).
2. `requiredStopControlPlaneVersions` (install each on the way, in order) and `withdrawnControlPlaneVersions`.
3. `lostChanges` (in their version but not in the target) and `knownIssues.open`.

Then summarize the rest briefly by product, most relevant to the user first. Never drop a breaking change or a step.

A `get_diff` across releases is often over 100,000 characters and saved to a file. Extract from it; never skim it or call the tool again:

```bash
jq -c '.data | {breaking: [.changes[] | .breakingChange // empty] | unique, steps: [.changes[] | select(.upgradeStep) | {upgradeStep, description}] | unique, requiredStops: .requiredStopControlPlaneVersions, withdrawn: .withdrawnControlPlaneVersions, lost: [.lostChanges[]? | .description], openIssues: [.knownIssues.open[]? | {title, severity, workaround}]}' <file>
```

For the rest, print only the user's products: `jq -r '.data.changes[] | select(.products | index("LLM Gateway")) | .description' <file>`. A saved `get_release` has its changes under `.data.patches[].changes[]`.

## Roadmap: `list_roadmap_items`

Use it for what's coming, "is X planned", and when X ships. Always filter: `search` with two or three key words (`audit SIEM`, `agent budget`), and/or `category` or `status`. The unfiltered list is very long. If `search` finds nothing, try one other wording before saying it isn't on the roadmap.

- Dates are targets, not commitments: say "targeted for <month year>", never "will ship". A `planned` or `in_progress` item whose target date has passed has not shipped yet; say so. No dates means unscheduled.
- A `completed` item has shipped: check whether the user's version has it, as in "Is X in my version" above.
- Don't present `cancelled` items as coming.

## Feature requests

Follow `support-tickets.md`: it checks the roadmap before any ticket.

Release notes: [changelogs.truefoundry.com](https://changelogs.truefoundry.com). Roadmap: [roadmap.truefoundry.com](https://roadmap.truefoundry.com).
