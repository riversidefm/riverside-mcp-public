# Scheduling and draft export

Timezone resolution and export / compose choices, for a publish call where the
user named a future or wall-clock time or the clip may require
`composeSettings`. The main skill file owns the publish safeguards.

## Resolve a wall-clock time

The user means a local wall-clock time, not UTC, when they say "tomorrow at
9", "Friday morning", or "the 20th at noon".

1. Use the user's stated or configured timezone. If neither is available, ask;
   do not assume UTC, your timezone, or the studio's timezone.
2. Resolve relative dates in that timezone. Require one unique local instant:
   if daylight saving makes the requested time nonexistent or makes it occur
   twice, explain the valid choices and ask rather than choosing an offset.
3. Convert that unique instant to UTC using the offset in force on that date.
4. Inspect the current `social_upload_create` schema for the accepted
   `scheduledAt` representation; do not copy a historical format.
5. Supply the main confirmation with the resolved local date/time and timezone,
   UTC equivalent, and exact value and representation to be submitted.

## Choose whether and how to export first

`composeSettings` makes the publish call export the clip before posting. Use it
only when export-first publishing is intended: the user identifies the clip as
a draft or unexported, or an explicit service response plus current guidance
requires it. If export state is merely unknown, ask rather than silently adding
compose settings.

- Read the available compose fields and defaults from the current
  `social_upload_create` schema.
- Explain the resulting render choices in plain language and ask what the user
  wants. An empty object still means accepting every current default.
- Pass the selected choices to the main workflow so its preview covers both the
  export and the post. A later material change requires a new preview and
  confirmation there.
