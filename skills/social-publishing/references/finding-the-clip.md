# Finding the clip by what was said

The user describes what to post by what was said ("the clip where I talk about
pricing") instead of naming it. Find it for them rather than asking them to
look it up.

1. Search with `search_riverside` (content-discovery owns its arguments). A
   result whose entity is a clip gives a `clipId` that publishes as it is.
2. When the search resolves a recording instead, the recording itself is never
   the post. List that project's edits with `platform_list_edits`, skip deleted
   ones and any edit at least 90% as long as the recording (that is the whole
   recording, not a clip). Edit durations are milliseconds; a recording's
   duration from search is seconds. Read at most the 10 most recently updated
   with `platform_get_edit` and keep those whose take is that recording.
3. Read each kept edit with `editing_read_aligned_transcript` and keep the ones
   that contain what the user described. A close paraphrase counts; a clip
   that only shares the topic does not.
4. Several match: list each with its title (or its length and creation date)
   and the line where it is said, and ask which one. Exactly one matches: name
   it and continue with it.
5. None match: say none of the edits you read match. If you skipped older
   edits, offer to read those first. Otherwise offer to make a clip from that
   recording (see video-editing). Never offer the recording, or a new
   full-length edit of it, as the post.

Continue with the chosen clip or edit through the normal publish workflow.
