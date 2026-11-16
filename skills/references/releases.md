---
name: releases
description: Read for release notes, breaking changes, upgrades, known issues, supported versions and the public product roadmap, for both products — "what's new", "what changes if I upgrade", "which version should I run", "is X fixed in my version", "is X planned / when does X ship", and before any feature-request ticket.
---

A release is `0.183`; a patch (what is installed) is `0.183.20`.

- **Control plane version:** `controlPlaneVersion` in the session context, unless the user names another; say which one you used.
- **Gateway version** (hybrid customers run their own gateway, e.g. `0.183.5`): no tool shows it; ask.
- Ask only for a version you need and don't have.

## Changelog tools

| The user asks | Call |
|---|---|
| What changes if I upgrade, any breaking changes | `diff_releases` with `from_control_plane_version` and `to_control_plane_version`, or the two gateway versions |
| Which version to upgrade to, is my version supported | `get_recommendation` with `current_control_plane_version` (or `current_gateway_version`) |
| Known issues in my version, should I upgrade now | `get_patch_health` with their version |
| What's new, what's in a release | `list_releases` (`only_monthly_stable: false` for every release, not only monthly Stable), then `get_release` with a release like `0.183` |
| Is X in my version, which version added X | `diff_releases` from their version to the newest patch: if X is there, they get it by upgrading (`first_released_in` names a patch that has it; a backport can bring it to an older release too); if not, they have it |

- No upgrade target named: use the recommended patch from `get_recommendation`, unless they ask for the newest.
- `PATCH_NOT_FOUND` or `RELEASE_NOT_FOUND`: say the release notes don't cover that version yet. Never guess its contents.

## Upgrade answers

Lead with, in this order:

1. Every change with an `upgrade_step`: quote the step.
2. `required_stops` (patches to install on the way, in order) and `withdrawn_patches`.
3. `lost_changes` (in their version but not in the target) and `known_issues.still_open`.

Then summarize the rest briefly by product, most relevant to the user first. Never drop a step.

An upgrade across releases is often over 100,000 characters, and `get_release` over 24,000: the result is saved to a file. Extract from it; never skim it or call the tool again:

```bash
jq -c '{steps: [.changes_by_release[].changes_by_product[].changes[] | select(.upgrade_step) | {upgrade_step, description}] | unique, required_stops, withdrawn_patches, lost_changes: [.lost_changes[]? | .description], still_open: .known_issues.still_open}' <file>
```

For the rest, print only the user's products: `jq -r '.changes_by_release[].changes_by_product[] | select(.product == "LLM Gateway") | .changes[].description' <file>`. A saved `get_release` result has the same changes under `.patches[].changes_by_product[]`.

## Roadmap: `list_roadmap_items`

Use it for what's coming, "is X planned", and when X ships. Always filter: `search` with two or three key words (`audit SIEM`, `agent budget`), and/or `category` or `status`. The unfiltered list is very long. If `search` finds nothing, try one other wording before saying it isn't on the roadmap.

- Dates are targets, not commitments: say "targeted for <month year>", never "will ship". A `planned` or `in_progress` item whose target date has passed has not shipped yet; say so. No dates means unscheduled.
- A `completed` item has shipped: check whether the user's version has it, as in "Is X in my version" above.
- Don't present `cancelled` items as coming.

## Feature requests

Follow `support-tickets.md`: it checks the roadmap before any ticket.

Release notes: [changelogs.truefoundry.com](https://changelogs.truefoundry.com). Roadmap: [roadmap.truefoundry.com](https://roadmap.truefoundry.com).
