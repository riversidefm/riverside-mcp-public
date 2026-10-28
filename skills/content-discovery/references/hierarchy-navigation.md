# Hierarchy navigation

Browsing the hierarchy, determining which item is newest, paging a list to
completeness, and getting a rendered file.

Page sizes, offsets, limits, paged-response and continuation shapes, and which
fields are required or nullable come from the live schema of the tool you are
calling, and the main skill file's rules govern everything here. This file covers
only the choices those sources cannot make for you.

## Traversal

There is no identity or "me" tool on this surface. Start from a search, or from
`platform_list_productions` / `platform_list_studios`.

1. `platform_list_studios` — optionally scoped to a production; pick a studio.
   `platform_get_production` returns one production with its studios, and
   `platform_get_studio` returns one studio with its parent production.
2. `platform_list_projects` — optionally scoped to a studio; pick a project.
3. `platform_get_project` — **the cheap fan-out.** It returns that project's
   recordings *and* its edits in a single call. Prefer it over calling
   `platform_list_recordings` and `platform_list_edits` separately.
4. Drill into the item itself: `platform_get_recording`, `platform_get_edit`
   (which also names its source recording).

Use a scoping parameter when the request is genuinely scoped to that container,
and leave it out when it is not.

## Paging to completeness

These tools return one page at a time alongside a count of everything that
matched, and paging is by offset. So:

- **Default to the first page.** Page further only when the request needs more
  than what came back.
- **When the answer depends on the whole set — "latest", "how many", "all of
  my…" — keep requesting successive pages until what you have collected accounts
  for the full reported count.** Stopping early yields a confidently wrong
  answer rather than an obviously partial one.
- Read the current schema for the paging parameters and their bounds. Do not
  assume a page size, and do not assume the response shape is what it once was.
- Offsets run over a backend-ordered list, so a given offset is not guaranteed
  to name the same item if the underlying data changes between calls. When
  completeness matters, page straight through without doing other work in
  between.
- If paging to completeness would be slow — a large archive, a studio with many
  projects — say so and offer to narrow the scope first, rather than silently
  truncating.

## Finding the latest of something

**Do not assume the first item returned is the latest.** Inspect the live schema
for any ordering controls. Unless the response itself guarantees the ordering
the user needs, collect the full candidate set and compare `createdAt` across it
yourself.

**Drop soft-deleted edits.** `platform_list_edits` can return edits marked
`deleted: true`. Exclude them before comparing, unless the user is specifically
asking about deleted edits.

The latest edit *within a studio* is the case that catches people out, because
`platform_list_edits` scopes by project and not by studio:

1. `platform_list_projects` for that `studioId`, paged to completion — every
   project in the studio.
2. `platform_list_edits` for each of those projects, each paged to completion.
3. Drop every edit marked `deleted: true`.
4. Take the highest `createdAt` across all of what remains.

**Do not shortcut this with an unscoped edit list.** The globally newest edit
may belong to a different studio entirely, which leaves you holding no candidate
in the studio the user actually asked about — and nothing warns you that it
happened.

The same shape applies to "yesterday's recording". Resolve what "yesterday"
means in the **user's local timezone** first — use their configured timezone, or
ask — because a recording timestamped just after midnight UTC can be the
previous evening locally. Then page `platform_list_recordings` to collect every
recording on that local date, and if more than one falls on it, show them with
their times and let the user choose.

## Getting a rendered file

No tool returns a download link. `exports_create_export` renders an edit,
`exports_list_edit_exports` lists an edit's exports newest first with each one's
`status`, and `exports_get_export` reads one export by id. An export's `s3Key`
is a storage key, not a URL.

The list comes back in one response, without pages, and leaves deleted exports
out. It can omit older exports, so even a non-empty list may not be complete.
An empty list is inconclusive: an unknown edit id also returns an empty list.
Never re-export only because the list is empty. A caller without access to the edit gets an `UNAUTHORIZED` error, not
an empty list.

When the user wants the file, resolve the edit as below and give them its
`riversideUrl` from `platform_get_edit` so they can export or download it in the
editor:

1. Resolve the recording, confirm its `status`, and capture its `projectId`.
2. `platform_get_project` — recordings and edits are siblings under a project,
   and this returns both. Confirm candidate edits came from the recording you
   mean with `platform_get_edit`. Continue only when exactly one matches. If
   several do, show their available identifying details and wait for the user
   to select the edit.
3. `exports_list_edit_exports` for that edit. If a `COMPLETED` export is
   listed, tell the user when it was made; otherwise report the `PENDING` or
   `FAILED` exports that are listed. If the list is empty, say the result is
   inconclusive rather than that the edit was never exported.
4. Share that edit's `riversideUrl`. Do not construct a download URL from an
   export's `s3Key`.

## Transcripts: prose here, cut-grade elsewhere

`platform_get_transcript` returns dialogue prose with one timestamp per
sentence. Those timestamps are session-relative, except for a speaker who has no
offset applied: that speaker is timed from their own track start, so their
timestamps are not comparable with the other speakers'. Prose timestamps are for
quoting and orienting, not for cutting.

For word-level times or exact cuts, stop here and hand off to the video-editing
skill, which reads the edit with `editing_read_aligned_transcript` and resolves
the selection through `editing_resolve_transcript_selection`. Do not attempt
that sequence from this skill.
