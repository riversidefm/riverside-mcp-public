# Checking a publish outcome

`social_upload_create` means accepted, never live. Read
`social_get_upload_status(uploadId)` to learn the outcome; only `COMPLETED`
proves the post is live. `externalId` can appear early and is not proof.

## Read and act

Branch on `terminal`, not a memorised status. `PENDING` (rendering/uploading)
and `SCHEDULED` (queued for `scheduledAt`) are non-terminal; `COMPLETED` is
terminal. `FAILED` is normally terminal, except
`PLATFORM_CONNECTION_EXPIRED` with `scheduledAt`: it is non-terminal because
reconnecting resumes the original scheduled post.

- **`PENDING`** — it may still publish and has no retry path. Do not republish.
  Check once shortly after publishing, then only on user request.
- **`SCHEDULED`** — report `scheduledAt` and stop the conversation.
- **`COMPLETED`** — report the outcome, but no URL: this tool cannot return or
  construct one.
- **Scheduled connection expired** — reconnect, do not republish, then re-read.
- **Immediate connection expired** — reconnect before any new publish and
  follow the returned `reason`.
- **`UNKNOWN` or a missing failure category** — this cannot prove whether a
  post exists. Do not republish until the platform or Riverside Support
  verifies the outcome. Never treat every `FAILED` upload as no post.
- **`RENDER_DID_NOT_COMPLETE`** — retry only in the Riverside web app, never
  by creating another MCP upload.

Relay the bounded Riverside-authored `reason`, not raw/internal text. This tool
only reads: it cannot cancel, edit, unpublish, or retry.

## Fields and access

`clipId` and `sessionId` are mutually exclusive; a text-only post has neither.
Unknown, cancelled, foreign-account, and inaccessible production-scoped uploads
share one authorization error. Report the upload as unreadable, not nonexistent;
readability does not prove who published it.

For account correlation, strip `_SHORTS` from upper-snake `platform`, then
compare case-insensitively with connected accounts. Thus `YOUTUBE_SHORTS` uses
the single `YouTube` account.
