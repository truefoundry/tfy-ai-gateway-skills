---
name: mcp-servers
description: Read when the user wants to find, register, update, delete or connect to an MCP server on the AI Gateway (TrueFoundry-managed, remote, OpenAPI, stdio or virtual), list a server's tools, or get its endpoint URL.
---

**MCP servers** registered on the MCP Gateway are one of `mcp-server/tfy-managed`, `mcp-server/remote`, `mcp-server/openapi`, `mcp-server/stdio` or `mcp-server/virtual`. Every write also follows `write-rules.md` (steps, collaborators, `force: false` on updates, UI link); read it in the same batch.

## Contents
- Finding servers and their tools
- Create: Step 1 Check for existing MCP servers · Step 2 Check the MCP catalogue · Step 3 Build the manifest · Step 4 Validate and apply
- Update and delete
- Endpoint URL
- Checklist

## Finding servers and their tools

- By name: `list_mcp_servers` with `filter={"op":"AND","value":[{"column":"name","op":"eq","value":"<name>"}]}`.
- By purpose: `list_mcp_servers` with `attributes=id,name,manifest` to keep the response small. If the result is saved to a file, extract only `id`, `manifest.name`, `manifest.type` and `manifest.description` with one `jq`.
- One server: `get_mcp_server` with its `id`.
- Tools: `list_mcp_server_tools` with `mcpServerId` (the server's `id`). Reuse the `id` if the `list_mcp_servers` result is still in the conversation; otherwise call `list_mcp_servers` again with a `name` filter. It errors if the server is not connected or misconfigured; the message says why.

Response shape of `list_mcp_servers`:

```yaml
data:
  - id: ...
    fqn: truefoundry:mcp-server:mcp-server-1
    manifest:
      name: mcp-server-1
      type: mcp-server/remote
      # type-specific fields
    createdBySubject: { ... }
pagination:
  total: ...
  offset: 0
```

## Create

### Step 1: Check for existing MCP servers

Steps 1 and 2 are independent: call `list_mcp_servers` (filtered as above) and `list_mcp_catalogue` in one batch.

- **Match found:** show it and ask whether to create a new server (with a different name) or update the existing one. If that choice is no longer in the conversation, ask again before applying.
- **No match:** continue.

### Step 2: Check the MCP catalogue

`list_mcp_catalogue` returns `{ "tfyManaged": [...], "integrations": [...] }`. Look for the requested server in this order:

1. **`tfyManaged`** — hosted by TrueFoundry. Each entry has a `tfyManagedMcpManifest` with `type: mcp-server/tfy-managed` and a `server_identifier`. Use Path A.
2. **`integrations`** — known remote servers with a `url` and, optionally, an `auth_data` showing the auth type (`oauth2`, `header` or none). Use Path B.
3. **Not in the catalogue** — search online. Prefer a remote (HTTP/SSE/streamable) endpoint; fall back to stdio only if none exists. Use Path C. If the user has an OpenAPI spec, use Path D. To combine or subset tools of existing servers, use Path E.

### Step 3: Build the manifest

Call `get_manifest_json_schema` for the chosen type. Templates below are simplified; `collaborators` follow `write-rules.md` → Collaborators. `name` is 3–73 chars, lowercase letters, digits and hyphens, starting with a letter; it cannot change later.

#### Path A: TFY-managed

Copy `tfyManagedMcpManifest` from the catalogue entry (keep its `server_identifier`) and add `name`, `description` and `collaborators`. The user supplies no URL or credentials; auth comes from the catalogue. If the server uses OAuth, each user is prompted to connect on first use.

```yaml
type: mcp-server/tfy-managed
name: <name>
description: <description>
server_identifier: <server_identifier from the catalogue>
collaborators: [...]
```

#### Path B: Catalogue integration (remote)

Take `url` from the catalogue entry and pick the auth from its `auth_data.type`. Use exactly one `auth_data` block.

```yaml
type: mcp-server/remote
name: <unique-name>
description: <description>
url: <url from the catalogue>
auth_data: <one block below, or omit for no auth>
collaborators: [...]
```

- **No `auth_data`:** omit `auth_data`.
- **`oauth2`:** call `get_mcp_server_oauth_config` with `mcpUrl: <the server URL>` (only `https://` URLs are accepted). Copy its `formContent` fields (`authorization_url`, `token_url`, `scopes`, `jwt_source`, plus `registration_url` and `code_challenge_methods_supported` when present) into `auth_data`. Dynamic Client Registration (DCR) is supported only if `formContent.registration_url` is present: then keep `registration_url` in `auth_data` and omit `client_id`/`client_secret`. Otherwise ask the user for `client_id` and `client_secret` (they register an OAuth app with the provider first). **The manifest field is `registration_url`; never write `registration_endpoint` — it is ignored and users cannot authenticate.**
- **`header`:** the catalogue shows header names with placeholder values (e.g. `Authorization: Bearer YOUR_API_KEY`). Ask whether one shared key or each user's own key; for a shared key ask for the value.

```yaml
# OAuth2 — provider and grant_type are required
auth_data:
  type: oauth2
  provider: custom            # or auth0 / okta / microsoft-entra
  grant_type: authorization_code
  authorization_url: <formContent.authorization_url>
  token_url: <formContent.token_url>
  registration_url: <formContent.registration_url>   # only with DCR
  client_id: <from user>                              # only without DCR
  client_secret: <from user>                          # only without DCR
  jwt_source: <formContent.jwt_source>
  scopes: <formContent.scopes>
```

`grant_type: authorization_code` is per-user login; the other values are `client_credentials`, `token_exchange`, `id_jag` and `jwt_bearer`.

```yaml
# Header — auth_level is required
auth_data:
  type: header
  headers:
    <Header-Name>: <value>
  auth_level: global          # per_user: each user enters their own key
```

With `auth_level: per_user`, write values as placeholders such as `Bearer {{API_KEY}}`; each user fills them in when they connect.

Other remote `auth_data` types are `passthrough` (forwards the caller's TrueFoundry token) and `aws-sigv4` (AWS Bedrock AgentCore); read their fields from the schema. Remote servers have no `transport` field.

#### Path C: Not in the catalogue

**Remote:** ask which auth the server needs (none, OAuth 2.0, or header/API key), then build it as in Path B.

**Stdio** (only when no remote endpoint exists):

```yaml
type: mcp-server/stdio
name: <unique-name>
description: <description>
command: <command>           # default npx
args: [<arg-1>, <arg-2>]
auth_data:                   # only if the server needs credentials
  type: env
  env:
    <VAR>: <value>
  auth_level: global         # per_user with {{PLACEHOLDER}} values
collaborators: [...]
```

#### Path D: OpenAPI spec

```yaml
type: mcp-server/openapi
name: <unique-name>
description: <description>
url: <API base URL, no path suffix>
openapi_spec_source:
  type: remote
  url: <spec URL>
enable_all_tools: true
collaborators: [...]
```

- If the user pastes the spec instead of a URL, use `openapi_spec_source: {type: inline, openapi_spec: <the spec as a JSON object or JSON/YAML string>}`. TrueFoundry stores it and rewrites it to `upload`.
- Use `enable_all_tools: true` only when the spec has ≤ 200 operations. Otherwise set `enable_all_tools: false` and list the operations in `tool_settings: [{method, path, name, description}]`. With neither, apply fails with "At least 1 tool is required".
- `auth_data` takes the same blocks as remote servers.

#### Path E: Virtual MCP server

Combines tools from existing servers, or exposes a subset of one server's tools. Call `list_mcp_server_tools` for each source server (independent calls, one batch), then ask the user which tools to include.

```yaml
type: mcp-server/virtual
name: <unique-name>
description: <description>
servers:
  - name: <source-server-name>
    enabled_tools: [<tool-1>, <tool-2>]
  - name: <another-source-server-name>
collaborators: [...]
```

`servers[].name` is the source server's **name**, not its `id` (the `id` is only for `list_mcp_server_tools`). Omit `enabled_tools` to expose all of a source's tools. A source cannot itself be a virtual server, and the user needs access to every source.

### Step 4: Validate and apply

Follow `write-rules.md` → Steps: `validate_manifest`, wait for `valid: true`, then `apply_manifest`. Then show the UI link and the endpoint URL (below).

## Update and delete

- **Update:** start from the server's current `manifest` (`get_mcp_server`), change only what was asked, keep the same `name`, and call `apply_manifest` with `force: false`. If it fails with "Following auth records … will be deleted", tell the user the change disconnects every user who has connected to this server (their tokens and personal keys are deleted). Retry with `force: true` only after they confirm.
- **Delete:** confirm with the user first, then call `delete_mcp_server` with `mcpServerId`. This is irreversible and deletes every user's saved connection for that server.

## Endpoint URL

Users need the endpoint to connect clients. Build it like this:

1. Take `proxyUrl` from `get_mcp_server` (reuse it if still in the conversation, otherwise call again). It looks like `{{mcpProxyBaseURL}}/<tenant>/mcp/<server-name>/server`.
2. Replace `{{mcpProxyBaseURL}}` with `manifest.url` of the `list_gateway_installations` entry where `isDefault: true` (else the first entry). Steps 1 and 2 are independent: call both in one batch.
3. Show the full URL, for example `https://gateway.example.com/acme/mcp/github-mcp/server`. Never show the placeholder.

## Checklist

- [ ] Did I check `list_mcp_servers` (by name filter) and `list_mcp_catalogue` in one batch?
- [ ] Did I use the TFY-managed path if the server is in `tfyManaged`?
- [ ] For OAuth2, did I copy `formContent` from `get_mcp_server_oauth_config`, include `provider` and `grant_type`, and use `registration_url` (never `registration_endpoint`)? Without `registration_url`, did I ask for `client_id`/`client_secret`?
- [ ] For header auth, did I set `auth_level`? For stdio credentials, did I use `auth_data.type: env`?
- [ ] For OpenAPI, did I use `openapi_spec_source` and `enable_all_tools` or `tool_settings`?
- [ ] For virtual, did I use `servers[].name` (not `id`)?
- [ ] For an update, did I pass `force: false` and ask before retrying with `force: true`?
- [ ] Collaborators on create per `write-rules.md`, and omitted on updates?
- [ ] Did I show the endpoint URL with the real gateway URL?

For more info: `search_docs` with "mcp gateway", "mcp server registry", "virtual mcp server".
