# Images and caption-only posts

An image from the user's Riverside media library can be an image post (X,
LinkedIn, Facebook, Instagram) or the custom thumbnail of a video post
(YouTube, Instagram, Facebook). A post with no clip and no image is a
caption-only post (X, LinkedIn, Facebook). Every other combination is rejected
by the live schema; read `social_upload_create` for the exact arguments before
composing.

## Find the image

The social tools take a `mediaId`, never a path or a URL.
`media_list_media` searches the library by file name and returns each item's
`mediaId`; `media_get_media` reads one. If several match, ask which one.

This skill does not upload files from the user's computer. When the image is
not in the library yet, ask the user to add it in Riverside, then look it up
again. Never invent or guess a `mediaId`.

Check the image against every selected destination before drafting: JPEG or
PNG only, Instagram JPEG only, and the per-platform cap
`social_get_publishing_guidelines` returns (at the time of writing X 5 MB,
Instagram 8 MB, Facebook 10 MB, LinkedIn none, any thumbnail 2 MB). When a
destination rejects it, say which one and why and ask for another image. The
backend checks size and format again on publish.

## Where the id goes

- **Image post:** `assets: [{ mediaId }]`, exactly one image, no `clipId` and
  no `composeSettings`. A Facebook image goes to the Page feed, not a Reel.
- **Thumbnail of a video post:** `thumbnailMediaId` next to the `clipId`, on
  YouTube, Instagram or Facebook. Instagram takes this or a cover frame, never
  both.
- **Caption-only post:** neither `clipId` nor `assets`, on X, LinkedIn or
  Facebook.

You cannot see the image. Describe it by the name the user gave it, never by
what you imagine it shows, and show that name in the confirmation.
