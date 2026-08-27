# Checking a publish outcome

`social_upload_create` returns when the publish is *accepted*, not when the post
exists. Rendering, scheduling, and the platform upload all happen afterwards and
each can fail silently. `social_get_upload_status(uploadId)` is the only way to
learn what actually happened, and the `uploadId` from each `social_upload_create`
result is its only input.

Never tell the user a post is live off `social_upload_create` alone.

## Statuses

| `status` | `terminal` | What it means |
|---|---|---|
| `PENDING` | `false` | Still rendering, or handed to the uploader. Nothing has reached the platform. |
| `SCHEDULED` | `false` | Queued for `scheduledAt`. Nothing to watch until then. |
| `COMPLETED` | `true` | The post exists. `externalId` is the platform's own post id. |
| `FAILED` | `true` | Nothing was posted. `reasonCode` and `reason` say why. |

Branch on `terminal`, never on a memorised list of statuses. `SCHEDULED` is the
one non-terminal status that is still a stopping point for this conversation:
report the scheduled time and stop checking.

`externalId` is null until `COMPLETED`. `reasonCode` and `reason` are set only
when `FAILED`. Exactly one of `clipId` and `sessionId` is set.

## Polling

Check once shortly after publishing, then only on the user's prompt. A render
can take minutes and a scheduled post hours or days, so there is no polling loop
worth running inside one conversation: report the current state and let the user
ask again.

If the user leaves before a terminal status, say plainly that the outcome is not
yet known and that the post may still publish on its own.

## Acting on a result

`social_get_upload_status` reads only. It cannot cancel, edit, retry, or
unpublish, and neither can any other tool in this skill.

- **`FAILED`** — relay `reason` as written; it is Riverside's own recovery text.
  A failed publish created no post, so republishing is admissible, but it is a
  new `social_upload_create` call and needs the main skill's full preview and a
  new explicit confirmation. Fix what `reason` names first.
- **`PENDING` for a long time** — do not republish. A duplicate publish of the
  same clip can suppress the first one's render and leave both stuck. Tell the
  user the publish is still processing and that a stuck publish is retried from
  the Riverside web interface, not from here.
- **`COMPLETED`** — report `externalId`. This skill returns no post URL and
  cannot construct one; do not guess a link from the id.
- **`SCHEDULED`** — report `scheduledAt`. Changing or cancelling a schedule
  happens in the Riverside web interface.

## Reading it back later

An `uploadId` stays readable after the conversation that created it, so a user
returning later can be answered from the id alone.

Two access facts to keep in mind:

- Any user in the same Riverside account can read any upload in it, not only
  their own. Do not treat a readable upload as proof of who published it.
- An unknown `uploadId`, one belonging to another account, and one whose upload
  was cancelled all return the same authorization error. A cancelled upload is
  indistinguishable from one that never existed, so report that the upload could
  not be read rather than asserting it does not exist.

## Correlating with connected accounts

`social_get_upload_status` returns `platform` in upper snake case (`YOUTUBE`,
`YOUTUBE_SHORTS`, `TIKTOK`, `INSTAGRAM`, `FACEBOOK`, `LINKEDIN`, `X`).
`social_get_connected_platforms` returns mixed case (`YouTube`, `TikTok`) for
the same platforms. Compare them case-insensitively, or an account match will
silently fail.
