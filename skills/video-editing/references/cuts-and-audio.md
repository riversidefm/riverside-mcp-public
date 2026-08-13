# Cuts and audio

Removing time from the timeline, handling keep or reorder requests, and the
audio-cleanup passes.

Methods, thresholds, defaults, and error codes come from the live tool schemas
and `editing_get_editing_guide`, and the main skill file's rules govern every
write here. This file covers only the choices those sources cannot make for you.

## Removal versus keep or reorder

`editing_cut_time_ranges` removes the ranges you name, across all recording
tracks, on the **playable** axis. It is the tool for "take this out", including
a transcript selection resolved with remove intent. Its argument is `cuts`;
for every exact or agent-proposed cut, include `source: "user"` on that cut.
The live schema is still authoritative for the complete shape.

Keep and move requests require a currently callable write whose live contract
explicitly supports retaining or resequencing ranges. If the current tool
catalog or guide does not expose one, say so, then follow the main skill file's
rule for an unavailable operation and offer whichever alternative the guide
names for that unavailability — as what it does, not as a substitute that keeps
or resequences. Two things stay off the table regardless: never guess a stale
tool name, and never invert a keep selection into cuts. Offer the supported
removal workflow only if the user explicitly reframes the request as ranges to
remove.

For a single approved cut:

1. Call `editing_cut_time_ranges` on the existing edit with the approved
   playable-time `cuts`, `source: "user"`, and the latest `expectedRevision`.
2. Keep the revision that call returns.
3. Call `editing_compare_revisions` from the pre-cut revision to the returned
   revision, then report the actual change from that comparison. This routine
   verification is part of the cut flow and does not require Edit lifecycle.

## The cleanup passes

| Pass | What it does | Reach for it when |
|---|---|---|
| `editing_remove_fillers` | Removes the disfluency regions the transcript labelled — fillers, noise, word-level stumbles. | The user wants the ums and ahs gone. |
| `editing_remove_pauses` | Cuts silences longer than the threshold you pass. | The user wants dead air tightened. Agree the threshold with them; too low and the speech sounds clipped. |
| `editing_apply_smart_mutes` | Mutes non-speaking segments instead of removing them, so timing is preserved. | Background noise is the problem but the running time must not change. |
| `editing_set_magic_audio` | Toggles enhanced audio on a recording track, with an optional mix level. | The user wants a cleaner, more processed voice — not for anything to be removed. |

`editing_restore_audio_cleanup` undoes one cleanup pass: name the pass you want
restored (its schema lists the accepted values). It is per-pass, not a general
undo, and it does not roll back manual cuts.

Be honest about what these actually do:

- Filler classification comes from the **transcript**, not from listening. The
  tool does not analyze audio.
- The filler tool's smart method is **duration-based, not content-adaptive**: it
  chooses between muting and cutting by how long a region is, and mutes
  crosstalk. Say that plainly rather than implying it judges meaning.
- Magic Audio changes how a track sounds. It removes nothing and creates no
  cuts, so it is not an answer to "make this shorter".

## Transcript preconditions

The transcript-derived cleanup paths — filler removal, pause removal, smart
mutes, and restoring those transcript-derived passes — need a loadable
transcript. Magic Audio is a track-processing path and does not inherit that
precondition merely because it appears in the same table.

So the undo is not a safety net if the transcript later becomes unavailable.
Say that before running a pass on an edit whose transcript is already shaky.
When a precondition error comes back, report its reason to the user; do not
retry the same call, and do not fall back to hand-computed cuts that pretend to
be the same operation.

## Worked flow: clean up a raw recording

1. Start from the edit you already have — creating a second one is the mistake
   this flow most often invites — and note its current `revision`.
2. `editing_remove_fillers` with `expectedRevision` set to that revision. Keep
   the `revision` it returns.
3. `editing_remove_pauses` with the agreed threshold and `expectedRevision` set
   to the revision step 2 returned. Keep the `revision` it returns.
4. `editing_compare_revisions` between the revision from step 1 and the one from
   step 3, and summarize from its attributed result: which removals each pass
   made, and the duration before and after.

Every step threads the revision the previous step returned. If any step comes
back with a revision conflict, stop and return to the entrypoint routing table
before any further call. Do not re-fire the same call with a newer revision.
