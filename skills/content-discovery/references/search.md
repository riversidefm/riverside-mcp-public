# Search

Finding content by what was said in it, or by its title or topic, rather than by
where it lives.

**Service limits and requiredness come from the live schema** — the recency
window, result and highlight caps, page size, next-page token, and which fields
are required or explicitly null all come from the tool you are calling, never
from a remembered figure. The main skill file's rules govern what
you do with the results. This file covers only the choices those sources cannot
make for you.

## Search first

One search call replaces walking the hierarchy and reading transcripts. Do not
fetch transcripts one at a time to scan them for a topic — that is exactly what
these two tools exist for.

## Exact or fuzzy

- **`search_recording_transcripts_exact`** — the user knows the wording. Terms
  are matched verbatim and OR-combined across recording transcripts. Highest
  precision, and it searches recordings only.
- **`search_riverside`** — the user knows the topic, the gist, or the title but
  not the exact words. It matches spoken transcript content on recording takes
  only; projects and clips match on their titles alone. Studios and productions
  are not searchable at all — no query reaches them, so walk the hierarchy to
  find one rather than spending a search call on it. To search what was
  actually said, scope the filter to takes, reading the schema for the current
  entity names and filter shape. It pages by passing the previous response's
  `nextSearchAfter` back on the next call.

**Mind the recency window.** The exact tool applies a default recency cutoff,
and anything older is silently missing from the results rather than reported as
excluded. Whenever the material might predate that cutoff — or you simply do not
know when it was recorded — pass an explicit `createdAfterDate` covering the
whole period the user means. Check the schema for the current default before
concluding it is wide enough.

## Duration constraints

When the user requests a clip or take duration, use `search_riverside` with
`filters[].durationRange` **only if the live input schema exposes it**. It
filters server-side before pagination. Use uppercase `CLIP` or
`TAKE`; `PROJECT` ranges are invalid. Keep the required nullable `field` and
`value`; a duration-only filter for clips lasting at least one minute is:

```json
{"entity":"CLIP","field":null,"value":null,"durationRange":{"min":60}}
```

Bounds are inclusive seconds: `min`, `max`, or both. Omitted or null individual
bounds are unbounded; at least one must be a finite nonnegative number, and
`min <= max` when both are set. Repeat the same filters with each
`nextSearchAfter` token. Filtering one returned page cannot establish all
qualifying matches or their absence.

If the live schema lacks the range or cannot express a requested scope, use
existing in-scope hierarchy traversal or report the limitation; never send
unsupported fields or drop a requested constraint. The exact transcript tool
has no duration-range argument. Any duration check after exact search is a
post-query check, not a complete search filtered by duration before pagination.

## What comes back, and where it goes

Inspect the live response for compact evidence and bridge ids. Use any returned
transcript fragment to confirm a real discussion rather than a passing mention,
then carry forward only identifiers whose meaning the response establishes:

- a matched recording-session id can feed the transcript flow; before creating
  an edit from multi-take material, confirm the intended take or start from an
  existing project edit rather than assuming a sibling take is equivalent;
- a `projectId` → the hierarchy, for that project's siblings and exports.

Use the live response and tool descriptions to decide whether a deeper
transcript read is needed; search evidence is not cut-grade timing.

Raw search result `duration` remains milliseconds for clips and seconds for
takes. Convert units when displaying or comparing; range bounds are seconds.

## When nothing comes back

Widen only within the scope the user requested. Preserve every studio, project,
recording, entity, and duration restriction they explicitly supplied; remove
only filters they did not supply, try the fuzzy tool if you used the exact one,
and loosen or extend `createdAfterDate` when the requested time range permits
it. If no in-scope match remains, report that or ask permission before searching
outside the requested scope. Walk the hierarchy within the same scope when search fails.

## Worked example — "find the episode where I talked about fundraising"

1. `search_recording_transcripts_exact` with the phrase — one call across the
   archive. Set `createdAfterDate` far enough back to cover when the episode
   could plausibly have been recorded.
2. Read each match's `highlights.transcription` to confirm it is the discussion
   the user meant.
3. Report where it was found, keep the returned bridge ids with their stated
   meanings, and ask the user what should happen next. Confirm the intended take
   before an edit-creation handoff when the result can represent multi-take
   material.

If the exact words may not be what was said, run the same search through
`search_riverside` scoped to takes instead.
