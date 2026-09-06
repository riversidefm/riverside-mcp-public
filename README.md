# Riverside Plugin for Claude Code, Cursor, ChatGPT, and Codex

Search your recordings by what you said in them, edit your videos, and publish clips to social media — all from Claude Code, Cursor, ChatGPT, or Codex.

## Installation

```text
/plugin install riverside
```

In Claude Code, the first tool call asks you to connect your Riverside account through a browser (one-time OAuth). A qualifying paid plan is required — Free and Pro accounts can't use the MCP.

## Cursor

Riverside is also packaged for the Cursor marketplace (`.cursor-plugin/plugin.json`). Once listed, install it from Cursor's plugin marketplace by searching "Riverside." To try it locally before that listing goes live, see [`docs/cursor-testing.md`](docs/cursor-testing.md).

## ChatGPT and Codex

Riverside is packaged for ChatGPT and Codex too (`.codex-plugin/plugin.json`), sharing the same four skills.

Until Riverside appears in the official directory, connect the tools manually:

- **ChatGPT prerequisites:** your Riverside account must be on a qualifying paid
  plan; Riverside Free and Pro accounts are not admitted. Separately, write
  actions have to be enabled for your ChatGPT workspace — which plans and
  settings allow them is OpenAI's to define, so check
  [OpenAI's developer mode documentation](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).
  Workspace admins may need to enable Developer Mode and approve Riverside. Use
  ChatGPT on the web; MCP apps are not available on mobile.
- **ChatGPT:** enable Developer Mode in **Settings → Security and login**, then create a Riverside plugin using `https://mcp.riverside.com/mcp` with OAuth authentication.
- **Codex:** run `codex mcp add riverside --url https://mcp.riverside.com/mcp`, then `codex mcp login riverside`.

After directory publication, installing the plugin supplies the skills while the Riverside app supplies the tools; enable and connect both. See the [`setup`](skills/setup/SKILL.md) skill and [current connection guide](https://support.riverside.com/hc/en-us/articles/37803607978141-Connect-to-Riverside-MCP) for the full flows.

## What You Can Do

### Search and Content Discovery

Search across your archive by spoken content or title, and navigate your
productions, studios, projects, recordings, edits, and transcripts.

- "Find the episode where I talked about fundraising"
- "Which recordings mention our Series A?"
- "Send me the download link for yesterday's recording"
- "List the recordings in my podcast studio"

### Video Editing

Turn recordings into edits, then cut, clean up, caption, lay out, and brand them.

- "Turn yesterday's recording into an edit and remove the filler words"
- "Cut this down to the part where we talk about pricing and add captions"
- "Apply my studio's brand kit to this edit"

### Social Publishing

Publish or schedule clips to YouTube, TikTok, Instagram, Facebook, LinkedIn, and X.

- "Post my latest clip to TikTok"
- "Schedule my interview highlights to YouTube Shorts for tomorrow at 9am"
- "Share this clip on LinkedIn"

## Requirements

- A [Riverside](https://riverside.com) account on a qualifying paid plan — Free and Pro accounts can't use the MCP
- A supported client: Claude Code (CLI, desktop, or IDE extension), Cursor, ChatGPT, or Codex

## Authentication

In Claude Code and Cursor, the first Riverside tool call starts the OAuth flow;
the client discovers Riverside's authorization server automatically. In ChatGPT
and Codex, connect before the first tool call using the steps above. ChatGPT
opens sign-in while creating or connecting Riverside, and Codex starts it with
`codex mcp login riverside`; neither waits for a first-tool-call prompt.

In every host, `https://riverside.com/auth` is the OAuth issuer identifier, not a
page to visit. The client opens Riverside's hosted sign-in in your browser, and
the prompt asking whether to grant the client access belongs to your client, not
to Riverside. Sign in and approve access; no API key is required.

A connection currently lasts **7 days**. There is no silent token refresh, so
when it expires — or if you revoke it — reconnect from the host's connection
settings or CLI and complete the browser flow again.

## Support & Security

- **Support:** the [Riverside Help Center](https://support.riverside.com/hc/en-us)
  for account, billing, or product questions. Connection steps for each client
  are in [Connect to Riverside MCP](https://support.riverside.com/hc/en-us/articles/37803607978141-Connect-to-Riverside-MCP).
- **Security vulnerability reports:** email
  [security@riverside.fm](mailto:security@riverside.fm). Please do not file
  security issues as public GitHub issues.

## Privacy

Riverside's privacy policy applies to any data accessed through this plugin:
[https://riverside.com/privacy-policy](https://riverside.com/privacy-policy)

Use of the Riverside service is governed by its terms and conditions:
[https://riverside.com/terms-conditions](https://riverside.com/terms-conditions)

## License

MIT — see [LICENSE](LICENSE).
