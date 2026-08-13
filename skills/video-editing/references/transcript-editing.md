# Transcript editing

Choosing what to keep, remove, or move by what was said rather than by a
timecode.

Parameters, selection kinds, values, and defaults come from the live tool schemas
and `editing_get_editing_guide`, and the main skill file's rules — revision
threading, time axes, fail-closed payloads — govern everything here. This file
covers only the choices those sources cannot make for you.

## Two levels of read

`editing_read_aligned_transcript` offers a compact locating view and a
word-detailed view. Inspect the live schema and choose the mode intentionally.

- **Compact rows** are for locating and shortlisting. They are acoustic
  segments, not sentences, so their bounds are not final cut points.
- **Word detail** is for cut-grade selection. Ask for it once you know roughly
  where the material is, and use the live bounded-read semantics and returned
  metadata to choose the window. If the result does not cover enough context,
  widen the window rather than assuming the transcript ended.

Rows sit on one global playable timeline shared by every speaker, in
chronological order, and **may overlap** where people interrupt or talk over
each other. Flags marking a row as starting or ending mid-sentence are a
warning: extend a kept span past a flagged row rather than cutting mid-sentence.

Treat word-mode output as working data. Report the ranges you selected with
short evidence snippets; do not dump the transcript back at the user.

## Handles are opaque

Each row carries a span handle and each word a word handle. Pass them onward
exactly as received. Never parse one, never rebuild a timestamp from it, and
never construct one yourself. The millisecond bounds printed beside them are
rounded outward — start floored, end ceiled — so they are for orientation; the
handles are the exact thing.

## Resolving a selection

`editing_resolve_transcript_selection` turns handles into canonical, edit-safe
ranges packaged as a ready-to-execute payload. It never mutates the edit. It
requires an intent, and the intent decides both the payload and the tool that
consumes it:

For every preview-before-apply request, state the execution gate explicitly:
do not execute until the user approves **and** `readyToApply` is true, then pass
`payload.input` unchanged. A user approval never overrides false readiness or a
null payload.

- **remove** — a cut payload for `editing_cut_time_ranges`, sorted and merged.
- **keep** and **move** — proceed only when the resolver and current callable
  catalog expose the executor named by the returned payload. If that executor is
  absent or unavailable, say so, then follow the main skill file's rule for an
  unavailable operation and offer whichever alternative the guide names for it.
  Two things stay off the table regardless: never invert a keep selection into
  cuts, and never fabricate the missing call. Offer removal only if the user
  explicitly reframes the request as content to remove.

Prefer a boundary range (`boundary_range`) for a contiguous quote: an inclusive
start anchor and end anchor, resolved to the true first playable start and final
playable end with no manual arithmetic on your part. Handle-, text-, and
time-based anchors exist too — check the schema for the current set.

### When the text repeats

A text anchor matches normalized and case-insensitively and ignores surrounding
punctuation, so a common phrase will match in more than one place. When a quote
repeats, disambiguate deliberately: use the occurrence selector the schema
offers, or anchor on neighbouring words that are unique, or anchor on handles
taken from the word-level read. Do not guess which occurrence the user meant,
and do not silently take the first.

## The quote workflow

1. Read the transcript at word detail over a window around the phrase, and keep
   the `revision` that read returned.
2. Resolve the selection against **that same revision**, with the intent that
   matches what the user asked for. Handles are scoped to one edit and one
   revision.
3. Check `readyToApply`. If it is false, or the payload came back null, stop and
   report the warnings — a fail-closed result is an answer, not an obstacle to
   work around.
4. If the payload's named tool is currently callable, execute its input
   unchanged, threading the same revision as `expectedRevision`; otherwise stop
   and explain the unavailable operation.
5. Thread the revision that write returns into whatever comes next.
