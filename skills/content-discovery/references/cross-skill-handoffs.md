# Cross-skill handoffs

Resolving ids for a video-editing or social-publishing task, and handing work
over to one of those skills.

Which ids a tool requires, which fields are optional or nullable, and every
window, limit, default, and continuation token come from the live schema of the
tool you are calling, and the main skill file's rules govern everything here.
This file covers only the choices those sources cannot make for you.

## Discovery owns hierarchy resolution

Use discovery to resolve `studioId`, `productionId`, and `projectId`, and to
find an existing recording session or edit when the workflow does not already
hold the relevant id. Neither the editing nor the social surface can discover a
studio, so a workflow needing one stays blocked until this skill supplies it.
An editing response can legitimately return a new `editId` or recover the
recording `sessionId`s behind an existing edit; keep those returned ids instead
of forcing the workflow back through discovery.

Reuse an id the user has already established for the same scope instead of
re-navigating. That is not licence to reuse a narrow scope for a wider request:
when the new ask is broader than the id you are holding, drop the id.

## Handing off to video-editing

For a raw-recording handoff, resolve the recording `sessionId` and its containing
`projectId`. Preserve any title or creation choice the user already supplied.
For an existing edit, hand off its `editId`.

- From a search result, treat `sessionId` as the matched recording session. For
  multi-take material, confirm it is the take the user intends rather than
  silently treating a sibling result as interchangeable.
- From the hierarchy, reuse a recording `id` as the session only when the live
  response or schema explicitly establishes that equivalence; otherwise obtain
  the session identifier the current surface provides.
- Going the other way, `editing_list_edit_recording_asset_sessions` returns the
  recording session(s) behind an existing edit.

Use the live recording response to obtain the containing `studioId` when the
brand or captions tools need it.

Discovery stops after resolving and handing off identifiers. Video-editing owns
all edit creation and mutation, including inspecting the live creation schema,
collecting every required field, and preserving the returned working state.

## Handing off to social-publishing

The minimum it needs is a `studioId` and a `clipId`, where the `clipId` is the
edit's `editId`.

1. `platform_list_studios`, and let the user pick — which captures both the
   `studioId` and its `productionId`.
2. Identify the clip within that studio. For *latest*, page every project list
   and edit list to completion, exclude deleted edits, then compare `createdAt`
   across what remains. Never take the first item or use an unscoped edit list:
   the globally newest edit may belong to another studio.
3. Hand over the two ids.

**Export-ready is not publish-ready.** `platform_list_exports` and
`platform_get_export` report the state of a rendered artifact. That is not the
clip state `social_upload_create` checks before publishing, and no tool in this
skill can read that state. So do not try to pre-confirm publishability, and
never present a ready export as proof that a clip will publish. Confirm the
export and composition choices with the user up front instead, so the publish
can proceed either way — the publishing skill owns its own confirmation step,
and restating it here would only give the user two versions of it.
