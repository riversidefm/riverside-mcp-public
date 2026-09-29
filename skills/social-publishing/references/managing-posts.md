# Managing posts before they publish

Finds, changes, reschedules, or cancels a post that has not gone out. A
published post cannot be edited, unpublished, or deleted here; the user does
that on the platform. The main safety contract governs every write.

## Find and read

1. `social_list_uploads(studioId, productionId, …)` finds it. Without
   `from`/`to` it returns the next 30 days, so a past post, or one further
   ahead, needs a window that covers it.
2. `social_get_upload(uploadId)` reads it in full. Show the user its current
   content before any change; that content is not the shape
   `social_update_upload` takes.
3. Branch on the `editable`, `mediaEditable`, and `cancellable` flags, not on
   the status. If the post cannot be changed or cancelled, say so and stop.

## Change or cancel

Show the exact change, or the cancellation, with the destination, account, and
scheduled time, and get an explicit yes. Then call `social_update_upload` with
only the fields that change, or `social_cancel_upload`. Report success only
from the returned result.

- **Timing:** `scheduledAt` moves the post and must be in the future;
  `publishNow` posts at once and cannot be undone. Never both.
- **Media:** only while `mediaEditable` is true. `clipId` swaps the video for
  another clip or edit; a video can be swapped, never removed. `assets`
  replaces the image set; `[]` drops images only where the platform takes
  caption-only posts. A video post never becomes an image post, nor the
  reverse. Say so when the user asks to remove media that cannot go.
- **Thumbnail:** `thumbnailMediaId` sets or replaces the image cover of a
  YouTube, Instagram, or Facebook video post; null removes it.
- **Text:** send the platform data object that matches the post's own
  platform. Change only the field the user named; a YouTube title and
  description stay separate.
- **X thread:** `xData.children` replaces the whole reply list. Start from the
  children `social_get_upload` returned, or omitted replies are deleted.

When the tool refuses a change, relay its reason and do not retry the same
change.
