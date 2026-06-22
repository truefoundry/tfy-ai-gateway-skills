---
name: mcp-servers
description: Deploy and connect MCP Servers to the AI Gateway to provide tools to models and agents
---

**MCP Servers** can be registered to MCP Gateway. MCP Servers can be of type `mcp-server/tfy-managed`, `mcp-server/remote`, `mcp-server/openapi`, `mcp-server/stdio`, or `mcp-server/virtual`.

## Contents
- Fetching existing MCP servers
- Listing tools for an MCP server
- Creating MCP Servers (Write Flow)
  - Step 1: Check the MCP Catalogue
  - Step 2: Build the manifest based on source (TFY Managed / Integration / Online search / OpenAPI / Virtual)
  - When to direct the user to the UI
  - Step 3: Validate and Apply

## Fetching existing MCP servers

> **CRITICAL**: Use only the admin tools for MCP servers — `list_mcp_servers_admin` (list all) and `get_mcp_server_admin` (get one by `id`). Do NOT use `list_mcp_servers` or `get_mcp_server`

Use the `list_mcp_servers_admin` tool to get the list of all MCP servers. The response looks like:

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
pagination:
  total: ...
  offset: 0
  limit: 100
```

## Listing tools for an MCP server

Always use `list_mcp_server_tools` (pass `mcpServerId` — the server's `id` from `list_mcp_servers_admin`) whenever you need to know what tools an MCP server exposes. Returns the tool list on success. Throws an error if the server is not connected or misconfigured — the error message indicates the issue.

## Creating MCP Servers (Write Flow)

### Step 1: Check the MCP Catalogue

**Always start here.** Call `list_mcp_catalogue` to get the catalogue of known MCP servers. The response has two sections:

```json
{
  "tfyManaged": [ ... ],
  "integrations": [ ... ]
}
```

Search for the user's requested MCP server by name in this order:

1. **`tfyManaged`** — TrueFoundry-managed servers. These are fully hosted by TrueFoundry — no URL, auth, or config needed from the user. Each entry has a `tfyManagedMcpManifest` with `type: "mcp-server/tfy-managed"` and a `server_identifier`.

2. **`integrations`** — Known remote MCP servers with pre-filled URLs and auth type info. Each entry has `url`, and optionally `auth_data` with the auth type (`oauth2`, `header`, or none). For OAuth2 integrations, you'll still need to collect `client_id` and `client_secret` from the user (unless the server supports Dynamic Client Registration).

3. **Not found in catalogue** — Search online. Prefer remote (HTTP/SSE) servers first; only fall back to stdio if no remote endpoint exists.

### Step 2: Build the manifest based on source

Call `get_manifest_json_schema` with the appropriate type (`mcp-server/tfy-managed`, `mcp-server/remote`, `mcp-server/stdio`) to get the full schema.

#### Path A: TFY Managed (from `tfyManaged`)

Use the `tfyManagedMcpManifest` directly from the catalogue entry. The manifest is minimal:

```yaml
name: <name>
description: <description>
type: mcp-server/tfy-managed
server_identifier: <server_identifier>
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>
  - role_id: mcp-server-user
    subject: team:everyone
```

No auth config needed — TrueFoundry manages everything.

#### Path B: Integration (from `integrations`)

Use the `url` from the catalogue. Check the `auth_data` field to determine the auth type:

- **No `auth_data`** → no auth needed. Build a simple remote manifest.
- **`auth_data.type: "oauth2"`** → Call `get_mcp_server_oauth_config` with the MCP server's URL to get OAuth metadata (authorization_url, token_url, scopes, etc.). Check if the metadata includes `registration_endpoint` — if yes, Dynamic Client Registration (DCR) is supported and `client_id`/`client_secret` are not needed. If no `registration_endpoint`, ask the user for their `client_id` and `client_secret` (they'll need to register an OAuth app with the provider first).
- **`auth_data.type: "header"`** → The catalogue shows the header keys with placeholder values (e.g. `"Authorization": "Bearer YOUR_API_KEY"`). Ask the user for the actual secret values.

```yaml
name: <unique-name>
description: <description>
url: <url-from-catalogue>
type: mcp-server/remote
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>
  - role_id: mcp-server-user
    subject: team:everyone
auth_data:
  # For oauth2 (without DCR — client_id and client_secret required):
  type: oauth2
  grant_type: authorization_code
  authorization_url: <from-oauth-metadata>
  token_url: <from-oauth-metadata>
  client_id: <from-user>
  client_secret: <from-user>
  jwt_source: access_token
  scopes: [<from-oauth-metadata>]
  # For oauth2 (with DCR — no client_id/client_secret needed):
  type: oauth2
  grant_type: authorization_code
  authorization_url: <from-oauth-metadata>
  token_url: <from-oauth-metadata>
  registration_endpoint: <from-oauth-metadata>
  jwt_source: access_token
  scopes: [<from-oauth-metadata>]
  # For header:
  type: header
  headers:
    <header-key>: <user-provided-secret>
```

#### Path C: Not in catalogue (search online)

1. Search online for the MCP server — look for a **remote** (HTTP/SSE/streamable) endpoint first.
2. If no remote endpoint found, search for a **stdio** package (npx, python, etc.).

**If remote:**
- Ask the user which auth type they want (no auth, OAuth 2.0, API Key/Header).
- If OAuth 2.0: call `get_mcp_server_oauth_config` with the server URL to get metadata. If no `registration_endpoint` in the response, ask the user for `client_id` and `client_secret`.
- If header-based: ask user for header key/value.
- Build the manifest same as Path B.

**If stdio:**

```yaml
type: mcp-server/stdio
name: <unique-name>
description: <description>
command: <command>
args:
  - <arg-1>
  - <arg-2>
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>
  - role_id: mcp-server-user
    subject: team:everyone
```

#### Path D: OpenAPI Spec

If the user has an OpenAPI spec URL for their service, create an `mcp-server/openapi` type server. Call `get_manifest_json_schema` with type `mcp-server/openapi` for the full schema.

```yaml
type: mcp-server/openapi
name: <unique-name>
description: <description>
openapi_spec_url: <url-to-openapi-spec>
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>
  - role_id: mcp-server-user
    subject: team:everyone
```

#### Path E: Virtual MCP Server

Use when the user wants to combine tools from multiple existing MCP servers into one, or expose only a subset of tools from a server. Call `get_manifest_json_schema` with type `mcp-server/virtual` for the full schema.

Before building the manifest, call `list_mcp_server_tools` for each backing server to discover available tools, then ask the user which tools to include.

```yaml
type: mcp-server/virtual
name: <unique-name>
description: <description>
mcp_servers:
  - mcp_server_id: <id-of-backing-server-1>
    tools:
      - <tool-name-1>
      - <tool-name-2>
  - mcp_server_id: <id-of-backing-server-2>
    tools:
      - <tool-name-3>
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>
  - role_id: mcp-server-user
    subject: team:everyone
```

`mcp_server_id` is the server's `id` from `list_mcp_servers_admin`. `tools` is the list of tool names to expose from that server.

### When to direct the user to the UI

The agent can create MCP servers from an OpenAPI spec **URL** (Path D above), but cannot create them by pasting raw OpenAPI spec JSON directly — the API doesn't accept inline spec content. If the user wants to create an MCP server by pasting the spec JSON, direct them to the UI:
```
{controlPlaneUrl}/llm-gateway/mcp-servers
```
Get `controlPlaneUrl` from `get_me`. The UI supports creating MCP servers of all types including pasting OpenAPI specs directly.

### Step 3: Validate and Apply

Build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Checklist

- [ ] Did I call `list_mcp_catalogue` first to check if the server is TFY-managed or a known integration?
- [ ] Did I call `get_manifest_json_schema` with the correct type?
- [ ] Did I use the TFY-managed path if the server was in `tfyManaged`?
- [ ] For OAuth2, did I call `get_mcp_server_oauth_config` and check if DCR is supported? If not, did I ask for `client_id`/`client_secret`?
- [ ] For header auth, did I ask the user for the actual secret values?
- [ ] Did I add collaborators (current user as manager, team:everyone as access)?
- [ ] Did I call `validate_manifest` before `apply_manifest`?
- [ ] Did I call `apply_manifest` directly (not from sandbox)?

For more info: `search_docs` with "mcp gateway", "mcp server registry", "virtual mcp server".
