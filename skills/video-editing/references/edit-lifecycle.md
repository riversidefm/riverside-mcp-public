# Edit lifecycle

Obtaining an `editId`, inspecting an edit, comparing or recovering a revision,
and the verified-plan path.

Parameters, values, defaults, and which errors are recoverable come from the
live tool schemas and `editing_get_editing_guide`, and the main skill file's
rules govern every write here. This file covers only the choices those sources
cannot make for you.

## Creating an edit

Video-editing owns every creation call. Before calling an entry point, inspect
its live schema and supply every field it marks required. Ask for any required
choice the user has not established. Do not invent a `type`: when it is
optional and the user did not choose one, omit it; when it is required, ask and
use only a value from the live enum.

| Tool | Choose it when |
|---|---|
| `editing_create_edit_from_recording` | The user wants to start editing a raw recording. Use the established recording `sessionId` and containing `projectId`; preserve any title the user supplied. Reuse a list item's `id` as the session only when the response or schema explicitly establishes that equivalence, and confirm the intended take for multi-take material. |
| `editing_clone_edit` | The user explicitly asked for a second version so the original stays untouched. |

A new edit assembled from ordered segments across source edits requires a
currently listed creation tool whose live schema explicitly supports that
operation. If the callable catalog has no such entry point, say the direct
assembly is unavailable — then follow the main skill file's rule for an
unavailable operation: offer a fallback the live response or
`editing_get_editing_guide` actually names for this case, described as what it
does rather than as an equivalent, and invent nothing neither of them names.

If `editing_create_edit_from_recording` returns a current unavailable or
non-retryable response, surface it and follow the fallback the live response or
guide provides. Do not freeze an old error label into this workflow.

## Reading an edit

| Tool | Use it for |
|---|---|
| `editing_read_timeline_in_range` | The primary "what actually exists here" read — tracks, clips, scenes, layouts, keyframes over a time window. On each clip, `trackTime` is its position on the timeline and `timeRange.start` is the in-point into its source asset. |
| `editing_read_aligned_transcript` | What is said, aligned to the timeline. |
| `editing_get_revision` | A cheap freshness check: the current revision and nothing else. |
| `editing_compare_revisions` | What changed between two revisions. |
| `editing_get_asset_metadata` | Name, type, duration, and resolution for a media asset id — the read that tells you an asset's duration before you place it. A still image reports no duration. |
| `editing_list_edit_recording_asset_sessions` | The recording session(s) behind an edit's clips: the bridge back to `platform_get_transcript` and the discovery tools. It throws when a source cannot be resolved. |
| `editing_get_export_publish_data` | Content-ID and copyright signals for the edit's media ahead of a YouTube publish. Report a flagged match rather than publishing over it. Publishing itself belongs to the social-publishing skill: hand off to it, where the exported edit id becomes the `clipId`. For other platforms, follow their current live guidance. |

### Summarizing what a run changed

`editing_compare_revisions` attributes each cut or mute to the feature that
produced it — one of the AI cleanup passes, or nothing for a manual edit — and
also reports which AI toggles flipped and the effective duration before and
after. Use it to tell the user what your run actually did, rather than
restating what you intended to do. Read the field names off the response
instead of assuming them.

## Applying a raw plan

- `editing_apply_verified_edit_plan` is the safest single call for a complex raw
  plan: it validates, applies, and verifies in one pass, requires
  `expectedRevision`, and rejects a stale plan without mutating anything.
- When you need a preflight you can inspect separately, run
  `editing_validate_edit_plan` against the exact same edit, operations, and
  `expectedRevision`, then pass the plan hash it returns to
  `editing_batch` as that call's validated-plan hash.
- Simple operations need neither path — use the dedicated write tool and don't
  preflight it.

## Stale-revision recovery

A revision-conflict error means the edit moved underneath you: something else
wrote to it after the revision you were holding. It is not a transient failure
and it is not retryable.

**Do not re-send the same write with the newer revision number substituted in.**
Merge semantics do not make the intervening change irrelevant — you do not know
what that change was, and the timeline your arguments were computed against no
longer exists. Times, ids, and transcript handles derived before the conflict
may now point somewhere else entirely, and re-firing the write applies them to
a timeline nobody checked.

Recover like this:

1. Re-read: `editing_get_revision` for the current number, plus whichever read
   your arguments came from (timeline or transcript) for the current content.
2. Re-derive the operation against what you just read. Transcript handles are
   revision-scoped, so resolve them again; never reuse the old ones.
3. Tell the user the edit changed under you, what the re-read shows, and what
   you intend to do — before writing again.
4. Only then re-issue the write, with the current revision.

If the re-read shows the other change already did what the user asked, say so
instead of applying it a second time.
