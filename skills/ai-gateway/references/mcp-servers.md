---
name: mcp-servers
description: Deploy and connect MCP Servers to the AI Gateway to provide tools to models and agents
---

**MCP Servers** can be registered to MCP Gateway. MCP Servers can be of type `mcp-server/remote`, `mcp-server/openapi`, or `mcp-server/stdio`.
**Virtual MCP Servers** allows to compose tools from multiple MCP Servers into a single MCP Server.

## Contents
- Fetching existing MCP servers
- Creating Remote MCP Servers (Write Flow)
- Creating Stdio MCP Servers (Write Flow)

## Fetching existing MCP servers

> **CRITICAL**: Use only the admin tools for MCP servers — `list_mcp_servers_admin` (list all) and `get_mcp_server_admin` (get one by `id`). Do NOT use `list_mcp_servers` or `get_mcp_server`

Use the `list_mcp_servers_admin` tool to get the list of all MCP servers. The response would look like this:

```yaml
data:
  - id: ...
    fqn: truefoundry:mcp-server:mcp-server-1
    manifest:
      name: mcp-server-1
      type: mcp-server/remote
      # Fields specific to mcp-server/remote
    createdBySubject: { ... }
    createdAt: ...
    updatedAt: ...
  - id: ...
    fqn: truefoundry:mcp-server:mcp-server-2
    manifest:
      name: mcp-server-2
      type: mcp-server/virtual
      servers:
        - name: mcp-server-1
          enabled_tools:
            - tool-1
            - tool-2
        - name: mcp-server-3
          enabled_tools:
            - tool-3
            - tool-4
      # Fields specific to mcp-server/virtual
    createdBySubject: { ... }
    createdAt: ...
    updatedAt: ...
pagination:
  total: ...
  offset: 0
  limit: 100
```

## Creating Remote MCP Servers (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with the MCP server type (e.g. `mcp-server/remote`, `mcp-server/openapi`) to get the full JSON schema.

### Phase 2: Determine Authentication

1. Use `ask_user_question` to ask the user what type of authentication they want (options depend on what the schema supports — typically: no auth, OAuth 2.0, API Key / Header-based).

2. **If OAuth 2.0 is selected**: You **MUST** call `get_mcp_server_oauth_config` with the MCP server's URL before proceeding. This returns the Raw OAuth 2.0 Authorization Server Metadata (RFC 8414) which provides `authorization_url`, `token_url`, supported `scopes`, and other metadata required to fill the auth config. Do NOT skip this step or guess the OAuth URLs.

3. Collect remaining auth details from the user (client_id, client_secret, scopes, etc.).

### Phase 3: Validate and Apply

Build the manifest → write to file → `python scripts/validate_schema.py --file-path <manifest.yaml>` → `apply_manifest` (no dry-run — not supported for MCP servers).

### Manifest Structure

```yaml
name: <unique-mcp-server-name>
description: <description>
url: <mcp-server-endpoint-url>
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>  # from get_me
  - role_id: mcp-server-access
    subject: team:everyone
type: mcp-server/remote
auth_data:
  type: oauth2
  grant_type: authorization_code
  authorization_url: <from-oauth-server-metadata>
  token_url: <from-oauth-server-metadata>
  client_id: <client-id>
  client_secret: <client-secret>
  jwt_source: access_token
  scopes:
    - <scope-1>
    - <scope-2>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I ask the user which auth type they want before proceeding?
- [ ] If OAuth, did I call `get_mcp_server_oauth_config` to get server metadata?
- [ ] Did I skip dry-run (not supported for MCP servers)?

## Creating Stdio MCP Servers (Write Flow)

Stdio MCP Servers run a local command (e.g., `npx`, `python`) that communicates via stdin/stdout.

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `mcp-server/stdio` to get the full JSON schema.

### Phase 2: Gather Details

1. Ask the user for the command, args, and any environment variables needed to run the MCP server.

### Phase 3: Validate and Apply

Build the manifest → write to file → `python scripts/validate_schema.py --file-path <manifest.yaml>` → `apply_manifest` (no dry-run — not supported for MCP servers).

### Manifest Structure

```yaml
type: mcp-server/stdio
name: <unique-mcp-server-name>
description: <description>
command: <command>                        # e.g. npx, python, node
args:
  - <arg-1>
  - <arg-2>
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>    # from get_me
  - role_id: mcp-server-access
    subject: team:everyone
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `mcp-server/stdio`?
- [ ] Did I ask the user for the command and args?
- [ ] Did I skip dry-run (not supported for MCP servers)?

For more info: `search_docs` with "mcp gateway", "mcp oauth", "mcp server registry".
