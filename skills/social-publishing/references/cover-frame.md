# Cover frame

An Instagram Reel and a TikTok video can use a frame of the video as their
cover. YouTube and Facebook take an image cover only (see the image routing
row); LinkedIn and X take neither.

## The fields

- **Instagram:** `instagramData.thumbnailOffset`.
- **TikTok:** `tiktokData.videoCoverTimestampMs`.

Both are milliseconds from the start of the video being published: the clip
or edit itself, not the recording it came from. Stay within its duration.
Omitted, the platform uses its default, the first frame.

Instagram takes a frame or an image (`thumbnailMediaId`), never both. On
`social_update_upload`, setting `instagramData.thumbnailOffset` replaces an
image cover.

## Choose the moment

You cannot see the video, so never pick a frame silently.

- When publishing to Instagram or TikTok without a chosen cover, offer once to
  use a moment from the video; accept a no.
- The user names a time, or a line of speech. For an edit, find that line
  with `editing_read_aligned_transcript(editId)`: its `playableStartMs` is on
  the edit's own timeline and is the value to send.
- `platform_get_transcript` times run from the start of the recording session,
  so use them only for a post that publishes the whole recording by
  `sessionId`. For any other clip, ask the user for the time.
- In the confirmation summary, show the cover as mm:ss and the line spoken
  there when known.
