---
name: personal-access-tokens
description: Read before creating or listing Personal Access Tokens (PATs) — user-owned tokens for authenticating against the Gateway and platform APIs.
---

**Personal Access Tokens (PATs)** belong to a user and are meant for development and testing. They become invalid when the owning user is deleted or deactivated. For production, CI/CD and shared apps, recommend a virtual account instead (see `virtual-accounts.md`).

PATs cannot be created with `apply_manifest`. Use `create_personal_access_token` directly; no schema call is needed.

## Inputs to collect

1. What the PAT is for (development, testing, CI, etc.) — if it is for production or a shared app, recommend a virtual account first.
2. A token name: 3-36 chars, lowercase letters, digits and hyphens; starts with a letter.
3. Optional expiration date. Without one, the tenant's maximum expiry is used.
4. Optional team to attribute the PAT to. A team is optional unless the tenant requires one; pass it only if the user names one. The team cannot be `everyone`, and the user must be a member of it.

## Steps

1. Call `check_personal_access_token_exists` with `name`. If it exists, ask for another name.
2. Call `create_personal_access_token` with `name`, plus `expirationDate` (ISO date, in the future) and `teamName` only if given. Send no other fields.
   - `TEAM_SELECTION_REQUIRED`: ask the user for a team (list options with `list_teams_for_user`) and retry.
   - `TEAM_SELECTION_DISABLED`: retry without `teamName`.
   - 403 when you are authenticated with a PAT: this tenant does not allow creating a PAT from a PAT; ask the user to create it in the UI at `{controlPlaneUrl}/access-management?tab=personal-access-token`.
3. **The response contains the token value once.** Show it to the user in that reply with a warning to store it securely, because it cannot be retrieved later. Never repeat it in later replies and never pass it to other tool calls.

## Other operations

- **PAT for another user (tenant admins only):** call `create_personal_access_token_for_user` with `name`, `userEmail`, and optionally `expirationDate` and `teamName` (the target user must be a member). Non-admins get 403.
- **Listing:** `list_personal_access_tokens` shows only your own PATs.

## Checklist

- [ ] Did I recommend a virtual account for production use cases?
- [ ] Did I collect a valid `name` and check it with `check_personal_access_token_exists`?
- [ ] Did I pass `teamName` only if the user chose a team (never `everyone`)?
- [ ] Did I show the token once with a store-securely warning, and not repeat it?

For more info: `search_docs` with "personal access token", "PAT creation", "API authentication".
