# Checking a publish outcome

`social_upload_create` means accepted, never live. Read
`social_get_upload_status(uploadId)` to learn the outcome; only `COMPLETED`
proves the post is live. `externalId` can appear early and is not proof.

## Read and act

Branch on `terminal`, not a memorised status. `PENDING` (rendering/uploading)
and `SCHEDULED` (queued for `scheduledAt`) are non-terminal; `COMPLETED` is
terminal. `FAILED` is terminal except `PLATFORM_CONNECTION_EXPIRED` with a
`scheduledAt`: reconnecting can bring that post back, so it is non-terminal.

- **`PENDING`** — it may still publish and has no retry path. Do not republish.
  Check once shortly after publishing, then only on user request.
- **`SCHEDULED`** — report `scheduledAt` and stop the conversation.
- **`COMPLETED`** — report the outcome, but no URL: this tool cannot return or
  construct one.
- **Connection expired, `scheduledAt` set** — reconnect, never republish, then
  re-read. The returned `reason` says which recovery applies: a `scheduledAt`
  still ahead resumes on its own, a past-due one only if the user accepts the
  web app's post-reconnect prompt.
- **Connection expired, no `scheduledAt`** — terminal, nothing was posted.
  Reconnect before any new publish and follow the returned `reason`.
- **`UNKNOWN` or a missing failure category** — this cannot prove whether a
  post exists. Do not republish until the platform or Riverside Support
  verifies the outcome. Never treat every `FAILED` upload as no post.
- **Any other `FAILED`** — it can be rescheduled or republished in place from
  the Riverside web app, whatever the `reasonCode`. Re-read the status first
  and confirm it is still `FAILED`; never create a second MCP upload.

Relay the bounded Riverside-authored `reason`, not raw/internal text. This tool
only reads: it cannot cancel, edit, unpublish, or retry.

## Fields and access

Returns `uploadId`, `platform`, `status`, `terminal`, `scheduledAt`,
`targetDate`, `externalId`, `reasonCode` and `reason` — no clip or session id,
and no post identifier beyond the platform's own `externalId`.
Unknown, cancelled, foreign-account, and inaccessible production-scoped uploads
share one authorization error. Report the upload as unreadable, not nonexistent;
readability does not prove who published it.

For account correlation, strip `_SHORTS` from upper-snake `platform`, then
compare case-insensitively with connected accounts. Thus `YOUTUBE_SHORTS` uses
the single `YouTube` account.
