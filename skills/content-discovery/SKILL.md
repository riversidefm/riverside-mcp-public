---
name: content-discovery
description: Use when the user wants to search, find, list, browse, or retrieve their Riverside content — productions, studios, projects, recordings, edits, exports, transcripts — by what was said in it, by its title or topic, or by where it lives; when they ask for a download or share link; or when another workflow first needs a studioId, productionId, projectId, sessionId, or editId. Not for creating or changing an edit (see video-editing), and not for publishing to social platforms (see social-publishing).
---

# Content discovery

Read-only search and navigation over the Riverside platform. Hierarchy tools
carry a `platform_` prefix and search tools carry a `search_` prefix; nothing on
this surface modifies content. Copy tool names verbatim.

**The live tool schemas are the authority.** Required and nullable fields, date
windows, limits, defaults, page sizes, and pagination tokens all come from the
schema of the tool you are about to call — never from memory, from an earlier
session, or from a number written in a skill file. Read the schema, then call.

## The entity bridge

A production contains studios. A studio contains projects. A project contains
both recordings and edits. An edit produces exports.

Which id crosses into another skill:

- **`studioId`** — social publishing needs one, and so do the brand and captions
  editing tools. No editing or social tool can discover a studio, so it has to
  come from here. A studio also carries its `productionId`.
- **`sessionId`** — the recording-session identifier used by transcript reads
  and edit creation. Reuse a recording's `id` only when the live response or
  schema says that item is the same session (for example, some upload or
  single-take records). For multi-take material, confirm the intended take or
  start from an existing project edit instead of assuming the ids coincide.
- **`editId`** — one cut of one or more recordings. Social publishing consumes
  it as the `clipId`.
- **`exportId`** — one rendered file. Download links live here, not on the edit.

## Where to read next

| Need | Read |
|---|---|
| Find content by exact words, topic, or title | [Search](references/search.md) |
| Browse hierarchy, determine latest, page completely, or obtain a download link | [Hierarchy navigation](references/hierarchy-navigation.md) |
| Resolve or hand off IDs for editing or social publishing | [Cross-skill handoffs](references/cross-skill-handoffs.md) |

**Routing contract:** Before the first Riverside workflow call, evaluate every
row against the observable request and state. Read every matching reference and
no unrelated reference. After each Riverside response, evaluate every row
again before the next workflow call; read any newly matching reference first.
Only this table routes references — a reference never routes to another one.

## Rules that hold in every flow

- **Ask, don't guess.** When more than one studio, project, recording, or edit
  fits what the user described, show the candidates and let them pick. Guessing
  produces a confident answer about the wrong content.
- **Keep broad requests broad.** Scoping parameters such as `projectId` on
  `platform_list_recordings` and `platform_list_edits` are optional. Omit them
  for "all my recordings"-style requests, and never carry a narrow scope
  captured in an earlier step into a request the user did not scope that way.
- **Links come from the platform.** Studios, projects, recordings, edits, and
  exports each carry a `riversideUrl`. Return the one the server gave you; never
  construct or guess a URL.
- **Preview links are opt-in.** `platform_get_recording` withholds the
  token-bearing `previewUrl` unless asked. Set `includePreviewUrl` only once the
  user has explicitly asked for a shareable preview, and read a null value as
  "no share link exists right now".
- **Verify readiness before sharing.** Recordings and exports carry a `status`.
  Confirm the content is ready before handing out a download URL or operating on
  it — a record existing does not mean its file is finished.
- **Export-ready is not publish-ready.** A ready export means the rendered
  artifact is downloadable. It is not the clip state `social_upload_create`
  checks, and no tool here exposes that state — so never offer a ready export as
  evidence that something can be published.
