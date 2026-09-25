# Bring your own image

An image on the user's disk can be an image post (X, LinkedIn, Facebook,
Instagram) or the custom thumbnail of a video post (YouTube, Instagram,
Facebook). A post with no clip and no image is a caption-only post (X,
LinkedIn, Facebook). Every other combination is rejected by the live schema;
read `social_upload_create` for the exact arguments before composing.

## Upload the file first

The social tools take a `mediaId`, never a path or a URL. Get one in three
calls, all with the user's `productionId` and `studioId`:

1. `stat` the file for its byte size. JPEG or PNG only; Instagram accepts
   JPEG only; a thumbnail must be at most 2 MB.
2. `media_create_media_upload` with `fileName`, `mimeType`, `fileSizeBytes`.
   It returns a `mediaId` and an `uploadUrl`.
3. `curl --fail-with-body -T "<path>" -H "Content-Type: <mimeType>"
   "<uploadUrl>"`. Only on exit 0 call `media_finalize_media_upload` with that
   `mediaId`; a finalized upload with no bytes is an empty image. Images
   finalize at once.

This needs a client that can read the file and run `stat` and `curl`; a
browser-only chat cannot. A file already in the library needs no upload:
`media_list_media` finds it by name and returns its `mediaId`.

## One-time network approval

The `curl` step leaves the client's sandbox to reach Riverside's storage. Each
client asks once; relay the prompt rather than retrying the command. A client
with a strict allowlist denies instead of asking: then stop and report the
domain that needs allowing.

- **Claude Code**: the first connection to a new domain prompts to allow it;
  "Yes, and don't ask again" saves it. Pre-allowing it under the sandbox's
  `allowedDomains` setting skips the prompt.
- **Codex**: network is off inside the workspace-write sandbox; with
  approvals on-request, Codex asks before running the command with network.
  Setting `network_access` to true under the workspace-write sandbox section
  of `config.toml` skips the ask.
- **Cursor**: a blocked command surfaces the sandbox restriction and Cursor
  asks for approval to run it outside the sandbox. Allowing the domain in
  `.cursor/sandbox.json` (project) or `~/.cursor/sandbox.json` keeps the
  upload inside it.

## Then publish

- **Image post**: `assets: [{ mediaId }]` and no `clipId`. One image per post.
- **Thumbnail**: `thumbnailMediaId` on a `clipId` or `sessionId` video post to
  YouTube, Instagram or Facebook. Never together with `assets`, and never with
  Instagram's `thumbnailOffset`.
- **Caption-only**: no `clipId`, `sessionId` or `assets`.

The image is not visible to you. Never describe it in the caption or claim to
have checked it. The main workflow's preview and confirmation still apply; the
`mediaId` and the user's own description of the file are what to show.
