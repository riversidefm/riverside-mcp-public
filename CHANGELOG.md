# Changelog

All notable changes to the Riverside plugin are documented in this file.

## Release process

The plugin declares an explicit `"version"` in `.claude-plugin/plugin.json`.
Because the version is explicit rather than derived from git metadata,
**installed users only pick up a new release when that field is bumped** —
the Claude plugin directory and Cursor marketplace treat an unchanged
version as "nothing new to install," even if the underlying skills, docs, or
MCP wiring changed underneath it.

Practical consequence: **bump `version` on every release**, including
docs-only or packaging-only changes, following semver:

- **patch** (`0.2.0` → `0.2.1`) — typo/doc fixes, no behavior change
- **minor** (`0.2.0` → `0.3.0`) — new skills, new sections of functionality,
  backwards-compatible tool/skill changes
- **major** (`0.x.y` → `1.0.0`) — breaking changes to skill names, required
  inputs, or the plugin's public shape

Also keep `.cursor-plugin/plugin.json`'s `"version"` in sync with the Claude
manifest — the two packages ship from the same repo and are expected to move
together.

## [0.6.2] - 2026-08-13

Refactors the bundled skills for structural progressive disclosure while
preserving current live-authority and safety behavior.

- **Smaller always-loaded entrypoints.** The content-discovery,
  social-publishing, and video-editing entrypoints retain their routing and
  safety contracts while moving workflow-specific detail out of the
  always-loaded surface. Setup remains self-contained.
- **Ten conditionally routed, one-hop references.** Content discovery routes to
  three references, social publishing to two, and video editing to five.
- **Deterministic selective loading.** Before the first workflow call and after
  each response, the operational skills evaluate every routing condition, load
  every matching reference, and avoid unrelated references. Edit creation now
  has one owner: discovery resolves identifiers and video editing performs the
  mutation from the live creation schema.
- **Context budgets are regression-tested.** Every ordinary one-reference route,
  setup, and the compound social scheduling-and-recovery route load fewer
  instruction bytes than their 0.6.1 monolithic entrypoint.
- **Live authority and safety gates remain in control.** Current MCP schemas and
  guide tools remain authoritative, while ambiguity handling, revision
  threading, mutation readiness, unchanged returned payloads, and final
  publishing confirmation remain enforced. Keep/reorder and cross-source
  assembly requests no longer route to a write that production has delisted.
- **Batch tool name corrected to `editing_batch`.** The skills instructed callers
  to use `editing_editing_batch` and stated that `editing_batch` was not
  callable. editing-mcp-v2 ENG-640 registers the tool as `batch`, so the
  gateway's `editing_` namespace serves `editing_batch` and the doubled-prefix
  name resolves to nothing. Every batch call, and every
  `editing_validate_edit_plan` preflight that feeds one, previously failed with
  tool-not-found. The reviewed live-surface snapshot and its validator allowlist
  were corrected to match.
- **An unavailable operation is no longer a dead end.** Keep/reorder and
  cross-source assembly previously refused outright and forbade "clone, batch,
  or cuts" — but the live guide names exactly those as its supported fallbacks
  for the same unavailability, so the skills contradicted the source they had
  just declared authoritative. They now fail closed on the direct operation and
  offer only a fallback the live response or the guide actually names, described
  as what it does rather than as an equivalent. Inventing a substitute, guessing
  a stale tool name, and inverting a keep selection into cuts all remain barred.
- **The guide is fetched by section.** `editing_get_editing_guide` takes
  `section` and `category`, and its default section is larger than the whole
  video-editing skill. The entrypoint now tells callers to read the current
  section names off the schema and request the narrowest one that covers the
  task, which is worth more context than this refactor's own restructuring.
- **One phrasing of the live-authority rule.** All ten references opened with
  the same "live schemas decide, the main skill file's rules still apply" point
  written ten different ways; they now share one. Measured saving is small (179
  bytes); the intent is that one rule reads the same everywhere.
- **The compound-route trade is now tested, not assumed.** A request matching
  three or more video-editing routing rows loads more than the 0.6.1 monolith
  did. That is the accepted cost of progressive disclosure — one- and
  two-reference routes, which dominate, each save 7-11 KB — and a new test pins
  the crossover so it cannot drift without review.
- **No runtime performance claim.** This release establishes structural
  progressive disclosure; it does not claim measured runtime token or latency
  savings. The compound-route figures above are byte counts, not measurements.

## [0.6.1] - 2026-08-12

Pre-submission corrections ahead of the Claude and ChatGPT directory listings.
Documentation, packaging metadata, and CI only — no skill guidance about tools
changed, and no tool name moved.

- **Removed `.app.json`.** A ChatGPT app id is workspace-scoped: committing one
  binds the package to a single workspace, and the value is world-readable in a
  public repository. The directory path does not consume it either — a
  Skills-only upload removes it, and an MCP-backed submission uses "With MCP"
  and submits the MCP server directly. `validate_openai_package.py` now asserts
  its **absence**, in both halves: no `apps` field in the manifest and no
  `.app.json` in the tree. The app-id and placeholder checks went with the file,
  including the `--allow-placeholder` flag.
- **`shortDescription` shortened to 28 characters** ("Search, edit & publish
  video"). It is the listing subtitle, and OpenAI's submission step rejects one
  over 30 — a failure that surfaces only at submission time, long after CI is
  green. The validator now asserts caps on `shortDescription`, `displayName`,
  `longDescription`, and `developerName` so it cannot regress.
- **Added `interface.supportURL`**, pointing at the public "Connect to Riverside
  MCP" help article. Both directories ask for a reachable support destination and
  OpenAI requires an HTTPS one, which an email address does not satisfy. The
  validator now requires the field and checks that the URL fields are `https://`.
- **The `setup` skill documents the ChatGPT/Codex lane.** It previously described
  only the Claude Code and Cursor first-tool-call flow. It now covers the current
  custom connection steps and the future directory path. In either case the
  plugin supplies skills while the separately managed Riverside connection
  supplies tools, so the two fail independently. Removing the plugin does not
  disconnect Riverside. Troubleshooting now names the right control point for
  each host rather than only Claude Code's `/mcp` and Cursor's settings panel.
- **Corrected the session lifetime in the README** from 12 hours to 7 days, and
  recorded that there is no silent token refresh — re-consent is required through
  the browser when a connection expires and cannot happen silently.
- **Fixed the authentication wording.** The README described
  `https://riverside.com/auth` as "the consent screen"; that URL is the OAuth
  issuer identifier and returns 404 to a browser. It is now named as the issuer,
  with the real flow described: the client discovers it and opens Riverside's
  hosted sign-in, and the grant prompt belongs to the host client rather than to
  Riverside, which has no consent UI of its own.
- **Replaced the support instruction with a link.** The README pointed readers at
  the homepage to go hunting for Help / Support; it now links the Riverside Help
  Center and the per-client connection article directly.
- **Stated the plan requirement without under-claiming.** "Grow or above" is
  narrower than the live entitlement and told eligible customers on other paid
  plans that they were excluded. The README, the `setup` skill, and the OpenAI
  `longDescription` now say a qualifying paid plan is required and that Free and
  Pro accounts cannot use the MCP, and the `setup` skill points at the
  informational pricing page rather than instructing the reader to upgrade.
- **Trimmed internal engineering detail out of the shipped bundle.**
  `expected-tools.txt`'s header keeps what it is, why it is a snapshot, how to
  refresh it, and the capture date and counts, and drops the incident narrative,
  infrastructure commands, and internal repository references. The docstrings in
  `validate_tool_names.py`, `validate_release.py`, and `validate_mcp_config.py`,
  and a comment in the CI workflow, now state the defect class each gate closes
  without the dated incident reports. The 61 tool names are byte-for-byte
  unchanged.

**Tool names are unchanged.** `expected-tools.txt` still lists the same 61 tools
across 5 namespaces captured on 2026-08-09.

## [0.6.0] - 2026-08-11

Adds the OpenAI (ChatGPT / Codex) packaging lane. No skill text changes — the
same four skills are now installable on a third host family.

- **New OpenAI package.** `.codex-plugin/plugin.json` declares the plugin for
  ChatGPT and Codex, `.app.json` carries the app binding, and `agents/openai.yaml`
  supplies plugin-level display metadata. `content-discovery`, `video-editing`,
  and `social-publishing` each declare the Riverside MCP as a
  `transport: streamable_http` dependency so ChatGPT makes the server available to
  them. `setup` deliberately declares no dependency: it troubleshoots the very
  connection that would otherwise be its prerequisite.
- **`mcpServers` is declared inline rather than as a path.** This repo's
  `.mcp.json` is the Claude *plugin* shape — a bare `{"<server>": {...}}` map —
  while every plugin in OpenAI's registry wraps `.mcp.json` in a top-level
  `mcpServers` key. Pointing OpenAI at the unwrapped file would hand it a shape
  no registry plugin uses, so `.codex-plugin/plugin.json` inlines the server and
  `validate_openai_package.py` asserts that copy agrees with `.mcp.json` and
  `mcp.json` on both server name and URL.
- **New gate: `scripts/validate_openai_package.py`.** Checks manifest and
  interface shape, `defaultPrompt` limits, asset existence, path containment,
  the MCP wrapper trap above, and the per-skill dependency declarations. It does
  not validate the app id against a prefix allowlist — OpenAI issues more than
  one prefix — but it does reject an unresolved placeholder id, and it rejects an
  id that keeps the `plugin_` URL route segment, which the browser shows after
  registration but which no stored id carries.
- **The release gate now covers the new files.** `.codex-plugin/plugin.json`
  joined the version-parity set, and `.app.json`, `.codex-plugin/plugin.json`,
  and `agents/` count as shipped, so a change to any of them requires a version
  bump like every other shipped file.

The app id in `.app.json` is a ChatGPT Developer Mode registration. It is package
metadata rather than a credential — OpenAI's own plugin registry publishes these
ids — but it is account-scoped, so a different workspace needs its own id.

## [0.5.1] - 2026-08-10

Closes a coverage hole in the tool-name gate added in 0.5.0. No shipped skill
text changes — this is a fix to what CI is able to see.

- **The tool-name gate now validates bare namespace globs.** It claimed to check
  prefix globs, but only ever looked at the two characters following a matched
  token, and a token had to end in an alphanumeric. `editing_remove_*` was
  therefore checked (token `editing_remove`, trailing `_*`) while a bare
  `editing_*` matched no token at all and was skipped silently — so a whole
  namespace could go unverified.
- A dedicated glob parser now recognises any identifier ending in `_*`,
  validates its prefix against `expected-tools.txt`, and records its span so the
  plain-token scan cannot report the same glob twice. Requiring that trailing
  underscore is also what keeps markdown emphasis (`*editing_batch*`) out of the
  glob parser.
- Added `NOT_A_TOOL_GLOBS`, a reason-bearing allowlist for glob-shaped prose
  that names no callable namespace. It has one entry: `list_*` in
  `content-discovery`, describing the shared pagination envelope. Real
  namespaces are not allowlistable — verifying them is the point of the gate.
- Failures name the file, the line, and the live namespace the stale one most
  likely came from (`platform-mcp-mcp_*` → "Did you mean `platform_*`?").

`expected-tools.txt` is untouched: still the 61 tools across 5 namespaces
captured on 2026-08-09. A snapshot refresh stays a separate reviewed change.

## [0.5.0] - 2026-08-09

Agent Plugins v1.0 conformance, and CI that can actually fail.

- **Added the Agent Plugins manifest** at the repo root (`plugin.json`). It is
  the specification's one hard MUST (§4.1.2): without it a conforming client
  rejects the plugin and runs none of its components. Note it deliberately
  carries no `displayName`, `logo`, `skills`, or `mcpServers` — the AP schema
  is closed, and those fields belong to `.cursor-plugin/plugin.json`.
- **Made root `mcp.json` conform**: added `$schema` and the required
  `type: "streamable-http"` discriminator. The URL is unchanged.
- **Kept the existing package layout**: `.claude-plugin/`, `.cursor-plugin/`,
  `.mcp.json`, and `skills/` retain their established paths. The vendor
  manifest versions and `content-discovery` guidance change as described in
  this release; the locations do not. Claude Code and Cursor read those exact
  paths, and renaming them to reverse-domain form would break both clients to
  satisfy a spec that does not ask for it.
- **Added four CI gates** covering what green CI did not: every tool name in
  `skills/**` and `README.md` must exist on the live surface
  (`expected-tools.txt`); `.mcp.json` must be valid and agree with `mcp.json`;
  the Agent Plugins files must validate against the official schemas; and a
  change to any shipped file must come with a version bump and a changelog
  entry.
- Fixed an unprefixed tool reference in `content-discovery` — the new
  tool-name gate found it on its first run.

## [0.4.0] - 2026-08-09

Corrects the documented plan requirement and moves the package's web links to
the canonical domain.

- Corrected the required plan from **Pro to Grow** in the `setup` skill
  (requirement and troubleshooting row). The README carried this correction
  already; it shipped without a version bump, so it is recorded here.
- Moved the package's **web URLs** to the canonical `riverside.com` domain:
  the privacy-policy link, both manifests' `homepage`, the author URL, and the
  links in the `setup` skill. Contact addresses remain on `riverside.fm`.
- Added the **terms and conditions** link to the README alongside the privacy
  policy. Both directory submissions ask for one, and the canonical path is
  `/terms-conditions` — `/terms` and five other obvious spellings 404.
- Made the README's Authentication section client-neutral rather than
  Claude-specific.
- Dropped the withdrawn "deprecated search alias" guidance from
  `content-discovery`; those aliases were removed from the gateway on
  2026-07-30 and no alias is served today.
- Corrected `platform_get_transcript` guidance to describe sentence-level
  timestamps, the word-level timing handoff, and the per-speaker no-offset
  caveat.
- Removed an internal task assignment from `docs/cursor-testing.md`.

**Tool names are unchanged from 0.3.0.** The 13 hierarchy tools keep their
`platform_*` names. The gateway's `platform` target was deployed and verified
on 2026-08-09 before this release.

## [0.3.0] - 2026-07-29

Re-aligned every skill with the live tool surface, tool by tool.

- Documented the two search tools (`search_recording_transcripts_exact` and
  `search_riverside`) in `content-discovery`, and replaced the old
  transcript-by-transcript discovery strategy with a search-first one. The skill
  had previously stated that no search tool existed on this surface.
- Corrected the batch tool's name to `editing_editing_batch` throughout
  `video-editing`; the name the skill used did not resolve at the gateway.
- Added a "Time axes" section to `video-editing` covering which tools take source
  time and which take playable time, and how to convert between `{n,d}` fractions
  and milliseconds.
- Documented `editing_get_asset_metadata` and
  `editing_list_edit_recording_asset_sessions`, the two editing tools that had no
  coverage.
- Fixed required and missing parameters: `editing_insert_overlay`'s `durationMs`,
  `editing_insert_audio`'s `dB`/`multiplier` (there is no `volume` parameter),
  `editing_resolve_transcript_selection`'s required `intent` plus its
  `readyToApply`/`payload` contract, `editing_create_edit_from_segments`'s
  fraction times and required `type`, and `editing_set_visual_crop`'s
  target/crop shape.
- Corrected tool behavior throughout `video-editing`, including
  `editing_remove_fillers`' transcript-based classification and duration-based
  `Smart` mode, the third field returned by `editing_get_captions_presets`,
  `editing_apply_brand`'s applied/skipped result, `editing_reorder_timeline`'s
  content duplication on overlapping ranges, and `editing_restore_audio_cleanup`
  also requiring a transcript.
- `content-discovery`: filter soft-deleted edits, prefer `platform_get_project`
  as a single fan-out, keep unscoped requests unscoped, document
  `platform_get_recording`'s opt-in `includePreviewUrl`, and stop presenting a
  `ready` export as proof that a clip can publish.
- `social-publishing`: never infer `youtubeData.privacyStatus`, X character
  weighting, the `composeSettings` field names and `quality` values, and that
  publish-readiness cannot be checked in advance.
- README: documented the search capability under "What You Can Do", and added
  Cursor to the title, the intro, and the requirements list.

## [0.2.0] - 2026-07-19

This release adds Claude plugin-directory metadata, Cursor marketplace
packaging, validation CI, and release documentation.

- Rewrote all skills for the current gateway tool surface (`platform_*`,
  `editing_*`, `social_*` prefixes), replacing the alpha's skills which
  referenced outdated tool names.
- Added two new skills: `video-editing` and `setup` (previously only
  `content-discovery` and `social-publishing` existed).
- Added Cursor marketplace packaging (`.cursor-plugin/plugin.json`,
  root `mcp.json`) alongside the existing Claude plugin packaging.
- Added packaging compliance for the Claude plugin directory: `LICENSE`,
  this changelog, a plugin logo, `displayName`/`keywords` metadata, and
  README sections required for review (Authentication, Support & Security,
  Privacy).
- Added a validation CI workflow that runs `claude plugin validate --strict`
  for the Claude manifest and a lightweight custom check
  (`scripts/validate_cursor_package.py`) for the Cursor package (version
  parity, path containment, skill frontmatter), on every PR and push to
  `main`.

The plugin logo (`assets/logo.png`) is Riverside's public site icon.

## [0.1.0] - 2026-04

Initial alpha release of the Riverside plugin.

- Initial plugin scaffold wrapping the Riverside remote MCP server
  (`https://mcp.riverside.com/mcp`).
- Two skills: `content-discovery` and `social-publishing`.
