---
name: setup
description: Use when installing or connecting Riverside on Claude Code, Cursor, ChatGPT, or Codex; when authentication, 401, auth-loop, tool-not-found, account, or plan issues prevent tools from working; or when a feature-disabled or precondition error might be mistaken for a connection failure. Do not use for normal content, editing, or publishing after the connection works.
---

# Setup and connection

This plugin wraps Riverside's remote MCP server at `https://mcp.riverside.com/mcp`.
The tools run against the user's own Riverside account over an authenticated
connection.

## Requirements

- **A Riverside account.** Sign up or sign in at https://riverside.com.
- **A qualifying paid plan.** The MCP is available only on qualifying Riverside
  paid plans; Free and Pro accounts are not admitted, and their tool calls will
  not authorize. Plan details are at https://riverside.com/pricing.
- A supported client with this plugin installed and enabled — Claude Code (CLI,
  desktop, or IDE extension), Cursor, ChatGPT, or Codex.

Each client authenticates separately. Connecting Riverside in one client does not
connect it in another.

## First-time connection

How the connection is established depends on the host family. Every path ends in
the same place: a browser sign-in at Riverside, after which the tools work.

### Claude Code and Cursor — connect on the first tool call

The connection is set up once, on the **first tool call**:

1. Trigger any Riverside tool (e.g. ask to list your studios or productions).
2. The client opens Riverside's hosted sign-in in your browser. It finds that
   page automatically by discovering the MCP endpoint, so there is no URL to
   enter by hand. Clients register themselves via Dynamic Client Registration —
   there is no client ID or secret to configure.
3. Sign in and approve access. The prompt asking whether to grant the client
   access belongs to your client, not to Riverside.
4. The browser hands the authorization back to the client, the MCP server
   connects, and the tool call proceeds.

### ChatGPT and Codex — connect before the first tool call

There is no first-tool-call prompt on these hosts. Use the connection lane the
host currently exposes.

Before connecting ChatGPT:

- The Riverside account must be on a qualifying paid plan; Riverside Free and
  Pro accounts are not admitted.
- ChatGPT Pro supports read/fetch actions only. ChatGPT Business and
  Enterprise/Edu support write/modify actions, and workspace admins may need to
  enable Developer Mode and approve Riverside.
- Use ChatGPT on the web. MCP apps are not available on mobile.

#### Before the directory listing is available

- **ChatGPT:** in the browser, enable Developer Mode under **Settings → Security
  and login**. Open **Plugins**, select **+**, name the connection Riverside, use
  `https://mcp.riverside.com/mcp`, choose OAuth, create it, and complete the
  Riverside sign-in.
- **Codex:** run
  `codex mcp add riverside --url https://mcp.riverside.com/mcp`, then
  `codex mcp login riverside`. Run `/mcp` in a Codex session to confirm the tools
  are listed.

Do not use an `npx` or `mcp-remote` bridge; both hosts support the remote HTTP
endpoint and OAuth directly.

#### After the directory listing is available

Two independent things have to be true:

1. **The plugin is installed and enabled.** This supplies the four Riverside
   skills — the guidance the model follows.
2. **The Riverside app is enabled, connected, and signed in.** This supplies the
   tools themselves. Find Riverside among the host's apps or connectors and
   complete the sign-in from its settings.

In either lane, the plugin and Riverside connection are managed separately and
can fail separately:

| State | What the user sees |
|---|---|
| Plugin installed, connection signed in | Riverside skills load and the tools work |
| Plugin installed, connection missing | The skill still loads, but no Riverside tools exist |
| Plugin installed, connection present but signed out | Tools may be listed, but calling one fails as not-logged-in |
| Plugin removed, connection still present | The tools keep working; only the skill guidance is gone |

Removing the plugin is not a way to disconnect Riverside — remove the custom
connection or disconnect the listed app instead. Equally, if the tools are
missing, reinstalling the plugin will not fix the separate MCP connection.

After the first connection on any host, it is remembered — subsequent tool calls
run without re-prompting until the authorization expires or is revoked. A
connection currently lasts about a week, and there is no silent refresh, so
reconnecting through the browser periodically is expected rather than a fault.

## Troubleshooting

Reconnect only for authentication or connection failures. A feature-disabled or
precondition error is an operational result, not evidence that authentication
failed.

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` / repeated auth loop / "unauthorized" | Authorization expired or was revoked | Reconnect Riverside from the host's connection settings or CLI and re-authenticate. Complete the browser sign-in fully. |
| No Riverside tools listed | Riverside is not connected | Check the separate Riverside connection and reconnect it; enabling the plugin alone provides no tools. |
| One requested tool is not found while other Riverside tools are listed | Capability is not exposed on this surface | Report it as unsupported on this surface; do not reconnect. Use a listed alternative only if it satisfies the request. |
| Tools appear but every call fails to authorize | Account on a plan that is not admitted | The MCP requires a qualifying paid plan; Free and Pro accounts cannot use it. Plan details are at https://riverside.com/pricing. |
| Sign-in never returns / hangs | Browser/redirect interrupted | Close the tab, retry to restart the flow, and complete the browser step in one go. |
| A specific tool reports feature disabled or a missing prerequisite | Tool or workflow unavailable or incomplete (e.g. an edit with no transcript) | Surface the message; do not reconnect or retry blindly. Load the relevant operational skill only if the user asks to recover or continue. |

Tips:

- The connection control point differs by client: Claude Code uses `/mcp`;
  Cursor uses **Settings → MCP** (or the Plugins panel); ChatGPT uses **Plugins**
  for a custom connection or the Riverside app settings after listing; Codex
  uses `codex mcp login riverside` and `/mcp`.

## Getting help

- Product, plans, and account: https://riverside.com
- Connection steps for each client:
  https://support.riverside.com/hc/en-us/articles/37803607978141-Connect-to-Riverside-MCP
- Support: https://support.riverside.com/hc/en-us
