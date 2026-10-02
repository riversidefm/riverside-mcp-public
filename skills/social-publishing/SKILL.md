---
name: social-publishing
description: Use when the user wants to post, share, publish, upload, or schedule a Riverside clip or edit, an image from their disk, or a caption-only update to a connected social platform — YouTube, YouTube Shorts, TikTok, Instagram, Facebook, LinkedIn, or X (e.g. "post my clip to TikTok", "post this image on LinkedIn", "use this picture as the thumbnail"); to find, change, reschedule, or cancel a post that has not gone out yet; to connect or disconnect a social account; or to ask how a published post is doing. Not for creating or editing clips (see video-editing), or for changing a post that has already published.
---

# Social publishing

Publishes Riverside content to external platforms and manages posts that have
not gone out yet. Tools are exposed at the gateway with the `social_` prefix.

| Tool | Purpose |
|---|---|
| `social_get_connected_platforms` | A studio's connected accounts, with live options and limits |
| `social_get_publishing_guidelines` | Current per-platform rules, media constraints, and error recovery |
| `social_upload_create` | Publish or schedule one post to one platform |
| `social_get_upload_status` | The real outcome of a publish |
| `social_list_uploads`, `social_get_upload` | Find and read posts |
| `social_update_upload`, `social_cancel_upload` | Change or cancel a post that has not published |
| `social_get_upload_analytics` | How a published post is doing |
| `social_connect_social_account`, `social_disconnect_social_account` | Connect or remove an account |

## Safety contract

`social_upload_create` creates a real post, and a published post cannot be
edited, unpublished, or deleted here. Never call a write tool to inspect
readiness, test an account, diagnose a failure, or learn what an argument does.

Treat every success, processing result, timeout, transport failure, or unknown
outcome as potentially having created a post. Never repeat such a call. Only an
explicit failure that matches the Results and recovery routing row below can
become eligible for retry.

The current tool schema, the chosen account from
`social_get_connected_platforms`, and `social_get_publishing_guidelines` are the
authority for fields, allowed values, limits, formats, and recovery — never
memory or values copied into this file.

## Prerequisites

- A `studioId`, and for listing posts or connecting accounts a `productionId`
  and `studioSlug`: content-discovery finds them (`platform_list_studios`,
  `platform_get_studio`, `platform_list_productions`).
- What to post: a `clipId` (a clip id, or an edit id passed unchanged), a
  `mediaId` for an image, or nothing for a caption-only post. A recording
  can't be published as it is; it needs a clip or an edit first (see
  video-editing).

## Mandatory routing

Before the first social workflow call, evaluate every row against the user's
request and known context. Read every matching reference, and no unrelated
reference. Re-evaluate the table after every social response or failed call;
read any newly matching reference before the next workflow call.

| Observable condition | Required reference |
|---|---|
| The user names a future or wall-clock time, or the clip is or may be a draft/unexported and require `composeSettings` | [Scheduling and draft export](references/scheduling-and-draft-export.md) |
| The publish is processing, partial, or failed; or the call times out, has a transport failure, returns no usable result, or otherwise leaves the outcome unknown | [Results and recovery](references/results-and-recovery.md) |
| A publish was made and its outcome is unconfirmed | [Publish outcome](references/upload-status.md) |
| The user names an image or a file on disk, wants an image thumbnail on a video post, or wants a post with no clip | [Bring your own image](references/bring-your-own-image.md) |
| A video post goes to Instagram or TikTok, or the user asks for a frame of the video as the cover | [Cover frame](references/cover-frame.md) |
| The user wants to find, change, reschedule, or cancel a post that has not published | [Managing posts](references/managing-posts.md) |
| The user wants to connect or disconnect an account, an account's connection is invalid, or they ask how a published post did | [Accounts and reporting](references/accounts-and-reporting.md) |

## Publish workflow

1. **Establish the studio.** If several studios fit, ask the user to choose.
2. **Select the account.** Call `social_get_connected_platforms(studioId)`.
   Use the account's `platformAccountId`; if several fit, ask by name. Never
   publish without one. An empty
   `accounts: []` is an ambiguous lookup failure: retry once, then report it and
   stop. A platform that is not connected routes to Accounts and reporting.
3. **Load live rules and compose.** Call `social_get_publishing_guidelines`
   for the platform and follow its counting rules; under N means fewer than
   N. Never infer or default
   YouTube privacy; ask. A YouTube title and description are separate fields:
   never copy one into the other; when the user names one, draft the other from
   the source and show both. Before a YouTube upload,
   `editing_get_export_publish_data` reports copyright / Content-ID signals;
   surface a flagged match rather than publishing over it.
4. **Re-read an edit.** Before every publish of an edit, read it again with
   `platform_get_edit`; never reuse a duration, ratio, or content value from an
   earlier turn. If it changed, preview again.
5. **Preview and confirm every target.** Show the exact metadata, account or
   channel by name, privacy or visibility, and resolved schedule and compose
   choices. Say that a published post cannot be undone here, then wait for
   explicit confirmation. Confirmation covers one call for that target and
   payload; a retry or changed field needs a new one. If the user declines,
   hesitates, or changes direction, stop.
6. **Publish once** per confirmed target; never turn one confirmation into
   extra targets or calls. Publish the content the user named and no other; if
   its id cannot be published, report that and stop.
7. **Report each result separately** with its own account, visibility,
   schedule, and outcome. Re-run mandatory routing before any follow-up.
