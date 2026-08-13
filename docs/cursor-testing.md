# Testing the Riverside plugin locally in Cursor

Use this loop to test the Cursor packaging (`.cursor-plugin/plugin.json`,
root `mcp.json`, `skills/`) before it is listed on the Cursor marketplace.

## 1. Symlink the plugin into Cursor's local plugins directory

```sh
mkdir -p ~/.cursor/plugins/local
ln -s /path/to/riverside-mcp ~/.cursor/plugins/local/riverside
```

Replace `/path/to/riverside-mcp` with the absolute path to your local
clone of this repo.

## 2. Load it in Cursor

1. Open Cursor.
2. Go to **Cursor Settings → Customize → Plugins** (Cmd/Ctrl+Shift+J, then
   the Plugins tab).
3. Confirm the **riverside** plugin appears in the local/installed plugins
   list, sourced from the symlink.

## 3. Verify the MCP server and OAuth

1. In the Plugins panel (or **Settings → MCP**), confirm the `riverside` MCP
   server from `mcp.json` shows up and Cursor attempts to connect to
   `https://mcp.riverside.com/mcp`.
2. Trigger a Riverside tool call from a chat. Cursor should start the OAuth
   flow automatically via Dynamic Client Registration (DCR) — no manual
   client ID/secret configuration is needed.
3. Complete the browser consent screen. Cursor may register or use these
   OAuth callbacks:
   - `https://www.cursor.com/agents/mcp/oauth/callback`
   - `http://localhost:8787/callback`
   - `cursor://anysphere.cursor-mcp/oauth/callback`
4. Confirm the tool call completes successfully after consent, and that
   subsequent tool calls in the same session don't re-prompt.

## 4. Re-testing after changes

Because `~/.cursor/plugins/local/riverside` is a symlink, edits to
`skills/*/SKILL.md`, `.cursor-plugin/plugin.json`, or `mcp.json` are picked
up by simply reloading/restarting Cursor — no need to re-link.

---

**Note:** steps 2–3 above (confirming the plugin loads and OAuth completes
end-to-end in a real Cursor instance) cannot be scripted from CI — they
require an interactive Cursor session and have to be run by hand.
