# Visuals and media

Changing what the frame looks like — layout, crop, overlays, inserted scenes,
text, lower-thirds, added audio, stock.

Parameters, values, and defaults come from the live tool schemas and
`editing_get_editing_guide`, and the main skill file's rules — including the
time-axis map that decides which axis each tool below takes — govern every write
here. This file covers only the choices those sources cannot make for you.

## Layout and crop

- `editing_apply_smart_layout` generates scenes and layouts from speaker
  activity. Its tuning options apply only to the smart style, and their defaults
  are tuned for a natural rhythm — override them only on explicit request.
- `editing_list_layouts` and `editing_get_layout` are how you find a specific
  template before applying it as a `change_layout` operation inside
  `editing_batch`. The list summary is usually enough; the single-layout
  read returns a large opaque plan blob, so don't fetch it reflexively. Note the
  list only surfaces layouts that carry a text description.
- `editing_set_visual_crop` applies one static, normalized crop to a clip or a
  track, framed from its first visible frame. A crop that changes over time is
  not this tool — that is a `modify_crop` operation inside `editing_batch`.
- Color grading is not among the operations this file walks you through. The
  color controls it does cover are the text tools' color override and whatever
  the guide's current operation list exposes through batch. If the user asks for
  grading, check the guide's current operation list and the live tool surface —
  this file's silence about a capability is not evidence that it is missing.

## Layered on top versus growing the timeline

This is the distinction users are least explicit about, so decide it out loud:

- `editing_insert_overlay` layers an image or video **on top of** existing
  content; the timeline's duration is unchanged. This is "put the logo or the
  B-roll over this bit".
- `editing_insert_media_as_scene` inserts an image or video as a NEW fullscreen
  scene that **grows** the timeline and ripples later content to the right. This
  is "add this clip into the video".
- `editing_insert_audio` places an audio asset — music, SFX, voice-over — with
  its own level and fades.

Pick by media family first: image or video → overlay or scene; audio →
`editing_insert_audio`. Then pick by whether the video is supposed to get longer.

`editing_insert_overlay` requires an explicit duration, and an inserted video
scene requires one whenever the media's own duration cannot be determined. Get
it from `editing_get_asset_metadata` rather than guessing; that read also gives
you the asset's type and resolution.

An inserted scene has to land inside the existing playable timeline, and the
playable end that bounds it comes from `editing_read_aligned_transcript` — never
from a source-axis read. Past the end, or inside an already-cut region, is
rejected.

## Text and lower-thirds

- `editing_add_text_overlay` uses built-in text roles — title, subtitle, body,
  speaker — rather than free-form styling.
- `editing_add_lower_third` places one lower third for a person's name plus an
  optional role; the caller supplies its start and duration.
- Both accept only a small set of style overrides. Check the schema for the
  current set instead of inventing a font, color format, or effect name.
- **`editing_add_lower_third` does not apply brand lower-third styling.** There
  is no supported brand text-style contract for it to apply. If the user asks
  for branded lower thirds, tell them the styling is the built-in speaker preset
  plus any explicit overrides — not their brand kit.

## Stock

Stock is an **open-world** search: the results come from an external library
that changes underneath you.

- Images and video: search with `editing_get_stock_media`, let the user (or your
  own reasoning over the real results) choose one, then place it with
  `editing_insert_stock_media`, which imports it and positions it as an overlay.
  If the chosen item no longer resolves you get a not-found error — re-search
  instead of retrying the same identifier.
- Music: browse the free built-in library with `editing_get_stock_music`. It is
  organized by collection and by section, and the variant names encode intensity
  and length. Place the chosen track with `editing_insert_audio`, using the
  track's media id as the asset id. This is the free library; the larger paid one
  is separate.
- **Never invent an external asset identifier.** Always search first, and only
  ever pass through an id that came back from a search. For stock video in
  particular the library's alt-text description is usually absent and its tags
  are often empty, so judge from the result's own url and your query rather than
  assuming a match.

## Not owned here

Uploading new media is a different tool family and is not part of this skill. If
the user needs a file that is not already in their library, say so plainly
rather than reaching for an editing tool that cannot do it.
