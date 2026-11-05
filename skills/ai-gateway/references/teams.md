---
name: teams
description: Read before listing, creating or changing teams — groups of users used for access control, rate limiting and budget scoping — including adding or removing members and managers.
---

**Teams** are groups of users used for access control and config scoping. Access granted to a team applies to all its members.

Note: there is an implicit `everyone` team that includes every user in the tenant (but not virtual accounts). It cannot be edited.

Teams can be created manually or provisioned from your IdP via SCIM. Members of SCIM-managed teams can only be changed in the IdP.

## Reading teams

- `list_teams_for_user` returns every team you can read (all teams for tenant admins) plus the teams you belong to. Pass `includeMembership=false` when you only need names and IDs, and `role=manager` for teams you can manage.
- `get_team` takes the team's `id` (from `list_teams_for_user`); it does not accept a name. `list_team_members`, `list_team_managers`, `generate_team_manifest`, `get_team_permissions`, `delete_team` and the add/remove tools also take the team `id`.

## Inputs to collect

- Team name (3-50 chars: letters, digits, `_` or `-`; starts with a letter).
- Member and manager emails. Every email must belong to an existing user in the tenant.

## Creating a team

1. In one parallel batch: `list_teams_for_user` with `includeMembership=false`, and `get_manifest_json_schema` with type `team` (reuse the schema if it is still in the conversation).
2. If a team with that name (or a similar one) exists, show it and ask whether to create a new team with a different name or update the existing one. Restate the user's choice (create a new name, or update `<name>`) in your reply before continuing. For an update, go to "Updating an existing team".
3. Build the manifest, then `validate_manifest` → `apply_manifest` per `write-rules.md`.
   - Applying a team manifest whose `name` matches an existing team updates that team. If the apply returns 403, a team with that name exists and you cannot manage it; ask the user for a different name.
   - A 422 listing emails means those users do not exist in the tenant.

## Updating an existing team

**Never change an existing team's members or managers with `apply_manifest`: a `members` or `managers` list replaces the whole current list, so everyone you leave out is removed.**

- **Add or remove people:** use `add_team_members` / `remove_team_members` / `add_team_managers` / `remove_team_managers` with the team `id` and body `{"emails": ["a@example.com"]}`. Everyone else stays.
- **Other field changes:** call `generate_team_manifest` (team `id`) right before editing, and either keep its `members` and `managers` exactly as returned or delete both fields so membership stays unchanged.
- SCIM-managed teams reject any `members` change.

## Manifest

```yaml
type: team
name: <team-name>             # 3-50 chars: letters, digits, _ or -; starts with a letter
displayName: <optional label>
description: <optional>
managers:                     # optional
  - <email>
members:                      # optional; every email must be an existing user
  - <email>
```

## Checklist

- [ ] Do I have the `team` schema from `get_manifest_json_schema` in the conversation? If not, call it again.
- [ ] Did I pass the team `id`, not its name, to `get_team` and the member/manager tools?
- [ ] For an existing team, did I use the add/remove member and manager tools instead of sending a `members` or `managers` list?

For more info: `search_docs` with "team management", "create team", "team access control".
