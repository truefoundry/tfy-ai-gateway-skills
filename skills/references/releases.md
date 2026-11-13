---
name: releases
description: Release notes, breaking changes, upgrades, known issues, and the public product roadmap, for both products. Use for "what's new", "what changes if I upgrade", "is X fixed in my version", "is X planned / when does X ship", and before any feature-request ticket.
---

Versions look like `0.184.13`; a release line is `0.184`. The user's version is `controlPlaneVersion` in the session context, unless they name another; say which one you used. Ask only if neither gives one.

## Changelog: `get_changelog`

Use it, not `search_docs`, for what a version changed, breaking changes, upgrades and known issues.

| The user asks | Call |
|---|---|
| What changes if I upgrade / any breaking changes | `from` = their version, `to` = their target |
| Upgrade, no target named | no arguments first: offer the latest release, or the recommended on-prem release for a self-hosted install; then `from`/`to` |
| What's new | no arguments, then `version` = the newest release line |
| Is X fixed / does my version have X | `search`, then compare the release it shipped in with their version |
| Which version added X | `search` |

An upgrade result can be very long. Lead with every **Action required** item (keep each required step exact), then required stops and withdrawn releases, then a short summary of the rest by product, most relevant to the user first. Never drop an action.

## Roadmap: `list_roadmap_items`

Use it for what's coming, "is X planned", and when X ships. Always filter: `search` with two or three key words (`audit SIEM`, `agent budget`), and/or `category` or `status`. The unfiltered list is very long. If `search` finds nothing, try one other wording before saying it isn't on the roadmap.

- Dates are targets, not commitments: say "targeted for <month year>", never "will ship". A `planned` or `in_progress` item whose target date has passed has not shipped yet; say so. No dates means unscheduled.
- A `completed` item has shipped: find its release with `get_changelog` and `search`, and say whether the user needs to upgrade for it.
- Don't present `cancelled` items as coming.

## Feature requests

Follow `references/support-tickets.md`: it checks the roadmap before any ticket.
