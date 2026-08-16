---
name: video-editing
description: Use when the user wants to cut, trim, clean up, caption, lay out, crop, brand, add overlays, stock media or music to, or otherwise change the content of a Riverside edit, or to turn a raw recording into an editable edit. Not for browsing or searching existing content (see content-discovery), and not for publishing to social platforms (see social-publishing). If the question is whether an editing error is really an authentication or connection problem, use setup first.
---

# Video editing

Server-side timeline editing. Tools are exposed at the gateway with the
`editing_` prefix. Work is keyed by an **`editId`**; revision-aware writes
advance a **`revision`**.

Current tool schemas and the live `editing_get_editing_guide` response are
authoritative for parameters, enums, limits, defaults, and recoverable errors.
This file carries only the invariants no single schema can state.

## Three rules that override everything

1. **Keep operating on the same edit.** When iterating on an existing edit, do
   NOT create a new edit or clone — keep passing the same `editId` and its
   latest `revision`. Create or clone only when the user explicitly asks for a
   separate version. The currently listed entry points
   (`editing_create_edit_from_recording` and `editing_clone_edit`) each return
   an `editId` that becomes the working edit for the rest of the flow.

2. **Thread the revision on revision-aware writes.** When the current write
   schema exposes `expectedRevision`, pass the latest revision back as that
   value; omitting it risks clobbering a concurrent edit. After a successful
   revision-changing write, use the revision it returns for the next such
   write. Preserve the revision's live type and value rather than coercing it.

   Do not generalize this into an argument for every tool that accepts an
   `editId`: reads and some non-revisioned operations do not accept
   `expectedRevision`. The live schema of the specific call decides whether the
   argument exists; the invariant is that you never omit or stale it when it
   does.

   A revision conflict is not retryable. Never replay the same write with a
   newer revision substituted. Stop before another write and evaluate the
   routing table again; the now-observable conflict selects the recovery
   workflow that re-reads and re-derives the operation.

3. **Never mix time axes.** See below. This is the easiest way to silently
   corrupt an edit.

## Time axes — read before computing any time

The timeline has two axes, and tools disagree about which one they take.

- **Source time** — positions in the original recorded media, before cuts.
- **Playable time** — positions on the edited, post-cut timeline the viewer sees.

With no cuts yet the two coincide and the distinction is harmless. Once any cut
exists they diverge, and a number from one axis fed to a tool on the other lands
in the wrong place with no error.

| Axis & unit | Tools |
|---|---|
| **Source**, `{n,d}` fractions of seconds | `editing_read_timeline_in_range` (every returned time: `trackTime`, `timeRange`, `duration`, scene times), fraction-based `editing_batch` params |
| **Source**, integer ms | `editing_add_lower_third` (`startMs`), `editing_add_text_overlay` (`startMs`), `editing_insert_overlay` (`startMs`) |
| **Playable**, integer ms | `editing_cut_time_ranges` (`startMs`/`endMs`), `editing_insert_audio` (`startMs`), `editing_insert_media_as_scene` (`startMs`), `editing_read_aligned_transcript` (`playableStartMs`/`playableEndMs`, and its `startMs`/`endMs` window), `editing_resolve_transcript_selection` (in and out) |

Rules that follow:

- **Never compare or reason across the axes** — not in a tool argument, and not
  in your own analysis. Converting a source `{n,d}` to milliseconds does not
  make it comparable to a playable millisecond value: once cuts exist, "these
  two numbers differ" tells you nothing about whether they name the same moment.
  Two values are comparable only when both came from the same axis.
- Convert a `{n,d}` fraction to ms *within one axis* with
  `Math.round(1000 * n / d)`.
- Derive playable-ms placements from `editing_read_aligned_transcript` or
  `editing_resolve_transcript_selection`, and source-ms placements from
  `editing_read_timeline_in_range`. Never cross over.
- `editing_insert_stock_media` places an overlay the same way
  `editing_insert_overlay` does; treat its `startMs` the same.
- `position` on the overlay tools is a **canvas** fraction, not a time — it
  shares the `{n,d}` shape and means something else entirely.

## Read the guide, then follow the guide

For anything beyond a single common operation, call `editing_get_editing_guide`
first — and then use only what that response actually lists.

**Ask for the narrowest slice that answers the question.** The guide is
sectioned, and one section can outweigh this whole skill, so an unscoped call is
the most expensive read on this surface. Take the current section and category
names off the tool's schema and request the one covering the task in hand. Never
pass a section or category from memory or inferred from a wrapper's name; if the
one you expected is absent, choose from what is present and say which you used.

**An unavailable operation is not a dead end.** When a tool is missing from the
live surface or comes back unavailable, say so — then offer a fallback that
response or the guide actually names, described as what it does, never as an
equivalent. Assemble no substitute of your own.

## Prefer the dedicated tool over batch

Each common operation has a dedicated high-level tool that resolves timeline
details for you. Reach for the low-level batch tool only for a multi-operation
atomic change, or for an operation with no standalone wrapper.

> **The batch tool's callable name is `editing_batch`.** An earlier surface
> exposed it under a doubled prefix; **`editing_editing_batch` is not a callable
> tool.** Confirm the name against the live tool surface rather than either
> spelling written from memory.

## Transcript handles fail closed

`editing_resolve_transcript_selection` returns opaque handles and a
ready-to-execute payload scoped to **one edit and one revision**. Never carry a
handle across edits or across revisions.

Execute `payload.input` **unchanged, and only when `readyToApply` is true**.
When it is false, or unresolved warnings leave `payload: null`, stop: report the
warning and re-resolve. Never synthesize a call from a null payload, and never
hand-edit the payload into something executable.

## Handing an edit off to publishing

When an edit is going out to a social platform, publishing itself belongs to
the social-publishing skill, and the exported edit id is the `clipId` it takes.
Before a YouTube handoff, clear the copyright / Content-ID pre-check on the
edit's media with `editing_get_export_publish_data`, and surface a flagged match
instead of publishing over it. For another platform, use its current live
guidance rather than generalizing the YouTube check. The YouTube pre-check
condition selects the Edit lifecycle row below.

## Where to read next

| Need | Read |
|---|---|
| Create or clone an edit, inspect an edit, compare revisions as the primary task, recover an actual revision conflict, run a verified plan, or prepare a YouTube handoff that requires the copyright pre-check | [Edit lifecycle](references/edit-lifecycle.md) |
| Keep, remove, or move transcript-selected speech | [Transcript editing](references/transcript-editing.md) |
| Cut, reorder, clean up, restore, or adjust audio | [Cuts and audio](references/cuts-and-audio.md) |
| Apply captions, presets, or a brand kit | [Captions and brand](references/captions-and-brand.md) |
| Change layout/crop/visual media, place existing assets, or use stock | [Visuals and media](references/visuals-and-media.md) |

**Routing contract:** Before the first Riverside workflow call, evaluate every
row against the observable request and state. Read every matching reference and
no unrelated reference. After each Riverside response, evaluate every row
again before the next workflow call; read any newly matching reference first.
Only this table routes references — a reference never routes to another one.

A post-operation revision comparison already prescribed by the owning
workflow reference does not activate an additional reference by itself. Every
condition listed in the routing table remains authoritative.
