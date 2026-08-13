# Captions and brand

Caption styling, and reading, changing, or applying a brand kit.

Parameters, values, and defaults come from the live tool schemas and
`editing_get_editing_guide`, and the main skill file's rules govern every write
here. This file covers only the choices those sources cannot make for you.

## Always pick an existing preset

`editing_get_captions_presets` lists what the studio already has. Choose from
it. Do not invent caption styling, and when the user asks for "our usual
captions" that is a preset lookup, not a style you assemble by hand.

Its response separates **the brand kit's caption styles** from **the general
preset catalog**. Within the brand styles there are two representations: the
current list, and a legacy per-aspect-ratio shape holding *the same* styles, for
kits that have not migrated.

- Those two are one pool represented twice. Read the legacy shape only when the
  current list is empty.
- **Never merge them, and never count them together.** "The studio has six
  caption styles", reached by adding the two, is wrong.
- Applying the brand? Pick from the brand styles — the one flagged as default,
  else the one with the lowest `sortOrder`. Array order is not sort order, so
  never fall back to whichever style happens to come first in the returned list.
  Not applying the brand? Pick from the general catalog, where the studio's own
  saved presets outrank the built-ins.

## Writing captions

`editing_set_captions` **merges**: fields you omit keep their current values,
and that includes sub-fields inside the style object. A small change is
therefore a small call — send only what is changing, and do not rebuild the
whole settings object from a read.

- Sending a preset id requires the studio id alongside it; the other fields do
  not.
- Explicit style fields **override** the resolved preset. Use them only for a
  deliberate override the user asked for, never to "fill in" a preset you have
  already selected.
- One documented gap: the preset's caption-animation accent color is not
  applied — the edit keeps the accent color it already had. Mention that rather
  than claiming an exact visual match with the preset.

## Kit versus edit

Three tools, two different targets. Confusing them is how a user ends up with
the studio's brand kit rewritten when they asked for one video to be branded.

| Tool | Target | Effect |
|---|---|---|
| `editing_get_brand` | the brand kit | Read-only fetch of the studio kit, optionally narrowed to a production. |
| `editing_apply_brand` | an **edit** | Applies the studio's kit to that edit's timeline, atomically. This is what "brand this video" means. |
| `editing_set_brand` | the **brand kit** | Edits the kit itself, as a partial patch. Touches no edit — and changes every future application, for the whole studio. |

- "Make this video match our brand" → `editing_apply_brand`. "Change our brand
  colors / logo / background" → `editing_set_brand`. If the request is genuinely
  ambiguous, ask; do not write the kit on a guess.
- Both may be feature-gated. A feature-disabled error is a real answer: surface
  it, and do not retry.

## Report what applied

`editing_apply_brand` reports, per brand area, what applied and what was skipped
and why. Read that back to the user. Saying "brand applied" when only some areas
landed is exactly the failure this result exists to prevent.

## Kit media fields point at existing assets

The kit's media fields — logo, background image — take the id of media that
already exists in the library, and the two background options are mutually
exclusive. Nothing in this tool family uploads anything. If the user hands you a
new file, tell them it has to be in their media library first; never invent or
guess an asset id.
