---
name: social-publishing
description: Use when the user wants to post, share, publish, upload, or schedule a Riverside clip to a connected social platform — YouTube, YouTube Shorts, TikTok, Instagram, Facebook, LinkedIn, or X (e.g. "post my clip to TikTok", "schedule this to YouTube for 9am", "share on LinkedIn"). Not for creating or editing clips (see video-editing), connecting or disconnecting social accounts, or managing posts once they are published.
---

# Social publishing

Publishes a Riverside clip to an external platform. Tools are exposed at the
gateway with the `social_` prefix.

| Tool | Purpose |
|---|---|
| `social_get_connected_platforms` | A studio's connected platforms and accounts, with each account's live options and limits |
| `social_get_publishing_guidelines` | Current per-platform metadata rules, media constraints, workflow, and error recovery |
| `social_upload_create` | Publish or schedule one clip to one platform |

## Safety contract

`social_upload_create` is destructive and open-world: it can create a real post
and this MCP has no cancel, edit, delete, undo, or unpublish operation. Never
call it to inspect readiness, test an account, diagnose a failure, or learn what
an argument does.

Treat every success, processing result, timeout, transport failure, or unknown
outcome as potentially having created a post. Never repeat such a call. Only an
explicit failure that matches the Results and recovery routing row below can
become eligible for retry.

The current tool schema, chosen account entry from
`social_get_connected_platforms`, and platform result from
`social_get_publishing_guidelines` are the authority for fields, allowed values,
limits, formats, and recovery — never memory or values copied into this file.

## Prerequisites

- A `studioId`. Only content-discovery can find one
  (`platform_list_studios`); no social tool discovers a studio.
- A `clipId`, typically an exported edit id from video-editing. An unexported
  clip may require the export-first choices in the scheduling reference.
- At least one connected account on the target platform.

## Mandatory routing

Before the first social workflow call, evaluate every row against the user's
request and known context. Read every matching reference, and no unrelated
reference. Re-evaluate the table after every social response or failed call;
read any newly matching reference before the next workflow call.

| Observable condition | Required reference |
|---|---|
| The user names a future or wall-clock time, or the clip is or may be a draft/unexported and require `composeSettings` | [Scheduling and draft export](references/scheduling-and-draft-export.md) |
| The publish is processing, partial, or failed; or the call times out, has a transport failure, returns no usable result, or otherwise leaves the outcome unknown | [Results and recovery](references/results-and-recovery.md) |

Both rows can apply during one workflow. A wall-clock phrase such as "tomorrow
at 9" matches the first row even before its timezone is known.

## Publish workflow

1. **Establish the studio.** Obtain the `studioId`; if several studios fit, ask
   the user to choose.

2. **Select the account.** Call
   `social_get_connected_platforms(studioId)`. Use the target account's
   `platformAccountId` and any live account-specific options. If several
   accounts fit, ask the user to choose the human-readable account or channel.
   Never publish without a valid `platformAccountId`.

   An empty `accounts: []` is an ambiguous account-detail lookup failure, not
   proof that nothing is connected. Retry this read once; if it remains empty,
   report that account details could not be fetched and stop.

3. **Load live rules.** Call `social_get_publishing_guidelines` for the chosen
   platform. Compose metadata using its current constraints and the current
   `social_upload_create` schema. Apply the platform's counting rules rather
   than raw string length.

   Never infer or default YouTube privacy. Ask the user to select from the live
   allowed values. Before a YouTube upload,
   `editing_get_export_publish_data` reports copyright / Content-ID signals for
   the edit's media; surface a flagged match rather than publishing over it.

4. **Preview and confirm every target.** Show the exact metadata,
   human-readable account or channel, and applicable privacy or visibility.
   Include any resolved schedule and compose choices supplied by the scheduling
   reference. State that this MCP cannot undo or manage the resulting post,
   then wait for explicit confirmation.

   Confirmation authorizes one call for only the previewed target and payload.
   A retry needs a new confirmation even when unchanged. If any material field
   changes, preview the change. If the user declines, hesitates, changes
   direction, or withdraws confirmation, stop.

5. **Publish once.** Make one `social_upload_create` call for each separately
   confirmed target account and platform. Do not turn one confirmation into
   extra targets or calls.

6. **Report each result separately.** Identify the target account, submitted
   visibility and schedule, and its own returned outcome. Never flatten several
   calls into a single success or failure. Re-run mandatory routing before any
   follow-up action.
