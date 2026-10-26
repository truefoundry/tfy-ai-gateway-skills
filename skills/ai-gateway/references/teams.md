---
name: teams
description: Create and manage teams — groups of users that can be used for access control, rate limiting, and budget scoping.
---

**Teams** are groups of users used for access control and config scoping across the platform. Granting a team access to a resource automatically grants access to all its members.

Note: There is an implicit `everyone` team which includes all users in the tenant (but not virtual accounts).

## Fetching existing teams

Use `list_teams_for_user` to list teams. This tool is **user-scoped** — it returns only teams the current user belongs to, not every team in the tenant. There is no tool to list all teams tenant-wide; `list_teams_for_user` is the only option. Use `get_team` to inspect a single team by name or ID. Use `list_team_members` and `list_team_managers` to get team membership.

## Creating Teams (Write Flow)

### Phase 1: Check for Existing Teams

Call `list_teams_for_user` and check if a team matching what the user asked for already exists.

- **Matches found:** Present the matching teams to the user and ask whether they want to create a new team (with a different name) or update an existing one. Carry their choice forward into Phase 2.
- **No matches:** Proceed to Phase 2.

Note: `list_teams_for_user` only returns teams the current user belongs to. A team with the same name may already exist tenant-wide. If creation fails with 403 or a name conflict, suggest a different name.

### Phase 2: Get Schema

1. Call `get_manifest_json_schema` with type `team`.

### Phase 3: Build and Apply

Collect team name and member emails → build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Updating an Existing Team

> **CRITICAL**: Never change an existing team's members or managers with `apply_manifest`: a `members` or `managers` list replaces the whole current list, so everyone you leave out is removed.

- **Add or remove people:** use `add_team_members` / `remove_team_members` / `add_team_managers` / `remove_team_managers` with the team `id` and body `{"emails": ["a@example.com"]}`. Everyone else stays.
- **Other field changes:** start from `generate_team_manifest` (team `id`) and either keep its `members` and `managers` exactly as returned or delete both fields so membership stays unchanged.
- SCIM-managed teams reject any `members` change.

### Manifest Structure

```yaml
type: team
name: <unique-team-name>
members:
  - <user-email-1>
  - <user-email-2>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `team`?
- [ ] For an existing team, did I use the add/remove member and manager tools instead of sending a `members` or `managers` list?

For more info: `search_docs` with "team management", "create team", "team access control".
